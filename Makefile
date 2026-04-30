CATALOG_GLOB = 'catalog/projects/**/*.yaml'

.PHONY: sync sync-governed-apps validate inventory readiness deploy-gate dry-run apply

sync:
	python3 scripts/sync_governed_apps.py
	python3 scripts/sync_nobl9_catalog.py

sync-governed-apps:
	python3 scripts/sync_governed_apps.py

validate:
	python3 scripts/slo_governance.py validate

inventory:
	python3 scripts/slo_governance.py inventory

readiness:
	python3 scripts/slo_governance.py apply-readiness

deploy-gate:
	python3 scripts/slo_governance.py deploy-gate $(if $(APP_ID),--app-id "$(APP_ID)",) $(if $(PROJECT),--project "$(PROJECT)",) $(if $(SERVICE),--service "$(SERVICE)",) --environment "$(or $(ENVIRONMENT),production)"

dry-run:
	python3 scripts/slo_governance.py apply-readiness
	sloctl apply --dry-run -y -f $(CATALOG_GLOB)

apply:
	python3 scripts/slo_governance.py apply-readiness
	sloctl apply -y -f $(CATALOG_GLOB)
