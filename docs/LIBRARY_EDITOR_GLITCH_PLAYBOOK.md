# Library Editor / Preview Glitch Playbook

## Purpose

This playbook records the safe investigation path and current ground truth for:
- the **resolved** Tool/Jaw editor pre-open glitch
- the **active** editor Models-tab / save / Library refresh regression cluster
- the detached preview first-open performance work

It exists to prevent future work from mixing those two problems together.


## Current State

As of April 24, 2026:

### Resolved
- Tool Editor opens without the old pre-open flash
- Jaw Editor opens without the old pre-open flash

### Improved but still active area
- Library detached 3D preview is much better than before
- preview open-time model flashing is gone
- remaining issue: first-open speed should still feel faster / more instant

### Active regression cluster after latest user verification
- Opening a Library editor and visiting `3D models` still causes focus/background blur loss and a rebuild-like visual sequence.
- Tool Editor model-row changes still do not persist for Tool IDs.
- Detached preview still shows old model data after attempted model saves.
- Closing an editor can still freeze the UI when switching between Tool and Jaw libraries.
- Models tab can still show unexpected default rotations.
- Copy Jaw still raises `Internal C++ object (PySide6.QtWidgets.QLineEdit) already deleted.`
- Delete Jaw still leaves the jaw card visible until the Library is closed/reopened.
- Color picker row targeting appears fixed according to the latest user report.


## The Most Important Rule

Do not "fix" detached preview speed by undoing the editor Models-tab lazy build.

That lazy Models-tab construction is the confirmed structural fix for the old editor glitch.

Treat these as separate systems:
- **Editor Models tab**: protected anti-glitch path
- **Editor Models-tab runtime behavior**: active regression area
- **Editor save/CRUD refresh behavior**: active regression area
- **Detached / external preview**: warmup and first-open speed path


## Confirmed Root Cause Of The Old Editor Glitch

The old editor-open glitch was isolated to **real Models-tab construction during editor init**.

Strongest proof:
- `NTX_EDITOR_DIAG_BYPASS_MODELS_TAB=1` removed the glitch

Therefore:
- the root cause was not just generic focus loss
- not just button click behavior
- not just generic dialog creation


## Current Safe Architecture

### 1. Editor open path
- Tool/Jaw editor opens with lightweight content first
- real `3D models` preview content is built only on first actual visit to that tab

Required invariant:
- no eager preview/transform surface creation during Tool/Jaw editor construction

### 2. Detached / external preview path
- Library detached preview and Selector detached/external preview share a common host path
- preview runtime can be warmed in the background
- this preload is independent from editor launch

### 3. Shared preference
- background preview preload is controlled by shared preference:
  - `enable_preview_preload`
- exposed via Preferences checkbox:
  - `Preload 3D preview in background for faster first open`


## Current Files To Protect

Editor anti-glitch path:
- `Tools and jaws Library/ui/shared/editor_models_tab.py`

Shared preview widget:
- `shared/ui/stl_preview.py`

Detached/external preview host:
- `Tools and jaws Library/ui/selectors/external_preview_host.py`

Shared preview runtime:
- `shared/ui/helpers/preview_runtime.py`

Library startup / warmup:
- `Tools and jaws Library/main.py`

Shared preload preference:
- `shared/services/ui_preferences_service.py`
- `Setup Manager/ui/preferences_dialog.py`
- `Tools and jaws Library/ui/preferences_dialog.py`


## What Is Safe To Change Now

Safe areas for current work:
- editor Models-tab lazy materialization internals, as long as eager preview construction is not restored
- save-data capture and service refresh paths
- stale warm-cache / preload cleanup paths
- copy/delete prompt and CRUD paths
- detached preview runtime warmup behavior
- detached preview first-open timing
- detached preview content reveal choreography
- shared preload preference behavior
- background warmup scheduling

Unsafe areas unless explicitly re-investigating the old bug:
- restoring eager editor Models-tab preview build
- moving detached preview preload logic back into editor dialog construction
- treating the old glitch as "just focus" and reverting to only focus hacks


## Latest Applied Fixes And Current Status

Applied in the working tree:
- shared `prompt_line_text()` for Tool/Jaw/Fixture copy prompts
- static modal blur overlay instead of direct host `QGraphicsBlurEffect`
- dynamic model color-button row lookup
- indexed async assembly mesh storage in `viewer.js`
- reverted recent upside-down assembly orientation behavior
- embedded preview `shutdown()` on editor accept/reject
- transform snapshot fallback when WebEngine is not ready
- active-edit commits before Jaw/Fixture data collection

Automated validation after these changes:
- focused tests passed
- full quality gate passed

User runtime status:
- color picker issue appears fixed
- all other listed issues still reproduce

Conclusion:
- Do not mark copy/save/delete/focus/freeze issues resolved yet.
- The next pass needs deeper runtime tracing, especially around preload/warm-cache state and actual service/database writes.


## Diagnostic History Worth Preserving

These diagnostics were important because they prevented random guessing:

- `NTX_EDITOR_GLITCH_DEBUG`
- `NTX_EDITOR_DIAG_BYPASS_MODELS_TAB`
- `NTX_EDITOR_DIAG_BYPASS_BLUR`
- `NTX_EDITOR_DIAG_BYPASS_HOST_STYLE`
- `NTX_EDITOR_DIAG_STUB_EDITOR`
- `NTX_EDITOR_DIAG_NO_DIALOG`
- `NTX_EDITOR_DIAG_NOOP_BUTTONS`
- `NTX_EDITOR_DIAG_DISABLE_APP_MOUSE_FILTER`
- `NTX_EDITOR_DIAG_KEYBOARD_ONLY_ACTIONS`
- native window probe logging

Most of these are historical investigation tools now, but they remain useful if the old editor glitch ever returns.


## What Has Been Confirmed In The Detached Preview Phase

### Good
- Selector preview feels strong / robust
- Library preview now opens in the correct place
- preview content no longer flashes on first open

### Still not ideal
- first Library detached preview open still feels slower than desired
- user experience can still feel stepwise:
  - window appears
  - surface/background appears
  - model appears


## Working Theory For Remaining Preview Speed Gap

The remaining issue is no longer a bad flash.
It is likely one or more of:

1. preview runtime warmup is not fully completing the same way in the real Library path as in the best Selector path
2. the detached preview window is becoming visible before the first usable rendered frame is truly ready
3. there is still extra first-visible work happening in the host/content reveal sequence even when runtime is warm


## Recommended Next Investigation Path

Use this order.

### Stage 0: Confirm running code and stale runtime state
Before changing behavior again:
- verify whether the Library process being tested was restarted after code changes
- disable or instrument preview preload / selector warm-cache / catalog-page preload
- log the concrete prompt implementation used by Copy Jaw
- log editor object IDs and preview object IDs across open/close/library-switch cycles

Goal:
- rule out stale preloaded instances and stale warm-cache widgets before adding more fixes

### Stage 1: Save path truth table
For Tool Editor model saves:
- log `_model_table_to_parts()` at accept time
- log payload passed to `ToolService.save_tool()`
- log database row immediately after save
- log data reloaded into the editor and detached preview

Goal:
- identify whether data is lost before save, rejected by service normalization, overwritten after save, or reloaded from a stale page/service/database handle

### Stage 2: Jaw CRUD refresh path
For Copy Jaw and Delete Jaw:
- verify which prompt function is actually called
- log selected jaw ID, service operation result, model row count before/after refresh
- inspect whether `_restore_selection()` or deferred initial-load state reselects stale data

Goal:
- distinguish widget-lifetime bug from wrong call path or stale service/page state

### Stage 3: Editor close / library switch freeze
Trace:
- embedded preview shutdown
- WebEngine object lifetime
- app focus/window signals
- pending timers from preview sync and catalog refresh
- module switch handler entry/exit

Goal:
- find the live object/timer/event-loop path that blocks switching after editor close

### Stage A: Measure true warm vs cold first-open
Record for Library detached preview:
- runtime already ready or not
- timestamp from preview-open trigger to dialog show
- timestamp from dialog show to first model-ready
- timestamp from model-ready to visible content reveal

Goal:
- prove whether the remaining latency is mostly before dialog show, before model-ready, or after model-ready

### Stage B: Compare Library and Selector host paths directly
Diff the real first-open sequence between:
- Library detached preview
- Selector detached/external preview

Focus on:
- payload preparation cost
- claim/reparent timing
- whether the same prewarmed widget state is actually being reused
- whether Library is doing extra model/setup churn on first open

### Stage C: Only optimize detached preview path
Possible safe optimization targets:
- stronger background warmup
- host dialog creation reuse
- earlier offscreen model bootstrap
- reducing first-open chrome/content staging steps

Do not touch the editor Models-tab lazy protection during this work.


## Regression Matrix

Any future change in this area must preserve all of the following:

1. Tool Editor still opens with no pre-open flash
2. Jaw Editor still opens with no pre-open flash
3. First visit to editor `3D models` tab still works
4. Selector detached preview still feels good
5. Library detached preview still opens in correct place
6. Background preload checkbox still controls preview warmup behavior


## Short Timeline

- Early theory: focus/exec/taskbar issue
- Isolation phase: many launch-path diagnostics added
- Breakthrough: user confirmed Models-tab bypass removes glitch
- Structural fix: first-activation lazy Models-tab materialization
- Post-fix work: restore detached/external preview warmup safely
- Shared host/runtime recovery landed
- Preview open-time model flashing removed
- Current work: make Library detached preview first open feel more instant


## Summary For Future Engineers

If you are looking at this later:
- the editor glitch is considered solved
- the solution is architectural, not cosmetic
- do not undo the editor Models-tab lazy build
- current optimization target is detached preview first-open speed, not editor launch stability
