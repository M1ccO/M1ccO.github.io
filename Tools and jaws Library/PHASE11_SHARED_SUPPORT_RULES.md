# Phase 11 Rules: Shared Support Modularization

**Applies to**: TOOLS/JAWS support-layer convergence work

---

## Non-Negotiable Rules

1. **Behavior-preserving only**
   - No workflow/UX behavior changes during extraction passes.
   - Refactors must preserve existing signals, callbacks, and side effects.

2. **Domain-boundary protection**
   - Never import from `ui/home_page_support/` into JAWS domain code.
   - Never import from `ui/jaw_page_support/` into TOOLS domain code.
   - Shared logic must live in canonical shared locations or neutral app-local shared helpers.

3. **Adapter pattern, not forced genericity**
   - Shared modules should accept callbacks/config for domain differences.
   - Keep domain-specific semantics in domain modules.

4. **Thin orchestrator contract**
   - Page methods should remain delegation wrappers where practical.
   - Keep orchestration readable and traceable.

5. **No schema changes in Phase 11**
   - This phase is support-layer modularization only.
   - DB migrations are out-of-scope unless explicitly approved.

6. **Validation after each extraction slice**
   - Compile touched files.
   - Run smoke test.
   - Run full quality gate before closing a pass.

7. **Documentation parity required**
   - Update status docs and README files with actual, current state.
   - Do not leave stale claims about lines/modules/features.

---

## Quality Commands

Run from repository root:

1. `python scripts/smoke_test.py`
2. `python scripts/run_quality_gate.py`

Optional targeted checks during a pass:

1. `python scripts/import_path_checker.py`
2. `python scripts/module_boundary_checker.py`
3. `python scripts/module_extension_checker.py`

---

## Completion Rules for Any Pass

1. No new diagnostics in touched files.
2. No boundary checker regressions.
3. No stale imports.
4. Status documentation updated with measurable delta.
