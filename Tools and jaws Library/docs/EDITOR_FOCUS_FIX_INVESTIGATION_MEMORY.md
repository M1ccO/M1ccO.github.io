# Editor Focus Glitch Investigation - MEMORY

## Executive Summary

**Current State (April 2026):** A faint flash still occurs when opening Tool/Jaw Editor from Tools and Jaws Library. Multiple fix attempts have been made with varying degrees of success. The issue is deeply tied to WebEngine/Chromium initialization.

## The Problem

When user clicks EDIT TOOL or ADD TOOL in Tools/Jaws Library:
1. A brief window showing PYTHONW3.EXE appears in taskbar OR at the position where the editor should appear
2. This flash happens BEFORE the blur effect is applied
3. The actual editor eventually opens

This is NOT a focus issue - it's a rendering/initialization issue.

## Root Cause Analysis

### Timeline of Editor Open (Original - Problematic)

```
1. add_tool() called
2. AddEditToolDialog() created  ← StlPreviewWidget (WebEngine/Chromium) created HERE
3. Blur applied to host window
4. Dialog positioned
5. dlg.exec() runs modal loop
```

**THE ROOT CAUSE:** The `StlPreviewWidget` (WebEngine/Chromium) is instantiated during `AddEditToolDialog.__init__()`, BEFORE blur is applied. WebEngine initialization spawns a Chromium process that briefly appears in taskbar.

### Evidence

- Work Editor (in Setup Manager) is smooth because it has NO 3D preview/WebEngine
- Tool/Jaw Editor has WebEngine via `StlPreviewWidget` in the 3D Models tab
- The flash occurs at the same position where the 3D Models tab content would appear
- 2026-04-23 clue: in one broken launch state the main editor did not open, but the 3D Preview transform dialog/toolbar appeared by itself at exactly the same screen location where the PYTHONW3/Python instance flash had been appearing. This further points to the preview/transform surface being created or painted independently during the editor first-frame gap.

## All Fix Attempts (Chronological)

### Attempt 1: Focus Fix Between Dialog Creation and exec()
- **Changes:** Added `dlg.show()`, `dlg.raise_()`, `dlg.activateWindow()`, and SetForegroundWindow between positioning and exec()
- **Result:** No improvement - WebEngine still loads during dialog creation

### Attempt 2: QTimer Deferred Focus
- **Changes:** Used `QTimer.singleShot(0, ...)` to defer focus to next event loop iteration
- **Result:** FAILED - exec() blocks the event loop, so callback never runs

### Attempt 3: processEvents() After Blur
- **Changes:** Added `QApplication.processEvents()` after blur is applied
- **Result:** Slightly improved but flash still visible

### Attempt 4: prime_dialog() Before Blur
- **Changes:** Used shared `prime_dialog()` function to pre-build layout while hidden (pattern from Work Editor)
- **Result:** FAILED - broke dialog opening entirely (AttributeError on test stubs)

### Attempt 5: Set Parent/Window Flags
- **Changes:** Tried `dlg.setParent(None)` and `dlg.setWindowFlags(..., Qt.Window)`
- **Result:** FAILED - broke editor completely

### Attempt 6: Open on General Tab (Not 3D Models)
- **Changes:** Added `self.tabs.setCurrentIndex(0)` to open on General tab instead of last tab
- **Result:** Failed - transforms still triggered WebEngine load

### Attempt 7: Lazy STL Preview in editor_models_tab
- **Changes:** Tried to defer `StlPreviewWidget` creation until tab is shown
- **Result:** FAILED - transform controls connect to `models_preview` and fail when it doesn't exist, breaking the entire editor

### Attempt 8: Modify StlPreviewWidget Itself (DEEP FIX)
- **Changes:** Modified `shared/ui/stl_preview.py` to lazy-load WebEngine:
  - Create placeholder at init, not WebEngine
  - Add `_ensure_web_ready()` method
  - Guard all `_web` method calls with `_ensure_web()`
- **Result:** FAILED - too many places in the widget use `self._web`, broke the preview completely

### Attempt 9: ProcessEvents BEFORE Dialog Creation
- **Changes:** Reordered: apply blur first, processEvents, THEN create dialog
- **Result:** Slightly improved, faint flash still visible

### Attempt 10: Deferred Transform Signal Connections
- **Changes:** Used `QTimer.singleShot(100, ...)` to defer signal connections to transform preview
- **Result:** Still shows faint flash

### Currently Pending: Attempt 10 + Deferred Transform (may not have been saved correctly)

### Attempt 11: Stage 1 Opt-In Instrumentation
- **Changes:** Added `shared/ui/editor_launch_debug.py` and opt-in tracing behind `NTX_EDITOR_GLITCH_DEBUG`.
- **Coverage:** CRUD launch begin/blur/dialog init/position/exec, Tool/Jaw dialog show + first paint, models tab build, transform signal connection, `StlPreviewWidget` WebEngine creation/load/show/load-finished, and handoff IPC commands.
- **Output:** When enabled, trace lines are written to `%TEMP%\ntx_editor_glitch.log` by default, or to `NTX_EDITOR_GLITCH_LOG` if set.
- **Purpose:** No production behavior change. The trace is meant to decide whether the remaining glitch overlaps IPC handoff callbacks or is fully local to editor/3D-preview first paint.

### Attempt 12: Lazy WebEngine Surface Creation
- **Trigger:** User confirmed the flash still existed, with an earlier frame showing a floating `python3` rectangle at the same position as the preview/transform surface.
- **Changes:** `StlPreviewWidget` now constructs its lightweight Qt shell during editor initialization, but delays actual `QWebEngineView` creation and HTML load until after the preview widget is shown. The WebEngine creation is scheduled shortly after `showEvent` so the editor top-level can paint first.
- **Intent:** Prevent Chromium/WebEngine native windows from appearing while the editor dialog is still hidden or half-constructed.
- **Risk to verify manually:** First 3D preview paint may appear a fraction later, but cached `load_stl`, `load_parts`, transform state, measurement overlays, and control hints should apply once the viewer reports ready.
- **Follow-up:** User reported the flash still occurs, sometimes prominently. The delay was not sufficient by itself.

### Attempt 13: Models-Tab-Gated WebEngine Activation
- **Changes:** Editor previews now disable automatic WebEngine startup. `build_editor_models_tab()` activates `StlPreviewWidget` only when the 3D Models tab becomes the current tab.
- **Intent:** Opening Tool/Jaw Editor on the General tab should not spawn Chromium/WebEngine at all. This should remove the standalone `python3` flash from ordinary editor open.
- **Tradeoff:** The 3D preview initializes on first visit to the 3D Models tab instead of during editor open.
- **Follow-up:** User reported the flash became barely visible most of the time but could still be noticeable.

### Attempt 14: Disable Automatic Startup Preview Warmup
- **Finding:** `Tools and jaws Library/main.py` still scheduled `schedule_background_asset_warmup(..., include_preview_runtime=True)` 250 ms after Library startup, both visible and hidden. That path creates an offscreen `StlPreviewWidget` specifically to force Chromium/D3D surface creation and can overlap editor opening.
- **Changes:** Startup background asset warmup now uses `include_preview_runtime=False`. Explicit `warm_preview_runtime` IPC remains available for selector/detached-preview flows that intentionally request preview warmup.
- **Intent:** Prevent unrelated background Chromium/WebEngine startup from causing sporadic `python3` flashes during normal Tool/Jaw Editor open.

### Attempt 15: Lazy QtWebEngine Module Import
- **Finding:** User clarified the flash appears and closes before the editor opens. Even after gating preview activation, `shared/ui/stl_preview.py` still imported `QWebEnginePage`/`QWebEngineView` at module import time while editor construction built/imported the models-tab code.
- **Changes:** `QWebEnginePage` and `QWebEngineView` are now imported only inside `_create_preview_web_view()`, which is called from `_ensure_web_view()` after explicit preview activation.
- **Intent:** Constructing/opening Tool/Jaw Editor on the General tab should not import or initialize QtWebEngine at all.

### Attempt 16: Suppress Accidental Early Editor Surface During Construction
- **Finding:** User confirmed the flash still happens before the finished editor opens. The floating title was `python3`, consistent with a parentless Qt top-level surface becoming visible before the editor title/style is fully applied.
- **Changes:** Tool/Jaw editor dialogs now set title, modal state, and size immediately after `QDialog.__init__()`, then set `Qt.WA_DontShowOnScreen` during heavy construction and clear it before `exec()` can show the completed editor. Removed an extra `QApplication.processEvents()` from `add_tool()` before dialog construction.
- **Intent:** If any helper/native call accidentally realizes or shows the editor window during construction, it should not be visible and should already have the correct title metadata.

### Attempt 17: Diagnostic Bypass Switches
- **Finding:** User correctly called out that repeated guessed fixes are not robust enough. The flash still occurs before the editor opens, so the next step must isolate subsystems with controlled bypass tests.
- **Changes:** Added default-off diagnostic environment switches:
  - `NTX_EDITOR_DIAG_BYPASS_MODELS_TAB=1` replaces the full 3D Models tab with a lightweight placeholder/table and does not import/build preview or transform UI.
  - `NTX_EDITOR_DIAG_BYPASS_BLUR=1` skips the Library host blur effect during editor launch.
  - `NTX_EDITOR_DIAG_BYPASS_HOST_STYLE=1` skips host palette/font/stylesheet adoption during editor construction.
- **How to use:** Run one switch at a time, repeat Tool/Jaw editor open loops, and compare whether the pre-editor `python3` flash disappears, remains faint, or remains prominent.
- **Interpretation:** If one bypass removes the flash, that subsystem becomes the structural-fix target. If all three still show the flash, the root cause is probably earlier than editor support construction (for example Qt top-level creation or process/window activation outside these subsystems).

### Attempt 18: Stub Editor Diagnostic
- **Finding:** User still saw the flash after initial bypass work, so a stronger A/B test is needed.
- **Changes:** Added `NTX_EDITOR_DIAG_STUB_EDITOR=1`. When enabled, Tool/Jaw CRUD opens a tiny generic diagnostic `QDialog` instead of importing or constructing the real Tool/Jaw editor class. The real editor imports were moved from module top-level to lazy helper functions so the stub path avoids those modules entirely.
- **Interpretation:**
  - If the flash disappears with `STUB_EDITOR=1`, the root cause is inside real editor module import/construction.
  - If the flash remains with `STUB_EDITOR=1`, the root cause is outside Tool/Jaw editor internals: CRUD launch choreography, generic `QDialog` top-level realization, host blur/activation, detached preview close, or process/window-manager behavior.

## What Worked

### The Reordering (Attempt 9) - Slight Improvement
Reordering the add_tool() function:
```python
# BEFORE:
dlg = AddEditToolDialog(...)
if host and host.isVisible():
    _blur = QGraphicsBlurEffect(host)
    host.setGraphicsEffect(_blur)
    # ... position

# AFTER:
host = getattr(page, 'window', lambda: None)()
_blur = None
if host and host.isVisible():
    _blur = QGraphicsBlurEffect(host)
    _blur.setBlurRadius(6)
    host.setGraphicsEffect(_blur)
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()  # Let blur repaint first

dlg = AddEditToolDialog(...)
# position and exec()
```

This moved dialog creation AFTER blur+processEvents, slightly reducing the flash.

## Key Code Locations

### Files Modified During Investigation

1. `Tools and jaws Library/ui/home_page_support/crud_actions.py`
   - add_tool(), edit_tool() functions

2. `Tools and jaws Library/ui/jaw_page_support/crud_actions.py`
   - add_jaw(), edit_jaw() functions

3. `Tools and jaws Library/ui/shared/editor_models_tab.py`
   - build_editor_models_tab()
   - _build_transform_controls()

4. `Tools and jaws Library/ui/tool_editor_dialog.py`
   - _build_ui_modular()

5. `Tools and jaws Library/ui/jaw_editor_dialog.py`
   - _build_ui()

6. `shared/ui/stl_preview.py` (ATTEMPT 8 - reverted)
   - StlPreviewWidget.__init__()
   - Multiple methods using self._web

### The Transform Connection Problem

In `editor_models_tab.py`, lines 157-172 (in _build_transform_controls):

```python
if dialog._assembly_transform_enabled:
    dialog.models_preview.set_fine_transform_enabled(...)  # Calls preview method
    dialog.models_preview.transform_changed.connect(...)       # Connects to preview
    dialog.models_preview.part_selected.connect(...)
    dialog.models_preview.part_selection_changed.connect(...)
```

These lines execute when the 3D models tab is built - NOT when the tab is shown. They call methods on `models_preview` which triggers WebEngine load.

## What Might Fix It (Future Work)

### Option A: Defer ALL Transforms Until Tab Click
Move the entire `_build_transform_controls()` to a lazy function called only when user switches to 3D models tab.

### Option B: Stub Preview at Init
In `StlPreviewWidget.__init__()`, create a stub object that doesn't load WebEngine until first method call. But many internal methods use `_web` directly.

### Option C: Replace WebEngine with VTK or Software Renderer
Replace the Qt WebEngine preview with a pure Python 3D renderer (like VTK or pyopengl) that doesn't spawn a separate Chromium process.

### Option D: Process-Spawn Delay
In `AddEditToolDialog.__init__()`, use a small delay before creating the models_tab:
```python
def __init__(self, ...):
    super().__init__(...)
    # Don't build models tab immediately
    def _delayed_build():
        from ui.tool_editor_support.models_tab import build_models_tab
        build_models_tab(self, self.tabs)
    QTimer.singleShot(50, _delayed_build)
```

### Option E: Accept Current State
The flash is now a "faint hint" rather than a prominent flash. This may be acceptable given the complexity of a full fix.

## Files to Reference

- Original blueprint: `Tools and jaws Library/docs/EDITOR_FOCUS_FIX_BLUEPRINT.md`
- Screenshot showing broken state: `Näyttökuva 2026-04-23 163524.png`
- Work Editor smooth implementation: `Setup Manager/ui/setup_page_support/work_editor_launch.py`
- Shared prime_dialog: `shared/ui/main_window_helpers.py` (prime_dialog function)
- STL Preview (the culprit): `shared/ui/stl_preview.py`

## Reproduction Steps

1. Open Tools and Jaws Library application
2. Select any tool in the list
3. Click "EDIT TOOL" button
4. Observe taskbar - PYTHONW3.EXE briefly appears OR flash appears at editor position

## Current Code Changes (if any)

Use `git diff` to check current state.

## Later Isolation Notes

### Attempt 18: No-Dialog Diagnostic
- Added `NTX_EDITOR_DIAG_NO_DIALOG=1` in both tool/jaw CRUD launch paths.
- Result from user: the flash is still visible even when the handler returns before any editor dialog is created.
- Conclusion: the remaining flash is earlier than real editor construction and earlier than generic diagnostic-dialog creation.

### Attempt 19: No-Op Bottom-Bar Buttons
- Added `NTX_EDITOR_DIAG_NOOP_BUTTONS=1`.
- Tool page bottom-bar buttons already support it, and Jaw page wiring now matches.
- In this mode the ADD/EDIT/DELETE/COPY button click only logs a diagnostic event and does not call CRUD handlers.
- Purpose: if the flash still appears with no-op button wiring, the root cause is outside the CRUD/editor launch stack entirely and is likely tied to click/focus/window-manager side effects or another slot outside the action handlers.

### Attempt 20: Disable Global App Mouse Filter
- Added `NTX_EDITOR_DIAG_DISABLE_APP_MOUSE_FILTER=1` in `ui/main_window.py`.
- In this mode the Library skips installing its `QApplication`-level event filter, which normally processes every mouse press before button handlers run.
- That filter currently does two things on every click:
  - `clear_focused_dropdown_on_outside_click(...)`
  - `_clear_active_page_selection_on_background_click(...)`
- Purpose: if the flash disappears only when this filter is disabled, the root cause is in global pre-handler mouse/focus plumbing rather than CRUD/editor launch code or the button slot itself.

### Attempt 21: Keyboard-Only Action Trigger
- Added `NTX_EDITOR_DIAG_KEYBOARD_ONLY_ACTIONS=1`.
- In this mode the bottom-bar ADD/EDIT/DELETE/COPY buttons are hidden and disabled.
- Tool/Jaw pages install:
  - `Ctrl+Alt+E` for Edit
  - `Ctrl+Alt+N` for Add
- The action target still respects `NTX_EDITOR_DIAG_NOOP_BUTTONS=1`, so keyboard-triggered no-op and keyboard-triggered real action can both be tested.
- Purpose: compare a pure keyboard-triggered action against a physical mouse click on the button widget. If the flash disappears with keyboard-only triggering, the remaining culprit is strongly tied to native `QPushButton` click/focus behavior rather than editor or CRUD code.

### Attempt 22: Models Tab Bypass And First-Activation Lazy Construction
- User finally ran the earlier diagnostic `NTX_EDITOR_DIAG_BYPASS_MODELS_TAB=1` and reported that the glitch disappears entirely in that mode.
- That result is stronger than the earlier generic launch diagnostics: it puts the culprit back inside models-tab construction, not in CRUD launch, button plumbing, or generic dialog opening.
- The shared models tab builder was then rewritten so the normal path keeps only the model table and lightweight placeholders during editor construction.
- Real 3D-preview content is now materialized only when the `3D models` tab is actually opened for the first time.
- Deferred on first tab activation:
  - `StlPreviewWidget` construction
  - transform toolbar construction and signal wiring
  - model action toolbar construction
  - preview refresh / selection sync / WebEngine activation
- Purpose: match the successful bypass structure without losing normal models-tab functionality once the user intentionally visits that tab.

### Attempt 23: Shared Preview Runtime Recovery For Libraries And Selectors
- Re-enabled safe preview-runtime warmup, but only through the detached/external preview runtime pool rather than editor construction.
- Unified Library detached preview windows and Selector detached/external preview windows onto the same payload-driven preview host implementation.
- The shared host now owns:
  - claiming/releasing prewarmed preview widgets
  - preview dialog creation and reuse
  - geometry restore/placement
  - measurement toggle state
  - delayed show-until-model-ready behavior
- `StlPreviewWidget` render lifecycle was also relaxed for visible previews:
  - detached/external visible previews now keep rendering steadily instead of reacting to ordinary focus churn
  - embedded previews still stop when hidden/closed
- Single-model loads now avoid unnecessary full reload when the same STL/label is already loaded.

---

*Investigation conducted: April 23, 2026*
*Status: Root cause isolated to models-tab construction; first-activation lazy build is now the structural fix under test*
