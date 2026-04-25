# Session History — 2026-04-24

Branch: `codex/before-shared-styles`  
Last commit at session start: `2f8ae91` — "LIbrary EDITOR flash FIXED once and for all!"

---

## Context

This session continued from a previous context that was compacted. The prior session had investigated several bugs introduced alongside the editor flash fix work (commits up to `2f8ae91`). The flash fix solved the Python instance flicker when opening Tool/Jaw Editor by making the 3D Models tab lazy — it is not built until the user first clicks on that tab.

---

## Latest User Verification Update - April 24, 2026

The user re-tested after the latest code changes and reported that **all problems still reproduce except the color picker issue**.

This means several earlier entries in this file must be treated as **attempted fixes / partial fixes**, not confirmed user-facing resolutions.

### User-confirmed current status

Confirmed improved:
- Model color picker no longer appears to apply color to the wrong model.

Still broken in user runtime:
- Adding or editing 3D models for a Tool ID still does not persist; reopening the Models tab shows the previous model data.
- The detached viewer still shows the old model data after editor save attempts.
- Opening the editor from either Library and then closing it can still freeze the UI when switching to the other Library.
- Opening the editor from Library and visiting the `3D Models` tab still causes focus/background blur loss and the editor/background rebuild sequence.
- The Models tab still appears to apply default rotation to some models.
- Copy Jaw still shows `Internal C++ object (PySide6.QtWidgets.QLineEdit) already deleted.`
- Delete Jaw still does not remove the jaw card row until closing/reopening the Library.

### Latest fixes applied but not user-confirmed

These changes are currently in the working tree and passed automated validation, but the user report says they are insufficient for the real runtime behavior:

- `shared/ui/helpers/editor_helpers.py`
  - Added `prompt_line_text()` so copy prompts capture text before dialog teardown.
  - Added `apply_modal_background_blur()` / `clear_modal_background_blur()` using a static blurred overlay instead of applying `QGraphicsBlurEffect` directly to the Library window.
- `Tools and jaws Library/ui/home_page_support/crud_actions.py`
  - Tool copy prompt now uses `prompt_line_text()`.
  - Tool editor launch now uses the static modal blur overlay.
- `Tools and jaws Library/ui/jaw_page_support/crud_actions.py`
  - Jaw copy prompt now uses `prompt_line_text()`.
  - Jaw editor launch now uses the static modal blur overlay.
- `Tools and jaws Library/ui/fixture_page_support/crud_actions.py`
  - Fixture copy prompt now uses `prompt_line_text()`.
- `Tools and jaws Library/ui/shared/model_table_helpers.py`
  - Color button click handling now resolves the current row dynamically instead of using a captured row index.
  - This is the only fix the user currently reports as successful.
- `Tools and jaws Library/preview/viewer.js`
  - Reverted the recent assembly orientation behavior that made models appear upside down.
  - Kept async mesh index ordering with `new Array(parts.length).fill(null)` and `nextMeshes[index] = mesh`.
- `shared/ui/stl_preview.py`
  - Added explicit `shutdown()` for embedded previews on editor accept/reject.
  - `get_part_transforms()` now returns cached transforms when WebEngine is not ready.
- `Tools and jaws Library/ui/shared/preview_controller.py`
  - Avoids entering the local event loop if a transform snapshot callback already completed synchronously.
- `Tools and jaws Library/ui/jaw_editor_dialog.py`
  - Commits active edits before collecting data.
  - Shuts down embedded preview on accept/reject.
- `Tools and jaws Library/ui/tool_editor_dialog.py`
  - Shuts down embedded preview on accept/reject.
- `Tools and jaws Library/ui/fixture_editor_dialog.py`
  - Commits active edits before collecting data.
  - Shuts down embedded preview on accept/reject.

### Automated validation after these latest changes

Automated validation passed:
- Focused tests: `12 passed`
- Full quality gate: `quality-gate: OK`
- Shared regression tests: `104 passed`
- Setup regression tests: `146 passed`

Important: automated validation does **not** mean these runtime bugs are solved. The user's newest report overrides the previous assumed status.

### Next investigation should start here

Before more fixes, investigate why the real runtime still diverges from automated tests:
- whether the running Library process is using stale code / warm-preloaded state
- whether copy prompts are still coming from another implementation path
- whether Tool model save is failing before `ToolService.save_tool()` or being overwritten after save
- whether Delete Jaw refresh is blocked by model/view selection restoration, deferred refresh state, stale service data, or page instance reuse
- whether editor Models-tab focus/blur loss is caused by WebEngine native-surface activation despite the static overlay attempt
- whether preload/warm-cache keeps old editor or preview instances alive across library switches

---

## Bugs Identified and Fixed This Session

### 1. Copy Jaw crash — `QLineEdit` C++ object already deleted

**Symptom:** Clicking Copy Jaw showed an error dialog:
> Internal C++ object (PySide6.QtWidgets.QLineEdit) already deleted.

**Root cause:** In `prompt_text()` (and `_prompt_text()` for tools), the `QLineEdit` widget was created without an explicit Qt parent. After `dlg.exec()` returns (dialog closed), `editor.text()` was called on the next line — but at that point Qt had already deleted the C++ peer of the `QLineEdit`.

**Files fixed:**
- `Tools and jaws Library/ui/jaw_page_support/crud_actions.py` — `prompt_text()`
- `Tools and jaws Library/ui/home_page_support/crud_actions.py` — `_prompt_text()`

**Fix:** Connected a lambda to `buttons.accepted` to capture `editor.text()` while the dialog is still open, before `dlg.accept()` closes it:

```python
captured: list[str] = []
buttons.accepted.connect(lambda: captured.append(editor.text()))
accepted = dlg.exec() == QDialog.Accepted
return captured[0] if captured else '', accepted
```

---

### 2. 3D model changes not saved when editing a jaw or tool

**Symptom:** After editing a jaw in the Jaw Editor (adding/changing STL model parts) and pressing Save, reopening the jaw showed the old model data. Changes to the 3D Models tab were never persisted to the database.

**Root cause:** In `jaw_editor_dialog.py`, the `accept()` method called `self.get_jaw_data()` for validation but **discarded the return value**:

```python
# BROKEN (HEAD before fix):
def accept(self):
    try:
        self.get_jaw_data()   # return value thrown away
    except ValueError as exc:
        ...
    super().accept()          # dialog closes here — widgets start being destroyed
```

Then `save_from_dialog` called `dlg.get_jaw_data()` (or `dlg.get_accepted_jaw_data()` which didn't exist in HEAD) on the **already-closed dialog**. After `super().accept()`, Qt begins destroying the dialog's C++ widget objects. `get_jaw_data()` calls `_model_table_to_parts()` which calls `self.model_table.rowCount()` — on a dialog whose widgets are already being torn down. This returned empty or stale data silently.

The same problem existed in `tool_editor_dialog.py`.

**Files fixed:**
- `Tools and jaws Library/ui/jaw_editor_dialog.py` — `accept()` and new `get_accepted_jaw_data()`
- `Tools and jaws Library/ui/tool_editor_dialog.py` — `accept()` and new `get_accepted_tool_data()`
- `Tools and jaws Library/ui/jaw_page_support/crud_actions.py` — `save_from_dialog()` uses `get_accepted_jaw_data()`
- `Tools and jaws Library/ui/home_page_support/crud_actions.py` — `save_from_dialog()` uses `get_accepted_tool_data()`

**Fix:** Capture the data at `accept()` time, before `super().accept()` closes the dialog:

```python
# FIXED:
def accept(self):
    try:
        self._accepted_jaw_data = self.get_jaw_data()  # captured while widgets alive
    except ValueError as exc:
        QMessageBox.warning(...)
        return
    super().accept()

def get_accepted_jaw_data(self) -> dict:
    return dict(getattr(self, '_accepted_jaw_data', {}))
```

`save_from_dialog` now calls `dlg.get_accepted_jaw_data()` (safe post-close) via `hasattr` guard.

---

### 3. List not refreshing after ADD / EDIT / DELETE / COPY

**Symptom:** After adding, deleting, or copying a jaw (or tool), the catalog list did not update immediately. Changes only appeared after restarting the app.

**Root cause:** All CRUD operations called `page.refresh_list()`. This method has a deferred-load guard:

```python
def refresh_list(self):
    if not self._initial_load_done and not self.isVisible():
        # defers silently — nothing happens
```

During the blur-effect teardown after the editor closes, the page's visibility check could transiently fail, causing the refresh to be silently skipped.

**Files fixed:**
- `Tools and jaws Library/ui/jaw_page_support/crud_actions.py` — all 3 call sites (`save_from_dialog`, `delete_jaw`, `copy_jaw`)
- `Tools and jaws Library/ui/home_page_support/crud_actions.py` — all 6 call sites (`save_from_dialog`, `delete_tool`, `copy_tool`, `_batch_edit_tools` ×2, `_group_edit_tools`)

**Fix:** Changed all calls from `page.refresh_list()` to `page.refresh_catalog()`, which bypasses the guard and runs unconditionally.

---

### 4. Silent exceptions in save path

**Symptom:** When a save failed for any reason other than a `ValueError` (e.g. SQLite errors, attribute errors on closed widgets), the exception was silently swallowed by Qt's event system with no feedback to the user.

**Root cause:** The original `save_from_dialog` only caught `ValueError`. Any other exception propagated out of the slot and was silently discarded.

**Files fixed:**
- `Tools and jaws Library/ui/jaw_page_support/crud_actions.py` — `save_from_dialog()`, `copy_jaw()`
- `Tools and jaws Library/ui/home_page_support/crud_actions.py` — `save_from_dialog()`

**Fix:** Added broad `except Exception` handlers that show a warning dialog so the user can see the actual error.

---

## Background: The Flash Fix (commit `2f8ae91`) — What Changed and Why

The editor flash fix (PYTHONW3.EXE appearing in taskbar before Jaw/Tool Editor opens) was tracked through 23 diagnostic attempts. The root cause was finally isolated to the 3D Models tab construction: `NTX_EDITOR_DIAG_BYPASS_MODELS_TAB=1` removed the flash entirely.

**The structural fix (Attempt 22):** `build_editor_models_tab()` in `shared/ui/editor_models_tab.py` was rewritten to be lazy. Instead of building the full 3D preview, transform controls, and model action buttons immediately during editor construction, it now:

1. Creates only the `model_table` (needed for data load/save)
2. Installs lightweight placeholder objects (`_BypassedPreview`, stub `QPushButton`s) on the dialog so that any code that references these attributes during init doesn't crash
3. Shows a text placeholder in the tab
4. Defers all real 3D UI (STL preview widget, transform toolbar, action buttons with connections) to the first time the user clicks the "3D Models" tab

This is what introduced bugs 1–4 above: the placeholder objects had no signal connections, and the data-capture-at-accept pattern was broken because the lazy approach exposed the existing flaw in `accept()`.

**Do not change:** The lazy tab materialization logic in `editor_models_tab.py`, the CRUD launch choreography (blur + `dlg.exec()` order), dialog parenting rules, or the `WA_DontShowOnScreen` guard — these are intentional and required for the flash fix to hold.

---

## Files Changed This Session (uncommitted as of session end)

| File | Change |
|---|---|
| `Tools and jaws Library/ui/jaw_editor_dialog.py` | `accept()` captures `_accepted_jaw_data`; added `get_accepted_jaw_data()`; added `_refresh_models_preview()` override; added `preview_plane/rot_x/y/z` fields to `get_jaw_data()` |
| `Tools and jaws Library/ui/tool_editor_dialog.py` | `accept()` captures `_accepted_tool_data`; added `get_accepted_tool_data()` |
| `Tools and jaws Library/ui/jaw_page_support/crud_actions.py` | All `refresh_list()` → `refresh_catalog()`; `save_from_dialog` uses `get_accepted_jaw_data`; `prompt_text` captures text before dialog closes; broad exception handling |
| `Tools and jaws Library/ui/home_page_support/crud_actions.py` | All `refresh_list()` → `refresh_catalog()`; `save_from_dialog` uses `get_accepted_tool_data`; `_prompt_text` captures text before dialog closes; `_batch_edit_tools` uses `get_accepted_tool_data` |
| `Tools and jaws Library/preview/viewer.js` | Assembly geometry baking (FreeCAD Z-up → Three.js Y-up baked into vertices); async mesh index ordering fix (`new Array(parts.length).fill(null)` + `nextMeshes[index] = mesh`) |

---

## 3D Viewer Fixes (viewer.js — from previous session, partially superseded)

**Superseded status:** The geometry-baking orientation change described below was later reverted because the user reported models appearing upside down. The async mesh index ordering fix is still considered valid and was retained. Treat the orientation/baking notes below as historical context, not current ground truth.

### Assembly alignment (parts misaligning relative to each other)

**Root cause:** Group-level `-Math.PI/2` X rotation + `setPartTransforms` setting positions in the rotated local space caused double-transformation on reload. When one part was removed and the assembly reloaded, positions were interpreted in the wrong coordinate frame.

**Fix:** Bake the FreeCAD Z-up → Three.js Y-up coordinate conversion into each geometry's vertices using `geometry.applyMatrix4(new THREE.Matrix4().makeRotationX(-Math.PI / 2))`. The group stays at identity rotation. `setPartTransforms` positions are always in Three.js world space with no ambiguity.

### Color applied to wrong part

**Root cause:** `loadAssembly` used `nextMeshes.push(mesh)` inside async STL load callbacks. Callbacks fire in completion order (not submission order), so the mesh for part 0 (CHUNK-CLOSED, largest file) arrived last and landed at index 2 instead of index 0.

**Fix:** Pre-allocate the array by index: `const nextMeshes = new Array(parts.length).fill(null)` and assign by submission index: `nextMeshes[index] = mesh`.

---

## Git / DB Sync Notes

The runtime database at `.runtime/configs/config_ntx2500_2a0f90/jaws_library_NTX2500.db` is tracked by git (was committed before `.gitignore` added the `.runtime/` rule). To sync jaw data between machines, this DB file must be manually committed and pushed after making changes — it does not sync automatically.
