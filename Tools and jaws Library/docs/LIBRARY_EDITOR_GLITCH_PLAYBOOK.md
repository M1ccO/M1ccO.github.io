# Library Editor Open Glitch Playbook

## Purpose
This document is the source of truth for the remaining "small glitch" that can happen when opening Tool Editor or Jaw Editor from the Library UI.

Goals:
- Preserve current behavior that the user prefers.
- Avoid reintroducing known white-screen regressions.
- Give a safe, repeatable path for future investigation and fixes.

Scope:
- `Tools and jaws Library` editor launch flow (Tool/Jaw CRUD open actions).
- Setup Manager <-> Library handoff/focus race interactions that can visually affect editor open.
- 3D preview and first-paint timing interactions during editor construction.

Out of scope:
- Selector animation timing/choreography tuning.
- Data model/schema changes.


## User-Visible Symptom
When opening Tool Editor or Jaw Editor from Library:
- Sometimes there is a brief visual glitch before the editor appears.
- In problematic states, the main window can appear to lose focus for a moment.
- The user can see a desktop/taskbar flicker sequence before normal editor opening.


## Confirmed Findings (Validated)
These findings are confirmed by direct code inspection and regression testing in this repo.

1. Stale transition-complete callbacks were a real cause of random hide/focus drops.
- IPC previously handled `hide_for_library_handoff` and `complete_sender_transition` via the same completion call.
- `complete_sender_transition()` hides sender even when there is no pending transition state.
- This enabled stale completion callbacks to hide Library unexpectedly.
- Guard was added to process completion only when a sender transition is actually pending.

2. Dialog parenting change in Library CRUD path can reintroduce white-screen behavior.
- Setting Tool/Jaw editor dialog parent to host window in CRUD open path regressed into white-screen behavior.
- Reverting those parenting changes restored preferred behavior.

3. Current user-preferred launch path is:
- Keep existing manual blur + `dlg.exec()` path in:
  - `Tools and jaws Library/ui/home_page_support/crud_actions.py`
  - `Tools and jaws Library/ui/jaw_page_support/crud_actions.py`
- Avoid re-parenting those dialogs during launch.

4. Remaining glitch is separate from the fixed stale-callback white flash.
- After stale callback guarding, one class of white flash was eliminated.
- A smaller launch glitch still exists and likely comes from launch/paint timing (not the old stale callback path).


## Critical Files
Library-side handoff and IPC show/hide:
- `Tools and jaws Library/main.py`
- `Tools and jaws Library/ui/main_window_support/setup_handoff.py`
- `shared/ui/transition_shell.py`

Setup-side handoff and IPC show/hide:
- `Setup Manager/main.py`
- `Setup Manager/ui/main_window_support/library_handoff_controller.py`
- `shared/ui/transition_shell.py`

Library editor launch paths:
- `Tools and jaws Library/ui/home_page_support/crud_actions.py`
- `Tools and jaws Library/ui/jaw_page_support/crud_actions.py`

Editor internals and first-paint heavy surfaces:
- `Tools and jaws Library/ui/tool_editor_dialog.py`
- `Tools and jaws Library/ui/jaw_editor_dialog.py`
- `Tools and jaws Library/ui/shared/editor_models_tab.py`
- `shared/ui/stl_preview.py`


## Do Not Change (Guardrails)
Until the remaining glitch is resolved, treat these as hard constraints.

1. Do not re-parent Tool/Jaw dialogs in Library CRUD open flow.
- Do not change `AddEditToolDialog(...)` / `AddEditJawDialog(...)` constructor use to `parent=host` in CRUD add/edit open functions.

2. Do not collapse `hide_for_library_handoff` and `complete_sender_transition` into the same unconditional behavior.
- Completion must stay state-aware (pending transition required).

3. Do not remove current stale completion guards without replacement.
- If tokenized transitions are added later, migrate guards, do not remove safety.

4. Do not redesign editor data/save logic while investigating visual glitch.
- Keep investigation isolated to focus/paint/transition timing.


## Known Good vs Known Bad Change Patterns

Known good:
- Keep Library CRUD editor launch path exactly as currently implemented (manual host blur + `dlg.exec()`, no explicit owner-parent).
- Keep stale-callback guards in both app IPC handlers.

Known bad:
- Forcing owner-parent in Library CRUD editor add/edit open path reintroduces white-screen regression.
- Treating any incoming `complete_sender_transition` as valid can hide sender at wrong time.


## Investigation Strategy For Remaining Small Glitch
Use this staged plan. Do not skip stages.

### Stage 1: Capture deterministic repro timing (no behavior change)
Add temporary debug logs around:
- Editor launch begin/end in both CRUD paths.
- Active window identity immediately before `dlg.exec()` and immediately after.
- Host visibility/opacity/effect state.
- Any `complete_sender_transition` or `hide_for_library_handoff` IPC received during editor open window.
- First paint milestones from editor dialog (`showEvent`, first `Paint`, and when `StlPreviewWidget` reports readiness).

What to record each sample:
- Timestamp ms.
- `activeWindow` class/title.
- Library main window `isVisible`, `isActiveWindow`, `windowOpacity`.
- Dialog `isVisible` changes.
- Pending sender transition state.

Pass/fail signal:
- If focus change/flicker occurs without any transition callback in interval, issue is local editor launch paint path.
- If transition callback overlaps glitch window, issue is still cross-window handoff race.


### Stage 2: Isolate heavy first-paint contributors (minimal toggles, temporary)
Introduce temporary runtime flags (default off) to measure:
- "Skip 3D preview widget construction on first dialog frame" experiment.
- "Build models tab lazily after dialog shown" experiment.
- "Delay `QGraphicsBlurEffect` application until after dialog is visible" experiment.

Important:
- Only one toggle active per run.
- Never combine multiple experiments in one sample run.
- Keep changes behind explicit debug flag so production behavior is unchanged during measurement.

Target:
- Identify which single factor reduces glitch frequency/visibility most.


### Stage 3: Implement minimal permanent fix
Choose one small fix based on Stage 2 data:
- If 3D preview cold-start dominates: lazy initialize `StlPreviewWidget` after dialog first paint.
- If blur timing dominates: keep blur but apply/release at safer point in event loop.
- If focus handoff still contributes: add transition tokenization so completion messages are matched to the exact handoff instance.

Do not implement broad refactors in this phase.


## Candidate Root Causes (Ranked)
Ranked from most likely to least likely based on current evidence.

1. First-paint cost of heavy editor content (especially 3D preview surface) causing a brief visual gap.
2. Blur effect + modal loop timing interaction during host/dialog focus transfer.
3. Residual asynchronous transition callback timing edge case (less likely after stale-callback guards, but still possible without transition token matching).


## Regression Test Matrix (Must Pass)
Run all tests after any attempted fix.

1. Library Tool Editor open:
- Repeated rapid open/close from Tool Library list.
- No white screen.
- Main Library window remains stable behind modal.

2. Library Jaw Editor open:
- Repeated rapid open/close from Jaw Library list.
- No white screen.
- Main Library window remains stable behind modal.

3. Setup Manager -> Library handoff:
- Open Library from Setup Manager.
- No hide/focus glitch from stale callbacks.

4. Library -> Setup Manager handoff:
- Return to Setup Manager.
- Transition remains smooth and deterministic.

5. Selector lifecycle sanity:
- Open selector, cancel/done, close via window controls.
- No regression in selector collapse behavior.
- No white screen in subsequent Work Editor open.


## Implementation Safety Checklist
Before commit:
- Ensure no changes to CRUD dialog parenting in Library add/edit open path.
- Ensure stale completion guard still exists in both `main.py` IPC handlers.
- Ensure no accidental behavior changes in save/cancel semantics.

After commit:
- Run focused manual repro loops (at least 20 opens Tool + 20 opens Jaw).
- Capture logs for any remaining glitch sample and compare timestamps.


## Suggested Next Engineering Task
Implement Stage 1 instrumentation only (no behavior changes), gather 10+ glitch samples, then choose one minimal Stage 3 fix based on measured timing.


## Instrumentation Added
Stage 1 instrumentation is now available behind `NTX_EDITOR_GLITCH_DEBUG`.

How to capture a sample:
- Start the relevant app with `NTX_EDITOR_GLITCH_DEBUG=1`.
- Reproduce Tool Editor and Jaw Editor opens.
- Inspect `%TEMP%\ntx_editor_glitch.log`, or set `NTX_EDITOR_GLITCH_LOG` to choose a specific log file.

Events captured:
- CRUD launch begin, blur application, dialog construction, positioning, and `exec()` result.
- Tool/Jaw editor `showEvent` and first paint.
- Models tab build, transform toolbar construction, deferred transform signal connection, and 3D preview creation.
- `StlPreviewWidget` WebEngine creation, HTML load start/end, `showEvent`, and load-finished readiness.
- Library/Setup Manager `hide_for_library_handoff` and `complete_sender_transition` IPC receipt.

2026-04-23 clue to preserve:
- The transform toolbar/dialog once appeared alone at the same screen position as the PYTHONW3/Python flash when the editor failed to open, increasing confidence that the remaining glitch is tied to preview/transform first-paint timing rather than ordinary dialog focus alone.

## Current Fix Under Test
`StlPreviewWidget` now supports disabling automatic native `QWebEngineView` creation/loading. Tool/Jaw editor model tabs use that mode, and the shared models tab builder activates the preview only when the 3D Models tab becomes the current tab. This keeps ordinary editor opening on the General tab from spawning Chromium/WebEngine at all. The expected tradeoff is that the 3D preview initializes on first visit to the 3D Models tab.

User-confirmed isolation on April 23, 2026:
- `NTX_EDITOR_DIAG_BYPASS_MODELS_TAB=1` removes the glitch.
- That makes the models-tab construction path the primary root-cause target again.
- The normal builder now mirrors that evidence more closely: editor construction keeps only the model table and placeholder widgets, and the real preview/transform/actions UI is materialized only on the first actual visit to the `3D models` tab.
- Detached/external preview recovery is now separated from editor launch:
  - preview-runtime warmup is restored only for the shared detached/external preview pool
  - Libraries and Selectors now use the same preview host implementation for detached/external 3D windows
  - visible detached/external previews favor stable rendering over focus-driven pause/resume churn

Automatic Library startup preview-runtime warmup is also disabled. The old startup timer could create an offscreen preview 250 ms after launch, causing Chromium/D3D surface creation to overlap a normal editor open. Explicit `warm_preview_runtime` IPC remains available for flows that intentionally request it.

QtWebEngine imports are lazy now as well: `shared/ui/stl_preview.py` no longer imports `QWebEnginePage`/`QWebEngineView` at module import time. The WebEngine classes load only when a preview is explicitly activated.

Tool/Jaw editor construction is guarded with `Qt.WA_DontShowOnScreen` until heavy initialization completes, and the real editor title/size/modal metadata is assigned immediately after `QDialog.__init__()`. This suppresses any accidental early top-level surface before `exec()` opens the completed editor.

## Diagnostic Bypass Tests
Use these switches one at a time. Do not combine them unless a single-switch result already identifies a suspect.

1. `NTX_EDITOR_DIAG_BYPASS_MODELS_TAB=1`
- Replaces the 3D Models tab with a lightweight placeholder/table.
- Expected isolation: if the flash disappears, the root cause is in models-tab construction, preview, transform controls, or model-table support.

2. `NTX_EDITOR_DIAG_BYPASS_BLUR=1`
- Skips the host `QGraphicsBlurEffect` during editor open.
- Expected isolation: if the flash disappears, the root cause is blur/effect compositor timing.

3. `NTX_EDITOR_DIAG_BYPASS_HOST_STYLE=1`
- Skips host palette/font/stylesheet adoption in Tool/Jaw editor constructors.
- Expected isolation: if the flash disappears, the root cause is style/polish/palette propagation during construction.

4. `NTX_EDITOR_DIAG_STUB_EDITOR=1`
- Opens a tiny generic diagnostic dialog instead of importing/constructing the real Tool/Jaw editor class.
- Expected isolation: if the flash disappears, the root cause is inside real editor import/construction. If it remains, investigate CRUD launch choreography, generic `QDialog` top-level creation, blur/activation, detached preview close, or process/window-manager behavior.

5. `NTX_EDITOR_DIAG_NO_DIALOG=1`
- Returns from the Tool/Jaw CRUD handler before any editor dialog is created.
- Expected isolation: if the flash still appears, the root cause is earlier than dialog creation and likely outside the editor stack.

6. `NTX_EDITOR_DIAG_NOOP_BUTTONS=1`
- Rewires the Tool/Jaw bottom-bar action buttons so click only emits a debug log and does not call add/edit/delete/copy handlers.
- Expected isolation: if the flash still appears, the root cause is outside CRUD launch entirely and likely tied to click/focus/window-manager behavior or another non-CRUD side effect.

7. `NTX_EDITOR_DIAG_DISABLE_APP_MOUSE_FILTER=1`
- Disables the Library main window's `QApplication`-level event filter for mouse handling.
- Expected isolation: if the flash disappears, the culprit is in global pre-handler click processing such as dropdown focus clearing or background-selection clearing, not in the button slot or editor stack.

8. `NTX_EDITOR_DIAG_KEYBOARD_ONLY_ACTIONS=1`
- Hides/disables the bottom-bar action buttons and installs keyboard shortcuts instead.
- `Ctrl+Alt+E` triggers Edit and `Ctrl+Alt+N` triggers Add.
- Expected isolation: if the flash disappears when the action is triggered from keyboard instead of a physical button click, the remaining culprit is strongly tied to the native button-click/focus path rather than CRUD/editor launch.

Recommended sequence:
- Restart the app between diagnostic runs.
- Start with `NTX_EDITOR_DIAG_STUB_EDITOR=1` because it gives the strongest split.
- Test Tool Editor first with 10-20 opens, then Jaw Editor if Tool results are ambiguous.
- Keep `NTX_EDITOR_GLITCH_DEBUG=1` enabled during diagnostic runs if timing logs are needed.


## Change Log
- 2026-04-23: Initial playbook created from verified regressions and handoff race fixes.
- 2026-04-23: Added opt-in Stage 1 trace instrumentation and recorded transform-toolbar/PYTHONW3 position clue.
- 2026-04-23: Added lazy WebEngine surface creation in `StlPreviewWidget` as the current focused fix under test.
- 2026-04-23: Tightened the fix so editor previews activate WebEngine only after the 3D Models tab is selected.
- 2026-04-23: Disabled automatic startup preview-runtime warmup to avoid unrelated background Chromium surface creation during editor open.
- 2026-04-23: Moved QtWebEngine imports behind explicit preview activation so editor construction cannot initialize WebEngine.
- 2026-04-23: Added an editor construction visibility guard and removed pre-construction event pumping in `add_tool()`.
- 2026-04-23: Added default-off diagnostic bypass switches for models tab, blur, and host style.
- 2026-04-23: Added `NTX_EDITOR_DIAG_STUB_EDITOR=1` and lazy real-editor imports for the strongest root-cause split.
- 2026-04-23: Added `NTX_EDITOR_DIAG_NO_DIALOG=1` to prove whether the flash survives without any dialog creation.
- 2026-04-23: Added `NTX_EDITOR_DIAG_NOOP_BUTTONS=1` so the bottom-bar click can be tested without entering CRUD/editor launch code at all.
- 2026-04-23: Added `NTX_EDITOR_DIAG_DISABLE_APP_MOUSE_FILTER=1` to bypass the Library's app-wide pre-handler mouse event filter.
- 2026-04-23: Added `NTX_EDITOR_DIAG_KEYBOARD_ONLY_ACTIONS=1` to compare mouse button clicks against keyboard-only action triggering.
- 2026-04-23: User confirmed `NTX_EDITOR_DIAG_BYPASS_MODELS_TAB=1` removes the glitch; normal models-tab builder now uses first-activation lazy materialization for preview, transforms, and model actions.
- 2026-04-23: Restored safe shared preview prewarm and unified Library + Selector detached/external preview windows on one payload-driven host, while keeping editor models-tab lazy.
