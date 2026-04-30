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


def main() -> int:
    projects, services, alert_policies, slos = [run_export(command) for command in EXPORTS]

    if CATALOG_ROOT.exists():
        shutil.rmtree(CATALOG_ROOT)
    CATALOG_ROOT.mkdir(parents=True, exist_ok=True)

    for document in projects:
        write_yaml(project_path(document), clean_document(document))
    for document in services:
        write_yaml(service_path(document), clean_document(document))
    for document in alert_policies:
        write_yaml(alert_policy_path(document), clean_document(document))
    for document in slos:
        write_yaml(slo_path(document), clean_document(document))

    print(
        f"Wrote {len(projects)} projects, {len(services)} services, "
        f"{len(alert_policies)} alert policies, and {len(slos)} SLOs into {CATALOG_ROOT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

