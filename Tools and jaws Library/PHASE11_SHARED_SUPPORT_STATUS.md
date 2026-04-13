# Phase 11 Status: Shared Support Modularization

**As of**: April 13, 2026  
**Owner**: Ongoing  
**Status**: COMPLETE — Slices 1-5 complete

---

## Baseline Snapshot

- `ui/home_page.py`: **583 lines**
- `ui/jaw_page.py`: **524 lines**
- `ui/home_page_support/`: **17 modules** (excluding `__init__.py`)
- `ui/jaw_page_support/`: **18 modules** (excluding `__init__.py`)

---

## Investigation Summary

High-overlap areas identified:

1. `detached_preview.py` responsibilities overlap strongly.
2. `topbar_builder.py` structural scaffolding overlaps.
3. `page_builders.py` layout shell patterns overlap.
4. `selection_helpers.py`/selection-signal utility patterns overlap.
5. Runtime helper patterns partially overlap.

Low-overlap or domain-specific areas:

1. Detail layout rules and detail field semantics.
2. Selector slot logic and compatibility behavior.
3. Domain CRUD payload and workflow differences.
4. Filter option semantics and data origin.

---

## Planned Execution Slices

### Slice 1 — Shared preview shell
- Target: extract detached-preview shell lifecycle + toolbar scaffolding.
- Keep domain-specific model load/transform logic in TOOLS/JAWS modules.
- Status: COMPLETE

Implemented in Slice 1:

1. Added shared helper module: `shared/ui/helpers/detached_preview_common.py`
2. Reused shared helpers in:
   - `ui/home_page_support/detached_preview.py`
   - `ui/jaw_page_support/detached_preview.py`
3. Shared operations now centralized:
   - preview toggle button check/uncheck
   - detached dialog default positioning
   - Escape shortcut wiring
   - measurement toggle icon/tooltip shell behavior
   - common open/close toggle flow
4. Domain-specific behavior preserved locally:
   - TOOL/JAW model payload loading
   - JAW transform restore
   - domain-specific measurement payload handling

### Slice 2 — Shared topbar skeleton
- Target: extract common topbar widget assembly.
- Keep per-domain filter controls and translation keys in adapters.
- Status: COMPLETE

Implemented in Slice 2:

1. Added shared helper module: `shared/ui/helpers/topbar_common.py`
2. Reused shared helpers in:
   - `ui/home_page_support/topbar_builder.py`
   - `ui/jaw_page_support/topbar_builder.py`
3. Shared operations now centralized:
   - search clear-button wiring
   - standard refresh button creation
   - topbar spacer insertion
   - compact QToolButton construction helper
4. Domain-specific behavior preserved locally:
   - TOOL/JAW-specific button sets and ordering
   - domain translation key usage
   - domain-only filter/control semantics

### Slice 3 — Shared page scaffold
- Target: split common splitter/list/detail container shell.
- Keep domain list widgets/delegates as injected dependencies.
- Status: COMPLETE

Implemented in Slice 3:

1. Added shared helper module: `shared/ui/helpers/page_scaffold_common.py`
2. Reused shared helpers in:
   - `ui/home_page_support/page_builders.py`
   - `ui/jaw_page_support/page_builders.py`
3. Shared operations now centralized:
   - root page layout shell creation
   - search input creation + refresh wiring
   - horizontal splitter shell creation
   - catalog list-card shell + common list-view defaults
   - list-view event-filter installation
   - detail container/card/scroll/panel shell creation
4. Domain-specific behavior preserved locally:
   - TOOL and JAW list widget class/delegate wiring
   - JAW selector-card and sidebar composition
   - per-domain click handlers and model plumbing

### Slice 4 — Shared selection plumbing
- Target: move generic selection signal/label update helpers.
- Keep per-domain selection semantics local.
- Status: COMPLETE

Implemented in Slice 4:

1. Added shared helper module: `shared/ui/helpers/selection_common.py`
2. Reused shared helpers in:
   - `ui/home_page_support/selection_signal_handlers.py`
   - `ui/jaw_page_support/selection_signal_handlers.py` (new)
   - `ui/jaw_page.py` (delegating wrappers)
3. Shared operations now centralized:
   - selection-model one-time signal wiring
   - generic multi-selection changed passthrough to count refresh
   - generic selected-count label rendering helper
4. Domain-specific behavior preserved locally:
   - TOOL/JAW current-item state fields
   - TOOL/JAW detail-population behavior
   - TOOL/JAW preview-sync side effects
   - TOOL/JAW selected-item identity extraction

### Slice 5 — Validation and cleanup
- Target: remove dead wrappers, update docs, run full gate.
- Status: COMPLETE

Implemented in Slice 5:

1. Performed dead-wrapper review after Slices 1-4 extraction.
2. Preserved intentional thin delegating wrappers in page orchestrators (kept for readability and stable call surface).
3. Updated phase and README documentation to reflect completion state.
4. Re-ran full validation suite for completion snapshot.

---

## Risks and Mitigation

1. **Risk**: Over-generalized shared code becomes hard to maintain.
   - **Mitigation**: adapter-first extraction, domain logic kept local.

2. **Risk**: Regression in preview behavior.
   - **Mitigation**: keep load/transform semantics domain-owned; only share shell.

3. **Risk**: Boundary violations.
   - **Mitigation**: run import/boundary checks after each slice.

---

## Exit Criteria

1. Shared support modules used by both TOOLS and JAWS for high-overlap areas.
2. No behavior regressions in smoke/quality gates.
3. Updated README and phase docs reflect final state.

Exit Criteria Result:

1. Shared support modules adopted by both domains for preview shell, topbar skeleton, page scaffold, and selection plumbing.
2. No regression detected by smoke test or quality gate.
3. Phase and README documentation updated to current completion state.

---

## Latest Validation (after Slice 5)

1. Editor diagnostics on phase-touched modules: PASS
2. `py_compile` on phase-touched shared/support modules: PASS
3. `python scripts/smoke_test.py`: PASS
4. `python scripts/run_quality_gate.py`: PASS

---

## Closure Commit Draft

Suggested commit message:

`Phase 11: complete shared support modularization (slices 1-5)`

Suggested body:

1. Add shared helpers for detached preview shell, topbar skeleton, page scaffold, and selection plumbing.
2. Rewire TOOLS and JAWS support modules to consume shared helpers while keeping domain behavior local.
3. Add JAW selection signal handler module and delegate JawPage selection wrappers.
4. Finalize Phase 11 docs/README status and run full quality snapshot.

---

## Appendix: What Moved Where

1. Shared preview shell
   - Added: `shared/ui/helpers/detached_preview_common.py`
   - Reused by:
     - `ui/home_page_support/detached_preview.py`
     - `ui/jaw_page_support/detached_preview.py`

2. Shared topbar skeleton
   - Added: `shared/ui/helpers/topbar_common.py`
   - Reused by:
     - `ui/home_page_support/topbar_builder.py`
     - `ui/jaw_page_support/topbar_builder.py`

3. Shared page scaffold
   - Added: `shared/ui/helpers/page_scaffold_common.py`
   - Reused by:
     - `ui/home_page_support/page_builders.py`
     - `ui/jaw_page_support/page_builders.py`

4. Shared selection plumbing
   - Added: `shared/ui/helpers/selection_common.py`
   - Reused by:
     - `ui/home_page_support/selection_signal_handlers.py`
     - `ui/jaw_page_support/selection_signal_handlers.py` (new)
     - `ui/jaw_page.py` (delegating wrappers)

---

## Reduction Summary (Now)

1. Orchestrator reduction from original modular-overhaul baselines:
   - `ui/home_page.py`: 2,223 -> 583 (reduced by 1,640 lines; ~73.8%)
   - `ui/jaw_page.py`: 1,423 -> 524 (reduced by 899 lines; ~63.2%)

2. Phase 11 extraction effect across modified existing domain files:
   - 442 lines deleted
   - 207 replacement lines added
   - Net reduction in touched existing files: 235 lines

3. Where reductions came from in Phase 11:
   - duplicated preview shell scaffolding from TOOLS/JAWS detached preview modules
   - duplicated topbar construction scaffolding from TOOLS/JAWS topbar builders
   - duplicated list/detail/splitter shell setup from TOOLS/JAWS page builders
   - duplicated selection-model wiring and selected-count label rendering from TOOLS/JAWS selection handlers

---

## File Deletions

During cleanup, the following legacy phase documents were removed:

1. `Tools and jaws Library/PHASE10_HOME_PAGE_AND_MACHINE_CONFIG.md`
2. `Tools and jaws Library/TOOL_EDITOR_REFACTOR.md`
3. `Tools and jaws Library/TOOLS_JAWS_MODULAR_OVERHAUL_GOALS.md`
4. `Tools and jaws Library/TOOLS_JAWS_MODULAR_OVERHAUL_RULES.md`
5. `Tools and jaws Library/TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md`

No additional runtime Python module files were removed in Slice 5.
