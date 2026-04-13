# Module Entrypoint Index (Phase 7)

This index is the deterministic starting point for contributors and agents.
Read this file first, then use the linked contract/manifests/checklists before editing code.

## Platform Core

- shared/ui/platforms/__init__.py
  - Purpose: Canonical public entrypoint for platform abstractions.
  - Use when: Creating or reviewing domain pages, delegates, editor bases, selector state, or export schemas.
  - Public API manifest: docs/module-public-api-manifests.json (module: shared.ui.platforms)
  - Checklist: docs/module-change-checklists.json (module: shared.ui.platforms)

- shared/ui/platforms/catalog_page_base.py
  - Purpose: Abstract page orchestrator for search/filter/list/selection flows.
  - Extension points: create_delegate, get_item_service, build_filter_pane, apply_filters.

- shared/ui/platforms/catalog_delegate.py
  - Purpose: Abstract catalog row rendering contract.
  - Extension points: _compute_size, _paint_item_content.

- shared/ui/platforms/editor_dialog_base.py
  - Purpose: Abstract schema-driven editor dialog contract.
  - Extension points: build_schema, validate_record, on_field_changed.

- shared/ui/platforms/selector_state.py
  - Purpose: Reusable selector state machine for domain filtering/assignment context.

- shared/ui/platforms/export_specification.py
  - Purpose: Domain-neutral export/import mapping and type coercion.

## Domain Entrypoints (Refactored)

- Tools and jaws Library/ui/home_page.py
  - Class: HomePage (CatalogPageBase subclass)
  - Domain: TOOLS
  - Contract: docs/TOOLS_MODULE_CONTRACT.md
  - Rules: TOOLS_JAWS_MODULAR_OVERHAUL_RULES.md (B-002/B-002b boundaries)

- Tools and jaws Library/ui/jaw_page.py
  - Class: JawPage (CatalogPageBase subclass)
  - Domain: JAWS
  - Contract: docs/JAWS_MODULE_CONTRACT.md
  - Rules: TOOLS_JAWS_MODULAR_OVERHAUL_RULES.md (B-001/B-001b boundaries)

- Tools and jaws Library/ui/jaw_catalog_delegate.py
  - Class: JawCatalogDelegate (CatalogDelegate subclass)
  - Domain: JAWS

- Tools and jaws Library/ui/tool_catalog_delegate_v2.py
  - Class: ToolCatalogDelegate (CatalogDelegate subclass)
  - Domain: TOOLS
  - Note: Candidate canonical delegate extension point in parallel path.

## Data Entrypoints

- Tools and jaws Library/data/migrations/__init__.py
  - Purpose: Backward-compatible migration router + domain-specific migration entrypoints.
  - Stable API: create_or_migrate_schema, migrate_jaws_schema, table_columns, json_loads.
  - New Phase 6 API: create_or_migrate_tools_schema, create_or_migrate_jaws_schema.

## Governance and Agent Hardening Entrypoints

- Tools and jaws Library/docs/module-public-api-manifests.json
  - Purpose: Machine-parseable exports, lifecycle, prohibited imports, quality checks.

- Tools and jaws Library/docs/module-change-checklists.json
  - Purpose: Deterministic verification requirements per module.

- Tools and jaws Library/docs/module-extension-points.json
  - Purpose: Allowlist of valid platform extension classes and required overrides.

- scripts/module_extension_checker.py
  - Purpose: Enforces extension-point boundaries and required override methods.

- scripts/run_quality_gate.py
  - Purpose: Executes all architecture and regression checks in sequence.
