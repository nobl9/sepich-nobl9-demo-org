# Nobl9 Demo Org Governance Repo

This repo is now structured to manage the entire Nobl9 demo org as code instead of just one project. The governed catalog lives in org-wide bundle files so you can review, diff, export, validate, and promote the full project/service/alert policy/SLO surface area from a single place.

## What lives here

- `catalog/org/projects.yaml`: all Nobl9 projects in the demo org.
- `catalog/org/services.yaml`: all services across projects.
- `catalog/org/alertpolicies.yaml`: all alert policies across projects.
- `catalog/org/slos.yaml`: all SLOs across projects.
- `scripts/export_nobl9_catalog.py`: refreshes the bundle files from live Nobl9 state.
- `scripts/slo_governance.py`: repo-native validation, inventory, and apply-readiness checks.
- `.github/workflows/`: pull request validation and controlled apply workflows.

## Local workflow

Refresh the repo from the live org:

```bash
make export
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

Run an authenticated Nobl9 dry run:

```bash
make dry-run
```

## Governance model

1. Export the live demo org into `catalog/org/*.yaml`.
2. Review and edit the catalog in Git.
3. Open a pull request and capture the operational reason for the change.
4. Let the `Nobl9 Org Governance` workflow validate object integrity and apply-readiness.
5. Merge to `main`.
6. Use the `Apply Nobl9 Org Catalog` workflow from `main` to promote the approved repo state into Nobl9.

## Important alerting note

Some alert policies include embedded alert methods with secret or hidden values. The export keeps these placeholders so the repo reflects the live org, but the apply-readiness check blocks promotion when `[hidden]` values are present. That prevents the workflow from accidentally overwriting real webhook secrets with placeholder text.

## Expected GitHub secrets

- `NOBL9_CLIENT_ID`
- `NOBL9_CLIENT_SECRET`

If you want a manual approval gate before applying, attach the apply job to a protected GitHub environment such as `nobl9-demo`.
