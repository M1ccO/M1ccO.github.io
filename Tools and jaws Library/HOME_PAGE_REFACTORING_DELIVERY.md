# DELIVERY: Complete HomePage Refactoring Design (2,223L → ~400L)

**Delivered**: April 13, 2026  
**Status**: Design phase complete ✅ Ready for implementation  
**Scope**: 3 comprehensive documents + complete source code

---

## What You're Getting

### Document 1: `HOME_PAGE_REFACTORING_DESIGN.md` ⭐ START HERE

**~1,800 lines**, comprehensive implementation guide

**Contents**:
- ✅ Complete new HomePage implementation (420 lines, fully typed, production-ready)
- ✅ Old → New line mapping (showing which old lines become new code vs extracted)
- ✅ What stays in home_page.py (9 categories, 420L total with rationale)
- ✅ What moves to home_page_support/ (5 extraction targets, new detail_panel_builder.py)
- ✅ Signal wiring diagram + external listener examples
- ✅ Implementation checklist (7 passes, 35+ subtasks, estimated hours)
- ✅ Parity test verification commands
- ✅ Success criteria gates (5 gates, all quantified)

**How to Use**:
1. Read the overview (sections 1-2)
2. Copy the complete HomePage class from section 2 (copy-paste ready)
3. Follow the line mapping (section 3) to understand the transformation
4. Use the implementation checklist (section 7) to track progress

---

### Document 2: `HOME_PAGE_REFACTORING_QUICK_START.md`

**~400 lines**, quick reference for developers

**Contents**:
- ✅ One-page refactoring overview
- ✅ Line-by-line breakdown (old 2,223L → new 420L)
- ✅ What gets extracted (with code samples)
- ✅ Implementation path (7 passes with code snippets)
- ✅ Quick checklist for each pass
- ✅ Success metrics (5 gates to verify)
- ✅ Reference links to other documents

**How to Use**: Bookmark this for during implementation; check off items as you progress.

---

### Document 3: `PHASE_4_MIGRATION_DESIGN.md` (Existing)

**4,200+ lines**, comprehensive platform architecture

**Complements refactoring design with**:
- Platform layer (CatalogPageBase) contract
- Integration architecture
- Parity test strategy (13 test groups)
- Rollback plan (3 levels)
- Timeline estimates
- Success criteria (quantitative + qualitative)

**How to Use**: Reference for platform contract questions; parity test execution.

---

## The Refactoring at a Glance

### Reduction: 2,223L → ~400L (82% smaller)

```
OLD HomePage (monolithic, 2,223L)
├─ _build_ui() [590L]
├─ Catalog logic [350L]
├─ Filter UI [150L]
├─ Detail panel + components [600L] ← to be extracted
├─ Selector [350L]
├─ Preview [150L]
└─ Batch ops [200L]

NEW HomePage (platform-based, ~420L)
├─ __init__() [140L]                    (initialize services + state)
├─ 4 abstract methods [140L]              (create_delegate, get_item_service, 
                                          build_filter_pane, apply_filters)
├─ Signal handlers [50L]                 (_on_item_selected_internal, 
                                          _on_item_deleted_internal)
├─ Detail panel toggle [30L]              (show/hide/toggle + delegate to support)
├─ Tool CRUD [50L]                       (add/edit/delete/copy)
├─ Batch helpers [50L]                   (_get_selected_tool, _selected_tool_uids)
├─ Preview [50L]                         (toggle, sync, warmup)
└─ Selector + module switch [60L]        (set_selector_context, etc.)
   ↓
   CatalogPageBase provides:
   • refresh_catalog()
   • list_view + model management
   • Selection persistence
   • item_selected / item_deleted signals

Extraction:
   • ~200L detail panel → home_page_support/detail_panel_builder.py
   • ~150L components → home_page_support/components_panel_builder.py
   • ~150L detail fields → home_page_support/detail_fields_builder.py
```

### What Changes

| Aspect | Before | After | Impact |
|--------|--------|-------|--------|
| **Lines** | 2,223 | ~420 | 82% reduction |
| **Class** | QWidget | CatalogPageBase | Inherits platform patterns |
| **Duplication** | 72-85% with jaw_page.py | 0% | Consolidates to base |
| **Signals** | None emitted | 2 signals (item_selected, item_deleted) | Enables decoupled listeners |
| **Selector** | Monolithic | Orthogonal state | Stays in HomePage, independent of platform |
| **Detail Panel** | Inline (400L) | Delegated to support | Cleaner separation of concerns |

---

## Implementation Path (14-24 hours)

### Pass 1: Class Structure (2-4h)
- Add `(CatalogPageBase)` to class declaration
- Implement 4 abstract methods
- Remove duplicate catalog logic
- Test: imports work

### Pass 2: Signals (2-3h)
- Wire item_selected + item_deleted
- Add signal handlers
- Update delete_tool() to emit signal
- Test: signals fire with correct args

### Pass 3: Detail Panel Extraction (3-5h)
- Create detail_panel_builder.py
- Move populate_details() + builders
- Update HomePage.populate_details() to delegate
- Test: detail panel renders

### Pass 4: Selector Isolation (1-2h)
- Verify selector state orthogonal
- Verify apply_filters() respects selector
- Test: selector mode works

### Pass 5: Preview Preservation (1-2h)
- Verify preview methods work
- Verify warmup engine works
- Test: preview renders

### Pass 6: Testing & Parity (4-6h)
- Run smoke_test.py
- Run import_path_checker.py
- Run parity tests (13/13 PASS)
- Manual verification

### Pass 7: Code Review & Finalization (1-2h)
- Code review
- Update documentation
- Commit changes

---

## Key Files Delivered

```
Tools and jaws Library/
├── HOME_PAGE_REFACTORING_DESIGN.md          ⭐ MAIN DESIGN (1,800L)
├── HOME_PAGE_REFACTORING_QUICK_START.md     Quick reference (400L)
├── PHASE_4_MIGRATION_DESIGN.md              Platform architecture (4,200L)
├── ui/home_page.py                          Current implementation (2,223L)
├── shared/ui/platforms/catalog_page_base.py CatalogPageBase contract (existing)
└── ui/home_page_support/
    ├── detail_panel_builder.py              NEW (to be created, ~200L)
    └── ... (14 existing support modules)
```

---

## What's New vs What Stays

### ✅ What's New

1. **HOME_PAGE_REFACTORING_DESIGN.md**
   - Complete new HomePage class (420L source code)
   - Line-by-line transformation mapping
   - Signal wiring + flow diagrams
   - Detailed implementation checklist

2. **HOME_PAGE_REFACTORING_QUICK_START.md**
   - One-page developer reference
   - Pass-by-pass implementation guide
   - Quick checklist format

3. **home_page_support/detail_panel_builder.py**
   - Extract from populate_details() (~200L)
   - New module for detail panel rendering

### ✅ What Stays (Behavior Preserved)

- All tool CRUD operations (add/edit/delete/copy)
- All user workflows (search, filter, select, preview)
- Excel import/export
- Selector context integration (Setup Manager)
- Detached + inline STL preview
- Batch operations
- Database schema (no migrations)
- IPC handoff between apps

---

## Validation Gates

All 5 gates must pass for Phase 4 acceptance:

```
✅ Gate 1: Class Structure
   • HomePage inherits CatalogPageBase
   • 4 abstract methods implemented
   • ~420 lines total
   Verify: wc -l home_page.py

✅ Gate 2: Signal Emission
   • item_selected fires on selection
   • item_deleted fires on deletion
   • Signal args correct (id, uid)
   Verify: Manual signal testing

✅ Gate 3: Smoke Tests
   • Tool Library app starts
   • Setup Manager app starts
   • No import errors
   Verify: python scripts/smoke_test.py → exit 0

✅ Gate 4: Parity Tests
   • All 13/13 test groups PASS
   • No behavior regressions
   • User workflows identical
   Verify: python tests/run_parity_tests.py → 13/13 PASS

✅ Gate 5: Code Quality
   • Import violations = 0
   • Duplication reduced
   • Code review approved
   Verify: python scripts/import_path_checker.py → exit 0
```

---

## How to Start Implementation

### Step 1: Review the Design

Open: `HOME_PAGE_REFACTORING_DESIGN.md`

- Read section 1 (Overview) — 2 min
- Read section 2 (New Implementation) — 5 min
- Skim section 3 (Line Mapping) — 3 min
- Reference section 4 (What Stays) during coding

### Step 2: Begin Pass 1 (Class Structure)

Open: `HOME_PAGE_REFACTORING_QUICK_START.md`

- Follow "Pass 1: Class Structure" section
- Use code samples provided
- Reference complete source from HOME_PAGE_REFACTORING_DESIGN.md
- Test after each change

### Step 3: Track Progress

Use the implementation checklist in section 7 of HOME_PAGE_REFACTORING_DESIGN.md:
- [ ] Pass 1: Class Structure (2-4h)
- [ ] Pass 2: Signals (2-3h)
- [ ] Pass 3: Detail Panel (3-5h)
- [ ] Pass 4: Selector (1-2h)
- [ ] Pass 5: Preview (1-2h)
- [ ] Pass 6: Testing (4-6h)
- [ ] Pass 7: Finalization (1-2h)

### Step 4: Verify at Each Gate

After completing each pass, run verification commands from Quick Start section "Success Metrics".

---

## What Success Looks Like

After complete implementation:

```
NEW METRICS:
✅ HomePage: 2,223L → ~420L (82% reduction)
✅ Duplicated patterns: 72-85% → 0% (moved to CatalogPageBase)
✅ Parity tests: 13/13 PASS (no regressions)
✅ Import violations: 0 (code quality maintained)
✅ Duplication: Consolidated to shared base class
✅ JawPage ready: Can now inherit from CatalogPageBase in Phase 5

USER EXPERIENCE:
✅ Search/filter works identically
✅ CRUD operations work identically
✅ Preview (inline + detached) works identically
✅ Selector mode works identically
✅ Excel import/export works identically
✅ Setup Manager ↔ Tool Library integration works identically
```

---

## Questions?

Refer to:

1. **For implementation details**: HOME_PAGE_REFACTORING_DESIGN.md (section 2, complete source code)
2. **For platform contract**: shared/ui/platforms/catalog_page_base.py or PHASE_4_MIGRATION_DESIGN.md (section 3)
3. **For parity tests**: PHASE_4_MIGRATION_DESIGN.md (section 11, test strategy)
4. **For signal examples**: HOME_PAGE_REFACTORING_DESIGN.md (section 6, integration points)
5. **For team communication**: HOME_PAGE_REFACTORING_QUICK_START.md (overview + quick checklist)

---

## Timeline Summary

**Design Phase**: ✅ COMPLETE (April 13, 2026)

**Implementation Phase** (next):
- Estimated: 14-24 hours (2-3 day sprint)
- 7 passes with incremental validation
- Starting: Pass 1 (Class Structure)
- Gating: Smoke tests + Parity tests (13/13 PASS)
- Completion: All 5 success gates passed

---

**Delivery Ready**: All design documents complete  
**Next Action**: Begin Pass 1 (Class Structure) with HOME_PAGE_REFACTORING_DESIGN.md section 2
