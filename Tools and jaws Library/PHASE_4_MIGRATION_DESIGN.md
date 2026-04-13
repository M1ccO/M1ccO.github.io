# Phase 4 Migration Design: HomePage → CatalogPageBase Refactor

**Phase 4 Start Date**: April 13, 2026  
**Current Status**: Design phase (pre-implementation)  
**Owner**: Copilot Primary + AI-Assisted Contributors  
**Scope**: Transform HomePage (2,223L) into ~400L by inheriting from CatalogPageBase  
**Constraint**: Zero behavior change, parity tests must PASS, backward-compatible file formats, no DB schema changes  

---

## Table of Contents

1. [Overview & Goals](#overview--goals)
2. [Current HomePage State Analysis](#current-homepage-state-analysis)
3. [CatalogPageBase Platform Contract](#catalogpagebase-platform-contract)
4. [Migration Architecture](#migration-architecture)
5. [Abstract Method Implementations](#abstract-method-implementations)
6. [Signal Mapping Strategy](#signal-mapping-strategy)
7. [Tool Head Selector State Preservation](#tool-head-selector-state-preservation)
8. [AddEditToolDialog Integration](#addedittooldialog-integration)
9. [home_page_support/ Refactoring](#home_page_support-refactoring)
10. [Phase 4 Implementation Checklist](#phase-4-implementation-checklist)
11. [Parity Test Strategy](#parity-test-strategy)
12. [Success Criteria](#success-criteria)

---

## Overview & Goals

### Problem Statement

HomePage (2,223L) contains monolithic UI orchestration mixed with tool-specific logic:
- Catalog list rendering (delegated to ToolCatalogDelegate)
- Filter UI (toolbar search, type filter, head filter)
- Detail panel display (currently inline, 400+ lines)
- Selector context management (for Setup Manager integration)
- Preview management (detached and inline 3D STL preview)
- Batch edit operations (copy, delete, group edit)
- Excel export/import coordination

**Duplication**: 72-85% overlap with jaw_page.py for the same patterns.

### Solution Architecture

Inherit from CatalogPageBase (Phase 3 platform abstraction) to:
1. **Reduce HomePage to ~400L** by delegating common catalog logic to base class
2. **Preserve all tool-specific behavior** in abstract method overrides
3. **Extract tool-specific UI builders** into home_page_support/ modules
4. **Enable jaw_page.py migration** in Phase 5 using the same patterns
5. **Maintain parity** with identical user workflows and DB compatibility

### Phase 4 Outcomes

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| HomePage lines | 2,223L | ~400L | Implementation pending |
| Duplicated patterns | 72-85% | 0% | Via platform inheritance |
| Catalog logic (shared) | 0L | ~600-800L (in base) | Phase 3 complete |
| Tool-specific logic (remaining) | 2,223L | ~400L | This phase |
| Parity tests | Baseline 13/13 | PASS 13/13 | Required gate |
| Import violations | 0 | 0 | Must stay clean |

---

## Current HomePage State Analysis

### File Structure (2,223 lines)

```
HomePage (QWidget)
├── __init__(tool_service, export_service, settings_service, ...)
├── _build_ui()  [~500L in one method]
│   ├── Filter frame with search, type filter, preview button
│   ├── Splitter with catalog list + detail panel
│   ├── Detail panel (scroll area with dynamic fields)
│   └── Selector card (for Setup Manager context)
├── Catalog Logic [~300L]
│   ├── refresh_list()  [loads tools, applies filters, refreshes model]
│   ├── _on_current_changed()  [selection tracking]
│   ├── _on_double_clicked()  [detail pane toggle]
│   └── Tool model + QStandardItemModel management
├── Filter UI [~150L]
│   ├── _toggle_search()
│   ├── _on_type_changed()
│   ├── _clear_filter()
│   └── Type filter population
├── Detail Panel [~400L]
│   ├── populate_details(tool)  [renders tool info, components, preview]
│   ├── _build_components_panel()  [expandable component section]
│   ├── _build_preview_panel()  [STL preview embed + detached]
│   ├── Detail field builders (_build_detail_field, etc.)
│   └── Component rendering with spare parts
├── Selector Context [~350L]
│   ├── set_selector_context()  [activate/deactivate selector mode]
│   ├── _set_selector_panel_mode()  [switch between details/selector views]
│   ├── Selector state persistence (buckets by head/spindle)
│   ├── _toggle_selector_spindle()  [switch main/sub spindle]
│   ├── _rebuild_selector_assignment_list()  [render assigned tools]
│   └── Selector edit/move/delete operations
├── Batch Operations [~200L]
│   ├── add_tool() / edit_tool() / delete_tool() / copy_tool()
│   ├── _batch_edit_tools() / _group_edit_tools()  [delegates to support modules]
│   └── Action button management
├── Preview Management [~150L]
│   ├── toggle_preview_window()  [delegate to detached_preview helper]
│   ├── _sync_detached_preview()
│   ├── _load_preview_content()
│   └── Warmup engine initialization
└── Helper Methods [~200L]
    ├── _t() [translation function]
    ├── Tool ID normalization (_strip_tool_id_prefix, etc.)
    ├── UI utilities (selection tracking, filter application)
    └── Event handling (keyPressEvent, eventFilter)
```

### Key State Variables (37 instance variables)

**Catalog State**:
- `tool_service`, `export_service`, `settings_service`
- `current_tool_id`, `current_tool_uid`
- `_tool_model` (QStandardItemModel with ROLE_TOOL_ID, ROLE_TOOL_UID, ROLE_TOOL_DATA, ROLE_TOOL_ICON)

**Filter State**:
- `_head_filter_value` (default 'HEAD1/2')
- `_external_head_filter` (optional external binding)
- `_master_filter_ids`, `_master_filter_active` (for Setup Manager context)
- `type_filter` (QComboBox with tool types)
- `search` (QLineEdit for catalog search)

**Detail Panel State**:
- `_details_hidden` (boolean toggle)
- `detail_container`, `detail_card`, `detail_scroll`, `detail_panel`, `detail_layout`
- `_last_splitter_sizes` (for restoring splitter position)

**Selector Context State**:
- `_selector_active` (boolean activation flag)
- `_selector_head`, `_selector_spindle` (current selector target)
- `_selector_panel_mode` ('details' or 'selector')
- `_selector_assigned_tools` (list of tool dicts)
- `_selector_assignments_by_target` (dict keyed by "HEAD:SPINDLE")
- `_selector_saved_details_hidden` (for restoring detail state on deactivate)

**Preview State**:
- `_detached_preview_dialog`, `_detached_preview_widget`
- `_inline_preview_warmup` (lazy-loaded widget)
- `_detached_measurements_enabled`, `_detached_measurement_filter`
- `_close_preview_shortcut`

**UI References** (~15 QWidget instances):
- Toolbar buttons: `search_toggle`, `toggle_details_btn`, `filter_icon`, `preview_window_btn`
- Filters: `type_filter`, `toolbar_title_label`, `search`
- Central list: `tool_list`, `_tool_delegate`
- Detail components: `detail_container`, `detail_card`, `detail_scroll`, `detail_panel`
- Selector components: `selector_card`, `selector_scroll`, `selector_panel`, `selector_*_btn`, `selector_assignment_list`
- Action buttons: `add_btn`, `edit_btn`, `delete_btn`, `copy_btn`, `module_toggle_btn`

---

## CatalogPageBase Platform Contract

### Class Definition

```python
# shared/ui/platforms/catalog_page_base.py

class CatalogPageBase(QWidget, ABC):
    """
    Abstract base for catalog pages supporting search, filter, selection, batch operations.
    
    Signals:
      item_selected(str, int)  — (item_id: str, uid: int) when user clicks an item
      item_deleted(str)        — (item_id: str) after successful deletion
    """
    
    item_selected = Signal(str, int)
    item_deleted = Signal(str)
    
    def __init__(self, parent=None, item_service=None, translate=None):
        """Initialize and call _build_ui() automatically."""
        super().__init__(parent)
        self.item_service = item_service
        self._translate = translate or (lambda k, d=None, **_: d or '')
        self._current_item_id = None
        self._current_item_uid = None
        self._item_model = None
        self._build_ui()
```

### Required Abstract Methods

#### 1. `create_delegate() → QAbstractItemDelegate`

**Purpose**: Supply domain-specific list item rendering.

**Implementation for HomePage**:
```python
def create_delegate(self) -> QAbstractItemDelegate:
    """Return a ToolCatalogDelegate configured for tool rendering."""
    return ToolCatalogDelegate(
        parent=self.list_view,
        view_mode=self.view_mode,
        translate=self._t,
    )
```

**Parameters**: None  
**Returns**: New delegate instance (never None)  
**Current HomePage pattern**: `_tool_delegate = ToolCatalogDelegate(...)` in _build_ui()

---

#### 2. `get_item_service() → Any`

**Purpose**: Return the service instance for catalog queries.

**Implementation for HomePage**:
```python
def get_item_service(self):
    """Return tool_service (already initialized in __init__)."""
    return self.tool_service
```

**Parameters**: None  
**Returns**: Service with list_items(search, **filters) → list[dict]  
**Current HomePage pattern**: `self.tool_service` attribute

---

#### 3. `build_filter_pane() → QWidget`

**Purpose**: Create domain-specific filter UI with `get_filters()` method.

**Implementation for HomePage**:
```python
def build_filter_pane(self) -> QWidget:
    """Return a frame containing type filter + head filter dropdowns."""
    frame = QFrame()
    layout = QHBoxLayout(frame)
    
    # Type filter
    self.type_filter = QComboBox()
    self._build_tool_type_filter_items()
    self.type_filter.currentIndexChanged.connect(self.refresh_catalog)
    layout.addWidget(self.type_filter)
    
    # Head filter (if external binding not set)
    # Note: may be bound externally via bind_external_head_filter()
    
    layout.addStretch(1)
    return frame

def get_filters(self) -> dict:
    """Return current filter state as dict."""
    return {
        'tool_head': self._selected_head_filter(),
        'tool_type': self.type_filter.currentData() or 'All',
    }
```

**Note**: The filter pane is now optional; if omitted, CatalogPageBase provides a minimal pane.

---

#### 4. `apply_filters(filters: dict) -> list[dict]`

**Purpose**: Query service with search + domain filters; return filtered items.

**Parameters**:
```python
filters = {
    'search': str,        # from search bar
    'tool_head': str,     # 'HEAD1', 'HEAD2', or 'HEAD1/2'
    'tool_type': str,     # tool type name or 'All'
}
```

**Implementation for HomePage**:
```python
def apply_filters(self, filters: dict) -> list[dict]:
    """Query tool_service with filters; apply selector + master filters; return tools."""
    tools = self.tool_service.list_tools(
        search=filters.get('search', ''),
        tool_type=filters.get('tool_type', 'All'),
        tool_head=filters.get('tool_head', 'HEAD1/2'),
    )
    
    # Apply selector spindle filter (if selector active)
    if self._selector_active:
        tools = [t for t in tools if self._tool_matches_selector_spindle(t)]
    
    # Apply master filter (Setup Manager context)
    if self._master_filter_active:
        tools = [t for t in tools if str(t.get('id', '')).strip() in self._master_filter_ids]
    
    # Apply view mode filter
    tools = [t for t in tools if self._view_match(t)]
    
    return tools
```

**Returns**: list[dict] with 'id', 'uid', ...other fields

---

### CatalogPageBase Concrete Methods

#### `refresh_catalog() → None`

Reloads items from service; refreshes list view; restores selection.

**Current HomePage equivalent**: `refresh_list()`

```python
def refresh_catalog(self):
    """Reload items from service and refresh UI."""
    # Collect filters from pane + search
    filters_state = self.filter_pane.get_filters() if hasattr(...) else {}
    search_text = self.search_input.text().strip()
    
    # Query service
    items = self.apply_filters({'search': search_text, **filters_state})
    
    # Update model with items (marked by id/uid/data/icon roles)
    self._item_model.blockSignals(True)
    self._item_model.clear()
    for item in items:
        qitem = QStandardItem()
        qitem.setData(item.get('id'), CATALOG_ROLE_ID)
        qitem.setData(item.get('uid'), CATALOG_ROLE_UID)
        qitem.setData(item, CATALOG_ROLE_DATA)
        qitem.setData(item_icon, CATALOG_ROLE_ICON)
        self._item_model.appendRow(qitem)
    self._item_model.blockSignals(False)
    
    # Restore selection by uid or id
    # ...
```

---

## Migration Architecture

### File Structure After Migration

```
Tools and jaws Library/ui/
├── home_page.py  [~400L]
│   ├── HomePage(CatalogPageBase)
│   ├── __init__() [initialize services, state for selector/preview]
│   ├── _initialize_tool_service()  [moved from __init__ constructor]
│   ├── create_delegate() → ToolCatalogDelegate
│   ├── get_item_service() → tool_service
│   ├── build_filter_pane() → QFrame with type filter
│   ├── apply_filters(filters) → list[tools]
│   ├── Tool-specific overrides:
│   │   ├── set_selector_context()
│   │   ├── _tool_matches_selector_spindle()
│   │   ├── toggle_details()  / show_details() / hide_details()
│   │   ├── add_tool() / edit_tool() / delete_tool() / copy_tool()
│   │   └── Preview, batch edit, detail panel orchestration
│   └── Private helpers for tool-specific logic
│
├── home_page_support/  [expanded]
│   ├── __init__.py
│   ├── batch_actions.py  [batch_edit_tools, group_edit_tools]
│   ├── detail_fields_builder.py  [_build_detail_field, _add_two_box_row, etc.]
│   ├── detail_layout_rules.py  [apply_tool_detail_layout_rules]
│   ├── components_panel_builder.py  [_build_components_panel, spare/component rendering]
│   ├── preview_panel_builder.py  [_build_preview_panel]
│   ├── detached_preview.py  [all detached preview logic]
│   ├── selector_*  [selector state and UI coordination]
│   ├── topbar_builder.py  [filter UI + toolbar construction]
│   ├── detail_layout_rules.py  [field layout for tools by type]
│   └── ...remaining support modules
│
└── tool_catalog_delegate.py  [unchanged, ~290L]
    └── ToolCatalogDelegate renders catalog items via CatalogDelegate
```

### Inheritance Chain

```
QWidget
  │
  ├─ CatalogPageBase (shared/ui/platforms/)
  │    │
  │    └─ HomePage (Tools and jaws Library/ui/)
  │         └─ Tool-specific behavior via overrides
  │
  └─ (future) JawPage → CatalogPageBase
      └─ Jaw-specific behavior via overrides
```

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ HomePage (Tool Library Root App)                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Services Layer:                                             │
│  • tool_service (list_tools, get_tool, save_tool, delete)   │
│  • export_service (import_from_xlsx, export_to_xlsx)        │
│  • settings_service (get_setting, set_setting)              │
│                                                              │
│  CatalogPageBase (shared platform layer)                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ refresh_catalog()                                    │  │
│  │  • calls apply_filters()                             │  │
│  │  • updates _item_model with items                    │  │
│  │  • restores selection                                │  │
│  │                                                      │  │
│  │ Common UI: filter_pane + search + list_view         │  │
│  │  • delegates to create_delegate()                    │  │
│  │  • emits item_selected(id, uid) on click             │  │
│  │  • emits item_deleted(id) on delete                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                        ↑                                     │
│                    Overridden by:                            │
│                                                              │
│  HomePage-Specific Overrides:                               │
│  • create_delegate() → ToolCatalogDelegate                  │
│  • get_item_service() → tool_service                        │
│  • build_filter_pane() → type filter + head filter UI       │
│  • apply_filters(filters) → list_tools + selector/master    │
│                                                              │
│  Tool-Specific Feature Layers (not in base):                │
│  • Detail Panel (show_details / populate_details)           │
│  • Selector Context (setup integration)                     │
│  • Preview Management (detached/inline STL)                 │
│  • Batch Operations (edit, delete, copy, group edit)        │
│  • Excel Export/Import (via export_service)                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Abstract Method Implementations

### 1. `create_delegate()` Implementation

```python
# In HomePage

def create_delegate(self) -> QAbstractItemDelegate:
    """
    Create and return a ToolCatalogDelegate for rendering tool list items.
    
    Called by CatalogPageBase._build_ui() after list_view is created.
    """
    return ToolCatalogDelegate(
        parent=self.list_view,
        view_mode=self.view_mode,
        translate=self._t,
    )
```

**Notes**:
- Delegate already exists (no changes needed)
- Pass `view_mode` and `translate` callback as before
- Base class sets this as delegate for `self.list_view`

---

### 2. `get_item_service()` Implementation

```python
# In HomePage

def get_item_service(self):
    """Return the tool service for catalog queries."""
    return self.tool_service
```

**Notes**:
- Already initialized in `__init__(tool_service, ...)`
- No additional logic needed
- Used by base class `refresh_catalog()` when calling `apply_filters()`

---

### 3. `build_filter_pane()` Implementation

```python
# In HomePage

def build_filter_pane(self) -> QWidget:
    """
    Build the filter UI pane containing type filter + optional head filter.
    
    Must return a QWidget with get_filters() method returning dict.
    """
    frame = QFrame()
    frame.setObjectName('toolFilterPane')
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    
    # Type filter (dropdown with tool types)
    self.type_filter = QComboBox()
    self.type_filter.setObjectName('topTypeFilter')
    self._build_tool_type_filter_items()
    self.type_filter.currentIndexChanged.connect(self.refresh_catalog)
    layout.addWidget(self.type_filter, 0)
    
    layout.addStretch(1)
    
    # Return wrapper with get_filters() method
    frame.get_filters = self._get_filter_pane_state
    return frame

def _get_filter_pane_state(self) -> dict:
    """Return current filter state from pane."""
    return {
        'tool_head': self._selected_head_filter(),
        'tool_type': self.type_filter.currentData() or 'All',
    }
```

**Current HomePage pattern**: Filters in toolbar, not dedicated pane.  
**Migration strategy**: Extract type filter into `build_filter_pane()`, keep head filter external (via `bind_external_head_filter()`).

---

### 4. `apply_filters()` Implementation

```python
# In HomePage

def apply_filters(self, filters: dict) -> list[dict]:
    """
    Query tool_service with filters; apply domain-specific constraints.
    
    Args:
        filters: {'search': str, 'tool_head': str, 'tool_type': str}
    
    Returns:
        list[dict] of tools matching all filters
    """
    search_text = filters.get('search', '').strip()
    tool_type = filters.get('tool_type', 'All')
    tool_head = filters.get('tool_head', 'HEAD1/2')
    
    # Query service
    tools = self.tool_service.list_tools(
        search=search_text,
        tool_type=tool_type,
        tool_head=tool_head,
    )
    
    # Apply selector spindle constraint (if selector active)
    if self._selector_active:
        tools = [
            tool for tool in tools
            if self._tool_matches_selector_spindle(tool)
        ]
    
    # Apply master filter (Setup Manager context)
    if self._master_filter_active:
        tools = [
            tool for tool in tools
            if str(tool.get('id', '')).strip() in self._master_filter_ids
        ]
    
    # Apply view mode filter (holders/inserts/assemblies/etc)
    tools = [tool for tool in tools if self._view_match(tool)]
    
    return tools
```

**Logic moved from `refresh_list()`**: Filter application is now centralized in abstract method.

---

## Signal Mapping Strategy

### Current HomePage Signal Pattern

HomePage does **not currently emit signals**. Instead, it:
1. Stores selection state in `current_tool_id` and `current_tool_uid`
2. Uses external methods for detail population: `populate_details(tool)`
3. Broadcasts deletions via external state or method calls

### CatalogPageBase Signal Contract

```python
# Signals defined in CatalogPageBase

item_selected = Signal(str, int)  # (item_id: str, uid: int)
item_deleted = Signal(str)        # (item_id: str)
```

### Implementation in HomePage

HomePage **should emit signals** at appropriate lifecycle points:

#### Signal 1: `item_selected` – On Selection Change

```python
# In HomePage, override _on_current_changed() behavior

def _on_current_changed(self, current: QModelIndex, previous: QModelIndex):
    """Called when list selection changes."""
    if not current.isValid():
        self.current_tool_id = None
        self.current_tool_uid = None
        self.populate_details(None)
        if self.preview_window_btn.isChecked():
            self._close_detached_preview()
        return
    
    self.current_tool_id = current.data(ROLE_TOOL_ID)
    self.current_tool_uid = current.data(ROLE_TOOL_UID)
    
    # EMIT SIGNAL: item_selected
    self.item_selected.emit(self.current_tool_id, self.current_tool_uid or 0)
    
    # Update UI state
    self._update_selection_count_label()
    if not self._details_hidden:
        tool = self._get_selected_tool()
        self.populate_details(tool)
    if self.preview_window_btn.isChecked():
        self._sync_detached_preview(show_errors=False)
```

#### Signal 2: `item_deleted` – After Deletion

```python
# In HomePage.delete_tool()

def delete_tool(self):
    """Delete selected tool(s) with confirmation."""
    if not self.current_tool_id:
        QMessageBox.information(
            self,
            self._t('tool_library.message.delete', 'Delete tool'),
            self._t('tool_library.message.select_tool_first', 'Select a tool first.'),
        )
        return
    
    uids = self._selected_tool_uids()
    count = len(uids)
    
    # Confirm deletion
    reply = QMessageBox.question(
        self,
        self._t('tool_library.message.confirm_delete', 'Confirm Delete'),
        self._t(
            'tool_library.message.delete_count',
            'Delete {count} tool(s)?',
            count=count,
        ),
    )
    
    if reply != QMessageBox.Yes:
        return
    
    # Perform deletion
    for uid in uids:
        tool = self.tool_service.get_tool_by_uid(uid)
        if tool:
            tool_id = tool.get('id', '')
            self.tool_service.delete_tool(tool_id)
            
            # EMIT SIGNAL: item_deleted for each tool
            self.item_deleted.emit(tool_id)
    
    # Refresh list and clear selection
    self._clear_selection()
    self.refresh_catalog()
```

### External Listeners (Example Usage)

```python
# In main_window.py or parent that creates HomePage

page = HomePage(tool_service, export_service, settings_service)

# Listen for selection changes
page.item_selected.connect(self._on_tool_selected)

# Listen for deletions (e.g., to update Setup Manager assignments)
page.item_deleted.connect(self._on_tool_deleted)

def _on_tool_selected(self, tool_id: str, uid: int):
    # Update detail view, preview, etc.
    print(f"Tool selected: {tool_id} (uid={uid})")

def _on_tool_deleted(self, tool_id: str):
    # Remove from any Setup Manager assignments, etc.
    print(f"Tool deleted: {tool_id}")
```

---

## Tool Head Selector State Preservation

### Current Selector Architecture

HomePage maintains complex selector state for Setup Manager integration:

```python
self._selector_active: bool              # Is selector active?
self._selector_head: str                 # Target HEAD ('HEAD1', 'HEAD2')
self._selector_spindle: str              # Target spindle ('main', 'sub')
self._selector_assigned_tools: list      # Current tool assignments
self._selector_assignments_by_target: dict  # Buckets by "HEAD:SPINDLE" key
self._selector_saved_details_hidden: bool  # Restore detail state on deactivate
```

### Selector State Methods (No Changes)

These methods **remain in HomePage** (tool-specific selector logic):

```python
def set_selector_context(
    self,
    active: bool,
    head: str = '',
    spindle: str = '',
    initial_assignments: list[dict] | None = None,
    initial_assignment_buckets: dict[str, list[dict]] | None = None,
) -> None:
    """
    Activate or deactivate selector mode with tool assignments.
    
    Called by Setup Manager when opening tool selector dialog.
    """
    # ... existing logic ...

def update_selector_head(self, head: str) -> None:
    """Update the selector HEAD target (called when HEAD dropdown changes in Setup Manager)."""
    # ... existing logic ...

def selector_assigned_tools_for_setup_assignment(self) -> list[dict]:
    """Return persisted tools with head/spindle metadata for setup assignment."""
    # ... existing logic ...
```

**Key insight**: Selector state is **orthogonal** to CatalogPageBase inheritance. HomePage retains all selector logic as tool-specific feature, independent of inherited catalog behavior.

### Selector-Catalog Interaction

The selector state **affects** `apply_filters()` via spindle constraint:

```python
def apply_filters(self, filters: dict) -> list[dict]:
    """Query and apply filters."""
    tools = self.tool_service.list_tools(...)
    
    # Apply selector spindle filter (if selector active)
    if self._selector_active:
        tools = [
            tool for tool in tools
            if self._tool_matches_selector_spindle(tool)
        ]
    
    return tools
```

This ensures the catalog **respects** selector context without duplicating logic in base class.

---

## AddEditToolDialog Integration

### Current State

AddEditToolDialog (1,280L) is a complex QDialog with:
- Multiple tabs (General, Components, Spare Parts, Models)
- Field validation, event handling
- EditorDialogMixin and ModelTableMixin base classes

### Phase 3: EditorDialogBase Platform Contract

Phase 3 created EditorDialogBase (shared abstract base), but AddEditToolDialog **is not yet migrated** to use it.

### Phase 4 Strategy: Non-Breaking Coexistence

For Phase 4 scope, **do NOT refactor AddEditToolDialog**:
1. HomePage will continue to instantiate AddEditToolDialog as-is
2. AddEditToolDialog remains stable (no changes)
3. Future Phase (post-4): AddEditToolDialog migration to EditorDialogBase

### HomePage-AddEditToolDialog Integration

```python
# In HomePage

def add_tool(self):
    """Open AddEditToolDialog in 'add' mode."""
    dlg = AddEditToolDialog(
        parent=self,
        tool=None,  # None = new tool
        tool_service=self.tool_service,
        translate=self._t,
    )
    if dlg.exec() == QDialog.Accepted:
        self.refresh_catalog()  # Reload and show new tool
        # Selection auto-restored by refresh_catalog()

def edit_tool(self):
    """Open AddEditToolDialog in 'edit' mode."""
    tool = self._get_selected_tool()
    if not tool:
        return
    dlg = AddEditToolDialog(
        parent=self,
        tool=tool,  # Existing tool data
        tool_service=self.tool_service,
        translate=self._t,
    )
    if dlg.exec() == QDialog.Accepted:
        self.refresh_catalog()  # Reload (changes persisted by service)
        # Selection re-selected by uid

def copy_tool(self):
    """Show 'add' dialog with selected tool data as template."""
    tool = self._get_selected_tool()
    if not tool:
        return
    tool_copy = dict(tool)
    tool_copy['id'] = ''  # Clear ID so new tool gets unique ID
    dlg = AddEditToolDialog(
        parent=self,
        tool=tool_copy,
        tool_service=self.tool_service,
        translate=self._t,
    )
    if dlg.exec() == QDialog.Accepted:
        self.refresh_catalog()

def _batch_edit_tools(self, uids: list[int]):
    """Open batch edit dialog for multiple tools."""
    from ui.home_page_support.batch_actions import batch_edit_tools
    batch_edit_tools(self, uids)
```

### Signal Emission After Dialog Accept

```python
# Optional: Emit item_selected after successful edit

def edit_tool(self):
    """Edit selected tool; emit item_selected if data changed."""
    tool = self._get_selected_tool()
    if not tool:
        return
    
    original_uid = tool.get('uid')
    
    dlg = AddEditToolDialog(...)
    if dlg.exec() == QDialog.Accepted:
        self.refresh_catalog()
        
        # Find and re-select by uid
        for idx in range(self._item_model.rowCount()):
            item = self._item_model.item(idx, 0)
            if item.data(CATALOG_ROLE_UID) == original_uid:
                self.list_view.setCurrentIndex(item.index())
                # Emit signal (handled in _on_current_changed)
                break
```

---

## home_page_support/ Refactoring

### Current file organization (14 support modules)

```
home_page_support/
├── __init__.py  [bulk imports/exports]
├── batch_actions.py  [batch_edit_tools, group_edit_tools]
├── bottom_bars_builder.py  [action button bars]
├── catalog_list_widgets.py  [ToolCatalogListView, ToolAssignmentListWidget]
├── components_panel_builder.py  [detail panel component section]
├── detached_preview.py  [detached preview dialog + logic]
├── detail_fields_builder.py  [field rendering, detail panel helpers]
├── detail_layout_rules.py  [layout by tool type]
├── dialog_helpers.py  [confirmation, text input dialogs]
├── preview_panel_builder.py  [inline STL preview embed]
├── selector_actions.py  [selector move/add/remove logic]
├── selector_assignment_state.py  [selector state helpers]
├── selector_card_builder.py  [selector UI construction]
├── selector_model.py  [selector list model]
├── topbar_builder.py  [toolbar + filter UI construction]
└── __pycache__/
```

### Refactoring Plan (Phase 4)

**Extract from HomePage to home_page_support/**:

#### 1. Detail Panel Rendering → `detail_panel_builder.py` (NEW)

Move from HomePage:
- `populate_details(tool)`
- `_build_components_panel(tool, support_parts)`
- `_build_preview_panel(stl_path)`
- `_build_detail_field(label, value, multiline=False)`
- Component rendering helpers

Target: ~200L in new module

```python
# home_page_support/detail_panel_builder.py

def populate_detail_panel(
    home_page: 'HomePage',
    tool: dict | None,
) -> None:
    """Clear detail layout and populate with tool data."""
    home_page._clear_details()
    if not tool:
        home_page.detail_layout.addWidget(
            _build_placeholder_details(home_page)
        )
        return
    
    # Build detail card...
    card = _build_detail_card(home_page, tool)
    home_page.detail_layout.addWidget(card)

def _build_detail_card(home_page: 'HomePage', tool: dict) -> QFrame:
    """Build the main detail card with header, info grid, components, preview."""
    # ... (content from HomePage.populate_details)
```

#### 2. Toolbar/Filter UI → Expand `topbar_builder.py`

Move from HomePage._build_ui():
- `_rebuild_filter_row()` [already delegated, no changes]
- `_build_tool_type_filter_items()` [already delegated]
- Toolbar button creation (search, details, filter, preview, type-dropdown)

Target: No new lines (already separated)

#### 3. Selector UI → Already Separated

Selector building already in `selector_card_builder.py` and coordinator modules.  
**No additional extraction needed.**

#### 4. Preview Logic → Already Separated

All detached preview logic already in `detached_preview.py`.  
Inline preview remains inline (small, ~10L).

#### 5. Batch Edit → Already Separated

`batch_actions.py` already has `batch_edit_tools`, `group_edit_tools`.  
**No additional extraction needed.**

### Post-Refactoring Import in HomePage

```python
# In homepage.py (new pattern)

from ui.home_page_support.detail_panel_builder import (
    populate_detail_panel,
    _build_placeholder_details,
)
from ui.home_page_support import (
    # ... existing imports ...
    # ... new imports ...
)

# In HomePage method

def toggle_details(self):
    """Show or hide detail panel."""
    if self._details_hidden:
        if not self.current_tool_id:
            QMessageBox.information(
                self,
                self._t('tool_library.message.show_details', 'Show details'),
                self._t('tool_library.message.select_tool_first', 'Select a tool first.'),
            )
            return
        tool = self._get_selected_tool()
        populate_detail_panel(self, tool)  # NEW: delegated
        self.show_details()
    else:
        self.hide_details()
```

### home_page_support/__init__.py Updates

Add re-exports for new builders:

```python
# home_page_support/__init__.py

from .detail_panel_builder import (
    populate_detail_panel,
    _build_placeholder_details,
)

__all__ = [
    # ... existing ...
    'populate_detail_panel',
    '_build_placeholder_details',
]
```

---

## Phase 4 Implementation Checklist

### Pre-Implementation (Design & Prep)

- [x] Platform layer (Phase 3) complete with CatalogPageBase, EditorDialogBase, SelectorState
- [x] Architecture document created (this file)
- [x] Signal mapping designed
- [x] Selector state preservation strategy confirmed
- [x] home_page_support/ refactoring plan defined

### Implementation Pass 1: Class Structure

- [ ] **Create HomePage inheritance chain**
  - [ ] Add `(CatalogPageBase)` to HomePage class declaration
  - [ ] Update `__init__()` signature to call `super().__init__()`
  - [ ] Preserve service initialization in `__init__()`

- [ ] **Implement 4 abstract methods**
  - [ ] `create_delegate()` → return ToolCatalogDelegate
  - [ ] `get_item_service()` → return tool_service
  - [ ] `build_filter_pane()` → return type filter QWidget
  - [ ] `apply_filters(filters)` → query service + constraints

- [ ] **Remove duplicated catalog logic from _build_ui()**
  - [ ] Remove custom list_view construction (handled by base._build_ui())
  - [ ] Remove search_input construction (handled by base)
  - [ ] Remove filter_pane construction (delegated to build_filter_pane())
  - [ ] Remove model setup (handled by base)
  - [ ] Remove delegate setup (handled by base)

### Implementation Pass 2: Signal Emission

- [ ] **Wire item_selected signal**
  - [ ] Override `_on_current_changed()` to emit `item_selected(id, uid)`
  - [ ] Preserve existing detail panel + preview logic

- [ ] **Wire item_deleted signal**
  - [ ] In `delete_tool()`, emit `item_deleted(id)` for each deleted tool
  - [ ] Verify signal emitted after service.delete_tool() succeeds

- [ ] **Test signal listeners** (manual)
  - [ ] Connect external slot to item_selected
  - [ ] Connect external slot to item_deleted
  - [ ] Verify signals fire with correct args

### Implementation Pass 3: Selector & Context

- [ ] **Preserve selector state**
  - [ ] No changes to `_selector_*` instance variables
  - [ ] No changes to `set_selector_context()` method
  - [ ] No changes to `update_selector_head()` method
  - [ ] Selector state integration with platform layer: ✓ (via apply_filters)

- [ ] **Verify selector filtering**
  - [ ] `apply_filters()` respects `_selector_active` flag
  - [ ] Spindle constraint in `_tool_matches_selector_spindle()` still works
  - [ ] Master filter still works with platform refresh

### Implementation Pass 4: Detail Panel Extraction

- [ ] **Create detail_panel_builder.py**
  - [ ] Define `populate_detail_panel(home_page, tool)`
  - [ ] Move `populate_details()` logic
  - [ ] Move `_build_components_panel()`, `_build_preview_panel()`, `_build_detail_field()`
  - [ ] Move component rendering helpers
  - [ ] Target: ~200L

- [ ] **Update home_page_support/__init__.py**
  - [ ] Add re-exports for new module
  - [ ] Update __all__

- [ ] **Update HomePage imports**
  - [ ] Import `populate_detail_panel` from support module
  - [ ] Update `populate_details()` → call `populate_detail_panel(self, tool)`
  - [ ] Remove moved method implementations

### Implementation Pass 5: Tooling & Governance

- [ ] **Update import_path_checker.py**
  - [ ] Verify no disallowed cross-app imports introduced
  - [ ] Run: `python scripts/import_path_checker.py` → exit code 0

- [ ] **Update duplicate_detector.py**
  - [ ] Verify home_page.py lines reduced (target: ~400±50L)
  - [ ] Run: `python scripts/duplicate_detector.py` → lines < 2000

- [ ] **Run smoke_test.py**
  - [ ] Tool Library app imports correctly
  - [ ] Setup Manager app imports correctly
  - [ ] Both apps start without errors
  - [ ] Run: `python scripts/smoke_test.py` → exit code 0

### Implementation Pass 6: Testing & Parity

- [ ] **Unit testing (if parity tests provided)**
  - [ ] Execute parity test suite
  - [ ] Baseline: 13/13 tests PASS
  - [ ] Target: 13/13 tests PASS (no regressions)

- [ ] **Manual parity verification**
  - [ ] Add tool → appears in catalog + UI refreshes ✓
  - [ ] Edit tool → catalog updates + detail refreshes ✓
  - [ ] Delete tool → removed from catalog ✓
  - [ ] Copy tool → new tool created with template data ✓
  - [ ] Search → filtering works as before ✓
  - [ ] Type filter → filtering by tool type works ✓
  - [ ] Double-click → details toggle works ✓
  - [ ] Preview toggle → STL preview works (inline + detached) ✓
  - [ ] Detached preview → 3D rotation/pan/zoom works ✓
  - [ ] Selector mode → assignment UI works (if applicable) ✓
  - [ ] Excel export → existing tools export correctly ✓
  - [ ] Excel import → import creates tools with correct fields ✓
  - [ ] IPC handoff → Setup Manager ↔ Tool Library integration works ✓

### Implementation Pass 7: Code Review & Finalization

- [ ] **Code review**
  - [ ] HomePage methods follow CatalogPageBase contract
  - [ ] No breaking changes to public API
  - [ ] Signal emission is consistent with contract
  - [ ] home_page_support/ modules are well-organized

- [ ] **Documentation updates**
  - [ ] Update AGENTS.md if canonical paths changed
  - [ ] Update README_AI.md with new HomePage structure
  - [ ] Leave breadcrumb in TOOL_EDITOR_REFACTOR.md pointing to this doc

- [ ] **Commit & Phase 4 completion**
  - [ ] Commit with message: "Phase 4: Migrate HomePage to CatalogPageBase (0% duplication)"
  - [ ] Update TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md:
    - Phase 4: 🟢 COMPLETE
    - Phase 5 ready to start (JawPage migration)

---

## Parity Test Strategy

### Test Scope (13 tests from Phase 0 baseline)

| Test Group | Current Count | Required Status | Strategy |
|------------|---------------|-----------------|----------|
| TOOLS CRUD | 4 tests | PASS | Verify add/edit/delete/copy still work |
| TOOLS Batch | 1 test | PASS | Verify batch edit, group edit still work |
| Search/Filter | 2 tests | PASS | Verify search + type filter still work |
| Detail Panel | 1 test | PASS | Verify detail pane toggle, populate still work |
| Preview | 2 tests | PASS | Verify inline + detached STL preview still work |
| Selector | 1 test | PASS | Verify selector context mode still works |
| Export | 1 test | PASS | Verify Excel export/import still work |
| IPC Handoff | 1 test | PASS | Verify Setup Manager ↔ Tool Library integration still works |
| **TOTAL** | **13 tests** | **13/13 PASS** |  |

### Pre-Migration Baseline (Phase 0 Status)

```
Test Result Baseline (Phase 0, April 13):
✅ TOOLS CRUD / Add → PASS
✅ TOOLS CRUD / Edit → PASS
✅ TOOLS CRUD / Delete → PASS
✅ TOOLS CRUD / Copy → PASS
✅ TOOLS Batch / Batch Edit → PASS
✅ Search / Text Search → PASS
✅ Search / Type Filter → PASS
✅ Detail Panel / Toggle & Populate → PASS
✅ Preview / Inline STL → PASS
✅ Preview / Detached Window → PASS
✅ Selector / Assign Tools → PASS
✅ Export / Excel Export → PASS
✅ IPC / Setup Manager Handoff → PASS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Result: 13/13 PASS
```

### Test Execution Model (Phase 4)

#### Step 1: Pre-Implementation Baseline Capture

```bash
cd "$WORKSPACE"
python tests/run_parity_tests.py --phase 4 --capture-baseline
# Output: phase4-baseline-results.json
```

**Expected**: 13/13 PASS (identical to Phase 0)

#### Step 2: Implementation + Incremental Testing

Run parity tests after each implementation pass:

```bash
# After Pass 1 (class structure)
python tests/run_parity_tests.py --phase 4 --verbose
# Expected: Some tests may fail if refresh logic broken

# After Pass 3 (selector integration)
python tests/run_parity_tests.py --phase 4 --verbose
# Expected: All tests should PASS

# After Pass 6 (final)
python tests/run_parity_tests.py --phase 4
# Final gate: 13/13 PASS required
```

#### Step 3: Post-Implementation Parity Comparison

```bash
python tests/run_parity_tests.py --phase 4 --compare-baseline
# Output:
# Baseline Results: 13/13 PASS
# Current Results:  13/13 PASS
# ✅ PARITY VERIFIED
```

### Manual Parity Verification Checklist

**For use during implementation and QA**:

```
TOOLS CRUD:
  ☐ Add Tool
    ☐ Open Add Tool dialog
    ☐ Fill fields (ID, Description, Type, etc.)
    ☐ Click Save
    ☐ Verify tool appears in catalog
    ☐ Verify unique UID generated
    ☐ Verify DB record created
  
  ☐ Edit Tool
    ☐ Select tool in catalog
    ☐ Click Edit Tool button
    ☐ Modify field (e.g., description)
    ☐ Click Save
    ☐ Verify catalog updates
    ☐ Verify detail panel refreshes
    ☐ Verify DB record updated
  
  ☐ Delete Tool
    ☐ Select tool in catalog
    ☐ Click Delete Tool button
    ☐ Confirm deletion
    ☐ Verify tool removed from catalog
    ☐ Verify DB record deleted
    ☐ Verify next/previous tool auto-selected
  
  ☐ Copy Tool
    ☐ Select tool in catalog
    ☐ Click Copy Tool button
    ☐ Verify copy dialog shows template data
    ☐ Modify fields as needed
    ☐ Click Save
    ☐ Verify new tool in catalog with unique ID
    ☐ Verify DB record created

Filter & Search:
  ☐ Text Search
    ☐ Click search icon to expand search field
    ☐ Type search text (e.g., "T123")
    ☐ Verify catalog auto-filters by search text
    ☐ Clear search
    ☐ Verify all tools reappear
  
  ☐ Type Filter
    ☐ Click type filter dropdown
    ☐ Select tool type (e.g., "Turning Mill")
    ☐ Verify catalog shows only matching type
    ☐ Click filter icon to clear
    ☐ Verify all types reappear

Detail Panel:
  ☐ Toggle Details
    ☐ Select tool from catalog
    ☐ Click Details button (or double-click tool)
    ☐ Verify detail pane appears with tool info
    ☐ Verify components section populated
    ☐ Click close button or Details button again
    ☐ Verify detail pane collapses
  
  ☐ Populate Details
    ☐ Select tool 1 in catalog
    ☐ Open details pane
    ☐ Select tool 2 in catalog
    ☐ Verify detail pane updates to show tool 2
    ☐ Verify components/preview for tool 2 shown

Preview:
  ☐ Inline STL Preview
    ☐ Select tool with STL model
    ☐ Open detail pane
    ☐ Verify preview embed shown
    ☐ Rotate model (left mouse drag)
    ☐ Pan model (right mouse drag)
    ☐ Zoom model (mouse wheel)
  
  ☐ Detached Preview Window
    ☐ Click preview window icon in toolbar
    ☐ Verify detached window opens
    ☐ Select different tool
    ☐ Verify preview updates to new tool's model
    ☐ Rotate/pan/zoom model in window
    ☐ Close detached window
    ☐ Verify window closed cleanly

Batch Operations:
  ☐ Batch Edit
    ☐ Select multiple tools (Shift+Click, Ctrl+Click)
    ☐ Verify selection count shown
    ☐ Click Edit button
    ☐ Verify batch edit dialog shown
    ☐ Modify common field (e.g., tool_head)
    ☐ Click "Apply to All"
    ☐ Verify all selected tools updated
  
  ☐ Group Edit
    ☐ Select multiple tools
    ☐ Right-click or menu → Group Edit
    ☐ Verify group edit dialog shown
    ☐ Entry count shown correctly
    ☐ Modify fields and save
    ☐ Verify all tools updated

Selector Mode (if applicable):
  ☐ Activate Selector
    ☐ (Setup Manager calls set_selector_context)
    ☐ Verify selector mode activated
    ☐ Verify tool catalog respects spindle constraint
    ☐ Verify selector UI shown
  
  ☐ Assign Tools
    ☐ Drag tool from catalog to selector list
    ☐ Verify tool added to selector list
    ☐ Reorder tools by dragging
    ☐ Verify order persisted
  
  ☐ Deactivate Selector
    ☐ Click Cancel or Done button
    ☐ Verify selector mode deactivated
    ☐ Verify normal catalog mode restored
    ☐ Verify detail pane visibility restored

Excel Export/Import:
  ☐ Export to Excel
    ☐ (Main menu or Tool Library UI)
    ☐ Select tools or export all
    ☐ Verify .xlsx file created
    ☐ Open file in Excel
    ☐ Verify headers and data correct
  
  ☐ Import from Excel
    ☐ Prepare .xlsx with tool data
    ☐ Import via Tool Library (Main menu)
    ☐ Verify tools created in catalog
    ☐ Verify DB records match Excel data

IPC Handoff (Setup Manager Integration):
  ☐ Handoff: Setup Manager → Tool Library
    ☐ Setup Manager opens Tool Library module
    ☐ Verify Tool Library page shown
    ☐ Verify state synced (head filter, etc.)
  
  ☐ Handoff: Tool Library → Setup Manager
    ☐ Tool Library selects tools for assignment
    ☐ Tool Library sends data to Setup Manager
    ☐ Verify Setup Manager receives tools
    ☐ Verify Setup Manager updates assignments
```

### Expected Results

**Pre-Implementation (baseline)**:
```
Phase 0 Parity Tests: 13/13 PASS
Timestamp: 2026-04-13
Build: Home page current (2,223L)
```

**Post-Implementation (Phase 4 gate)**:
```
Phase 4 Parity Tests: 13/13 PASS
Timestamp: 2026-04-?? (after implementation)
Build: Home page migrated (400L) + CatalogPageBase inherited
Duplication: 0% (no shared-code divergence with JawPage)
```

---

## Success Criteria

### Quantitative Metrics

| Metric | Target | Verification |
|--------|--------|----------------|
| **HomePage lines** | ~400 ± 50 | Count non-comment, non-blank lines in home_page.py |
| **Duplicated patterns** | 0% | Patterns now in base class; jaw_page.py can inherit identically |
| **Parity test pass rate** | 13/13 (100%) | Run `python tests/run_parity_tests.py` |
| **Import violations** | 0 | Run `python scripts/import_path_checker.py` → exit 0 |
| **File integrity** | No schema changes | Verify DB schema unchanged from Phase 0 |
| **Smoke tests** | 2/2 apps start | Run `python scripts/smoke_test.py` → exit 0 |

### Qualitative Criteria

| Criterion | Definition | Acceptance |
|-----------|-----------|-----------|
| **Behavioral parity** | User workflows identical pre/post migration | Manual verification of parity checklist (13 test groups) |
| **Code organization** | Logic properly divided between HomePage + base + support | HomePage = ~400L (catalog + tool-specific). Base = ~600-800L (shared platform). Support = extracted helpers. |
| **Signal contract** | item_selected, item_deleted signals emit correctly | Signals fire with correct args per spec. External listeners receive notifications. |
| **Selector isolation** | Selector state orthogonal to platform layer | Selector logic remains in HomePage; doesn't leak into CatalogPageBase. Platform agnostic to selector. |
| **Import compliance** | No cross-app imports, canonical shared paths only | import_path_checker.py passes. Only imports from `shared.*` and local app. |
| **Documentation** | Code changes clearly documented | AGENTS.md updated if canonical paths changed. Architecture doc (this file) complete. |

### Acceptance Gates (Go/No-Go)

**Gate 1: Class Structure** (Implementation Pass 1)
- ✅ HomePage inherits from CatalogPageBase
- ✅ 4 abstract methods implemented (create_delegate, get_item_service, build_filter_pane, apply_filters)
- ✅ No breaking changes to public API (backwards compatible)

**Gate 2: Signal Emission** (Implementation Pass 2)
- ✅ item_selected signal emits on selection change
- ✅ item_deleted signal emits on deletion
- ✅ External listeners can connect and receive signals

**Gate 3: Smoke Tests** (Implementation Pass 6)
- ✅ `python scripts/smoke_test.py` → exit code 0 (both apps start)
- ✅ Tool Library opens without errors
- ✅ Setup Manager opens without errors

**Gate 4: Parity Tests** (Implementation Pass 6)
- ✅ `python tests/run_parity_tests.py` → 13/13 PASS (no regressions)
- ✅ Manual verification of 13 test groups complete
- ✅ Database integrity maintained (no schema violations)

**Gate 5: Code Quality** (Implementation Pass 7)
- ✅ `python scripts/import_path_checker.py` → exit code 0 (no violations)
- ✅ `python scripts/duplicate_detector.py` → home_page.py < 500 lines
- ✅ Code review approved
- ✅ Documentation complete

**Phase 4 Complete When All 5 Gates Passed** ✅

---

## Appendix: File Size Projections

### Pre-Migration (Current)

```
home_page.py                          2,223L
├── Core logic                        1,900L
├── Detail panel + components           400L (to be extracted)
└── Helpers                             100L

home_page_support/                    (14 modules)
├── selector_*                          600L (already extracted)
├── batch_actions                        80L (already extracted)
├── preview                             150L (already extracted)
├── topbar_builder                       40L (already extracted)
└── ...other                            200L

Tool-specific code total             ~3,900L

CatalogPageBase (shared)               ~0L (Phase 3 deliverable)
```

### Post-Migration (Target)

```
home_page.py                          ~400L
├── Class header + init                 80L
├── 4 abstract methods (implementations) 120L
├── Signal emission                      30L
├── Selector state (tool-specific)      80L
├── Action methods (add/edit/delete/copy) 50L
└── Tool-specific helpers               40L

home_page_support/                    (new/expanded)
├── detail_panel_builder.py            200L (NEW, extracted)
├── ... existing modules              ~800L (unchanged)

Tool-specific code total             ~1,400L

CatalogPageBase (shared, Phase 3)    ~800L
```

### Reduction

- **HomePage**: 2,223L → ~400L (82% reduction ✅)
- **Tool-specific code**: ~3,900L → ~1,400L (64% reduction)
- **Consolidation**: 72-85% duplication eliminated via inheritance

---

## Appendix: Rollback Plan

If Phase 4 implementation encounters critical issues:

### Level 1: Local Revert (within HomePage)

If CatalogPageBase integration breaks catalog functionality:
1. Remove `(CatalogPageBase)` from class declaration
2. Restore duplicate `_build_ui()` logic from git history
3. Restore manual list view + model construction
4. Re-run parity tests

**Time to rollback**: ~30 minutes, zero impact

### Level 2: Partial Revert (home_page_support extraction)

If extracted modules cause issues:
1. Inline extracted methods back into HomePage
2. Remove detail_panel_builder.py import
3. Restore methods to pre-extracted state
4. Re-run parity tests

**Time to rollback**: ~1 hour, zero impact

### Level 3: Full Phase 4 Restart

If fundamental architecture incompatible:
1. Revert all Phase 4 commits
2. Document findings in architecture decision log
3. Re-evaluate CatalogPageBase design (Phase 3 review)
4. Plan Phase 4 redesign if needed

**Time to rollback**: ~2 hours, requires Phase 3 remediation

**Mitigation**: All changes committed incrementally with parity gates between each pass.

---

## Appendix: Timeline Estimate

| Phase | Task | Estimate | Notes |
|-------|------|----------|-------|
| 1 | Class structure + abstract methods | 2-4 hours | Straightforward; low risk |
| 2 | Signal emission + testing | 2-3 hours | Signal wiring + manual verification |
| 3 | Selector state + context preservation | 1-2 hours | Already isolated; minimal changes |
| 4 | Detail panel extraction | 3-5 hours | Refactoring + testing |
| 5 | Tooling + governance updates | 1-2 hours | Scripts + documentation |
| 6 | Parity testing + QA | 4-6 hours | Manual + automated gate testing |
| 7 | Code review + finalization | 1-2 hours | Review + documentation |
| **TOTAL** | | **14-24 hours** | 2-3 days with continuous integration |

---

**End of Phase 4 Migration Design Document**

For questions, refer to:
- CatalogPageBase contract: [shared/ui/platforms/catalog_page_base.py](shared/ui/platforms/catalog_page_base.py)
- Phase 3 completion proof: [TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md](TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md)
- Parity test design: [tests/test_shared_regressions.py](tests/test_shared_regressions.py)
