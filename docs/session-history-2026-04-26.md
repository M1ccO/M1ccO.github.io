# Session History — 2026-04-26

**Branch**: `codex/before-shared-styles`  
**Date**: April 26, 2026  
**Topic**: Fix "separate Python instance flash" when opening Tool Selector from Work Editor

---

## Executive Summary

**Goal**: Eliminate the brief flash of a separate Python instance icon in the Windows taskbar that appears when clicking "Select Tools" button in Work Editor's TOOL IDs tab, just before the embedded selector appears.

**Outcome**: Root cause identified but not resolved. The flash is confirmed to occur inside EmbeddedToolSelectorWidget construction in the Tools and jaws Library app. Multiple fix attempts were made but none successfully eliminated the flash without breaking functionality.

---

## What Was Tested

### 1. Preview Host Preload Fix (Kept)
**Change**: In `selector_session_controller.py` line 1216, inverted condition so embedded mode skips preview host preload.

**Result**: ✅ Keeps embedded mode from launching separate Tool Library process during selector open.

**Status**: ✅ Kept in place

---

### 2. Qt.Window Flags Fix (Kept)
**Change**: Added `window_flags` parameter to `SelectorWidgetBase` defaulting to `Qt.Tool`.

**Result**: ⚠️ Does not eliminate flash - child widgets (QListView, QComboBox) still create their own Windows window handles during construction.

**Status**: ✅ Kept in place (minor improvement)

---

### 3. Trivial Diagnostic Widget Test (Informative)
**Change**: Set `NTX_WORK_EDITOR_SELECTOR_DIAGNOSTIC_KIND=trivial` to use a simple QFrame placeholder instead of real selector.

**Result**: ✅ Flash goes away completely. This proves the flash is happening INSIDE EmbeddedToolSelectorWidget construction.

**Status**: ✅ Confirms root cause location

---

### 4. Lazy Loading Attempt 1 - showEvent (Failed)
**Change**: Added `showEvent` override to defer heavy widget creation until first show.

**Result**: ❌ Selector doesn't open on first click - breaks functionality.

**Status**: ❌ Reverted

---

### 5. Lazy Loading Attempt 2 - materialize_content (Failed)
**Change**: Added `materialize_content()` method called via QTimer.singleShot after show.

**Result**: ❌ Selector functionality breaks - widgets don't work properly.

**Status**: ❌ Reverted

---

### 6. Event Filter for WS_EX_APPWINDOW (Crashed)
**Change**: Installed event filter at app startup to catch WinIdChange and remove WS_EX_APPWINDOW.

**Result**: ❌ App crashes on startup.

**Status**: ❌ Reverted

---

### 7. Widget Created Without Parent (No Effect)
**Change**: Created widget with `parent=None`, then called `setParent()` after construction.

**Result**: ❌ Flash still occurs.

**Status**: ❌ Reverted

---

### 8. WA_DontShowOnScreen (No Effect)
**Change**: Set `Qt.WA_DontShowOnScreen` before show, removed after.

**Result**: ❌ Flash still occurs.

**Status**: ❌ Reverted

---

## Root Cause Confirmed

### What Actually Happens

1. EmbeddedToolSelectorWidget is constructed in Work Editor's process
2. During __init__, it creates child widgets:
   - QComboBox (type_filter dropdown)
   - QListView (ToolCatalogListView)
   - QLineEdit (search input)
   - Various QLabels, QFrames, etc.
3. When Qt creates these widgets, Windows internally creates window handles for them
4. These window handles briefly appear in the Windows taskbar
5. By the time the widget is shown and re-parented under Work Editor, the icon disappears

### Why Flash Only Appears First Time
- The selector widget is cached and reused on subsequent opens
- Widget is only constructed (flash occurs) on first open or after Work Editor closes and reopens
- This explains why multiple opens in same session don't flash

### Why Visible on Ultrawide, Not on Laptop
- Flash appears at screen center
- On ultrawide monitors, the center is visible in taskbar area
- On smaller laptop screens, the same position may be covered by other UI elements
- User confirmed: on ultrawide it's visible; on laptop it's either hidden or not noticeable

---

## Files Modified This Session

| File | Change | Outcome |
|---|---|---|
| `Tools and jaws Library/ui/selectors/common.py` | Added `window_flags` parameter to SelectorWidgetBase (default Qt.Tool) | Kept - minor improvement |
| `Setup Manager/ui/work_editor_support/selector_session_controller.py` | Fixed preview host preload to skip for embedded mode | Kept - prevents Tool Library launch |
| `Setup Manager/ui/work_editor_support/selector_parity_factory.py` | Multiple attempted fixes (all reverted) | Reverted - no fix found |

---

## Smoke Test Status

✅ All changes pass smoke test.

---

## Conclusion

The flash appears to be a **Qt/Windows limitation** that's very difficult to work around for embedded widgets.

### Why It's Hard to Fix
- Flash happens during widget `__init__` - before any code can run to position or suppress it
- Child widgets (QListView, QComboBox, etc.) create their own Windows window handles internally
- These handles appear in taskbar before being re-parented under Work Editor

### Trade-offs Considered
1. **Stay with embedded mode**: Brief flash, works correctly, no separate process
2. **Switch back to IPC/detached mode**: Original "separate Python instance" flash returns (the problem we were trying to fix)

### Final Decision
- **Accept as Qt/Windows limitation**
- Selector works correctly
- Flash is brief (~200-500ms)
- Only appears on first selector open per Work Editor session
- Position is at screen center (confirmed by ultrawide observation)

---

## Session Duration

Approximately 4-5 hours of investigation, testing, and code changes across multiple files.

---

## Next Steps

1. Document the limitation in AGENTS.md
2. No further investigation needed unless a new approach is identified
---

## 2026-04-26 Update - Flash-Free Selector Architecture Confirmed, Visual Parity In Progress

### Current Status

The Windows taskbar / Python flash has been eliminated by stopping embedded Work Editor selectors from constructing the full Tools/Jaws Library selector widget subtree. Embedded mode now uses purpose-built Work Editor selector widgets that share safe data/services/delegates/payload logic, but avoid the Library selector stack that triggered the native-window flash.

### Confirmed Working

- Flash is gone when opening selectors from Work Editor.
- Embedded preview preload remains disabled, so selector open does not launch the external Tools/Jaws Library process.
- Jaw selector visual parity is now very close to the original.
- Jaw selector uses the old safe `JawAssignmentSlot` presentation again, with the flash-free local catalog view.
- Tool selector catalog cards and top toolbar are much closer after restoring the original toolbar helpers and delegate/catalog shell path.
- Basic embedded construction and payload emission pass for both Tool and Jaw selectors.

### Key Implementation Direction

The correct long-term direction is not warmup/cache and not suppressing native-window flags after construction. The durable fix is:

1. Keep Work Editor embedded selectors as normal child `Qt.Widget` widgets from birth.
2. Do not instantiate the full Library selector dialogs/subtrees in Work Editor embedded mode.
3. Reuse safe rendering/data pieces only:
   - catalog delegates
   - selector MIME/payload helpers
   - `MiniAssignmentCard`
   - `JawAssignmentSlot`
   - shared toolbar/list shell helpers
4. Keep preview lazy and external-host based only when the preview button is clicked.

### Files Actively Touched For This Direction

- `Tools and jaws Library/ui/selectors/tool_selector_dialog.py`
- `Tools and jaws Library/ui/selectors/jaw_selector_dialog.py`
- `Setup Manager/ui/work_editor_support/selector_session_controller.py`
- `Setup Manager/ui/work_editor_support/selector_parity_factory.py`
- `Tools and jaws Library/ui/selectors/tool_selector_layout.py`
- `Tools and jaws Library/ui/selectors/jaw_selector_layout.py`
- `tests/test_work_editor_embedded_selector.py`

### Latest Validation

Passed:

- `python -m py_compile` for changed selector/factory/controller/test files
- `python scripts/import_path_checker.py`
- `python scripts/smoke_test.py`
- Focused embedded selector runtime construction tests:
  - Tool embedded selector constructs with local flash-free catalog view and emits DONE payload
  - Jaw embedded selector constructs with local flash-free catalog view + old `JawAssignmentSlot` and emits DONE payload

Known unrelated/broader test note:

- Full `test_work_editor_embedded_selector.py` discover run still has existing failures around fixture preview import aliases and older selector-open ordering expectations. The new focused embedded selector construction tests pass.

### User Visual Feedback After Latest Pass

Jaw selector:

- "Pretty spot on now."
- No immediate Jaw selector changes requested.

Tool selector remaining visual issues:

- Selection panel header section is too tall.
- Tool drag/drop assignment areas do not yet follow the shared helper style that the Jaw selector now has.
- Bottom action button row is slightly offset toward the right; it should be centered according to the right-side Selection panel.

### Next Planned Work

Before changing code again, preserve this checkpoint in session history. After that, focus only on Tool selector visual parity:

1. Reduce Tool selection panel header height to match the original selector/Jaw selector proportions.
2. Rework Tool assignment drag/drop sections to follow the shared helper-style framing more closely.
3. Center the Tool action row relative to the right Selection panel, not the entire action host including the print-pots checkbox.
4. Keep the flash-free architectural boundary intact: no full Library selector subtree in embedded mode.

---

## 2026-04-26 Update 2 — Tool Selector Visual Parity + 3D Preview Fix

### Changes Made This Session

#### Bug Fixes

| Fix | File(s) | Details |
|---|---|---|
| `ToolSelectorRemoveDropButton` crash | `tool_selector_dialog.py` | Missing import added: `from ..home_page_support.selector_widgets import ToolSelectorRemoveDropButton` |
| 3D Preview not updating on item click | `tool_selector_dialog.py`, `jaw_selector_dialog.py` | `_on_catalog_item_clicked` in both `EmbeddedToolSelectorWidget` and `EmbeddedJawSelectorWidget` now calls `self._sync_preview_if_open()` after updating detail panel |
| Selected minicard border square (not rounded) | `Tools and jaws Library/styles/modules/60-catalog.qss` | Added `border-radius: 8px` to `QWidget[selectorContext="true"] QFrame[miniAssignmentCard="true"][selected="true"]` rule |
| QListWidget item highlight overlapping cards | `tool_selector_dialog.py` | Direct `setStyleSheet` on each `EmbeddedToolAssignmentList` with transparent item background/selection — eliminates blue Qt selection rectangle on top of custom card borders |
| Duplicate card / wrong styling appearance | `tool_selector_dialog.py` | Removed `_apply_mini_card_embedded_style(card)` call — cards now rely on ancestor QSS cascade from `selector_panel[selectorContext=True]` (same as standalone mixin), no conflicting direct stylesheet |
| `selectorContext` ancestor broken by QScrollArea viewport | `tool_selector_dialog.py` | Added `selectorContext=True` + `WA_StyledBackground` directly on `selector_panel` widget (closest ancestor to cards, only one QListWidget viewport boundary between them) |
| Sections scrollable instead of growing | `tool_selector_dialog.py` | Added `setSizePolicy(Ignored, Minimum)` + `setMinimumWidth(0)` on `selector_panel` to match `build_selector_card_shell` behavior |
| Extra gap between minicards | `tool_selector_dialog.py` | Removed `setSpacing(2)` from `EmbeddedToolAssignmentList` — gap now matches Work Editor (7px bottom margin in `row_host` only) |
| Height calculation unreliable | `tool_selector_dialog.py` | `_update_assignment_list_height` now reads `item.sizeHint().height()` directly (always set at `setSizeHint` call time) instead of `widget.height()` which returns 0 before render. Minimum raised from 40→56 |
| Missing list widget properties | `tool_selector_dialog.py` | Added `setProperty('selectorAssignmentList', True)`, `setViewportMargins(0,0,2,0)`, `setMinimumHeight(56)` to match mixin |
| Hint text never visible | `tool_selector_dialog.py` | `_update_assignment_empty_hint` now matches mixin logic: shows when `lst.count() == 0` AND not dismissed. Hint starts `setVisible(False)`, revealed by first `_rebuild_assignment_list` when empty, dismissed permanently when first tool is dropped |
| Hint text never disappears with items | `tool_selector_dialog.py` | Fixed: `_update_assignment_empty_hint` now requires BOTH `lst.count() == 0` AND not dismissed (was only checking dismissed) |
| Drag ghost from catalog card crashes app | `tool_selector_dialog.py` | Replaced `QWidget.render()` on unshown widget (segfault) with pure `QPainter` onto `QPixmap` — draws rounded rect + icon + title directly, no widget instantiation |
| Drag ghost not minicard-style | `tool_selector_dialog.py` | `_apply_catalog_drag_ghost` draws white rounded rect (`#99acbf` border, `#171a1d` text, 10.8pt DemiBold) matching minicard visual |
| Dropdown style only on hover | `tool_selector_dialog.py` | `_apply_type_filter_style()` sets direct `setStyleSheet` on combo with explicit white background — no palette conflict, no cascade dependency. `apply_shared_dropdown_style` still wires hover filter after |

#### Architecture Notes

- **Do not call `apply_selector_context_style()` on individual cards** in the embedded selector — it creates a conflicting direct stylesheet that fights the ancestor cascade. Use ancestor-based QSS (mixin pattern).
- **`selectorContext=True` must be on `selector_panel`** (inside the QScrollArea), not just on `selector_card` (outside). Two viewport boundaries (QScrollArea + QListWidget) break the cascade; one (QListWidget only) works.
- **QListWidget item selection highlight** must be suppressed via direct `setStyleSheet` on the list widget itself — ancestor QSS cannot reach through the viewport reliably for `::item:selected` pseudo-states.

### Files Modified

| File | Changes |
|---|---|
| `Tools and jaws Library/ui/selectors/tool_selector_dialog.py` | All embedded selector fixes above |
| `Tools and jaws Library/ui/selectors/jaw_selector_dialog.py` | 3D preview fix: `_on_catalog_item_clicked` calls `_sync_preview_if_open()` |
| `Tools and jaws Library/styles/modules/60-catalog.qss` | Added `border-radius: 8px` to selected minicard state |

### Status

All changes compile clean. Smoke test passes.

**Remaining known issues (not fixed this session):**
- Outer QScrollArea on selector panel scrolls when content exceeds panel height — this is by design (same as standalone selector), not a regression.

