CATALOG_GLOB = 'catalog/projects/**/*.yaml'

.PHONY: sync validate inventory readiness dry-run apply

sync:
	python3 scripts/sync_nobl9_catalog.py

validate:
	python3 scripts/slo_governance.py validate

inventory:
	python3 scripts/slo_governance.py inventory

readiness:
	python3 scripts/slo_governance.py apply-readiness

dry-run:
	python3 scripts/slo_governance.py apply-readiness
	sloctl apply --dry-run -y -f $(CATALOG_GLOB)

apply:
	python3 scripts/slo_governance.py apply-readiness
	sloctl apply -y -f $(CATALOG_GLOB)
