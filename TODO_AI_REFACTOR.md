# TODO AI Refactor Plan

Last updated: 2026-04-12

## Mission
Continue safe, behavior-preserving optimization/refactoring across the repo with strict boundary rules:
- No schema/file-format/protocol/workflow changes unless explicitly required.
- No direct imports between `Setup Manager` and `Tools and jaws Library`.
- Use canonical `shared.*` only for clearly cross-app reusable logic.
- Keep diffs focused and reviewable.

## Mandatory Read Before Any Changes
1. `AGENTS.md`
2. `architecture-map.json`
3. `docs/duplicate-reduction-plan.md`
4. `docs/shim-retirement-policy.md`
5. `Setup Manager/WORK_EDITOR_REFACTOR_STATUS.md`
6. `AI_AGENT_COMMAND_BRIEF.md`

## Always Run After Each Task
1. `python -m py_compile <touched .py files>`
2. `python scripts/import_path_checker.py`
3. `python scripts/duplicate_detector.py`
4. `python scripts/run_quality_gate.py`

---

## Priority 1: Shared Dropdown Style Consolidation

### Goal
Eliminate duplicate dropdown-style plumbing between app-local widget helpers by centralizing canonical behavior in `shared`.

### Current State
- Setup app has local implementation in `Setup Manager/ui/widgets/common.py`.
- Tools app has similar implementation in `Tools and jaws Library/ui/widgets/common.py`.
- Shared contains most primitives in `shared/ui/helpers/common_widgets.py`.

### Tasks
1. Add a canonical shared function for dropdown styling in `shared/ui/helpers/common_widgets.py`.
2. Migrate app-local callers to use the shared function.
3. Keep app-specific wrappers only if they add app-specific behavior (e.g., icon override).
4. Remove duplicate local implementation blocks that become dead code.
5. Ensure no import path rule violations.

### Acceptance Criteria
- No behavior/UI regressions in combo interactions.
- Duplicate detector baseline does not increase.
- Both apps still launch and dropdowns behave identically.

---

## Priority 2: Setup Manager `setup_page.py` Responsibility Reduction

### Goal
Reduce size/complexity of `Setup Manager/ui/setup_page.py` by extracting coherent app-local responsibilities into `Setup Manager/ui/setup_page_support/`.

### Tasks
1. Identify 2-3 safe seams (list rendering, filter/sort state handling, action wiring helpers).
2. Extract one seam per pass (small-to-medium diff).
3. Keep `setup_page.py` orchestration-focused.

### Acceptance Criteria
- No workflow/UI text/signal-flow changes.
- Existing setup-page behaviors remain unchanged.
- Quality gate passes.

---

## Priority 3: Setup Manager `drawing_page.py` Responsibility Reduction

### Goal
Reduce burden in `Setup Manager/ui/drawing_page.py` with app-local support extraction.

### Tasks
1. Extract pure/state-light helpers first (filter/query normalization, list model transforms).
2. Then extract UI section builders if still large.
3. Keep page class as coordinator.

### Acceptance Criteria
- Behavior preserved.
- No schema/storage changes.
- Validation commands pass.

---

## Priority 4: Tools App `home_page.py` Continued Reduction

### Goal
Continue splitting monolith into existing `home_page_support` modules by responsibility.

### Tasks
1. Extract one coherent slice at a time (selector state sync, panel builders, payload adapters).
2. Prefer existing support modules over creating many new files.
3. Keep launch/selector integration behavior unchanged.

### Acceptance Criteria
- No launch/workflow regressions.
- Diff remains narrowly scoped.
- Quality gate passes.

---

## Priority 5: Shared App Bootstrap Visual Policy

### Goal
Consolidate duplicated startup visual helpers from both app `main.py` files.

### Candidate Duplicates
- `FastTooltipStyle`
- `_build_fixed_light_palette`
- related `styleHint` logic

### Tasks
1. Create shared bootstrap visual helper module in `shared` (if truly cross-app).
2. Rewire both app `main.py` files to consume shared implementation.
3. Keep app-specific differences as explicit override hooks.

### Acceptance Criteria
- Startup look-and-feel unchanged.
- Duplicate signature count stays <= baseline.

---

## Priority 6: Data Layer Primitive Consolidation (Careful)

### Goal
Reduce duplicated base mechanics in `data/database.py` and `data/jaw_database.py` across both apps without violating app ownership boundaries.

### Tasks
1. Extract only neutral primitives (connection/lifecycle helpers).
2. Keep app-specific schemas/migrations/config untouched.
3. Do not merge app-specific domain logic.

### Acceptance Criteria
- No migration/schema changes.
- All CRUD behavior unchanged.
- Quality gate passes.

---

## Work Editor Follow-up (Setup Manager)

Use `Setup Manager/WORK_EDITOR_REFACTOR_STATUS.md` as the source of truth.

### Remaining Safe Follow-up
1. Collapse thin wrapper clusters in `work_editor_dialog.py` where safe.
2. Extract dialog lifecycle setup blocks (tabs/buttons/repolish/event filters) if still noisy.
3. Keep callback API stable for `work_editor_support` modules.

---

## Execution Rules For AI Agents

1. One coherent responsibility slice per pass.
2. Prefer extraction of pure/mostly-pure helpers first.
3. Avoid introducing shims; if required, add removal notes and timeline.
4. Never broaden scope mid-pass.
5. Report:
   - what moved
   - why boundary is safe
   - files changed
   - validation run/results
   - residual risks

---

## Definition of Done (Per PR / Pass)
1. All required validation commands pass.
2. Duplicate baseline does not increase.
3. Import-path checker passes with no forbidden paths.
4. Behavior is unchanged from user perspective.
5. Diff is reviewable and narrowly focused.
