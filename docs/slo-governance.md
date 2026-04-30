# Nobl9 Org Governance Operating Model

## Why this repo exists

The demo environment already has a functioning Nobl9 org full of projects, services, alert policies, and SLOs. This repo makes that configuration reviewable, reproducible, and easier to govern:

- the repo becomes the source of truth for org-wide Nobl9 configuration
- pull requests become the approval path for reliability changes
- GitHub Actions becomes the controlled path for applying approved changes

## Guardrails enforced in-repo

The validator checks a few opinionated rules to keep the catalog healthy:

- every object must have the minimum identifying fields needed for replay and apply
- every service, alert policy, and SLO must reference a project that exists in the repo
- every SLO must reference a service that exists in the repo
- every alert policy referenced by an SLO must exist in the repo
- composite SLOs can only reference SLOs already defined in the catalog
- apply is blocked when the export still contains `[hidden]` placeholders from secret-bearing alert methods

## Workflow design

### `Nobl9 Org Governance`

Runs on pull requests and on pushes to `main`.

- validates repo structure and object relationships
- publishes a markdown inventory summary in the workflow run
- if Nobl9 credentials are configured, runs an authenticated `sloctl apply --dry-run`

### `Apply Nobl9 Org Catalog`

Runs manually from GitHub Actions.

- validates the repo again before promotion
- checks apply-readiness so placeholder secret values are never pushed
- installs `sloctl`
- applies `catalog/org/*.yaml` from the checked out `main` branch
- optionally replays SLO history if an RFC3339 `replay_from` input is provided

## Suggested team process

1. Start by refreshing the bundle files from live Nobl9 with `make export`.
2. Treat changes to targets, windows, objectives, composite weighting, alerting, and ownership as review-worthy changes.
3. Use the pull request template to record the operational reason for the update.
4. Resolve any `[hidden]` placeholder issues before running org-wide apply.
5. Prefer changing YAML here first, then promoting with the apply workflow, instead of editing objects ad hoc in the Nobl9 UI.

