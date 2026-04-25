# Editor Launch Glitch Investigation - Memory

## Executive Summary

Current state as of April 24, 2026:
- The old editor-open flash/glitch is fixed.
- The root cause was isolated to **editor Models-tab construction**, not generic focus loss.
- Detached/external 3D preview behavior was then separated from editor launch and stabilized.
- Remaining work is no longer only "detached preview speed". A newer runtime regression cluster is active around editor Models-tab activation, model save persistence, editor close/library switching, Copy Jaw, and Delete Jaw.


## Final Outcome

### Resolved
- Tool Editor open from Library: no pre-open flash in normal path
- Jaw Editor open from Library: no pre-open flash in normal path

### Not the same issue anymore
- Detached preview first-open speed can still feel slower than desired
- That is a preview warmup / host / first-visible-load problem, not the old editor glitch

### Active after latest user verification
- Opening a Library editor and visiting `3D models` still loses focus/background blur and produces a rebuild-like visual sequence.
- Tool Editor model changes still do not persist for Tool IDs.
- Detached preview still shows old model data after attempted model saves.
- Editor close can still freeze the UI when switching to the other Library.
- Models tab can still apply unexpected default rotation.
- Copy Jaw still raises `Internal C++ object (PySide6.QtWidgets.QLineEdit) already deleted.`
- Delete Jaw still leaves the jaw card visible until Library close/reopen.
- Color picker row targeting appears fixed.


## The Key Discovery

The strongest signal in the whole investigation was this:

- User ran `NTX_EDITOR_DIAG_BYPASS_MODELS_TAB=1`
- The glitch disappeared

That result overruled earlier focus-based theories.

Meaning:
- the root cause was inside the real editor Models-tab construction path
- not merely CRUD launch
- not merely button click behavior
- not merely generic dialog creation


## Important User Clue To Preserve

On April 23, 2026, user reported a crucial clue:
- in one broken state the actual editor did not open
- instead, only the 3D Preview transform toolbar/dialog appeared
- it appeared at **exactly the same screen position** as the earlier `python3` / Python-instance flash

This was a major indicator that preview/transform surface construction was escaping the intended editor first-frame sequence.


## Attempt History

### Early phase: focus-based fixes

#### Attempt 1: Focus fix between dialog positioning and `exec()`
- Added `dlg.show()`, `dlg.raise_()`, `dlg.activateWindow()`, foreground forcing
- Result: not enough

#### Attempt 2: Deferred focus with `QTimer`
- Result: not enough

#### Attempt 3: `processEvents()` around blur / launch timing
- Result: small visual changes only, not a robust fix

#### Attempt 4: `prime_dialog()` style prebuild
- Result: regressed / broke dialog path in tests

#### Attempt 5: parent / window-flag experiments
- Result: bad regressions, including broken editor open


### Middle phase: preview/WebEngine suspicion

#### Attempt 6: Open on General tab
- Not enough by itself

#### Attempt 7: Lazy STL preview in editor models tab
- First pass was incomplete and broke transform assumptions

#### Attempt 8: Deep rewrite inside `StlPreviewWidget`
- Too invasive, preview broke, not the right step at that moment

#### Attempt 9: Reorder blur/process/dialog creation
- Slight improvement only

#### Attempt 10: Deferred transform signal connections
- Still showed flash

#### Attempt 11: Stage 1 instrumentation
- Added detailed launch tracing behind `NTX_EDITOR_GLITCH_DEBUG`
- Useful for proving timing and narrowing suspects

#### Attempt 12: Lazy WebEngine surface creation
- Delayed actual WebEngine view creation until later
- Helped, but not enough

#### Attempt 13: Models-tab-gated WebEngine activation
- Stronger reduction, but still not a full fix

#### Attempt 14: Disable automatic startup preview warmup
- Removed one unrelated source of background preview startup overlap

#### Attempt 15: Lazy QtWebEngine module import
- Prevented module-import-time WebEngine side effects

#### Attempt 16: Suppress accidental early editor surface during construction
- Added construction-time visibility guard


### Isolation phase: decisive diagnostics

#### Attempt 17: Diagnostic bypass switches
- Added:
  - `NTX_EDITOR_DIAG_BYPASS_MODELS_TAB`
  - `NTX_EDITOR_DIAG_BYPASS_BLUR`
  - `NTX_EDITOR_DIAG_BYPASS_HOST_STYLE`

#### Attempt 18: Stub editor diagnostic
- Opened tiny generic dialog instead of real editor
- Flash still existed in some runs, so more isolation was needed

#### Attempt 19: No-dialog diagnostic
- Returned before dialog creation entirely

#### Attempt 20: No-op buttons
- Bypassed CRUD handlers completely

#### Attempt 21: Disable global app mouse filter
- Bypassed Library-wide click preprocessing

#### Attempt 22: Keyboard-only action trigger
- Removed mouse button path from the test

These diagnostics were valuable because they prevented more random guessing.
But the **real breakthrough** still came when the user finally tested Models-tab bypass explicitly.


### Winning structural fix

#### Attempt 23: First-activation lazy Models-tab construction
- Normal editor path was rewritten to behave more like the successful bypass mode
- During editor construction:
  - keep model table / lightweight shell only
  - do not materialize real preview surface
  - do not build full transform/action preview machinery yet
- On first actual visit to `3D models` tab:
  - create real preview UI
  - build transform controls
  - wire signals
  - activate preview path

Result:
- user confirmed the editor flash was gone


## Post-Fix Recovery Work

Once the editor glitch was fixed, work shifted to restoring detached/external preview performance without reintroducing the editor bug.

### Attempt 24: Shared preview runtime recovery
- Restored safe preview-runtime warmup for detached/external preview only
- Kept editor lazy Models-tab fix intact
- Unified Library + Selector detached preview hosting on one shared host

### Attempt 25: Stable visible rendering in shared preview widget
- Detached/external visible previews stopped reacting so aggressively to focus churn
- Reduced visible flicker while preview remained open

### Attempt 26: Stronger offscreen preview prewarm
- Runtime warmup was adjusted so the WebEngine/native surface actually had time to initialize before being returned to the pool

### Attempt 27: Immediate preview dialog open with hidden first visual load
- Preview window opens immediately
- Real preview content stays hidden until first model load is ready
- This removed the model flashing that happened during preview open

Result:
- user confirmed: model flashing on preview open is gone
- but preview first-open speed still feels a bit slower than desired


## Attempt 28: Runtime Regression Cluster Fix Attempt

This pass applied several fixes after the user reported model-save, wrong-color, rotation, freeze, Copy Jaw, and Delete Jaw problems.

Applied changes:
- replaced direct Library-window blur effect with a static modal background blur overlay
- introduced shared `prompt_line_text()` for copy prompts
- made model color buttons resolve their current row dynamically
- kept async assembly mesh ordering stable in `viewer.js`
- reverted the recent upside-down orientation behavior
- added embedded preview shutdown on editor accept/reject
- made transform snapshot reads fall back to cached state when WebEngine is not ready
- committed active Jaw/Fixture edits before data collection

Automated result:
- focused tests passed
- full quality gate passed

User result:
- color picker issue appears fixed
- all other reported issues still reproduce

Conclusion:
- Attempt 28 is only a partial fix.
- The remaining failures likely require runtime tracing of actual call paths, warm/preloaded objects, service/database writes, and module-switch/event-loop state.
- Do not rely on automated tests alone for this cluster; the user runtime is the authority.


## Current Detached Preview State

What is good now:
- Selector preview is reported as very good
- Library preview opens in the correct place
- Model flashing on preview open is gone

What still needs improvement:
- Library detached preview first-open speed should feel more instant
- current behavior can still feel stepwise:
  - window opens
  - background appears
  - model appears

This is now the live problem area.


## Preferences / Control Added

Shared UI preference added:
- `enable_preview_preload`

User-facing control added:
- Preferences checkbox:
  - `Preload 3D preview in background for faster first open`

Behavior:
- enabled: Library preview runtime may warm in the background
- disabled: no background preview warmup should run

This setting affects detached/external preview warmup behavior, not the protected lazy editor Models-tab fix.


## Files Most Relevant Now

Editor anti-glitch protection:
- `Tools and jaws Library/ui/shared/editor_models_tab.py`

Editor model save / table state:
- `Tools and jaws Library/ui/tool_editor_dialog.py`
- `Tools and jaws Library/ui/jaw_editor_dialog.py`
- `Tools and jaws Library/ui/shared/model_table_helpers.py`
- `Tools and jaws Library/ui/shared/preview_controller.py`
- `Tools and jaws Library/ui/tool_editor_support/payload_codec.py`

Detached/external preview runtime and host:
- `shared/ui/stl_preview.py`
- `shared/ui/helpers/preview_runtime.py`
- `Tools and jaws Library/ui/selectors/external_preview_host.py`
- `Tools and jaws Library/ui/home_page_support/detached_preview.py`
- `Tools and jaws Library/ui/jaw_page_support/detached_preview.py`
- `Tools and jaws Library/ui/fixture_page_support/detached_preview.py`
- `Tools and jaws Library/ui/selectors/detached_preview.py`

Background warmup / preference control:
- `Tools and jaws Library/main.py`
- `shared/services/ui_preferences_service.py`
- `Setup Manager/ui/preferences_dialog.py`
- `Tools and jaws Library/ui/preferences_dialog.py`

Library CRUD / refresh paths:
- `Tools and jaws Library/ui/home_page_support/crud_actions.py`
- `Tools and jaws Library/ui/jaw_page_support/crud_actions.py`
- `Tools and jaws Library/ui/jaw_page.py`
- `Tools and jaws Library/services/jaw_service.py`
- `Tools and jaws Library/services/tool_service.py`


## Practical Guidance For Future Work

If the editor-open flash returns:
- first verify no one restored eager Models-tab build
- do not start with generic focus guesses

If detached preview still feels too slow:
- investigate first-visible detached preview load path
- measure:
  - runtime already warm vs not warm
  - dialog open vs first model-ready timing
  - host chrome paint vs actual web/canvas paint

For the active regression cluster:
- first verify whether the tested Library process was restarted or is using a warm/preloaded instance
- instrument actual Copy Jaw call path to prove which prompt implementation is being used
- instrument Tool model save from editor table -> payload codec -> service -> database -> reload
- instrument Delete Jaw from service delete -> page refresh -> model row count -> selection restore
- instrument editor close -> embedded preview shutdown -> module switch handler
- avoid more focus timers until WebEngine activation and modal overlay/focus transitions are logged


## Current Status Label

Status:
- **Editor launch glitch: resolved**
- **Editor Models-tab runtime focus/blur issue: active**
- **Tool model save persistence: active**
- **Copy Jaw / Delete Jaw runtime issues: active**
- **Editor close / library switch freeze: active**
- **Color picker row targeting: appears fixed**
- **Detached preview first-open speed: improved, but still open for optimization**
