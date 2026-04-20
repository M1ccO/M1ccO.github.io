# Selector Override Migration Implementation

## Initial Plan

The approved direction for this migration was:

1. Restore one production selector host.
   Use the old Library-owned standalone selector flow again so Setup Manager does not own embedded production selector UI.

2. Keep preview ownership inside the Library process.
   Selector preview windows, detached preview behavior, and selector geometry should all be owned by the Tools and Jaws Library process.

3. Move per-work tool editing into the Tool Selector.
   The Tool Selector should become the only place where per-work tool edits happen during a selector session:
   - override T-code
   - override description
   - comments
   - pot editing
   - print-pots state

4. Turn Tool IDs into a read-only projection.
   The Work Editor Tool IDs tab should only reflect selector-owned assignment state and launch selectors. It should no longer be a second mutation owner.

5. Preserve assignment state correctly.
   Reopening the selector or reopening Work Editor should preserve:
   - comment
   - pot
   - override_id
   - override_description
   - assignment-side description
   - assignment-side tool_type
   - default_pot

6. Add verification and remove dead paths after parity.
   IPC transport, selector result apply rules, print-pots round-trip, and read-only Tool IDs behavior should be regression-covered before old production branches are removed.


## Implemented So Far

### 1. Selector-owned tool row editing

Tool row editing was moved into the Tool Selector so the selector session can directly own:

- override T-code
- override description
- comment editing
- pot value editing

Implemented pieces:

- Added shared assignment-edit helpers in `shared/ui/tool_assignment_editing.py`.
- Updated `Tools and jaws Library/ui/selectors/tool_selector_state.py` so:
  - double-click edits the selected assignment row
  - `Edit Selection` uses the same dialog
  - comment editing is handled through the same dialog instead of a separate add-comment path
- Updated selector row rendering to show edited badges and pot badges from the selector-owned assignment snapshot.

Result:

- `Add Comment` and `Edit Selection` now conceptually share one edit path.
- Selector row edits no longer depend on Work Editor-local inline editing logic.


### 2. Selector-owned pot editing and print-pots state

Pot editing was moved under the Tool Selector session instead of staying Work Editor-owned.

Implemented pieces:

- Added a selector pot editor entry point in `tool_selector_layout.py` and `tool_selector_state.py`.
- Added shared pot editor plumbing through `shared/ui/tool_assignment_editing.py`.
- Reworked `Setup Manager/ui/work_editor_support/pot_editor.py` into a thin adapter around the shared dialog.
- Added selector-side `print_pots` state round-trip in:
  - `Tools and jaws Library/ui/selectors/tool_selector_payload.py`
  - `Tools and jaws Library/ui/selectors/tool_selector_dialog.py`
  - `Tools and jaws Library/ui/main_window.py`
  - `Tools and jaws Library/ui/main_window_support/selector_session.py`
  - `Tools and jaws Library/ui/main_window_support/selector_callback.py`
  - `Setup Manager/ui/work_editor_support/selector_provider.py`
  - `Setup Manager/ui/work_editor_dialog.py`

Result:

- The selector can own print-pots behavior during the session.
- Pot editing can be opened from the selector.
- Print-pots state is included in selector request and result payloads.


### 3. Work Editor Tool IDs moved toward read-only

The Work Editor Tool IDs views were simplified so they stop being a second production mutation owner.

Implemented pieces:

- Added `set_read_only()` to `Setup Manager/ui/work_editor_support/ordered_tool_list.py`.
- `Setup Manager/ui/work_editor_support/tools_tab_builder.py` now configures the Tool IDs lists in read-only mode.
- Legacy Tool IDs-side actions are hidden from the tab layout.
- Hidden compatibility widgets were retained for persistence and migration safety:
  - `print_pots_checkbox`
  - `edit_pots_btn`

Result:

- Tool IDs is now primarily a read-only overview of selector-owned assignment state.
- Selector launching remains available.


### 4. Assignment payload preservation across selector open/apply/save

The selector bucket and persistence path were extended so rich assignment data survives round-trips.

Implemented pieces:

- `Setup Manager/ui/work_editor_support/selectors.py`
  now preserves and rebuilds:
  - `comment`
  - `pot`
  - `override_id`
  - `override_description`
  - `description`
  - `tool_type`
  - `default_pot`

- `Setup Manager/ui/work_editor_support/ordered_tool_list.py`
  now preserves the same assignment-side fields in:
  - `set_tool_assignments()`
  - `get_tool_assignments()`

- `Setup Manager/services/work_service.py`
  now normalizes and serializes:
  - `description`
  - `tool_type`
  - `default_pot`
  in addition to previously preserved override and pot/comment fields.

Result:

- Saved work JSON can now carry richer selector-owned tool assignment state without a schema rewrite.


### 5. Setup card and Work Editor display alignment

A later bugfix pass addressed the mismatch where edited selector data was not always shown correctly after reopening Work Editor or when rendering setup cards.

Implemented pieces:

- `Setup Manager/ui/work_editor_support/ordered_tool_list.py`
  was updated so row rendering falls back to the saved assignment snapshot when live library lookup data is incomplete.
  This fixes cases where rows lost:
  - description
  - icon type context
  - edited-state formatting

- The Tool IDs duplicate `T-code` formatting bug was fixed so rows no longer display like:
  - `T1001 - T1001 — Description`

- `Setup Manager/services/print_service.py`
  was updated so setup-card tool rendering falls back to assignment-side:
  - `description`
  - `tool_type`
  before applying:
  - `override_id`
  - `override_description`

Result:

- Reopened Work Editor rows now render more reliably from the persisted snapshot.
- Setup cards can render edited tool data even when the reference lookup is incomplete.


### 6. Selector window sizing

The default selector size was increased to better fit the new selector-owned editing controls.

Implemented pieces:

- Increased default selector sizing in:
  - `Setup Manager/ui/work_editor_dialog.py`
  - `Tools and jaws Library/ui/selectors/tool_selector_dialog.py`
  - `Tools and jaws Library/ui/main_window.py`

Result:

- The selector now opens noticeably wider than before.


### 7. Regression coverage added or updated

Tests were added or updated around the migration-critical paths.

Covered areas include:

- selector result apply rules
- assignment bucket transport
- override preservation
- pot preservation
- print-pots round-trip
- WorkService round-trip for rich tool assignment payloads
- setup-card helper behavior for override and snapshot fallback

Relevant tests:

- `tests/test_selector_adapter_phase6.py`
- `tests/test_work_editor_embedded_selector.py`
- `tests/test_priority1_targeted.py`

Current known passing targeted test runs during this implementation:

- `tests/test_priority1_targeted.py`
- `tests/test_selector_adapter_phase6.py`
- `tests/test_work_editor_embedded_selector.py`


## What Still Remains

### 1. Full production-host cleanup is not finished

The migration has moved behavior toward selector-owned editing, but the broader top-level host cleanup is still incomplete.

Still remaining:

- finish demoting embedded production selector paths to diagnostic-only
- remove dead embedded production logic after parity is proven
- complete cleanup of old Work Editor-local mutation affordances that are now obsolete


### 2. Tool IDs still contains compatibility-era code

Tool IDs is effectively read-only in the visible UI, but `ordered_tool_list.py` still contains older editing/comment helpers and mixed responsibilities that should be reduced further.

Still remaining:

- remove dead inline editing/comment code once migration confidence is high
- simplify the class so it becomes a pure read-only projection plus selector-launch support
- reduce fallback logic that only exists for transitional compatibility


### 3. Shared formatting path is not fully unified yet

One of the plan goals was to derive selector rows and Tool IDs rows from one shared interpretation path. The behavior is closer now, but not fully centralized.

Still remaining:

- centralize effective-tool display formatting
- centralize edited/comment/pot badge decisions
- centralize icon-orientation and fallback rules


### 4. More end-to-end verification is still needed

Targeted tests now cover important logic, but the migration still needs broader confidence passes.

Still remaining:

- manual verification of selector-only editing flow
- manual verification of setup-card output from edited selector data
- manual verification of preview stability while selector stays open
- manual verification of selector geometry persistence independent of Work Editor size
- quality-gate run for the whole branch before final cleanup


### 5. Potential persistence edge cases should still be watched

The core save/load path now preserves richer assignment metadata, but this migration touches multiple handoff points between apps and services.

Still worth watching:

- reopening a selector after mixed edits across both spindles and both heads
- duplicate tool IDs with different UIDs
- deleted-library-tool cases where only assignment snapshot data remains
- print/export paths beyond the setup-card path already patched


### 6. Documentation and code cleanup follow-up

After parity is confirmed, this branch should still do a cleanup pass.

Recommended follow-up:

- remove transitional comments and compatibility scaffolding
- update any refactor status documents that describe selector ownership
- document the final supported selector host path and selector payload contract


## Short Status Summary

This migration slice has already moved the most important ownership in the right direction:

- Tool Selector now owns the editing UX during the selector session
- Work Editor persists the returned assignment snapshot
- Tool IDs is moving into read-only projection mode
- rich assignment fields now round-trip more reliably through save/load and setup-card rendering

The main remaining work is cleanup, parity verification, and removing the last transitional production paths once behavior is confirmed stable.
