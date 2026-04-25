# Editor Launch Glitch Fix - Blueprint

## Status: Structural Fix Landed, But New Runtime Regressions Active

As of April 24, 2026:
- The pre-editor flash/glitch when opening Tool Editor / Jaw Editor from Library is resolved in normal use.
- The winning fix was not a focus tweak.
- The confirmed structural fix is: **do not build the real editor 3D Models tab preview/transform surface during dialog construction**.
- New user verification on April 24, 2026 reports that opening the editor and then visiting the `3D models` tab still causes focus/background blur loss and a rebuild-like sequence.
- That newer problem must be treated as active. It may be related to lazy WebEngine activation, preview preload/warm-cache state, or modal background handling, but it is **not yet root-caused**.

The old title of this document is preserved for continuity, but the final diagnosis is broader than "focus".


## Final Diagnosis

The original glitch looked like a focus/taskbar problem, but isolation proved otherwise.

What was actually happening:
- A transient `python3` / preview-like surface could appear **before** the editor itself opened.
- The glitch survived many launch/focus experiments.
- The glitch disappeared only when the full editor Models tab was bypassed.

Confirmed root cause:
- **Editor models-tab construction** was causing the pre-open visual glitch.
- Specifically, preview/transform-related UI creation during editor construction was enough to trigger the bad visual behavior even before the final editor dialog opened.


## Winning Fix

### Permanent Rule
Keep Tool/Jaw editor 3D models content on **first-activation lazy construction**.

That means:
- editor dialog opens normally
- General tab builds immediately
- real 3D preview UI is not materialized during dialog init
- preview/transform/actions for the Models tab are created only when the user actually opens the `3D models` tab for the first time

### Why it worked

Diagnostic proof:
- `NTX_EDITOR_DIAG_BYPASS_MODELS_TAB=1` removed the glitch completely.
- Stub-dialog, no-dialog, button, mouse-filter, and keyboard-path diagnostics did **not** isolate the issue away from editor models-tab construction.

So the correct fix was to make the normal editor path behave more like the successful bypass path.


## What Must Stay True

These are now part of the safe launch contract.

1. Do not restore eager Models-tab preview construction during Tool/Jaw editor init.
2. Do not reactivate WebEngine/preview startup during editor dialog construction.
3. Do not move detached/external preview warmup logic back into editor launch.
4. Keep Tool/Jaw editor launch behavior isolated from detached preview preload behavior.


## Current Architecture Split

### Editor path
- Tool/Jaw editor keeps the lazy Models-tab materialization.
- This is the anti-glitch protection and must remain in place.

### Detached/external preview path
- Library detached preview and Selector detached/external preview use shared preview-runtime warmup and shared host logic.
- This is allowed to preload in the background because it is **not** part of editor construction anymore.


## What Was Tried And Ruled Out

The following were investigated but were not the real final fix:
- `dlg.show() / raise_() / activateWindow()` focus forcing
- deferred focus with `QTimer`
- extra `processEvents()` timing changes
- parent/flag changes for Tool/Jaw editor dialogs
- blur timing guesses
- generic dialog substitution
- button click / mouse filter / keyboard trigger path isolation

Some of these slightly changed visibility, but none solved the root cause robustly.


## Current Related State

After the editor glitch fix:
- Editor open glitch: **fixed**
- Models tab first visit: intentionally lazy
- Models tab first visit from Library: **active regression** - user still sees focus/blur loss and UI rebuild behavior
- Detached preview first-open speed: improved substantially but still not yet "lightning fast"
- Detached preview first-open visual flashing: reduced and then removed
- Shared preference now exists for background preview preload:
  - `enable_preview_preload`
  - exposed in Preferences as a checkbox


## Active April 24 Regression Cluster

The user reports that these problems still reproduce after the latest attempted fixes:

- Tool Editor `3D models` changes do not persist for Tool IDs.
- Detached preview still shows old model data after attempted editor model saves.
- Editor close can freeze the UI when switching between Tool Library and Jaw Library.
- Editor `3D models` tab still causes background blur/focus loss and a rebuild-like visual sequence.
- Models tab still applies unexpected default rotation to some models.
- Copy Jaw still raises `Internal C++ object (PySide6.QtWidgets.QLineEdit) already deleted.`
- Delete Jaw still leaves the deleted jaw card visible until Library restart/reopen.

Only one latest fix is user-confirmed:
- The model color picker no longer applies color to the wrong model.

### Latest attempted fixes and status

Applied but not user-confirmed:
- Static modal blur overlay replaced direct `host.setGraphicsEffect(QGraphicsBlurEffect(...))`.
- Copy prompts now use shared `prompt_line_text()` to capture text before dialog teardown.
- Embedded editor preview now has `shutdown()` called on accept/reject.
- Jaw/Fixture editors commit active edits before collecting save data.
- `StlPreviewWidget.get_part_transforms()` falls back to cached transforms when WebEngine is not ready.
- Viewer assembly mesh ordering is index-stable while the recent upside-down orientation change was reverted.

Automated validation is green, but user runtime still reproduces the failures. The next investigation must start from the assumption that these changes are incomplete.


## Files That Matter

Primary fix area:
- `Tools and jaws Library/ui/shared/editor_models_tab.py`

Supporting preview behavior:
- `shared/ui/stl_preview.py`

Shared detached/external preview hosting:
- `Tools and jaws Library/ui/selectors/external_preview_host.py`
- `shared/ui/helpers/preview_runtime.py`

Background preload control:
- `Tools and jaws Library/main.py`
- `shared/services/ui_preferences_service.py`
- `Setup Manager/ui/preferences_dialog.py`
- `Tools and jaws Library/ui/preferences_dialog.py`


## Future Rule For Engineers

If someone sees the editor glitch again:
- first suspect a regression in **eager Models-tab build**
- do **not** start from generic focus tweaks
- verify that the editor path still avoids building the real preview/transform surface during dialog construction
- also verify whether the failure occurs only when the lazy Models tab materializes WebEngine for the first time
- check whether background preview preload or warm-cached Library state is holding stale preview/editor instances


## Regression Checklist

- Tool Editor opens with no pre-open flash.
- Jaw Editor opens with no pre-open flash.
- Visiting `3D models` still constructs and shows the preview correctly.
- Visiting `3D models` from a Library-opened editor must preserve modal focus and background blur.
- Saving model rows from Tool Editor must persist to the database and detached preview.
- Copy Jaw must not access deleted Qt widgets.
- Delete Jaw must remove the card row immediately after delete.
- Closing an editor must not freeze later Library switching.
- Detached/external preview can preload independently without affecting editor opening.
- Preferences checkbox for preview preload correctly enables/disables background preview warmup.
