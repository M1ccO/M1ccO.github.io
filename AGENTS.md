# AGENTS

## Goal
This repository is optimized for deterministic AI-assisted coding. Always prefer canonical shared modules and avoid introducing duplicate implementations across apps.

## Workspace Layout
- `Setup Manager/`: setup/workflow app
- `Tools and jaws Library/`: tool/jaw library app
- `shared/`: canonical cross-app modules

## Canonical Shared Paths
- Services:
  - `shared.services.localization_service`
  - `shared.services.ui_preferences_service`
- Models:
  - `shared.models.tool`
  - `shared.models.jaw`
- UI:
  - `shared.ui.stl_preview`
  - `shared.ui.preferences_dialog_base`
  - `shared.ui.helpers.editor_helpers`
  - `shared.ui.helpers.common_widgets`
  - `shared.ui.helpers.editor_table`
  - `shared.ui.cards.mini_assignment_card`
- Platform Layer (Phases 3-9, all COMPLETE — use these for any new domain work):
  - `shared.ui.platforms.catalog_page_base` — `CatalogPageBase` abstract page orchestrator
  - `shared.ui.platforms.editor_dialog_base` — `EditorDialogBase` schema-driven editor
  - `shared.ui.platforms.catalog_delegate` — `CatalogDelegate` abstract card renderer
  - `shared.ui.platforms.selector_state` — `SelectorState` pure-Python filter state machine
  - `shared.ui.platforms.export_specification` — `ExportSpecification` domain-neutral Excel I/O
- Data:
  - `shared.data.model_paths`

## Import Rules
- Allowed: canonical `shared.*` imports and app-local imports for app-specific domains.
- Disallowed:
  - Legacy shared paths (e.g. `shared.editor_helpers`, `shared.model_paths`, `shared.editor_table`, `shared.mini_assignment_card`)
  - Cross-app imports from one app directly into the other app.
  - New wrapper modules that only forward imports unless temporary and explicitly marked.
  - Importing from `ui/home_page_support/` inside JAWS domain code (or vice versa).
  - Importing `tool_editor_support/` from `jaw_editor_dialog.py` unless logic is proven reusable.

## Intentional Boundaries (Do Not Merge)
- App-specific migration domains: `Tools and jaws Library/data/migrations/` package (tools_migrations.py + jaws_migrations.py)
- App-specific runtime config in each app `config.py`
- Setup-specific jaw default behavior in `Setup Manager/models/jaw.py`
- TOOLS and JAWS remain separate database domains (no merged table — out of scope)

## Validation Commands
- Full quality gate (6 checks):
  - `python scripts/run_quality_gate.py`
- Individual checks:
  - `python scripts/import_path_checker.py`
  - `python scripts/module_boundary_checker.py`
  - `python scripts/smoke_test.py`
  - `python scripts/duplicate_detector.py`
  - `python scripts/run_parity_tests.py`

## Architecture Source Of Truth
- Machine-readable ownership/dependency map: `architecture-map.json`
- Module ownership + maturity registry: `Tools and jaws Library/docs/module-registry.json`
- Architecture Decision Records: `Tools and jaws Library/docs/architecture-decisions.json`
- Deprecation + shim tracker: `Tools and jaws Library/docs/deprecations.json`
- Module entrypoint index: `Tools and jaws Library/docs/module-index.md`
- AI agent contribution guide: `Tools and jaws Library/docs/ai-agent-contribution-guide.md`
- Adapter design reference: `shared/ui/platform_glue/ADAPTERS_DESIGN_REFERENCE.md`
- Shim retirement policy: `docs/shim-retirement-policy.md`
- Work Editor refactor progress/status: `Setup Manager/WORK_EDITOR_REFACTOR_STATUS.md`
- Shared support goals: `Tools and jaws Library/PHASE11_SHARED_SUPPORT_GOALS.md`
- Shared support rules: `Tools and jaws Library/PHASE11_SHARED_SUPPORT_RULES.md`
- Shared support status: `Tools and jaws Library/PHASE11_SHARED_SUPPORT_STATUS.md`

## Modular Platform Overhaul — STATUS (as of April 13, 2026)

All 10 phases COMPLETE. The Tools and Jaws Library has been fully migrated to the platform layer.

| Phase | Title | Status |
|-------|-------|--------|
| 0 | Baseline & Freeze Rules | 🟢 COMPLETE |
| 1 | Domain Module Contracts | 🟢 COMPLETE |
| 2 | Module Governance Artifacts | 🟢 COMPLETE |
| 3 | Shared Module Platform Layer | 🟢 COMPLETE |
| 4 | TOOLS Migration (Pilot) | 🟢 COMPLETE — home_page.py 2,223L → 700L |
| 5 | JAWS Migration | 🟢 COMPLETE — jaw_page.py 1,423L → 558L |
| 6 | Data/Migration Segmentation | 🟢 COMPLETE — migrations.py → migrations/ package |
| 7 | AI-Agent Hardening | 🟢 COMPLETE |
| 8 | Legacy Coupling Retirement | 🟢 COMPLETE — adapters, shims, duplicate modules retired |
| 9 | Future Domain Template | 🟢 COMPLETE — Fixtures example domain verified |

**Post-overhaul file layout (Tools and jaws Library)**:
- `ui/home_page.py` — thin orchestrator (~583L), inherits `CatalogPageBase`
- `ui/jaw_page.py` — thin orchestrator (~524L), inherits `CatalogPageBase`
- `ui/home_page_support/` — 17 active modules including detail builders, filter/runtime/link coordinators, page builders, selector context, topbar builder, detached preview, and selection handlers
- `ui/jaw_page_support/` — 18 active modules including topbar builder, detail/bottom-bar builders, selector modules, page builders, detached preview, selection helpers, and selection signal handlers
- `ui/tool_editor_support/` — `component_picker_dialog.py`, `spare_parts_table_coordinator.py`, `component_linking_dialog.py`, `measurement_rules.py`, `transform_rules.py`
- `data/migrations/` — package with `tools_migrations.py` + `jaws_migrations.py` (backward-compatible)
**Adding a new domain**: Use `shared.ui.platforms.*` as the base (CatalogPageBase, EditorDialogBase, CatalogDelegate, ExportSpecification). Target ~1,000 lines total (model + service + page + editor + export spec + migrations).

## Temporary Shim Policy
- Temporary compatibility shims must include a removal note and target date/phase.
- Shims should be removed in the next cleanup cycle once all call sites are migrated.
- Track all shims in `docs/deprecations.json` with explicit removal targets.
- Search for `ADAPTER:` and `SHIM:` comments to find all active bridges.

## Ongoing Refactor Tracking
- For behavior-preserving reduction of `Setup Manager/ui/work_editor_dialog.py`, follow:
  - `Setup Manager/WORK_EDITOR_REFACTOR_STATUS.md`
- For support-layer convergence tracking (Phase 11), see:
  - `Tools and jaws Library/PHASE11_SHARED_SUPPORT_STATUS.md`
- Keep refactor passes small and responsibility-scoped.
