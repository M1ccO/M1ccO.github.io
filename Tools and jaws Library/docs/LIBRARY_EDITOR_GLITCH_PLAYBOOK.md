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


## Change Log
- 2026-04-23: Initial playbook created from verified regressions and handoff race fixes.

