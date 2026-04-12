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
- Data:
  - `shared.data.model_paths`

## Import Rules
- Allowed: canonical `shared.*` imports and app-local imports for app-specific domains.
- Disallowed:
  - Legacy shared paths (e.g. `shared.editor_helpers`, `shared.model_paths`, `shared.editor_table`, `shared.mini_assignment_card`)
  - Cross-app imports from one app directly into the other app.
  - New wrapper modules that only forward imports unless temporary and explicitly marked.

## Intentional Boundaries (Do Not Merge)
- App-specific migration domains under each app `data/migrations.py`
- App-specific runtime config in each app `config.py`
- Setup-specific jaw default behavior in `Setup Manager/models/jaw.py`

## Validation Commands
- Full quality gate:
  - `python scripts/run_quality_gate.py`
- Individual checks:
  - `python scripts/import_path_checker.py`
  - `python scripts/smoke_test.py`
  - `python scripts/duplicate_detector.py`

## Architecture Source Of Truth
- Machine-readable ownership/dependency map: `architecture-map.json`
- Shim retirement policy: `docs/shim-retirement-policy.md`
- Work Editor refactor progress/status: `Setup Manager/WORK_EDITOR_REFACTOR_STATUS.md`
- Tool Editor refactor log: `Tools and jaws Library/TOOL_EDITOR_REFACTOR.md`

## Temporary Shim Policy
- Temporary compatibility shims must include a removal note and target date/phase.
- Shims should be removed in the next cleanup cycle once all call sites are migrated.

## Ongoing Refactor Tracking
- For behavior-preserving reduction of `Setup Manager/ui/work_editor_dialog.py`, follow:
  - `Setup Manager/WORK_EDITOR_REFACTOR_STATUS.md`
- For `Tools and jaws Library/ui/tool_editor_dialog.py` modularization (April 2026), see:
  - `Tools and jaws Library/TOOL_EDITOR_REFACTOR.md`
  - ~428 lines extracted into three `tool_editor_support/` modules:
    - `component_picker_dialog.py` — searchable component picker dialog
    - `spare_parts_table_coordinator.py` — spare parts table + debounced refresh
    - `component_linking_dialog.py` — spare-to-component linking dialog
- Keep refactor passes small and responsibility-scoped.
