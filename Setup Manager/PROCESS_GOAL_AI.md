# Process Goal + Status (AI Resume)

## Objective
Refactor main modules to reduce size/duplication, keep behavior stable, and prepare profile-driven machine variants without breaking DB compatibility.

## Done
- `Tools and jaws Library/ui/jaw_page.py`
  - `_build_ui` split into focused builders.
  - `populate_details` split (`_build_empty_details_card`, `_build_jaw_detail_header`, `_build_jaw_preview_card`).
  - integrated `jaw_page_support` detail/preview rule helpers.
  - fixed selector-context signature mismatch causing Setup Manager -> Tool/Jaw open failure.
  - dead-path cleanup completed (unused helper methods/branches removed).
- `Tools and jaws Library/ui/home_page.py`
  - selector panel partially modularized with shared builders.
  - dead imports and dead helper methods removed.
- Shared selector UI builders added:
  - `Tools and jaws Library/ui/shared/selector_panel_builders.py`
  - `Tools and jaws Library/ui/shared/__init__.py`
  - used by `home_page.py` and `jaw_page.py`.
- MainWindow selector-session normalization extracted:
  - `Tools and jaws Library/ui/main_window_support/selector_session.py`
  - `Tools and jaws Library/ui/main_window_support/__init__.py`
  - `ui/main_window.py` now uses helper state mapping.
- Multi-file dead-import cleanup done in:
  - `export_page.py`, `jaw_editor_dialog.py`, `jaw_export_page.py`, `main_window.py`, `tool_editor_dialog.py`.
- Setup docs updated:
  - `Setup Manager/README.md` (compact technical)
  - `Setup Manager/README_AI.md` (AI quick spec)

## Not Done (Open Work)
- Full machine-profile capability layer (stations/axes/features gating) not completed.
- Full compatibility view-model layer over legacy schema not completed.
- Remaining oversized modules still need deeper split:
  - `tool_editor_dialog.py`
  - `work_editor_dialog.py`
- Wider regression coverage (automated tests) still missing; validation mostly compile + runtime smoke.

## Next
1. `tool_editor_dialog.py` + `tool_editor_support/*`
   - run strict zero-reference sweep, remove dead compatibility paths.
   - extract repeated tab/form row builders to shared support module.
2. `Setup Manager/ui/work_editor_dialog.py`
   - continue profile/spec-driven extraction for large hardcoded page blocks.
3. Add lightweight regression harness:
   - selector payload mapping tests
   - profile/view-model normalization tests
   - save/load compatibility smoke tests.

## Constraints (Keep)
- Python + PySide6.
- DB compatibility-first, additive migrations only.
- Setup Manager remains reference consumer; Tool/Jaw master data ownership stays in Tools and jaws Library.
