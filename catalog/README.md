# Catalog

This is the governed Nobl9 source of truth that is eligible for promotion.

The layout is intentionally aligned to how platform and application teams reason about ownership:

- `catalog/projects/<project>/project.yaml`
- `catalog/projects/<project>/alert-policies/*.yaml`
- `catalog/projects/<project>/services/<service>/service.yaml`
- `catalog/projects/<project>/services/<service>/slos/*.yaml`

Teams can still create SLOs in the Nobl9 UI, from templates, or with AI assistance. The purpose of this catalog is to hold the normalized, governed state that enterprise deployment standards can evaluate and promote.

