#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "catalog" / "projects"
POLICY_PATH = ROOT / "standards" / "slo-governance-policy.yaml"
INVENTORY_PATH = ROOT / "inventory" / "governed-apps.yaml"
EXCEPTIONS_PATH = ROOT / "exceptions" / "policy-exceptions.yaml"
HIDDEN_PLACEHOLDER = "[hidden]"


@dataclass(frozen=True)
class Resource:
    path: Path
    document: dict
    kind: str
    name: str
    project: str | None

    @property
    def labels(self) -> dict:
        return self.document.get("metadata", {}).get("labels", {}) or {}

    @property
    def spec(self) -> dict:
        return self.document.get("spec", {}) or {}

    @property
    def key(self) -> tuple[str, str | None, str]:
        return (self.kind, self.project, self.name)


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_yaml_text(raw: str) -> list[dict]:
    documents = yaml.safe_load(raw) or []
    if isinstance(documents, list):
        return documents
    return [documents]


def load_resources() -> list[Resource]:
    resources: list[Resource] = []
    for path in sorted(CATALOG_ROOT.rglob("*.yaml")):
        with path.open("r", encoding="utf-8") as handle:
            documents = list(yaml.safe_load_all(handle))
        for document in documents:
            if not document:
                continue
            batch = document if isinstance(document, list) else [document]
            for item in batch:
                metadata = item.get("metadata", {}) or {}
                kind = item.get("kind")
                name = metadata.get("name")
                project = metadata.get("project")
                resources.append(
                    Resource(
                        path=path,
                        document=item,
                        kind=kind,
                        name=name,
                        project=project,
                    )
                )
    return resources


def contains_hidden_placeholder(value: object) -> bool:
    if isinstance(value, str):
        return HIDDEN_PLACEHOLDER in value
    if isinstance(value, list):
        return any(contains_hidden_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(contains_hidden_placeholder(item) for item in value.values())
    return False


def classify_objective(objective: dict) -> str | None:
    candidates = [
        str(objective.get("name", "")).lower(),
        str(objective.get("displayName", "")).lower(),
    ]
    if any("availability" in item for item in candidates):
        return "availability"
    if any("latency" in item for item in candidates):
        return "latency"
    if objective.get("countMetrics"):
        return "availability"
    if objective.get("rawMetric") and "latency" in " ".join(candidates):
        return "latency"
    if objective.get("composite"):
        if "latency" in " ".join(candidates):
            return "latency"
        if "availability" in " ".join(candidates):
            return "availability"
    return None


def load_inventory() -> dict:
    return load_yaml(INVENTORY_PATH)


def load_policy() -> dict:
    return load_yaml(POLICY_PATH)


def load_exceptions() -> dict:
    return load_yaml(EXCEPTIONS_PATH)


def load_active_anomaly_annotations(
    project: str,
    categories: list[str],
    lookback_hours: int,
) -> tuple[list[dict], str | None]:
    if not categories:
        return [], None

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    command = [
        "sloctl",
        "get",
        "annotations",
        "-p",
        project,
        "--system",
        "--from",
        cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "-o",
        "yaml",
    ]
    for category in categories:
        command.append(f"--category={category}")

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip() or "unknown error"
        return [], message

    annotations = load_yaml_text(result.stdout)
    active = [
        annotation
        for annotation in annotations
        if annotation.get("kind") == "Annotation"
        and annotation.get("spec", {}).get("category") in categories
        and not annotation.get("spec", {}).get("endTime")
    ]
    return active, None


def build_exception_lookup() -> dict[tuple[str, str], dict]:
    exception_lookup: dict[tuple[str, str], dict] = {}
    for item in load_exceptions().get("exceptions", []):
        exception_lookup[(item.get("project"), item.get("service"))] = item
    return exception_lookup


def exception_is_active(item: dict) -> bool:
    expires_on = item.get("expires_on")
    if not expires_on:
        return False
    return expires_on >= date.today().isoformat()


def governed_apps_by_project(inventory: dict) -> dict[str, dict]:
    return {
        app.get("project"): app
        for app in inventory.get("apps", [])
        if app.get("project")
    }


def governed_apps_by_app_id(inventory: dict) -> dict[str, dict]:
    return {
        app.get("app_id"): app
        for app in inventory.get("apps", [])
        if app.get("app_id")
    }


def service_tier(service: Resource) -> str | None:
    policy = load_policy()
    tier_label = (
        policy.get("inventory_selection", {}).get("service_tier_label")
        or "business-criticality-tier"
    )
    values = service.labels.get(tier_label, [])
    return values[0] if values else None


def build_indexes(
    resources: list[Resource],
) -> tuple[dict[tuple[str, str], Resource], dict[tuple[str, str], list[Resource]], dict[tuple[str, str], Resource]]:
    services: dict[tuple[str, str], Resource] = {
        (resource.project, resource.name): resource
        for resource in resources
        if resource.kind == "Service"
    }
    slos_by_service: dict[tuple[str, str], list[Resource]] = defaultdict(list)
    alert_policies: dict[tuple[str, str], Resource] = {
        (resource.project, resource.name): resource
        for resource in resources
        if resource.kind == "AlertPolicy"
    }
    for resource in resources:
        if resource.kind == "SLO":
            slos_by_service[(resource.project, resource.spec.get("service"))].append(resource)
    return services, slos_by_service, alert_policies


def evaluate_service(
    service: Resource,
    slos_by_service: dict[tuple[str, str], list[Resource]],
    policy: dict,
    exception_lookup: dict[tuple[str, str], dict],
    alert_policies: dict[tuple[str, str], Resource] | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    service_key = (service.project, service.name)
    exception = exception_lookup.get(service_key)
    exception_active = bool(exception and exception_is_active(exception))
    required_labels = policy.get("required_metadata_labels", [])
    tier_defaults = policy.get("service_tiers", {})

    missing_labels = [label for label in required_labels if not service.labels.get(label)]
    if missing_labels:
        message = (
            f"Governed service missing required labels: {service.project}/{service.name} -> "
            + ", ".join(missing_labels)
        )
        if exception_active:
            warnings.append(message + f" (exception {exception.get('id')} active)")
        else:
            errors.append(message)

    tier = service_tier(service)
    required_categories = tier_defaults.get(tier, {}).get("required_slos", [])
    service_slos = slos_by_service.get(service_key, [])
    for slo in service_slos:
        missing_slo_labels = [label for label in required_labels if not slo.labels.get(label)]
        if not missing_slo_labels:
            continue

        message = (
            f"Governed SLO missing required labels: {slo.project}/{slo.name} "
            f"(service {service.name}) -> " + ", ".join(missing_slo_labels)
        )
        if exception_active:
            warnings.append(message + f" (exception {exception.get('id')} active)")
        else:
            errors.append(message)

    coverage = {
        category
        for slo in service_slos
        for category in (
            classify_objective(objective) for objective in slo.spec.get("objectives", [])
        )
        if category
    }
    missing_categories = sorted(set(required_categories) - coverage)
    if missing_categories:
        message = (
            f"Governed service missing required SLO coverage: {service.project}/{service.name} -> "
            + ", ".join(missing_categories)
        )
        if exception_active:
            warnings.append(message + f" (exception {exception.get('id')} active)")
        else:
            errors.append(message)

    if alert_policies is not None:
        hidden_alerts = sorted(
            {
                alert_name
                for slo in service_slos
                for alert_name in slo.spec.get("alertPolicies", [])
                if (service.project, alert_name) in alert_policies
                and contains_hidden_placeholder(alert_policies[(service.project, alert_name)].document)
            }
        )
        if hidden_alerts:
            errors.append(
                f"Governed service references alert policies with hidden placeholders: "
                f"{service.project}/{service.name} -> {', '.join(hidden_alerts)}"
            )

    return errors, warnings


def project_resources(resources: list[Resource], project: str) -> list[Resource]:
    return [
        resource
        for resource in resources
        if (resource.kind == "Project" and resource.name == project) or resource.project == project
    ]


def validate(resources: list[Resource]) -> list[str]:
    errors: list[str] = []
    if not resources:
        return ["No YAML manifests found under catalog/."]

    seen_keys: dict[tuple[str, str | None, str], Path] = {}
    projects: dict[str, Resource] = {}
    services: dict[tuple[str, str], Resource] = {}
    alert_policies: dict[tuple[str, str], Resource] = {}
    slos: dict[tuple[str, str], Resource] = {}
    slos_by_service: dict[tuple[str, str], list[Resource]] = defaultdict(list)

    for resource in resources:
        if not resource.kind:
            errors.append(f"{resource.path}: missing kind")
        if not resource.name:
            errors.append(f"{resource.path}: missing metadata.name")
        if resource.kind in {"Service", "AlertPolicy", "SLO"} and not resource.project:
            errors.append(f"{resource.path}: missing metadata.project for {resource.kind}")

        if resource.key in seen_keys:
            errors.append(
                f"{resource.path}: duplicate resource key {resource.key}; already defined in {seen_keys[resource.key]}"
            )
        else:
            seen_keys[resource.key] = resource.path

        if resource.kind == "Project":
            projects[resource.name] = resource
        elif resource.kind == "Service":
            services[(resource.project, resource.name)] = resource
        elif resource.kind == "AlertPolicy":
            alert_policies[(resource.project, resource.name)] = resource
        elif resource.kind == "SLO":
            slos[(resource.project, resource.name)] = resource

    for resource in resources:
        if resource.kind in {"Service", "AlertPolicy", "SLO"} and resource.project not in projects:
            errors.append(
                f"{resource.path}: references missing project {resource.project}"
            )

        if resource.kind == "Service":
            if "spec" not in resource.document:
                errors.append(f"{resource.path}: service is missing spec")

        if resource.kind != "SLO":
            continue

        service_name = resource.spec.get("service")
        if not service_name:
            errors.append(f"{resource.path}: SLO is missing spec.service")
        elif (resource.project, service_name) not in services:
            errors.append(
                f"{resource.path}: references missing service {service_name} in project {resource.project}"
            )
        else:
            slos_by_service[(resource.project, service_name)].append(resource)

        objectives = resource.spec.get("objectives", [])
        if not objectives:
            errors.append(f"{resource.path}: SLO must define at least one objective")

        time_windows = resource.spec.get("timeWindows", [])
        if not time_windows:
            errors.append(f"{resource.path}: SLO must define at least one time window")

        alert_names = resource.spec.get("alertPolicies", [])
        for alert_name in alert_names:
            if (resource.project, alert_name) not in alert_policies:
                errors.append(
                    f"{resource.path}: references missing alert policy {alert_name}"
                )

        for objective in objectives:
            composite = objective.get("composite")
            if not composite:
                continue
            references = composite.get("components", {}).get("objectives", [])
            for reference in references:
                ref_project = reference.get("project")
                ref_slo = reference.get("slo")
                if (ref_project, ref_slo) not in slos:
                    errors.append(
                        f"{resource.path}: composite objective references missing SLO {ref_project}/{ref_slo}"
                    )

    return errors


def apply_readiness(resources: list[Resource]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(validate(resources))

    hidden_alert_policies = sorted(
        {
            f"{resource.project}/{resource.name}"
            for resource in resources
            if resource.kind == "AlertPolicy" and contains_hidden_placeholder(resource.document)
        }
    )
    if hidden_alert_policies:
        errors.append(
            "Alert policies contain hidden placeholder values and are not safe to re-apply: "
            + ", ".join(hidden_alert_policies)
        )

    policy = load_policy()
    inventory = load_inventory()
    exception_lookup = build_exception_lookup()
    services, slos_by_service, _ = build_indexes(resources)

    governed_projects = {
        app.get("project")
        for app in inventory.get("apps", [])
        if app.get("project")
    }

    for project in sorted(governed_projects):
        project_services = sorted(
            [
                service
                for (service_project, _), service in services.items()
                if service_project == project
            ],
            key=lambda service: service.name,
        )
        if not project_services:
            warnings.append(
                f"Governed project has no services in catalog yet: {project} (project bootstrap only)"
            )
            continue

        for service in project_services:
            service_errors, service_warnings = evaluate_service(
                service,
                slos_by_service,
                policy,
                exception_lookup,
            )
            errors.extend(service_errors)
            warnings.extend(service_warnings)

    return errors, warnings


def inventory(resources: list[Resource], markdown: bool = False) -> str:
    projects: dict[str, dict[str, list[Resource] | Resource]] = {}
    slos_by_service: dict[tuple[str, str], list[Resource]] = defaultdict(list)

    for resource in resources:
        if resource.kind == "Project":
            projects.setdefault(
                resource.name,
                {"project": resource, "services": [], "slos": [], "alert_policies": []},
            )
        elif resource.kind == "Service":
            bucket = projects.setdefault(
                resource.project,
                {"project": None, "services": [], "slos": [], "alert_policies": []},
            )
            bucket["services"].append(resource)
        elif resource.kind == "SLO":
            bucket = projects.setdefault(
                resource.project,
                {"project": None, "services": [], "slos": [], "alert_policies": []},
            )
            bucket["slos"].append(resource)
            slos_by_service[(resource.project, resource.spec.get("service"))].append(resource)
        elif resource.kind == "AlertPolicy":
            bucket = projects.setdefault(
                resource.project,
                {"project": None, "services": [], "slos": [], "alert_policies": []},
            )
            bucket["alert_policies"].append(resource)

    if markdown:
        lines = ["## Nobl9 Org Catalog Inventory", ""]
        for project_name in sorted(projects):
            bucket = projects[project_name]
            lines.append(
                f"- Project `{project_name}`: {len(bucket['services'])} services, {len(bucket['slos'])} SLOs, {len(bucket['alert_policies'])} alert policies"
            )
            for service in sorted(bucket["services"], key=lambda item: item.name):
                review_cycle = service.spec.get("reviewCycle", {}).get("rrule", "missing")
                tier = service_tier(service) or ""
                slo_count = len(slos_by_service.get((project_name, service.name), []))
                lines.append(
                    f"- Service `{service.name}`: tier `{tier}`, review `{review_cycle}`, {slo_count} attached SLOs"
                )
        return "\n".join(lines)

    lines = []
    for project_name in sorted(projects):
        bucket = projects[project_name]
        lines.append(
            f"{project_name}: {len(bucket['services'])} services, {len(bucket['slos'])} SLOs, {len(bucket['alert_policies'])} alert policies"
        )
        for service in sorted(bucket["services"], key=lambda item: item.name):
            review_cycle = service.spec.get("reviewCycle", {}).get("rrule", "missing")
            tier = service_tier(service) or ""
            slo_count = len(slos_by_service.get((project_name, service.name), []))
            lines.append(
                f"  - {service.name}: tier={tier} review={review_cycle} slos={slo_count}"
            )
    return "\n".join(lines)


def deploy_gate(
    resources: list[Resource],
    app_id: str | None,
    project: str | None,
    service: str | None,
    environment: str,
) -> tuple[bool, list[str], list[str], list[str]]:
    infos: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    anomaly_findings = False

    inventory_data = load_inventory()
    policy = load_policy()
    exception_lookup = build_exception_lookup()
    apps_by_project = governed_apps_by_project(inventory_data)
    apps_by_app_id = governed_apps_by_app_id(inventory_data)

    resolved_app = None
    if app_id:
        resolved_app = apps_by_app_id.get(app_id)
        if not resolved_app:
            infos.append(
                f"App `{app_id}` is not in governed scope for environment `{environment}`. Deployment gate passes."
            )
            return True, infos, warnings, errors

    if project:
        project_app = apps_by_project.get(project)
        if not project_app:
            infos.append(
                f"Project `{project}` is not in governed scope for environment `{environment}`. Deployment gate passes."
            )
            return True, infos, warnings, errors
        if resolved_app and resolved_app.get("project") != project:
            errors.append(
                f"Provided app_id `{app_id}` resolves to project `{resolved_app.get('project')}`, not `{project}`."
            )
            return False, infos, warnings, errors
        resolved_app = project_app

    if not resolved_app:
        errors.append("Provide either --app-id or --project to evaluate the deployment gate.")
        return False, infos, warnings, errors

    target_project = resolved_app.get("project")
    infos.append(
        f"Evaluating governed deployment target `{target_project}` for environment `{environment}`."
    )

    scoped_resources = project_resources(resources, target_project)
    scoped_validation_errors = validate(scoped_resources)
    if scoped_validation_errors:
        errors.extend(scoped_validation_errors)
        return False, infos, warnings, errors

    services, slos_by_service, alert_policies = build_indexes(scoped_resources)
    project_services = sorted(
        [svc for (svc_project, _), svc in services.items() if svc_project == target_project],
        key=lambda svc: svc.name,
    )

    if service:
        target_service = services.get((target_project, service))
        if not target_service:
            errors.append(
                f"Governed deployment target is missing service `{service}` in project `{target_project}`."
            )
            return False, infos, warnings, errors
        selected_services = [target_service]
    else:
        selected_services = project_services

    if not selected_services:
        errors.append(
            f"Governed project `{target_project}` has no services in catalog yet. Bootstrap exists, but deployment is blocked until service definitions and SLOs are added."
        )
        return False, infos, warnings, errors

    for selected_service in selected_services:
        service_errors, service_warnings = evaluate_service(
            selected_service,
            slos_by_service,
            policy,
            exception_lookup,
            alert_policies,
        )
        errors.extend(service_errors)
        warnings.extend(service_warnings)

    anomaly_policy = policy.get("anomaly_gate", {}) or {}
    anomaly_environments = set(anomaly_policy.get("environments", []))
    if anomaly_policy.get("enabled") and environment in anomaly_environments:
        lookback_hours = int(anomaly_policy.get("lookback_hours", 24))
        fail_categories = anomaly_policy.get("fail_on_active_categories", []) or []
        warn_categories = anomaly_policy.get("warn_on_active_categories", []) or []

        fail_annotations, fail_query_error = load_active_anomaly_annotations(
            target_project, fail_categories, lookback_hours
        )
        warn_annotations, warn_query_error = load_active_anomaly_annotations(
            target_project, warn_categories, lookback_hours
        )

        if fail_query_error:
            warnings.append(
                f"Unable to query active fail-on anomalies for project `{target_project}`: {fail_query_error}"
            )
        if warn_query_error:
            warnings.append(
                f"Unable to query active warn-on anomalies for project `{target_project}`: {warn_query_error}"
            )

        for annotation in fail_annotations:
            spec = annotation.get("spec", {}) or {}
            anomaly_findings = True
            errors.append(
                f"Active anomaly blocks deployment: {target_project}/{annotation.get('metadata', {}).get('name')} "
                f"category={spec.get('category')} slo={spec.get('slo')} started={spec.get('startTime')}"
            )

        for annotation in warn_annotations:
            spec = annotation.get("spec", {}) or {}
            anomaly_findings = True
            warnings.append(
                f"Active anomaly warning: {target_project}/{annotation.get('metadata', {}).get('name')} "
                f"category={spec.get('category')} slo={spec.get('slo')} started={spec.get('startTime')}"
            )

    if anomaly_findings:
        infos.append(
            f"Investigate in Nobl9: open [Nobl9](https://app.nobl9.com/), go to Dashboards -> SLO oversight, and filter Project = `{target_project}`."
        )

    passed = not errors
    if passed:
        target_label = f"{target_project}/{service}" if service else target_project
        infos.append(f"Deployment gate passed for `{target_label}`.")
    return passed, infos, warnings, errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and summarize Nobl9 SLO governance manifests.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("validate", help="Validate the catalog.")

    readiness_parser = subcommands.add_parser("apply-readiness", help="Check whether the catalog is safe to apply.")
    readiness_parser.add_argument("--markdown", action="store_true", help="Print markdown output.")

    inventory_parser = subcommands.add_parser("inventory", help="Print the catalog inventory.")
    inventory_parser.add_argument("--markdown", action="store_true", help="Print markdown output.")

    deploy_gate_parser = subcommands.add_parser(
        "deploy-gate",
        help="Evaluate whether a governed app or service is allowed to deploy.",
    )
    deploy_gate_parser.add_argument("--app-id", help="Governed application ID from governed-apps.yaml.")
    deploy_gate_parser.add_argument("--project", help="Governed Nobl9 project name.")
    deploy_gate_parser.add_argument("--service", help="Optional service name within the governed project.")
    deploy_gate_parser.add_argument(
        "--environment",
        default="production",
        help="Deployment environment label for reporting purposes.",
    )
    deploy_gate_parser.add_argument("--markdown", action="store_true", help="Print markdown output.")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    resources = load_resources()

    if args.command == "validate":
        errors = validate(resources)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(
            f"Validated {len(resources)} resources across {len([resource for resource in resources if resource.kind == 'Project'])} project(s)."
        )
        return 0

    if args.command == "apply-readiness":
        errors, warnings = apply_readiness(resources)
        if args.markdown:
            print("## Apply Readiness")
            print("")
            if errors:
                print("- Status: `blocked`")
                for error in errors:
                    print(f"- Error: {error}")
            else:
                print("- Status: `ready`")
            for warning in warnings:
                print(f"- Warning: {warning}")
        else:
            if errors:
                for error in errors:
                    print(f"ERROR: {error}", file=sys.stderr)
            for warning in warnings:
                print(f"WARNING: {warning}")
        return 1 if errors else 0

    if args.command == "inventory":
        print(inventory(resources, markdown=args.markdown))
        return 0

    if args.command == "deploy-gate":
        passed, infos, warnings, errors = deploy_gate(
            resources,
            app_id=args.app_id,
            project=args.project,
            service=args.service,
            environment=args.environment,
        )
        if args.markdown:
            print("## Deployment Gate")
            print("")
            print(f"- Status: `{'passed' if passed else 'blocked'}`")
            for info in infos:
                print(f"- Info: {info}")
            for warning in warnings:
                print(f"- Warning: {warning}")
            for error in errors:
                print(f"- Error: {error}")
        else:
            for info in infos:
                print(f"INFO: {info}")
            for warning in warnings:
                print(f"WARNING: {warning}")
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
        return 0 if passed else 1

    parser.error(f"unsupported command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
