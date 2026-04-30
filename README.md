# Nobl9 Demo Org Governance Repo

This repo is designed to demo a more sustainable enterprise model for SLO governance:

- teams can create SLOs in the Nobl9 UI, from templates, or with AI assistance
- governed services are declared in inventory
- enterprise standards define what production-ready reliability looks like
- the catalog holds the governed Nobl9 source of truth
- enterprise deployment pipelines can enforce that governed production services do not ship without the required reliability contract

## What lives here

- `standards/`: enterprise SLO policy and approved governance rules.
- `inventory/`: governed applications and services that are evaluated at deployment time.
- `catalog/`: project and service-aligned Nobl9 source of truth.
- `exceptions/`: time-bound waivers for temporary policy gaps.
- `scripts/sync_nobl9_catalog.py`: normalizes the live Nobl9 org into the project/service-aligned catalog.
- `scripts/slo_governance.py`: validation, inventory coverage, and apply-readiness checks.
- `.github/workflows/`: governance validation and controlled apply workflows.

## Local workflow

Refresh the catalog from the live org:

```bash
make sync
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

1. Teams discover or draft SLOs in the UI, from templates, or with AI assistance.
2. `make sync` normalizes the live Nobl9 state into a project/service-aligned governed catalog.
3. Standards and inventory define which services are enterprise-governed for deployment.
4. The governance workflow validates object integrity, governed-service coverage, and apply-readiness.
5. The enterprise apply path promotes only governed, policy-compliant state into Nobl9.

## Important alerting note

Some alert policies include embedded alert methods with secret or hidden values. The export keeps these placeholders so the repo reflects the live org, but the apply-readiness check blocks promotion when `[hidden]` values are present. That prevents the workflow from accidentally overwriting real webhook secrets with placeholder text.

## Expected GitHub secrets

- `NOBL9_CLIENT_ID`
- `NOBL9_CLIENT_SECRET`

If you want a manual approval gate before applying, attach the apply job to a protected GitHub environment such as `nobl9-demo`.

## Demo Headline

**Teams can start SLOs however they want. Enterprise standards decide what is allowed to ship to production.**
