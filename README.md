# Nobl9 Demo Org Governance Repo

This repo is designed to demo a more sustainable enterprise model for SLO governance:

- teams can create SLOs in the Nobl9 UI, from templates, or with AI assistance
- governed services are declared in inventory
- enterprise standards define what production-ready reliability looks like
- the catalog holds the governed Nobl9 source of truth
- enterprise deployment pipelines can enforce that governed production services do not ship without the required reliability contract

## What lives here

- `standards/`: enterprise SLO policy and approved governance rules.
- `inventory/`: broader app inventory plus the governed application subset evaluated at deployment time.
- `catalog/`: project and service-aligned Nobl9 source of truth, built only for governed scope.
- `exceptions/`: time-bound waivers for temporary policy gaps.
- `scripts/sync_governed_apps.py`: syncs governed applications from enterprise app inventory metadata.
- `scripts/sync_nobl9_catalog.py`: materializes the governed project catalog from live Nobl9 state and bootstraps missing projects.
- `scripts/slo_governance.py`: validation, inventory coverage, apply-readiness, and deployment-gate checks.
- `.github/workflows/`: governance validation, deployment-gate, and controlled apply workflows.
- `.github/workflows/example-governed-app-deploy.yaml`: end-to-end example of gate -> app deploy -> Nobl9 reconcile.
- `.codex/skills/nobl9-enterprise-release-governance/`: repo-local Codex skill for updating or evaluating the enterprise governance model.

## Local workflow

Refresh governed scope and rebuild the governed catalog from the live org:

```bash
make sync
```

Sync governed applications from enterprise app inventory only:

```bash
make sync-governed-apps
```

Validate repo governance rules:

```bash
make validate
```

Review the catalog inventory:

```bash
make inventory
```

Check whether the exported catalog is safe to apply:

```bash
make readiness
```

Evaluate the deploy-time gate for a governed app or service:

```bash
make deploy-gate PROJECT=storefront-platform-demo SERVICE=storefront ENVIRONMENT=production
```

Run an authenticated Nobl9 dry run:

```bash
make dry-run
```

## Governance model

1. Teams discover or draft SLOs in the UI, from templates, or with AI assistance.
2. `make sync-governed-apps` turns broader app inventory metadata into the governed app subset.
3. `make sync` uses `governed-apps.yaml` as the source of truth for which Nobl9 projects are materialized into `catalog/`.
4. If a governed project does not exist in Nobl9 yet, sync creates a bootstrap `project.yaml` scaffold so apply can create it.
5. Standards and inventory define which services are enterprise-governed for deployment.
6. The deployment gate evaluates whether a governed app or service is allowed to ship.
7. The governance workflow validates object integrity, governed-service coverage, and apply-readiness.
8. The enterprise apply path promotes only governed, policy-compliant state into Nobl9.

## Enterprise Inventory Angle

In many enterprise environments, the SLO platform is not the system of record for application inventory. A separate source such as a CMDB, internal developer portal, or application portfolio tool usually carries metadata like business criticality.

This demo models that connective tissue explicitly:

- `inventory/app-inventory.yaml` represents the broader enterprise app inventory
- `inventory/governed-apps.yaml` is the synced subset used for deployment governance and governed catalog buildout
- each app record is intentionally simple: `app_id`, `name`, `business_criticality_tier`, and `ad_group_name`
- apps marked `tier1` in inventory metadata are automatically included in governed scope
- when a governed app has no live Nobl9 project yet, a naming policy generates the initial project name and a bootstrap project manifest

## UI Sync Angle

If a team builds or edits SLOs directly in the Nobl9 UI for a governed app, `make sync` pulls those changes back into the repo because the app's project stays in governed scope. That keeps Git as the durable source of truth without forcing teams to start in YAML.

## Enterprise Runtime Model

For demo clarity, this repo shows the sync and governance model in GitHub-friendly terms. In a real enterprise, these loops are often split across different automation surfaces:

- app inventory sync is often run by an enterprise scheduler, integration platform, or internal automation service
- Nobl9-to-Git catalog sync may run on a schedule, via webhook, or from a platform job outside GitHub
- deployment gate belongs in GitHub or the deployment orchestrator because it is part of the release decision
- post-deploy Nobl9 reconcile also fits naturally in GitHub because it follows the approved release path

So the practical model is:

- background syncs may live outside GitHub
- governed source of truth still lives in Git
- release governance stays close to the deployment workflow

## Deployment Gate

The deploy-time layer is meant to plug into a standard enterprise pipeline. A pipeline can call:

- `python3 scripts/slo_governance.py deploy-gate --project <project> --service <service>`
- or `python3 scripts/slo_governance.py deploy-gate --app-id <app_id>`

The gate behaves like this:

- if the target is not in governed scope, it passes with an informational result
- if the target is governed, it checks the catalog for the required service metadata and SLO coverage
- if the project is only bootstrapped and has no services yet, deployment is blocked until service definitions exist
- if an approved exception exists for a governed service, the gate warns instead of blocking

The repo also includes a demo workflow, `Nobl9 Deployment Gate`, that shows how a standard enterprise deployment pipeline could invoke the check from GitHub Actions.

That workflow supports both:

- manual runs with `workflow_dispatch` for demos
- reusable `workflow_call` invocation so an enterprise deploy workflow can put the gate directly in front of application deployment

There is also an example end-to-end workflow, `Example Governed App Deploy`, that demonstrates the full Zoomies-style sequence:

1. call the reusable deployment gate
2. deploy the application
3. reconcile Nobl9 from the governed catalog

Those GitHub workflows are meant to show the release-governance pattern clearly. They are not meant to imply that every upstream sync in a real enterprise must run in GitHub Actions.

## Important alerting note

Some alert policies include embedded alert methods with secret or hidden values. The export keeps these placeholders so the repo reflects the live org, but the apply-readiness check blocks promotion when `[hidden]` values are present. That prevents the workflow from accidentally overwriting real webhook secrets with placeholder text.

## Expected GitHub secrets

- `NOBL9_CLIENT_ID`
- `NOBL9_CLIENT_SECRET`

If you want a manual approval gate before applying, attach the apply job to a protected GitHub environment such as `nobl9-demo`.

## Demo Headline

**Teams can start SLOs however they want. Enterprise standards decide what is allowed to ship to production.**
