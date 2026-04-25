# Session History — 2026-04-25

Branch: `codex/before-shared-styles`  
Last commit at session start: `2f8ae91` — "LIbrary EDITOR flash FIXED once and for all!"

---

## Context

This session focused on three main issues:
1. **Module switch freeze** — After closing the editor, switching between Tool and Jaw libraries would freeze
2. **Editor tab fade** — Switching between General and 3D Models tabs in the editor caused a visual fade
3. **HEAD2 filter broken** — Clicking HEAD2 in the tool library had no effect after opening the editor

---

## Issue 1: Module Switch Freeze After Editor Close

### Symptom
After opening the Jaw Editor (or Tool Editor) from the Library, closing it and then clicking TOOLS/JAWS to switch modules would freeze the UI. The user reported "Entire window frozen" - no interaction possible.

### Root Cause
During module switch (`_apply_module_mode()`), the code accessed widgets that had been deleted when the editor closed, causing a `RuntimeError`:

> Internal C++ object (PySide6.QtWidgets.QPushButton) already deleted

This error was being caught somewhere deep in the call stack, causing the entire switch operation to silently fail.

### Investigation Steps
1. Added `_close_library_detached_previews(self)` at start of `_apply_module_mode()` - didn't fix
2. Added blur cleanup - didn't fix  
3. Added `processEvents()` calls - didn't fix the freeze
4. The click handler was being called (`_toggle_module` executed) but `_apply_module_mode` was silently failing

### Fix Applied
Created `_safe_set_module_pages()` with try/except guards around all page operations:

```python
def _safe_set_module_pages(self, module: str):
    """Switch page state with deleted-widget guards."""
    try:
        if module == 'jaws':
            for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page, self.jaws_page]:
                try:
                    page.set_module_switch_target('TOOLS')
                except Exception:
                    pass
            self._open_jaws_view('all')
            # ... more guarded operations
    except Exception as e:
        logging.getLogger(__name__).warning("_safe_set_module_pages failed: %s", e)
```

Also simplified `_on_head_nav_clicked()` to directly call page methods instead of using the hidden combo signal chain.

### Files Changed
- `Tools and jaws Library/ui/main_window.py`
  - Added `_safe_set_module_pages()` helper method
  - Simplified `_on_head_nav_clicked()` to update pages directly
  - Modified `_apply_module_mode_impl()` to use `_safe_set_module_pages()`

### Status: FIXED ✓

---

## Issue 2: Editor Tab Switch Fade

### Symptom
When switching from General tab to 3D Models tab in the editor, the preview briefly faded (went white/invisible) then appeared. Same when switching back.

### Root Cause
This is an inherent tradeoff with the lazy preview initialization that was introduced to fix the original editor flash:

1. Editor opens with lazy placeholder in Models tab
2. On first click to Models tab, `showEvent` fires on `StlPreviewWidget`
3. 75ms delay (`_EDITOR_PREVIEW_WEBENGINE_DELAY_MS`) before WebEngine creates
4. WebEngine loads HTML (~50-100ms)
5. `_sync_rendering_state()` is called in both `showEvent` and `hideEvent` during tab switches
6. This briefly disables rendering during the visibility change

The `_schedule_editor_preview_activation()` also had multiple `_restore_modal_visual_state()` calls at 0, 120, 320ms which caused focus churn.

### Fixes Attempted
1. Removed redundant `_sync_rendering_state()` calls from `hideEvent` for embedded previews
2. Removed multiple `_restore_modal_visual_state()` calls after preview activation  
3. Used conditional WebEngine delay: 0ms if already loaded, 75ms if not

### Result
The fade still occurs due to inherent lazy initialization. This is documented in `docs/EDITOR_FOCUS_FIX_BLUEPRINT.md` as a known tradeoff. The alternative (eager preview creation) would bring back the original editor flash bug.

### Files Changed
- `Tools and jaws Library/ui/shared/editor_models_tab.py` - simplified `_ensure_preview_ready()` 
- `shared/ui/stl_preview.py` - attempted hideEvent fixes (reverted)

### Status: KNOWN TRADEOFF - Not fully fixed

---

## Issue 3: HEAD2 Filter Not Working After Editor

### Symptom
Clicking the HEAD2 button in the tool library rail had no effect after opening and closing the editor. The list would show no tools or wrong tools.

### Root Cause  
After editor closes, `_on_head_nav_clicked()` called `self.tool_head_filter_combo.setCurrentData(head_key)` which didn't trigger the combo's signal (`currentIndexChanged`). The signal chain:
1. Button clicked → `_on_head_nav_clicked()` 
2. `_on_head_nav_clicked()` → `setCurrentData()` on hidden combo
3. Combo signal → `_on_global_tool_head_changed()`
4. Updates pages

The signal wasn't firing after editors due to some signal connection issue.

### Fix Applied
Simplified `_on_head_nav_clicked()` to directly update pages without going through the combo signal chain:

```python
def _on_head_nav_clicked(self, head_key: str):
    """Handle HEAD1/HEAD2 nav button click — drives the hidden combo for page wiring."""
    for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page]:
        page.set_head_filter_value(head_key, refresh=False)
        page.refresh_list()
    self._update_head_nav_active(head_key)
```

Also removed debug code added during investigation (status bar messages, print statements).

### Files Changed
- `Tools and jaws Library/ui/main_window.py` - simplified `_on_head_nav_clicked()`
- `Tools and jaws Library/ui/home_page_support/topbar_filter_state.py` - reverted debug prints
- `Tools and jaws Library/ui/home_page_support/runtime_actions.py` - reverted debug

### Status: FIXED ✓

---

## Issue 4: Tool Selector Scrollable Areas (Started but Reverted)

### Symptom
User wanted selection areas in the Tool Selector to:
1. Be fixed size from top, grow downward when tools are dropped
2. Anchor to the top (not scroll from center)
3. Show scrollbar only when more tools than fit

### Changes Made
Modified `tool_selector_layout.py`:
- Changed `QSizePolicy.Minimum` → `QSizePolicy.MinimumExpanding`  
- Changed scrollbar policy from `AlwaysOff` → `AsNeeded`
- Changed frame size policy from `Fixed` → `MinimumExpanding`

### Result
User reported areas still appeared scrollable. Issue was complex and needed more investigation. Changes were reverted to restore original behavior.

### Status: REVERTED - No current changes

---

## Summary of Files Changed This Session

| File | Change |
|---|---|
| `Tools and jaws Library/ui/main_window.py` | Added `_safe_set_module_pages()`, simplified `_on_head_nav_clicked()` |
| `Tools and jaws Library/ui/shared/editor_models_tab.py` | Simplified `_ensure_preview_ready()` |
| `shared/ui/stl_preview.py` | Attempted hideEvent fix (reverted) |
| `Tools and jaws Library/ui/home_page_support/topbar_filter_state.py` | Debug additions removed |
| `Tools and jaws Library/ui/home_page_support/runtime_actions.py` | Debug additions removed |
| `Tools and jaws Library/ui/selectors/tool_selector_layout.py` | Started scroll fix (reverted) |

---

## Still Active Issues (From Previous Session)

Based on `docs/session-history-2026-04-24.md` and continued issues:

1. **Tool model changes not persisting** - May still exist, needs retesting
2. **Detached preview showing old models** - May still exist, needs retesting  
3. **Copy Jaw QLineEdit crash** - Was partially fixed, needs verification
4. **Delete Jaw doesn't remove card** - May still exist, needs verification

---

## What Was NOT Changed This Session

The following areas were investigated but not modified due to complexity or risk:

- `shared/ui/stl_preview.py` core lazy initialization
- Tool/Jaw service save paths
- Database persistence layer
- Preview transform caching

---

## Recommended Next Steps

1. Retest all outstanding issues from 2026-04-24 session with fresh Library process restart
2. If HEAD2 still breaks, investigate `_profile_head_keys()` returning stale data
3. Consider dedicated session for selector scrollable area fix with proper UI mockup first

---

## Session Duration

This session covered multiple topics across several hours of investigation, testing, and code changes.

---

## Follow-up (Same Date): Work Editor / Library Handoff Stability

### Context

After the above fixes, a new round of debugging focused on persistent handoff issues between Setup Manager and Tools/Jaws Library:
1. Setup Manager freeze during some Library open/handoff paths
2. Setup Manager freeze after editing Tool/Jaw in Library, returning to Setup Manager, then reopening Library

### Root-Cause Findings

1. **Pending sender transition could remain uncleared** in edge cases, making Setup Manager look frozen.
2. **First open IPC path could still feel blocking** under stale socket states.
3. On failing cycles, Tool Library logs showed:
   - `ipc: request received ... show=True`
   - but missing the next expected `selector_active_request` line,
   indicating `apply_external_request(...)` could throw and interrupt the handoff callback chain.

### Follow-up Fixes Applied

#### A) Setup Manager handoff fallback timer

File:
- `Setup Manager/ui/main_window_support/library_handoff_controller.py`

Changes:
- Added fallback timer that auto-recovers sender transition if completion callback does not arrive.
- Timer clears on normal completion/failure paths.

Env:
- `NTX_LIBRARY_HANDOFF_FALLBACK_TIMEOUT_MS` (default `4500`, `0` disables)

#### B) Fast non-blocking first IPC attempt

Files:
- `Setup Manager/ui/main_window.py`
- `Setup Manager/ui/main_window_support/library_handoff_controller.py`

Changes:
- Extended `_send_to_tool_library(...)` to accept `retries` and `timeout_ms`.
- First open attempt now uses short timeout + single retry, then falls back to async retry.
- Launch path is used only when needed.

Env:
- `NTX_LIBRARY_OPEN_FAST_IPC_TIMEOUT_MS` (default `220`)

#### C) Exception-safe Tool Library IPC show path

File:
- `Tools and jaws Library/main.py`

Changes:
- Wrapped `win.apply_external_request(...)` in `try/except` with `logger.exception(...)`.
- Ensured handoff/show flow continues even if apply step fails.
- Wrapped `_show_main_window()` in guarded `try/except`; on failure still sends transition-complete callback so Setup Manager does not remain frozen.
- Improved socket consume exception logging.

### User Validation Outcome

User-confirmed result after these follow-up fixes:

> "OKay, now it doesn't freeze!"

### Follow-up Files Changed

| File | Change |
|---|---|
| `Setup Manager/ui/main_window_support/library_handoff_controller.py` | Added handoff fallback timer + fast IPC open dispatch |
| `Setup Manager/ui/main_window.py` | Added retry/timeout parameters to `_send_to_tool_library(...)` |
| `Tools and jaws Library/main.py` | Added exception-safe external request/show flow and emergency callback completion |
