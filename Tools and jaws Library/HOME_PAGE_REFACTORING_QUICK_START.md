# Phase 4: HomePage Refactoring — Quick Reference Summary

**Status**: Design complete, ready for implementation  
**Timeline**: 14-24 hours (2-3 day sprint)  
**Target Reduction**: 2,223L → ~420L (82% smaller)  
**Key Constraint**: Zero behavior change, parity tests must PASS

---

## The Refactoring at a Glance

### What Changes
```
BEFORE:                           AFTER:
HomePage (QWidget)                HomePage(CatalogPageBase)
  ├─ _build_ui() [590L]    →      ├─ __init__() [140L]
  ├─ refresh_list() [100L]  →     ├─ 4 abstract methods [140L]
  ├─ Filter logic [150L]    →     ├─ Signal handlers [50L]
  ├─ Detail panel [400L]    →     ├─ Tool CRUD ops [50L]
  ├─ _build_selector_* [80L] →    ├─ Batch helpers [50L]
  └─ ... [700+L]                  └─ Preview & selector [60L]
                                       ↓
                                    ~420L total

File Size:    2,223L         Reduction:    82%
Duplication:  72-85% shared  Pattern:      →0% (delegated)
                              Maintainability: Low → High
```

### The Platform Layer (CatalogPageBase)

```python
# Shared platform (Phase 3, existing)

CatalogPageBase:
  ├─ Signals: item_selected(id, uid), item_deleted(id)
  ├─ _build_ui(): common catalog layout
  ├─ refresh_catalog(): reload + restore selection
  └─ apply_batch_action(): delete + emit signals
```

### HomePage's Role (Phase 4)

```python
class HomePage(CatalogPageBase):
    # Tool-specific implementations of abstract methods
    def create_delegate(self) -> ToolCatalogDelegate
    def get_item_service(self) -> ToolService
    def build_filter_pane(self) -> QWidget  # type filter
    def apply_filters(filters) -> list[dict]  # with selectors
    
    # Tool-specific features (preserved)
    def set_selector_context(active, head, spindle)
    def toggle_details()
    def add_tool() / edit_tool() / delete_tool() / copy_tool()
    def toggle_preview_window()
    
    # Signal handlers (NEW)
    def _on_item_selected_internal(id, uid)
    def _on_item_deleted_internal(id)
```

---

## Line-by-Line Breakdown

### Old HomePage (2,223L)

| Section | Lines | Status |
|---------|-------|--------|
| Imports | 50 | Keep |
| Constructor | 45 | Keep (simplified) |
| Helpers | 45 | Keep |
| _build_ui() | 590 | **REMOVE** → CatalogPageBase |
| _build_selector_card() | 80 | Keep (call support) |
| _build_bottom_bars() | 100 | Keep (call support) |
| Catalog refresh | 100 | **REMOVE** → CatalogPageBase |
| Filter UI | 150 | Simplify to build_filter_pane() |
| Detail panel | 400 | **EXTRACT** → detail_panel_builder.py |
| Components panel | 150 | **EXTRACT** → components_panel_builder.py |
| Detail fields | 150 | **EXTRACT** → detail_fields_builder.py |
| Field helpers | 100 | **EXTRACT** → detail_fields_builder.py |
| Tool CRUD | 100 | Keep |
| Selector | 100 | Keep |
| Preview + batch | 73 | Keep |
| **TOTAL** | **2,223** | **→ ~420** |

### New HomePage (~420L)

```
Imports + Header          50L
Constructor               140L  (simplified, calls super().__init__)
Abstract methods          140L  (create_delegate, get_item_service, 
                                 build_filter_pane, apply_filters)
Signal handlers            50L  (_on_item_selected_internal, 
                                 _on_item_deleted_internal)
Detail panel toggle        30L  (show/hide/toggle + populate delegate)
Tool CRUD                  50L  (add/edit/delete/copy)
Batch helpers              50L  (_get_selected_tool, _selected_tool_uids, etc.)
Preview mgmt               50L  (toggle_preview, _sync, _warmup)
Selector context           50L  (set_selector_context, etc.)
Module switch + helpers    30L  (set_page_title, set_module_switch_target, etc.)
────────────────────────────
TOTAL                     ~420L
```

---

## What Gets Extracted

### 1. Detail Panel Rendering (~200L) → **detail_panel_builder.py**

**Current Location**: lines ~1200-1550  
**Extract**: populate_details() + all component builders  
**New Module**: home_page_support/detail_panel_builder.py

```python
# home_page_support/detail_panel_builder.py

def populate_detail_panel(home_page, tool):
    """Main entry point - called by HomePage.populate_details()"""
    
def _build_placeholder_details():
def _build_components_panel(tool, support_parts):
def _build_preview_panel(stl_path):
def _build_detail_field(label, value, multiline=False):
def _add_two_box_row(layout, label1, val1, label2, val2):
# ... other component helpers
```

**Why Extract?**
- 200+ lines of UI rendering (detail panel complexity)
- Logic disconnected from HomePage's signal flow
- Future JawPage may reuse pattern
- Testable in isolation

---

## Implementation Path

### Pass 1: Class Structure (2-4 hours)

```python
# Change this:
class HomePage(QWidget):

# To this:
class HomePage(CatalogPageBase):
    def __init__(self, tool_service, ...):
        # Store services
        self.tool_service = tool_service
        # ...rest of init...
        super().__init__(parent, item_service=tool_service, translate=...)
    
    # Implement 4 abstract methods
    def create_delegate(self) -> ToolCatalogDelegate: ...
    def get_item_service(self) -> Any: ...
    def build_filter_pane(self) -> QWidget: ...
    def apply_filters(self, filters: dict) -> list[dict]: ...
```

**Verification**: Import test passes; no syntax errors

---

### Pass 2: Signals (2-3 hours)

```python
# In __init__()
self.item_selected.connect(self._on_item_selected_internal)
self.item_deleted.connect(self._on_item_deleted_internal)

# Add handlers
def _on_item_selected_internal(self, item_id: str, uid: int):
    self.current_tool_id = item_id
    self.current_tool_uid = uid
    if not self._details_hidden:
        tool = self.tool_service.get_tool(item_id)
        self.populate_details(tool)

def _on_item_deleted_internal(self, item_id: str):
    if self.current_tool_id == item_id:
        self.populate_details(None)
```

**Verification**: Signals fire; handlers execute; parity tests 50%+ pass

---

### Pass 3: Detail Panel Extraction (3-5 hours)

```python
# HomePage.populate_details() now:
def populate_details(self, tool: dict | None) -> None:
    from ui.home_page_support.detail_panel_builder import populate_detail_panel
    populate_detail_panel(self, tool)
```

**Verification**: Detail panel renders; parity tests 90%+ pass

---

### Pass 4-7: Testing & Finalization (8-12 hours)

- Selector state verification
- Preview management verification
- Smoke tests: both apps start
- Parity tests: 13/13 PASS
- Import quality gates
- Code review + commits

---

## Quick Checklist for Implementation

**Before You Start**:
- [ ] Read `HOME_PAGE_REFACTORING_DESIGN.md` (complete source code)
- [ ] Backup current home_page.py
- [ ] Have CatalogPageBase contract open for reference

**Pass 1: Class Structure**

- [ ] Add `(CatalogPageBase)` to class declaration
- [ ] Update imports (add CatalogPageBase from shared)
- [ ] Update `__init__()` → call `super().__init__()`
- [ ] Implement `create_delegate()` → return ToolCatalogDelegate
- [ ] Implement `get_item_service()` → return self.tool_service
- [ ] Implement `build_filter_pane()` → return type filter frame
- [ ] Implement `apply_filters(filters)` → call tool_service.list_tools()
- [ ] Remove custom _build_ui() catalog logic (list view, search, model setup)
- [ ] Test: `python -c "from ui.home_page import HomePage; print('OK')"`

**Pass 2: Signals**

- [ ] Add signal connections in `__init__()` (2 connect calls)
- [ ] Implement `_on_item_selected_internal()`
- [ ] Implement `_on_item_deleted_internal()`
- [ ] Update `delete_tool()` → emit item_deleted signal
- [ ] Test: Manual verification (print to console on signal fire)

**Pass 3: Detail Panel**

- [ ] Create `home_page_support/detail_panel_builder.py`
- [ ] Move `populate_details()` + all detail builders
- [ ] Update HomePage `populate_details()` → delegate
- [ ] Update `home_page_support/__init__.py` → add re-exports
- [ ] Test: Detail panel renders; select tool → detail shows

**Pass 4-7: QA & Finalization**

- [ ] Run `python scripts/smoke_test.py` → exit 0
- [ ] Run `python scripts/import_path_checker.py` → exit 0
- [ ] Run `python tests/run_parity_tests.py` → 13/13 PASS
- [ ] Manual parity verification (13 test groups)
- [ ] Code review
- [ ] Commit + update status docs

---

## Success Metrics

| Gate | Target | How to Verify |
|------|--------|---------------|
| **Class Structure** | Implement 4 abstract methods | `wc -l home_page.py` (should be ~500L after pass 1) |
| **Signals** | item_selected/item_deleted emit | Connect listeners manually + log to console |
| **Smoke Tests** | Both apps start without errors | `python scripts/smoke_test.py` |
| **Parity Tests** | 13/13 PASS → no regressions | `python tests/run_parity_tests.py` |
| **Code Quality** | Import violations = 0 | `python scripts/import_path_checker.py` |

---

## Reference Documents

1. **Complete Implementation Source**: [HOME_PAGE_REFACTORING_DESIGN.md](HOME_PAGE_REFACTORING_DESIGN.md)
   - Full ~420L source code (copy-paste ready)
   - Detailed line mapping
   - Signal flow diagrams

2. **Platform Contract**: [PHASE_4_MIGRATION_DESIGN.md](PHASE_4_MIGRATION_DESIGN.md)
   - CatalogPageBase specification
   - Parity test strategy
   - Rollback plan

3. **CatalogPageBase Reference**: [shared/ui/platforms/catalog_page_base.py](../shared/ui/platforms/catalog_page_base.py)
   - Abstract method contracts
   - Signal definitions
   - Usage examples

---

**Ready to start? Begin with HOME_PAGE_REFACTORING_DESIGN.md → Pass 1: Class Structure**
