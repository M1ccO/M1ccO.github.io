# Work Editor Glitch Investigation Report

## Scope
- Problem investigated: visible Work Editor opening glitch/flicker in `Setup Manager`
- Audience: future LLM/code agents continuing UI stability work
- Goal: preserve what actually fixed the issue, what was ruled out, and what still deserves follow-up

## Final Outcome
- The Work Editor glitch appears resolved after subtree-parenting fixes in the tab content itself.
- The decisive fixes were not extra preload tricks, opacity tricks, or modal reveal choreography.
- The decisive fixes were:
  - ensuring `Zero Points` and `Tool IDs` heavy subtrees are created under their real tab/content parents from birth
  - eliminating detached-born widget construction patterns that were later adopted into layouts
  - normalizing helper/container/widget parentage inside those tab builders

## What Actually Fixed It

### Root cause that matched reality
- The user’s diagnosis was correct: the real source remained `Zero Points` and `Tool IDs`.
- Earlier work merely moved the visible glitch from tab-open time into Work Editor startup by priming those tabs earlier.
- That meant:
  - the tab subtree was still structurally wrong
  - the timing of the artifact changed, but the real cause did not

### Decisive structural fix
- The winning fix was to make tab widgets more widget-native and subtree-correct:
  - jaw selector panels in `Zero Points` stopped being created under the top-level dialog
  - titled section groups stopped being created detached / root-owned when they belonged inside tab subtrees
  - helper rows (for example checkbox wrapper rows) stopped being created parentless and only adopted later
  - some machining-center zero-point controls stopped being created under `dialog` and were instead created under the actual operation host subtree
  - `Tool IDs` internal panels and list widgets were tightened so they belong to the local subtree directly

### Key files where the decisive fixes landed
- `Setup Manager/ui/work_editor_support/tab_builders.py`
- `Setup Manager/ui/work_editor_support/zero_points.py`
- `Setup Manager/ui/work_editor_support/tools_tab_builder.py`
- `Setup Manager/ui/work_editor_support/jaw_selector_panel.py`
- `Setup Manager/ui/work_editor_support/ordered_tool_list.py`
- `Setup Manager/ui/work_editor_support/machining_center.py`
- `Setup Manager/ui/work_editor_dialog.py`
- `shared/ui/helpers/editor_helpers.py`

## Important Architecture Work That Still Matters
- Family-aware Work Editor shells were added and should be preserved:
  - `Setup Manager/ui/work_editor_factory.py`
  - `Setup Manager/ui/machine_family_runtime.py`
- Current family shells:
  - `LatheWorkEditorDialog`
  - `MachiningCenterWorkEditorDialog`
- High-level callers should continue to use the family factory instead of scattering family checks into callers.

## What Helped But Was Not The Final Fix

### 1. Parented Work Editor dialog launch
- Parenting create/edit/batch/group dialogs to the host window was still a real improvement.
- It addressed one Windows `QDialog` first-show issue.
- Keep that change.
- But it was not sufficient by itself to remove the remaining glitch.

### 2. Removal of hidden Work Editor preload lifecycle
- Removing dead Work Editor preload/materialization code simplified startup behavior.
- This was the right cleanup.
- Keep it removed.
- But it was not the final glitch fix either.

### 3. Startup priming / eager tab build
- Priming heavy tabs reduced tab-open glitches.
- However, it mostly front-loaded the same structural issue into startup.
- Keep priming only where it helps legitimate readiness, but do not mistake it for the root fix.

### 4. Controlled modal reveal experiment
- A custom reveal path using opacity/off-screen/manual event loop was tried.
- It increased complexity and was not the decisive fix.
- Treat that experiment as ruled out for this issue.

## What Was Ruled Out As “Final Root Cause”
- Not mainly:
  - selector-mode parity alone
  - general create/edit asymmetry alone
  - preload absence alone
  - `dialog.exec()` alone
  - tab warmup alone
- The real fix came from subtree-correct widget construction in `Zero Points` / `Tool IDs`.

## Strong Working Principle Learned
- If a heavy Qt UI subtree visually belongs to a tab/content host, create it under that host immediately.
- Avoid this pattern:
  - create widget with `parent=None`
  - or create under the top-level dialog/root
  - then add/reparent later into the visual subtree
- That pattern can produce paint-order / polish-order / first-show artifacts even if the UI eventually looks correct.

## Remaining Work Worth Investigating

### A. Residual Work Editor audit
- Even though the user reported the glitch as solved, a narrow robustness audit is still worth keeping in mind:
  - continue checking for detached-born helpers inside `Tool IDs` and `Zero Points`
  - prefer local parent ownership for helper rows, section groups, list widgets, and small wrappers

### B. Libraries-side broader audit
- This parent/subtree issue may be system-wide, not just a Work Editor issue.
- A quick scan of `Tools and jaws Library` found several likely audit targets where similar patterns may still exist.

#### Highest-priority library audit targets
- Selectors:
  - `Tools and jaws Library/ui/selectors/tool_selector_layout.py`
  - `Tools and jaws Library/ui/selectors/jaw_selector_layout.py`
  - `Tools and jaws Library/ui/selectors/fixture_selector_dialog.py`
  - `Tools and jaws Library/ui/selectors/common.py`
- Detail panel builders:
  - `Tools and jaws Library/ui/home_page_support/detail_panel_builder.py`
  - `Tools and jaws Library/ui/jaw_page_support/detail_panel_builder.py`
  - `Tools and jaws Library/ui/fixture_page_support/detail_panel_builder.py`
- Shared selector/detail helpers:
  - `Tools and jaws Library/ui/shared/selector_panel_builders.py`
  - `shared/ui/helpers/page_scaffold_common.py`
  - `shared/ui/helpers/editor_helpers.py`
- Editor pages/forms:
  - `Tools and jaws Library/ui/tool_editor_support/general_tab.py`
  - `Tools and jaws Library/ui/shared/editor_models_tab.py`
  - `Tools and jaws Library/ui/measurement_editor/forms/*.py`
- Export/editor dialogs:
  - `Tools and jaws Library/ui/export_page.py`
  - `Tools and jaws Library/ui/jaw_export_page.py`
  - `Tools and jaws Library/ui/fixture_editor_dialog.py`
  - `Tools and jaws Library/ui/jaw_editor_dialog.py`

#### Patterns found during quick scan
- `QWidget()` / `QFrame()` / `QScrollArea()` created without an explicit local parent in many UI builders
- some explicit `setParent(...)` / `setParent(None)` flows in detail preview and selector-related code
- several `create_titled_section(...)` usages that may still rely on later adoption into layout instead of local birth parent

### C. Shared helper audit
- The broader lesson should be propagated to shared helpers:
  - if a helper creates visible container widgets, it should usually accept and use a local parent
  - this is especially important for titled sections, wrapper rows, preview hosts, and selector panels

## Recommended Next Audit Rule
- When scanning UI code, flag anything that matches this shape:
  - visible widget/container created without explicit local parent
  - later added into a different subtree
  - later reparented manually
  - later polished/styled after being mounted
- Review priority should be higher when the widget is:
  - part of startup-heavy tabs
  - a scroll/content host
  - a preview surface
  - a selector/assignment panel
  - a composite card/group/section host

## Keep These Good Changes
- Keep family-shell Work Editor architecture.
- Keep host-parented Work Editor dialog launch.
- Keep dead Work Editor preload path removed.
- Keep the subtree-parenting fixes in `Zero Points` / `Tool IDs`.

## Avoid These Traps
- Do not reintroduce hidden preload/materialization paths unless there is hard evidence.
- Do not go back to broad duplicate implementations per profile.
- Do not try to “solve” a subtree-parenting bug primarily with opacity/reveal tricks.
- Do not assume a glitch is fixed just because its timing changed.

## Bottom Line
- The decisive fix was subtree-parenting correctness in `Zero Points` and `Tool IDs`.
- The user’s original diagnosis was correct.
- Earlier startup-path work helped simplify and isolate the problem, but did not finish it.
- The next best use of time is a targeted Libraries-side audit for the same detached-born widget pattern.
