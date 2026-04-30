# Nobl9 Enterprise SLO Governance Model

## Why this repo exists

The demo environment already has a functioning Nobl9 org full of projects, services, alert policies, and SLOs. The goal of this repo is not to force every team to author everything in YAML from day one. The goal is to show a sustainable enterprise model where:

- teams can create SLOs in the UI, from templates, or with AI help
- governed production services are declared in inventory
- enterprise standards define what is required to ship safely
- the governed catalog becomes the Git source of truth
- deployment pipelines enforce policy for governed services

This is intentionally inspired by the Glitchy Zoomies deployment model, where the important idea is that software and the reliability contract move forward together at release time.

## Guardrails enforced in-repo

The validator and policy files focus on deployment-time governance:

- every governed production service must exist in inventory
- governed services must exist in the Nobl9 catalog
- governed services must carry required metadata labels
- governed services must have the required SLO categories for their tier
- every service, alert policy, and SLO must reference a project that exists in the repo
- every SLO must reference a service that exists in the repo
- every alert policy referenced by an SLO must exist in the repo
- composite SLOs can only reference SLOs already defined in the catalog
- apply is blocked when the export still contains `[hidden]` placeholders from secret-bearing alert methods

## Workflow design

### `Nobl9 Org Governance`

Runs on pushes to `main` and by manual invocation.

- validates repo structure and object relationships
- validates governed inventory coverage against enterprise standards
- publishes a markdown inventory summary in the workflow run
- if Nobl9 credentials are configured, runs an authenticated `sloctl apply --dry-run`

### `Apply Nobl9 Org Catalog`

Runs manually from GitHub Actions.

- validates the repo again before promotion
- checks apply-readiness so placeholder secret values are never pushed
- installs `sloctl`
- applies `catalog/projects/**/*.yaml` from the checked out `main` branch
- optionally replays SLO history if an RFC3339 `replay_from` input is provided

## Suggested team process

1. Let teams create or refine SLOs in the UI, from templates, or with AI suggestions.
2. Use `make sync` to normalize the live org into the governed catalog structure.
3. Add or update governed services in inventory only when the enterprise wants deployment enforcement.
4. Resolve any `[hidden]` placeholder issues before running org-wide apply.
5. Use the enterprise deployment path as the hard enforcement point for governed production services.

## Customer-Friendly Framing

The simplest way to explain the model is:

**Teams are free to create SLOs in the easiest way possible. Enterprise governance decides what is required before production deployment.**
