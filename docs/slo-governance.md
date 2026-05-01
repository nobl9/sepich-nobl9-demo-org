# Nobl9 Enterprise SLO Governance Model

## Why this repo exists

The demo environment already has a functioning Nobl9 org full of projects, services, alert policies, and SLOs. The goal of this repo is not to force every team to author everything in YAML from day one. The goal is to show a sustainable enterprise model where:

- teams can create SLOs in the UI, from templates, or with AI help
- governed production services are declared in inventory
- enterprise standards define what is required to ship safely
- the governed catalog becomes the Git source of truth
- deployment pipelines enforce policy for governed services

This model is intentionally centered on the idea that software and the
reliability contract move forward together at release time.

## Guardrails enforced in-repo

The validator and policy files focus on deployment-time governance:

- broader enterprise app inventory can exist outside Nobl9
- governed deployment scope can be synced from app criticality metadata
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

Before getting into the GitHub workflows, it helps to separate two kinds of automation:

- background sync automation
- release-time governance automation

In many enterprises, background sync automation does not live in GitHub at all. It may run from a scheduler, integration platform, internal platform service, or another orchestration layer that talks to systems like ServiceNow or an internal developer portal.

GitHub is usually the better home for release-time governance because that is where deployment decisions are already audited and enforced.

### `Nobl9 Org Governance`

Runs on pushes to `main` and by manual invocation.

- validates repo structure and object relationships
- validates governed inventory coverage against enterprise standards
- publishes a markdown inventory summary in the workflow run
- if Nobl9 credentials are configured, runs an authenticated `sloctl apply --dry-run`

### `Apply Nobl9 Org Catalog`

Runs manually from GitHub Actions and also supports reusable `workflow_call` invocation.

- validates the repo again before promotion
- checks apply-readiness so placeholder secret values are never pushed
- installs `sloctl`
- applies `catalog/projects/**/*.yaml` from the checked out `main` branch
- optionally replays SLO history if an RFC3339 `replay_from` input is provided

### `Nobl9 Deployment Gate`

Runs manually from GitHub Actions for demos and also supports reusable `workflow_call` invocation so another deployment workflow can depend on it.

- evaluates a governed app, project, or service target
- passes with an informational result when the target is outside governed scope
- blocks when a governed deployment target is missing required service metadata or SLO coverage
- blocks when a governed project is only bootstrapped and has no service definitions yet
- surfaces approved exceptions as warnings instead of hard failures
- can be used as a shared GitHub gate in front of application deploy workflows

### `Example Governed App Deploy`

Runs manually from GitHub Actions as a customer-facing illustration of the full
release-governance pattern.

- calls the reusable `Nobl9 Deployment Gate` workflow first
- runs a placeholder application deployment job
- calls the reusable `Apply Nobl9 Org Catalog` workflow to reconcile live Nobl9 state after deploy
- demonstrates the intended order of operations even before a real application deployment pipeline is connected

For demos, this should be the primary workflow to run and revisit in Actions
history because it now produces:

- descriptive run names with target and environment
- numbered jobs that match the release flow
- a final `Demo Run Summary` job that explains what happened in business terms

## Enterprise Sync Model

In practice, I would usually split the operating model like this:

1. inventory sync
2. catalog sync
3. deployment gate
4. post-deploy Nobl9 reconcile

Typical ownership looks like:

- inventory sync: enterprise scheduler or integration automation
- catalog sync: scheduler, webhook-driven sync, or platform automation
- deployment gate: GitHub Actions or the deployment orchestrator
- Nobl9 reconcile after deploy: GitHub Actions or the deployment orchestrator

This repo intentionally demonstrates more of that model in GitHub because it is easier to show and reason about in a customer-facing demo. The important architectural point is not "GitHub does everything." The important point is that governed Git state and deployment-time reliability decisions are explicit and auditable.

## Suggested team process

1. Let teams create or refine SLOs in the UI, from templates, or with AI suggestions.
2. Maintain broader enterprise app metadata in `inventory/app-inventory.yaml`.
3. Use `make sync-governed-apps` to select governed apps based on inventory criticality.
4. Use `make sync` to rebuild `catalog/` from live Nobl9 state using `governed-apps.yaml` as the source of truth for project scope.
5. If a governed app has no Nobl9 project yet, let sync generate the bootstrap `project.yaml` so apply can create it.
6. Use the deployment gate from the enterprise pipeline to decide whether a governed app or service is allowed to ship.
7. Resolve any `[hidden]` placeholder issues before running org-wide apply.
8. Use the enterprise deployment path as the hard enforcement point for governed production services.

## Customer-Friendly Framing

The simplest way to explain the model is:

**Teams are free to create SLOs in the easiest way possible. Enterprise governance decides what is required before production deployment.**

## Demo-Friendly Source-Of-Truth Story

For demo purposes, this repo now shows a realistic chain of custody:

1. enterprise app inventory declares application metadata such as criticality
2. governance syncs the governed production subset from that metadata
3. the governed app subset drives which Nobl9 projects are built into catalog
4. deployment standards decide whether governed services are allowed to ship

That model supports both directions:

- if a governed app is new, the repo can bootstrap the Nobl9 project from governed scope
- if teams add or refine SLOs in the Nobl9 UI for a governed app, sync pulls those objects back into Git

## Deployment Gate Contract

For demo purposes, the deploy-time contract is now explicit:

- pipelines identify a target by `app_id`, `project`, or `project + service`
- if the target is outside governed scope, the gate returns a pass with context
- if the target is governed, the gate checks the governed catalog only for that target
- governed services must have required labels and SLO coverage for their tier
- active exceptions downgrade service-specific failures to warnings
- bootstrap-only projects do not fail apply-readiness, but they do fail deployment gate until service/SLO definitions exist

A simple enterprise pattern is:

1. app deploy workflow calls `Nobl9 Deployment Gate`
2. gate blocks or passes the governed target
3. successful app deploy is followed by Nobl9 reconciliation

The example workflow in this repo makes that sequence concrete in GitHub Actions.

For demo purposes, the app inventory is intentionally lightweight and easy to explain:

- `app_id`: a stable enterprise UID
- `name`: human-readable application name
- `business_criticality_tier`: the criticality signal used for governance scope
- `enterprise_metadata`: a lightweight stand-in for upstream CMDB metadata such as assignment group, cost center, business unit, and environment type

The idea is to make this feel closer to an upstream enterprise application registry such as ServiceNow, not a Nobl9-specific modeling file.
