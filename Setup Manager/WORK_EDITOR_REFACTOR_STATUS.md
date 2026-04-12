# Work Editor Refactor Status

Last updated: 2026-04-12

## Goal
Reduce responsibility in `Setup Manager/ui/work_editor_dialog.py` so the dialog remains orchestration-focused, while behavior stays unchanged.

## Completed In This Refactor Track

### 1) Jaw selector sub-widget extraction
- Extracted jaw panel widget logic from `work_editor_dialog.py` into:
  - `Setup Manager/ui/work_editor_support/jaw_selector_panel.py`
- Dialog now coordinates usage; widget internals are app-local support code.

### 2) Tool picker dialog extraction
- Extracted embedded tool picker dialog into:
  - `Setup Manager/ui/work_editor_support/tool_picker_dialog.py`
- Preserved search/filter/selection behavior and result payload shape.

### 3) Ordered tool list extraction
- Extracted embedded ordered-list component into:
  - `Setup Manager/ui/work_editor_support/ordered_tool_list.py`
- Preserved drag/drop, ordering, inline edit, comments, and assignment serialization behavior.
- Included callback injection fix to avoid bound-method argument mismatch when using configured class callables.

### 4) Icon resolver extraction
- Moved tool/icon helper responsibility into:
  - `Setup Manager/ui/work_editor_support/icon_resolvers.py`
- Dialog now injects resolver functions into ordered-list support.

### 5) Zero-point helper extraction
- Moved zero-point UI helper logic into:
  - `Setup Manager/ui/work_editor_support/zero_points.py`
- Dialog methods are preserved and now delegate to support helpers, so existing adapters/builders remain compatible.

### 6) Selector adapter extraction
- Moved selector-facing adapter logic into:
  - `Setup Manager/ui/work_editor_support/selector_adapter.py`
- Includes head/spindle labeling, selector result application, ref merges, and warning/session adapters.

## Files Added During This Track
- `Setup Manager/ui/work_editor_support/jaw_selector_panel.py`
- `Setup Manager/ui/work_editor_support/tool_picker_dialog.py`
- `Setup Manager/ui/work_editor_support/ordered_tool_list.py`
- `Setup Manager/ui/work_editor_support/icon_resolvers.py`
- `Setup Manager/ui/work_editor_support/zero_points.py`
- `Setup Manager/ui/work_editor_support/selector_adapter.py`

## Core File Still Being Reduced
- `Setup Manager/ui/work_editor_dialog.py`

## What Is Left (Safe Next Steps)

### A) Trim thin wrapper methods in dialog
- Many dialog methods are now one-line delegations.
- Next step: group these wrappers by concern and move only repeated boilerplate or facade-like wrappers to a small app-local facade module, while keeping bridge callback surface stable.

### B) Isolate dialog lifecycle setup blocks
- Extract small setup helpers for:
  - tab creation and registration
  - dialog button row setup
  - final combo repolish/event-filter wiring
- Keep ownership of signals/lifecycle in dialog class.

### C) Normalize support module boundaries
- Ensure support modules stay responsibility-focused:
  - widget/controller modules for UI behavior
  - adapter modules for data/selector coordination
  - builder modules for tab construction
- Avoid creating forwarding wrappers with no logic.

### D) Keep validation strict after each pass
- Run:
  - `python -m py_compile` for touched files
  - `python scripts/run_quality_gate.py`
- Keep duplicate-detector baseline unchanged or lower.

## Non-Negotiables For Remaining Work
- No schema changes.
- No file format or payload shape changes.
- No user-visible workflow changes.
- No direct imports between Setup Manager and Tools and jaws Library.
- Use `shared/` only for clearly canonical cross-app logic.
- Avoid compatibility shims unless absolutely necessary.

## Notes
- This track is intentionally incremental. The objective is safer responsibility extraction, not broad rewrites.
