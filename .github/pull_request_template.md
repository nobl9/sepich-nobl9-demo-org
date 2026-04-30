## What changed?

Describe the project, service, alerting, or SLO-governance change in plain language.

## Why are we changing it?

Link the change to a demo goal, risk, incident pattern, or reliability review outcome.

## Governance checklist

- [ ] I updated the catalog in `catalog/` instead of changing Nobl9 only in the UI.
- [ ] I reviewed whether alert policies or composite dependencies also need changes.
- [ ] I considered whether the change alters ownership, labels, review cadence, or project scope.
- [ ] I checked whether exported alert policies still contain `[hidden]` placeholders.
- [ ] I know whether this should be promoted with replay after merge.
