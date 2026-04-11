# Process Goal + Status (AI Resume)

## Objective
Make main modules smaller and more modular, keep runtime behavior stable, and prepare profile-driven machine variants without breaking current DB contracts.

## Completed
- `Tools and jaws Library/ui/home_page.py`
  - Large UI construction moved behind support modules:
    - `ui/home_page_support/topbar_builder.py`
    - `ui/home_page_support/selector_card_builder.py`
    - `ui/home_page_support/components_panel_builder.py`
    - `ui/home_page_support/detail_fields_builder.py`
    - `ui/home_page_support/preview_panel_builder.py`
  - Selector assignment state extracted earlier to:
    - `ui/home_page_support/selector_assignment_state.py`
  - Main file now delegates major blocks instead of inline-building them.

- `Tools and jaws Library/ui/jaw_page.py`
  - Selector-slot orchestration extracted to:
    - `ui/jaw_page_support/selector_slot_controller.py`
  - Dead legacy classes/constants removed (unused row widget paths).

- `Tools and jaws Library/ui/tool_editor_dialog.py`
  - Tool-type detail branching extracted to:
    - `ui/tool_editor_support/detail_layout_rules.py`
  - Measurement overlay normalization/serialization extracted to:
    - `ui/tool_editor_support/measurement_rules.py`
  - Transform normalization/compaction extracted to:
    - `ui/tool_editor_support/transform_rules.py`
  - Dead helper methods/import paths removed from dialog.

- Shared and wiring
  - `ui/shared/selector_panel_builders.py` reused by Home/Jaw flows.
  - `ui/main_window_support/selector_session.py` in use for selector session mapping.
  - `__init__.py` exports updated in support packages to make extracted modules first-class.

- Stability and verification
  - Repeated `py_compile` and `compileall` passes done on edited modules.
  - Offscreen smoke checks passed for `HomePage`, `JawPage`, `AddEditToolDialog`.
  - Setup Manager -> Tools/Jaws open-path regression fixed (selector-context mismatch issue).

## Open
- Machine-profile capability layer is still partial:
  - no full central profile contract yet for station/axis/feature gating.
- Compatibility view-model layer is still partial:
  - legacy schema adapters are improved but not fully centralized for all editors.
- `Setup Manager/ui/work_editor_dialog.py` still oversized and needs the same extraction depth.
- Automated regression suite is still missing (current checks are compile + smoke).

## Next (Priority)
1. `Setup Manager/ui/work_editor_dialog.py`
   - extract large UI sections + selector/jaw hardcoded construction into `work_editor_support/*`.
   - keep schema and service interfaces unchanged.
2. Machine profile core
   - add explicit profile capability object (spindles, heads/stations, axis/features toggles).
   - use profile gating instead of scattered conditionals.
3. Compatibility adapters
   - centralize work/tool/jaw payload normalization + serialization.
4. Lightweight tests
   - selector payload mapping
   - profile gating behavior
   - save/load compatibility smoke fixtures.

## Constraints
- Keep Python + PySide6 core.
- Keep DB compatibility-first (additive-only if migration needed).
- Keep ownership split:
  - Setup Manager consumes references
  - Tools/Jaws Library remains master-data source.
