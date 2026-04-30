#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "catalog" / "org"
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

    unlabeled_projects = sorted(
        resource.name for resource in resources if resource.kind == "Project" and not resource.labels
    )
    if unlabeled_projects:
        warnings.append(
            "Projects without labels: " + ", ".join(unlabeled_projects)
        )

    services_without_review = sorted(
        f"{resource.project}/{resource.name}"
        for resource in resources
        if resource.kind == "Service" and not resource.spec.get("reviewCycle")
    )
    if services_without_review:
        warnings.append(
            "Services without reviewCycle: " + ", ".join(services_without_review[:20])
            + (" ..." if len(services_without_review) > 20 else "")
        )

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
                tier = ", ".join(service.labels.get("service-tier", []))
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
            tier = ",".join(service.labels.get("service-tier", []))
            slo_count = len(slos_by_service.get((project_name, service.name), []))
            lines.append(
                f"  - {service.name}: tier={tier} review={review_cycle} slos={slo_count}"
            )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and summarize Nobl9 SLO governance manifests.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("validate", help="Validate the catalog.")

    readiness_parser = subcommands.add_parser("apply-readiness", help="Check whether the catalog is safe to apply.")
    readiness_parser.add_argument("--markdown", action="store_true", help="Print markdown output.")

    inventory_parser = subcommands.add_parser("inventory", help="Print the catalog inventory.")
    inventory_parser.add_argument("--markdown", action="store_true", help="Print markdown output.")

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

    parser.error(f"unsupported command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
