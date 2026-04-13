# Phase 11 Goals: Shared Support Modularization

**As of**: April 13, 2026  
**Scope**: Tools and jaws Library support-layer convergence after Phase 10

---

## Goal Statement

Reduce duplicated support-layer logic between TOOLS and JAWS by extracting reusable UI/service helpers into shared modules, while preserving behavior and domain boundaries.

---

## Current Baseline

- `ui/home_page.py`: 583 lines
- `ui/jaw_page.py`: 560 lines
- `ui/home_page_support/`: 17 active modules (excluding `__init__.py`)
- `ui/jaw_page_support/`: 17 active modules (excluding `__init__.py`)

The counts are now close, but substantial overlap remains in support responsibilities.

---

## Primary Goals

1. Extract high-overlap support logic into shared modules with domain adapters.
2. Keep `home_page.py` and `jaw_page.py` as thin orchestrators.
3. Preserve strict boundaries:
   - No cross-import from home support into jaw support.
   - No cross-import from jaw support into home support.
4. Keep quality gate fully green after every extraction slice.

---

## Quantitative Targets

1. Move at least 45% of duplicated support responsibilities to shared modules in Phase 11.
2. Reduce direct code duplication in paired support modules by at least 35%.
3. Keep both page files at or below 600 lines.
4. Keep parity/regression checks unchanged and passing.

---

## High-ROI Shared Candidates

1. Detached preview dialog shell lifecycle and control-row scaffolding.
2. Topbar skeleton assembly (search toggle, detail toggle, reset button, preview button, title row).
3. Generic page scaffolding builders (splitter/list/detail shell patterns).
4. Shared selection-signal utilities (selection changed/current changed plumbing, count labels).
5. Small runtime/link action helpers where behavior is identical.

---

## Domain-Specific (Do Not Force-Share)

1. Filter semantics and filter option sources.
2. Detail layout rule engines and domain field mapping.
3. Selector slot behavior and spindle/head compatibility rules.
4. Domain CRUD payload behavior.

---

## End-of-Phase Acceptance

1. Shared modules are used by both TOOLS and JAWS support layers.
2. No import-path or module-boundary violations.
3. Smoke test, quality gate, and regression checks pass.
4. Documentation updated (README + phase status docs).
