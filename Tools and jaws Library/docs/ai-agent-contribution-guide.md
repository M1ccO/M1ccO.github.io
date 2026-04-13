# AI Agent Contribution Guide (Phase 7)

This guide defines the deterministic path for making safe changes in this repository.

## 1. Mandatory Read Order

1. TOOLS_JAWS_MODULAR_OVERHAUL_GOALS.md
2. TOOLS_JAWS_MODULAR_OVERHAUL_RULES.md
3. TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md
4. docs/module-index.md
5. docs/module-public-api-manifests.json
6. docs/module-change-checklists.json
7. docs/module-extension-points.json

If a requested change conflicts with these files, follow RULES and STATUS over local assumptions.

## 2. Deterministic Change Workflow

1. Identify the owning module from docs/module-index.md.
2. Read module contract:
   - TOOLS: docs/TOOLS_MODULE_CONTRACT.md
   - JAWS: docs/JAWS_MODULE_CONTRACT.md
   - Platform: docs/PLATFORM_LAYER_FORWARD_SPEC.md
3. Read module checklist from docs/module-change-checklists.json.
4. Implement the smallest behavior-preserving change.
5. Run required checks:
   - python scripts/module_extension_checker.py
   - python scripts/module_boundary_checker.py
   - python scripts/run_quality_gate.py
6. Update status tracker proof lines in TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md when phase deliverables are completed.

## 3. Boundary Rules You Must Not Violate

- No cross-app imports between Setup Manager and Tools and jaws Library.
- No TOOLS-to-JAWS support directory coupling:
  - ui/home_page_support must not import ui/jaw_page_support.
  - ui/jaw_page_support must not import ui/home_page_support.
- No cross-domain service coupling:
  - services/tool_service.py must not import jaw_service.
  - services/jaw_service.py must not import tool_service.
- Keep migrations additive-only.

See scripts/module_boundary_checker.py for enforced checks.

## 4. Extension-Point Safety (Phase 7)

Only registered extension classes may subclass platform base classes:

- CatalogPageBase
- CatalogDelegate
- EditorDialogBase

Registered classes and required override methods are defined in docs/module-extension-points.json and enforced by scripts/module_extension_checker.py.

If you add a new extension class:
1. Add the class with required overrides.
2. Register it in docs/module-extension-points.json.
3. Update docs/module-public-api-manifests.json.
4. Add or update module checklist entries.
5. Run quality gate.

## 5. Common Tasks and Correct Entrypoints

- Add tool/jaw catalog filtering: edit ui/home_page.py or ui/jaw_page.py via CatalogPageBase overrides.
- Adjust catalog rendering: edit ui/jaw_catalog_delegate.py or ui/tool_catalog_delegate_v2.py.
- Add migration step: edit data/migrations/tools_migrations.py or data/migrations/jaws_migrations.py; keep router exports stable.
- Change shared catalog behavior: edit shared/ui/platforms/catalog_page_base.py, then validate all extension subclasses.

## 6. Definition of Done for Agent Changes

A change is complete only when all are true:

1. Module-level checklist is satisfied.
2. module_extension_checker passes.
3. run_quality_gate passes.
4. No new boundary/import violations are introduced.
5. Status evidence is updated if the change advances a phase deliverable.
