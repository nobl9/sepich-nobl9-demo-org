#!/usr/bin/env python3

from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path
import shutil

import yaml


ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "catalog" / "projects"
GOVERNED_APPS_PATH = ROOT / "inventory" / "governed-apps.yaml"
EXPORTS = (
    ["sloctl", "get", "projects", "-o", "yaml"],
    ["sloctl", "get", "services", "-A", "-o", "yaml"],
    ["sloctl", "get", "alertpolicies", "-A", "-o", "yaml"],
    ["sloctl", "get", "slos", "-A", "-o", "yaml"],
)


def run_export(command: list[str]) -> list[dict]:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    documents = yaml.safe_load(result.stdout) or []
    if not isinstance(documents, list):
        return [documents]
    return documents


def clean_document(document: dict) -> dict:
    cleaned = copy.deepcopy(document)
    cleaned.pop("status", None)
    spec = cleaned.get("spec", {})
    spec.pop("createdAt", None)
    spec.pop("createdBy", None)

    if cleaned.get("kind") == "SLO":
        windows = spec.get("timeWindows", [])
        for window in windows:
            if window.get("isRolling"):
                window.pop("period", None)

    if cleaned.get("kind") == "Project" and not spec.get("description"):
        spec.pop("description", None)

    if not spec:
        cleaned.pop("spec", None)

    return cleaned


def governed_app_lookup(governed_apps: dict) -> dict[str, dict]:
    return {
        app.get("project"): app
        for app in governed_apps.get("apps", [])
        if app.get("project")
    }


def enrich_labels(document: dict, governed_app: dict | None) -> dict:
    if not governed_app:
        return document

    enriched = copy.deepcopy(document)
    metadata = enriched.setdefault("metadata", {})
    labels = metadata.setdefault("labels", {})

    app_id = governed_app.get("app_id")
    if app_id:
        labels["app-id"] = [app_id]

    ad_group_name = governed_app.get("ad_group_name")
    if ad_group_name:
        labels["ad-group-name"] = [ad_group_name]

    cost_center = governed_app.get("cost_center")
    if cost_center:
        labels["cost-center"] = [cost_center]

    business_unit = governed_app.get("business_unit")
    if business_unit:
        labels["business-unit"] = [business_unit]

    env_type = governed_app.get("env_type")
    if env_type:
        labels["env-type"] = [env_type]

    return enriched


def load_governed_apps() -> dict:
    with GOVERNED_APPS_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def write_yaml(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(document, handle, sort_keys=False)


def project_path(resource: dict) -> Path:
    metadata = resource.get("metadata", {})
    return CATALOG_ROOT / metadata["name"] / "project.yaml"


def alert_policy_path(resource: dict) -> Path:
    metadata = resource.get("metadata", {})
    return CATALOG_ROOT / metadata["project"] / "alert-policies" / f"{metadata['name']}.yaml"


def service_path(resource: dict) -> Path:
    metadata = resource.get("metadata", {})
    return (
        CATALOG_ROOT
        / metadata["project"]
        / "services"
        / metadata["name"]
        / "service.yaml"
    )


def slo_path(resource: dict) -> Path:
    metadata = resource.get("metadata", {})
    service_name = resource.get("spec", {}).get("service", "_unmapped")
    return (
        CATALOG_ROOT
        / metadata["project"]
        / "services"
        / service_name
        / "slos"
        / f"{metadata['name']}.yaml"
    )


def build_governed_scope(governed_apps: dict) -> set[str]:
    return {
        app.get("project")
        for app in governed_apps.get("apps", [])
        if app.get("project")
    }


def synthesize_project(app: dict) -> dict:
    labels = {
        "governed-app": ["true"],
    }
    if app.get("app_id"):
        labels["app-id"] = [app["app_id"]]
    if app.get("ad_group_name"):
        labels["ad-group-name"] = [app["ad_group_name"]]
    if app.get("cost_center"):
        labels["cost-center"] = [app["cost_center"]]
    if app.get("business_unit"):
        labels["business-unit"] = [app["business_unit"]]
    if app.get("env_type"):
        labels["env-type"] = [app["env_type"]]
    tier = app.get("derived_from", {}).get("business_criticality_tier")
    if tier:
        labels["business-criticality-tier"] = [tier]

    return {
        "apiVersion": "n9/v1alpha",
        "kind": "Project",
        "metadata": {
            "name": app["project"],
            "displayName": app.get("name"),
            "labels": labels,
        },
        "spec": {
            "description": (
                "Bootstrap project scaffold synthesized from governed-apps.yaml. "
                "Teams can add or sync services and SLOs after the project exists in Nobl9."
            )
        },
    }


def main() -> int:
    governed_apps = load_governed_apps()
    governed_scope = build_governed_scope(governed_apps)
    governed_lookup = governed_app_lookup(governed_apps)
    if not governed_scope:
        raise SystemExit(
            f"No governed applications found in {GOVERNED_APPS_PATH}. Run sync_governed_apps.py first."
        )

    projects, services, alert_policies, slos = [run_export(command) for command in EXPORTS]

    filtered_projects = [
        document
        for document in projects
        if document.get("metadata", {}).get("name") in governed_scope
    ]
    existing_project_names = {
        document.get("metadata", {}).get("name")
        for document in filtered_projects
    }
    for app in governed_apps.get("apps", []):
        project_name = app.get("project")
        if project_name in governed_scope and project_name not in existing_project_names:
            filtered_projects.append(synthesize_project(app))

    filtered_services = [
        document
        for document in services
        if document.get("metadata", {}).get("project") in governed_scope
    ]
    filtered_slos = [
        document
        for document in slos
        if document.get("metadata", {}).get("project") in governed_scope
    ]

    needed_alert_policies = {
        (document.get("metadata", {}).get("project"), alert_name)
        for document in filtered_slos
        for alert_name in document.get("spec", {}).get("alertPolicies", [])
    }
    filtered_alert_policies = [
        document
        for document in alert_policies
        if (document.get("metadata", {}).get("project"), document.get("metadata", {}).get("name"))
        in needed_alert_policies
    ]

    if CATALOG_ROOT.exists():
        shutil.rmtree(CATALOG_ROOT)
    CATALOG_ROOT.mkdir(parents=True, exist_ok=True)

    for document in filtered_projects:
        governed_app = governed_lookup.get(document.get("metadata", {}).get("name"))
        write_yaml(project_path(document), clean_document(enrich_labels(document, governed_app)))
    for document in filtered_services:
        governed_app = governed_lookup.get(document.get("metadata", {}).get("project"))
        write_yaml(service_path(document), clean_document(enrich_labels(document, governed_app)))
    for document in filtered_alert_policies:
        governed_app = governed_lookup.get(document.get("metadata", {}).get("project"))
        write_yaml(alert_policy_path(document), clean_document(enrich_labels(document, governed_app)))
    for document in filtered_slos:
        governed_app = governed_lookup.get(document.get("metadata", {}).get("project"))
        write_yaml(slo_path(document), clean_document(enrich_labels(document, governed_app)))

    print(
        f"Wrote {len(filtered_projects)} governed projects, {len(filtered_services)} services, "
        f"{len(filtered_alert_policies)} alert policies, and {len(filtered_slos)} SLOs into {CATALOG_ROOT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
