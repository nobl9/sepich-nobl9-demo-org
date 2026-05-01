#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[1]
APP_INVENTORY_PATH = ROOT / "inventory" / "app-inventory.yaml"
GOVERNED_APPS_PATH = ROOT / "inventory" / "governed-apps.yaml"
POLICY_PATH = ROOT / "standards" / "slo-governance-policy.yaml"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_project_catalog() -> list[dict]:
    projects: list[dict] = []
    for path in sorted((ROOT / "catalog" / "projects").glob("*/project.yaml")):
        with path.open("r", encoding="utf-8") as handle:
            projects.append(yaml.safe_load(handle) or {})
    return projects


def first_label(metadata: dict, label_name: str) -> str | None:
    labels = metadata.get("labels", {}) or {}
    values = labels.get(label_name) or []
    if not values:
        return None
    return values[0]


def normalized(value: str | None) -> str:
    return (value or "").strip().lower()


def slugify(value: str | None) -> str:
    collapsed = re.sub(r"[^a-z0-9]+", "-", normalized(value))
    return collapsed.strip("-") or "governed-app"


def enterprise_metadata(defaults: dict, app: dict) -> dict:
    default_metadata = (
        defaults.get("enterprise_metadata", {})
        or defaults.get("service_now_metadata", {})
        or defaults
    )
    app_metadata = (
        app.get("enterprise_metadata", {})
        or app.get("service_now_metadata", {})
        or {}
    )
    return {
        "assignment_group": (
            app_metadata.get("assignment_group")
            or app.get("ad_group_name")
        ),
        "cost_center": (
            app_metadata.get("cost_center")
            or app.get("cost_center")
            or default_metadata.get("cost_center")
        ),
        "business_unit": (
            app_metadata.get("business_unit")
            or app.get("business_unit")
            or default_metadata.get("business_unit")
        ),
        "environment_type": (
            app_metadata.get("environment_type")
            or app.get("env_type")
            or default_metadata.get("environment_type")
            or default_metadata.get("env_type")
        ),
    }


def main() -> int:
    app_inventory = load_yaml(APP_INVENTORY_PATH)
    policy = load_yaml(POLICY_PATH)
    project_catalog = load_project_catalog()
    inventory_defaults = app_inventory.get("defaults", {})

    inventory_selection = policy.get("inventory_selection", {})
    include_tiers = set(inventory_selection.get("auto_include_if_app_tier_in", ["tier1"]))
    app_tier_field = inventory_selection.get("app_criticality_field", "business_criticality_tier")
    app_id_label = inventory_selection.get("app_id_label", "app-id")
    project_name_suffix = inventory_selection.get("project_name_suffix", "-demo")

    governed_apps: list[dict] = []
    for app in app_inventory.get("apps", []):
        app_tier = app.get(app_tier_field)
        if app_tier not in include_tiers:
            continue

        app_id = app.get("app_id")
        matching_projects = [
            project
            for project in project_catalog
            if first_label(project.get("metadata", {}), app_id_label) == app_id
        ]
        if not matching_projects:
            matching_projects = [
                project
                for project in project_catalog
                if normalized(project.get("metadata", {}).get("displayName")) == normalized(app.get("name"))
            ]

        if matching_projects:
            project = matching_projects[0].get("metadata", {}).get("name")
            project_source = "catalog"
        else:
            project = f"{slugify(app.get('name'))}{project_name_suffix}"
            project_source = "naming-policy"
        governed_apps.append(
            {
                "app_id": app_id,
                "name": app.get("name"),
                "project": project,
                "deployment_policy": "enforce",
                "derived_from": {
                    "business_criticality_tier": app_tier,
                    "project_source": project_source,
                },
            }
        )

    output = {
        "version": "v1",
        "portfolio": app_inventory.get("portfolio", "unknown"),
        "description": (
            "Governed production applications synced from app-inventory.yaml using "
            "enterprise criticality metadata."
        ),
        "apps": governed_apps,
    }

    with GOVERNED_APPS_PATH.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(output, handle, sort_keys=False)

    print(
        f"Synced {len(governed_apps)} governed app(s) from {APP_INVENTORY_PATH.name} "
        f"into {GOVERNED_APPS_PATH.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
