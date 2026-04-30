---
name: nobl9-enterprise-release-governance
description: Use this skill when updating or evaluating the repo's Nobl9 enterprise governance model, including governed app scope, catalog sync, bootstrap project creation, deployment-gate behavior, or the GitHub workflow chain that puts reliability checks in front of deployment.
---

# Nobl9 Enterprise Release Governance

## Overview

Use this skill for repo-local work where the goal is to keep the enterprise Nobl9 operating model coherent:

- upstream app inventory determines governed scope
- governed scope determines which Nobl9 projects belong in Git
- governed projects can bootstrap a project scaffold before live Nobl9 exists
- governed UI changes sync back into Git
- deployment workflows block or pass release based on the governed reliability contract

This skill is modeled after the Glitchy Zoomies release-governance pattern, but adapted for this repo's broader enterprise framing.

## When To Use

Use this skill when the user asks to:

- change the enterprise SLO standard or governance model
- update governed app sync, catalog sync, or bootstrap behavior
- adjust deploy-time checks for governed apps or services
- wire or review GitHub workflows for gate -> deploy -> reconcile
- explain how Git, Nobl9, app inventory, and deployment pipelines fit together

Do not use this skill for:

- greenfield SLO drafting for one service with no governance angle
- generic Nobl9 product explanations that do not involve this repo's operating model

## Repo Control Points

Start with these files:

- `inventory/app-inventory.yaml`
- `inventory/governed-apps.yaml`
- `standards/slo-governance-policy.yaml`
- `scripts/sync_governed_apps.py`
- `scripts/sync_nobl9_catalog.py`
- `scripts/slo_governance.py`
- `.github/workflows/slo-deployment-gate.yaml`
- `.github/workflows/slo-apply.yaml`
- `.github/workflows/example-governed-app-deploy.yaml`
- `README.md`
- `docs/slo-governance.md`

## Workflow

Follow this order:

1. Identify the operating layer being changed.
   - `inventory scope`
   - `catalog sync`
   - `bootstrap onboarding`
   - `deployment gate`
   - `GitHub workflow chain`

2. Read the governing source files before editing.
   - Inventory questions start with `inventory/` and `standards/`.
   - Sync questions start with the two sync scripts.
   - Release-governance questions start with `scripts/slo_governance.py` and the deployment workflows.

3. Preserve the enterprise separation of concerns.
   - Background syncs may live outside GitHub in a real enterprise.
   - Release governance belongs in GitHub or the deployment orchestrator.
   - Git is the governed source of truth.
   - Nobl9 is the live reliability control plane after promotion.

4. Prefer governed scope over full-org scope.
   - Only governed apps should drive catalog materialization.
   - Governed apps should be simple enterprise records, not service-by-service policy files.
   - Service-level requirements come from service metadata and policy, not from duplicating service lists in governed-app inventory.

5. For onboarding a new governed app:
   - update `inventory/app-inventory.yaml`
   - run `python3 scripts/sync_governed_apps.py`
   - run `python3 scripts/sync_nobl9_catalog.py`
   - expect a bootstrap `project.yaml` when the project does not yet exist in Nobl9
   - expect deployment gate to block until services and SLOs exist

6. For deployment governance changes:
   - keep enforcement in `scripts/slo_governance.py`
   - keep GitHub workflows reusable with `workflow_call` when possible
   - prefer a flow of `gate -> deploy -> reconcile`
   - treat non-governed targets as informational pass, not hard failure

7. Validate with repo-local commands.
   - `python3 scripts/slo_governance.py validate`
   - `python3 scripts/slo_governance.py apply-readiness`
   - `python3 scripts/slo_governance.py deploy-gate --project <project> --service <service> --environment production`
   - `python3 scripts/slo_governance.py inventory`

## Required Output Shape

When analyzing or reviewing this model, prefer these sections:

1. `Governed target`
   - app, project, service, or workflow surface being changed

2. `Decision`
   - what should happen in the enterprise model
   - whether the change belongs in background sync or release governance

3. `Repo changes`
   - which inventory, standard, script, or workflow files should change

4. `Validation`
   - which commands or workflow behaviors confirm the model still holds

## Repo Defaults

For this repo, assume:

- governed scope is derived from `business_criticality_tier`
- `tier1` apps are auto-included by default
- governed apps map to a Nobl9 project in `governed-apps.yaml`
- `catalog/` should contain governed projects only
- deploy gate should be reusable as a GitHub workflow
- the end-to-end demo flow is `gate -> deploy app -> reconcile Nobl9`

## Notes

- Be careful not to let `governed-apps.yaml` turn into a second policy engine.
- Prefer simple enterprise-style inventory fields upstream and richer enforcement downstream.
- When using Glitchy Zoomies as inspiration, copy the operating pattern, not the app-specific details.
