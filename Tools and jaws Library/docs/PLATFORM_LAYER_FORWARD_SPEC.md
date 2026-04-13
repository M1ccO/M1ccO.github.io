# Platform Layer Forward Specification

**Status**: Phase 1 Design Draft (April 13, 2026)  
**Format**: Markdown with Python pseudocode  
**Purpose**: Blueprint for Phase 3+ platform abstractions that both TOOLS and JAWS modules will inherit from, enabling zero-copy domain onboarding

> **For AI Agents**: This is NOT code to implement now. This is a forward spec: guidance for Phase 3 refactoring. Study this to understand how TOOLS and JAWS will be **restructured**, not how they currently work.

---

## Overview

### What is the Platform Layer?

A set of abstract base classes that capture common patterns across TOOLS and JAWS domains:

- **Catalog pages**: Browsing, searching, filtering, batch actions
- **Editor dialogs**: Form rendering, validation, persistence
- **Delegates**: Item painting, sizing, selection state
- **Selectors**: Dynamic lists (filter panes, spindle selectors)
- **Export/Import**: Excel I/O with domain-specific mapping

### Why Phase 3, Not Phase 1?

1. **De-risk**: Let TOOLS and JAWS remain independent in Phase 1-2; prove refactoring strategy doesn't break anything
2. **Stabilize contracts**: Define final API shape via TOOLS_MODULE_CONTRACT.md and JAWS_MODULE_CONTRACT.md first
3. **Minimize test burden**: Platform base classes verified once; domains inherit with minimal local tests
4. **Future-proof**: When Fixtures (new domain) arrives, new team drops in 1,000 lines of domain code + 50 lines of platform glue

### Phase Sequencing

```
Phase 0: Baseline ✅ (locked, no changes)
Phase 1: Domain Contracts (active) — Define TOOLS/JAWS APIs
Phase 2: Governance Artifacts — Module registries, ADRs, quality gates
Phase 3: Platform Layer (start ~July 2026) — Extract base classes
Phase 4: Domain Migration — Migrate TOOLS → inherit from platform
Phase 5: Domain Migration — Migrate JAWS → inherit from platform
Phase 6: Platform Hardening — Performance, edge cases, error handling
Phase 7: Export/Import Consolidation — Unified Excel I/O layer
Phase 8: Future Domain Template — Fixtures domain as proof-of-template
Phase 9+: Maintenance & Evolution
```

---

## Platform Layer Architecture

```
ui/
├── domain_modules/
│   ├── tools_module/     # Domain-specific (TOOLS)
│   │   ├── __init__.py
│   │   ├── home_page.py  # Inherits CatalogPageBase
│   │   ├── tool_editor_dialog.py  # Inherits EditorDialogBase
│   │   └── ...
│   │
│   └── jaws_module/      # Domain-specific (JAWS)
│       ├── __init__.py
│       ├── jaw_page.py   # Inherits CatalogPageBase
│       ├── jaw_editor_dialog.py  # Inherits EditorDialogBase
│       └── ...
│
├── platforms/            # Platform layer (shared abstractions)
│   ├── __init__.py
│   ├── catalog_page_base.py      # Abstract page orchestrator
│   ├── editor_dialog_base.py     # Abstract editor form
│   ├── catalog_delegate.py       # Abstract item painter
│   ├── selector_state.py         # Abstract filter/selector state
│   └── export_specification.py   # Export/import mapper
│
└── platform_glue/        # Adapters for Phase 3 transition
    ├── __init__.py
    └── legacy_preview_bridge.py  # Bridges old preview to new platform
```

---

## Core Abstractions

### 1. CatalogPageBase

**Purpose**: Common interface for all browsable catalog pages (TOOLS, JAWS, Fixtures, etc.)

**Responsibilities**:
- Create item delegate
- Execute searches/filters
- Render list view
- Manage selection state
- Emit item_selected, item_deleted signals

```python
class CatalogPageBase(QWidget):
    """Abstract base for catalog pages."""
    
    # Signals
    item_selected = Signal(str, int)  # (item_id, uid)
    item_deleted = Signal(str)  # (item_id)
    
    def __init__(self, parent=None, item_service=None, translate=None):
        super().__init__(parent)
        self.item_service = item_service
        self.translate = translate
        self._build_ui()
    
    # === Abstract Methods (Override in Subclass) ===
    
    def create_delegate(self) -> QAbstractItemDelegate:
        """Return domain-specific delegate (ToolCatalogDelegate, etc.)."""
        raise NotImplementedError
    
    def get_item_service(self) -> CatalogServiceBase:
        """Return item service (ToolService, JawService, etc.)."""
        raise NotImplementedError
    
    def build_filter_pane(self) -> QWidget:
        """Build domain-specific filter UI (tool head selector, spindle selector, etc.)."""
        raise NotImplementedError
    
    def apply_filters(self, filters: dict) -> List[dict]:
        """Query service with domain-specific filters."""
        raise NotImplementedError
    
    # === Common Implementation ===
    
    def _build_ui(self):
        """Construct common layout: filter pane + search bar + list view."""
        self.filter_pane = self.build_filter_pane()
        self.search_input = QLineEdit()
        self.search_input.textChanged.connect(self.refresh_catalog)
        
        self.list_view = QListView()
        self.list_view.setItemDelegate(self.create_delegate())
        self.list_view.clicked.connect(self._on_list_item_clicked)
        
        layout = QVBoxLayout(self)
        layout.addWidget(self.filter_pane)
        layout.addWidget(self.search_input)
        layout.addWidget(self.list_view)
        self.setLayout(layout)
    
    def refresh_catalog(self) -> None:
        """Reload and re-render catalog."""
        filters = self.filter_pane.get_filters()  # Domain-specific
        search_text = self.search_input.text()
        items = self.apply_filters({'search': search_text, **filters})
        
        self.list_model = QStandardItemModel()
        for item in items:
            self.list_model.appendRow(self._create_list_item(item))
        self.list_view.setModel(self.list_model)
    
    def get_selected_items(self) -> List[dict]:
        """Return list of currently selected items."""
        selected = []
        for index in self.list_view.selectedIndexes():
            # Reconstruct item dict from model
            selected.append(...)
        return selected
    
    def _on_list_item_clicked(self, index: QModelIndex) -> None:
        """Handle list item click; emit signal."""
        item_id = index.data(Qt.UserRole + 1)
        uid = index.data(Qt.UserRole + 2)
        self.item_selected.emit(item_id, uid)
    
    def apply_batch_action(self, action: str, items: List[dict]) -> None:
        """Batch operation (copy, delete, export, etc.)."""
        if action == 'delete':
            for item in items:
                self.item_service.delete_item(item['id'])
                self.item_deleted.emit(item['id'])
            self.refresh_catalog()
        # ... etc for copy, export
```

**Domain Subclass Example (HomePage for TOOLS)**:

```python
class HomePage(CatalogPageBase):
    """TOOLS catalog page."""
    
    def create_delegate(self) -> QAbstractItemDelegate:
        return ToolCatalogDelegate()
    
    def get_item_service(self) -> ToolService:
        return self.item_service
    
    def build_filter_pane(self) -> QWidget:
        pane = ToolFilterPane(self.translate)
        # Include tool_head (HEAD1/HEAD2) and tool_type (Turning/Drilling/etc.)
        return pane
    
    def apply_filters(self, filters: dict) -> List[dict]:
        return self.get_item_service().list_tools(
            search_text=filters['search'],
            tool_head=filters.get('tool_head', 'HEAD1'),
            tool_type=filters.get('tool_type', 'All')
        )
```

---

### 2. EditorDialogBase

**Purpose**: Common interface for all item edit/create dialogs (TOOLS, JAWS, Fixtures, etc.)

**Responsibilities**:
- Build form schema
- Load/render record data
- Validate changes
- Save to service
- Emit accepted signal

```python
class EditorDialogBase(QDialog):
    """Abstract base for item editor dialogs."""
    
    accepted = Signal()
    
    def __init__(self, parent=None, item=None, item_service=None, translate=None, 
                 batch_label=None, group_edit_mode=False, group_count=None):
        super().__init__(parent)
        self.item = item or {}
        self.item_service = item_service
        self.translate = translate
        self.batch_label = batch_label
        self.group_edit_mode = group_edit_mode
        self.group_count = group_count
        self._build_ui()
        if self.item:
            self.load_record(self.item)
    
    # === Abstract Methods (Override in Subclass) ===
    
    def build_schema(self) -> dict:
        """Return form schema (fields, types, constraints)."""
        raise NotImplementedError
    
    def validate_record(self, record_dict: dict) -> bool:
        """Validate domain-specific constraints."""
        raise NotImplementedError
    
    def on_field_changed(self, field_name: str, value: any) -> None:
        """Handle field change; trigger cross-field logic."""
        # Override for dependent field updates
        pass
    
    # === Common Implementation ===
    
    def _build_ui(self):
        """Construct form from schema."""
        self.schema = self.build_schema()
        form_layout = QFormLayout()
        self.field_widgets = {}
        
        for field_name, field_config in self.schema.items():
            if field_config['type'] == 'text':
                widget = QLineEdit()
                widget.textChanged.connect(
                    lambda text, fn=field_name: self.on_field_changed(fn, text)
                )
            elif field_config['type'] == 'number':
                widget = QDoubleSpinBox()
                widget.valueChanged.connect(
                    lambda val, fn=field_name: self.on_field_changed(fn, val)
                )
            elif field_config['type'] == 'choice':
                widget = QComboBox()
                widget.addItems(field_config['options'])
                widget.currentTextChanged.connect(
                    lambda text, fn=field_name: self.on_field_changed(fn, text)
                )
            else:
                continue
            
            form_layout.addRow(field_config.get('label', field_name), widget)
            self.field_widgets[field_name] = widget
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        
        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form_layout)
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
    
    def load_record(self, record_dict: dict) -> None:
        """Populate form fields from record."""
        for field_name, widget in self.field_widgets.items():
            value = record_dict.get(field_name)
            if isinstance(widget, QLineEdit):
                widget.setText(str(value or ''))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value or 0.0))
            elif isinstance(widget, QComboBox):
                widget.setCurrentText(str(value or ''))
    
    def get_record_data(self) -> dict:
        """Extract form data as dict."""
        record = {}
        for field_name, widget in self.field_widgets.items():
            if isinstance(widget, QLineEdit):
                record[field_name] = widget.text()
            elif isinstance(widget, QDoubleSpinBox):
                record[field_name] = widget.value()
            elif isinstance(widget, QComboBox):
                record[field_name] = widget.currentText()
        return record
    
    def accept(self) -> None:
        """Validate, save, and close."""
        record = self.get_record_data()
        if not self.validate_record(record):
            QMessageBox.warning(self, "Validation Error", "Please check your input.")
            return
        
        # Merge with original (preserve unedited fields)
        self.item.update(record)
        uid = self.item_service.save_item(self.item)
        self.item['uid'] = uid
        self.accepted.emit()
        super().accept()
```

**Domain Subclass Example (AddEditToolDialog for TOOLS)**:

```python
class AddEditToolDialog(EditorDialogBase):
    """TOOLS item editor."""
    
    def build_schema(self) -> dict:
        return {
            'id': {'type': 'text', 'label': 'Tool ID', 'required': True},
            'tool_type': {'type': 'choice', 'label': 'Type', 'options': ALL_TOOL_TYPES},
            'description': {'type': 'text', 'label': 'Description'},
            'tool_head': {'type': 'choice', 'label': 'Head', 'options': ['HEAD1', 'HEAD2']},
            'geom_x': {'type': 'number', 'label': 'Geom X (mm)'},
            'geom_z': {'type': 'number', 'label': 'Geom Z (mm)'},
            'radius': {'type': 'number', 'label': 'Nose Radius (mm)'},
            # ... etc
        }
    
    def validate_record(self, record_dict: dict) -> bool:
        if not record_dict.get('id'):
            return False
        if record_dict['tool_head'] not in ['HEAD1', 'HEAD2']:
            return False
        if record_dict['radius'] < 0:
            return False
        return True
    
    def on_field_changed(self, field_name: str, value: any) -> None:
        # Tool-specific cross-field logic (e.g., if tool_type changes, reset geometry)
        if field_name == 'tool_type':
            # Auto-populate defaults based on type
            pass
```

---

### 3. CatalogDelegate

**Purpose**: Render single item in list view (item painting, sizing, selection)

**Common Behavior**:
- Paint item background (selected/hover/normal states)
- Render item metadata (icon, title, description)
- Compute sizeHint for dynamic row heights

```python
class CatalogDelegate(QAbstractItemDelegate):
    """Abstract delegate for catalog list items."""
    
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """Render item."""
        item_dict = self._get_item_data(index)
        
        # Draw background
        painter.fillRect(option.rect, self._get_background_color(option))
        
        # Draw custom content
        self._paint_item_content(painter, option, item_dict)
    
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Return item height."""
        item_dict = self._get_item_data(index)
        return self._compute_size(option, item_dict)
    
    # === Abstract Methods ===
    
    def _paint_item_content(self, painter: QPainter, option: QStyleOptionViewItem, 
                           item_dict: dict) -> None:
        """Domain-specific rendering."""
        raise NotImplementedError
    
    def _compute_size(self, option: QStyleOptionViewItem, item_dict: dict) -> QSize:
        """Domain-specific sizing."""
        raise NotImplementedError
    
    # === Helper ===
    
    def _get_item_data(self, index: QModelIndex) -> dict:
        return index.data(Qt.UserRole + 1)
    
    def _get_background_color(self, option: QStyleOptionViewItem) -> QColor:
        if option.state & QStyle.State_Selected:
            return QColor(70, 130, 180)  # Selection highlight
        elif option.state & QStyle.State_MouseOver:
            return QColor(240, 240, 240)  # Hover
        else:
            return QColor(255, 255, 255)  # Normal
```

**Domain Subclass Example (ToolCatalogDelegate for TOOLS)**:

```python
class ToolCatalogDelegate(CatalogDelegate):
    """TOOLS item rendering."""
    
    def _paint_item_content(self, painter: QPainter, option: QStyleOptionViewItem, 
                           tool_dict: dict) -> None:
        # Draw tool icon
        icon = get_tool_type_icon(tool_dict['tool_type'])
        icon_rect = option.rect.adjusted(5, 5, -95, -5)
        painter.drawPixmap(icon_rect, icon.pixmap(icon_rect.size()))
        
        # Draw tool ID and description
        text_rect = option.rect.adjusted(50, 5, -5, -5)
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.drawText(text_rect, tool_dict['id'])
        painter.setFont(QFont("Arial", 8))
        painter.drawText(text_rect.adjusted(0, 20, 0, 0), tool_dict['description'])
    
    def _compute_size(self, option: QStyleOptionViewItem, tool_dict: dict) -> QSize:
        # Fixed 60px height for tools
        return QSize(option.rect.width(), 60)
```

---

### 4. SelectorState

**Purpose**: Manage dynamic filter/selector UI state (tool_head selector, spindle_side selector, etc.)

**Common Behavior**:
- Store current selection
- Notify observers on change
- Validate selection constraints

```python
class SelectorState:
    """Abstract selector state container."""
    
    changed = Signal(str)  # Signal emitted when state changes
    
    def __init__(self, options: List[str]):
        self.options = options
        self._current = options[0] if options else None
    
    def get_current(self) -> str:
        return self._current
    
    def set_current(self, value: str) -> None:
        if value not in self.options:
            raise ValueError(f"Invalid selection: {value}")
        if value != self._current:
            self._current = value
            self.changed.emit(value)
    
    def get_options(self) -> List[str]:
        return self.options
```

---

### 5. ExportSpecification

**Purpose**: Define domain-specific Excel export/import schema

**Common Behavior**:
- Map item dict → Excel row (columns, formatting)
- Map Excel row → item dict (parsing, validation)
- Handle multi-sheet workbooks (Tools sheet, Jaws sheet, Metadata sheet)

```python
class ExportSpecification:
    """Define Excel I/O schema for catalog items."""
    
    def __init__(self, domain_name: str, item_service: CatalogServiceBase, image_service=None):
        self.domain_name = domain_name
        self.item_service = item_service
        self.image_service = image_service
    
    # === Abstract Methods ===
    
    def get_column_definitions(self) -> List[dict]:
        """Return list of column specs."""
        # [
        #   {'name': 'Tool ID', 'field': 'id', 'width': 20},
        #   {'name': 'Type', 'field': 'tool_type', 'width': 15},
        #   ...
        # ]
        raise NotImplementedError
    
    def item_to_row(self, item: dict) -> List[any]:
        """Convert item dict to Excel row."""
        raise NotImplementedError
    
    def row_to_item(self, row: List[any]) -> dict:
        """Convert Excel row to item dict."""
        raise NotImplementedError
    
    # === Common Implementation ===
    
    def export_to_file(self, file_path: str, items: List[dict]) -> None:
        """Write items to Excel file."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = self.domain_name
        
        # Write header
        columns = self.get_column_definitions()
        for col_idx, col_spec in enumerate(columns, 1):
            ws.cell(row=1, column=col_idx, value=col_spec['name'])
        
        # Write rows
        for row_idx, item in enumerate(items, 2):
            row_data = self.item_to_row(item)
            for col_idx, value in enumerate(row_data, 1):
                ws.cell(row=row_idx, column=col_idx, value=value)
        
        wb.save(file_path)
    
    def import_from_file(self, file_path: str) -> List[dict]:
        """Read items from Excel file."""
        wb = openpyxl.load_workbook(file_path)
        ws = wb.active
        
        items = []
        for row_idx in range(2, ws.max_row + 1):
            row = [ws.cell(row_idx, col).value for col in range(1, ws.max_column + 1)]
            item = self.row_to_item(row)
            if item:  # Skip invalid rows
                items.append(item)
        
        return items
```

---

## Phase 3 Transition Strategy

### Step 1: Adapter Layer (Week 1)

Create adapters to bridge current code → future platform:

```
ui/platform_glue/
├── legacy_preview_bridge.py  # Bridge old preview UI to platform
└── legacy_catalog_bridge.py  # Bridge old home/jaw pages to CatalogPageBase
```

**Example: LegacyPreviewBridge**

```python
class LegacyPreviewBridge(QWidget):
    """Bridges old StlPreviewWidget to new platform support."""
    
    def __init__(self, stl_path, preview_plane='XZ', preview_rot=(0, 0, 0)):
        super().__init__()
        self.stl_path = stl_path
        self._preview_widget = StlPreviewWidget()  # Old impl
        self._setup_preview()
    
    def set_preview_plane(self, plane: str) -> None:
        # Translate new platform plane concept to old widget API
        if plane == 'XZ':
            self._preview_widget.camera.lookAt(0, 1, 0)
        elif plane == 'XY':
            self._preview_widget.camera.lookAt(0, 0, 1)
        # ...
    
    def get_preview_plane(self) -> str:
        # Infer plane from old camera position
        # ...
```

### Step 2: Dual Inheritance (Weeks 2-3)

Add platform base class to HomePage/JawPage **without removing old code**:

```python
# BEFORE (Phase 2)
class HomePage(QWidget):
    # ... 2,223 lines of old code

# AFTER (Phase 3, Week 2)
class HomePage(CatalogPageBase, QWidget):  # Inherit platform
    def create_delegate(self):
        return ToolCatalogDelegate()
    
    def build_filter_pane(self):
        return self._old_filter_pane  # Reuse old
    
    # ... keep all 2,200 lines of old code; gradually reduce
```

### Step 3: Gradual Migration (Weeks 4-8)

Each week, delete 200-300 lines from HomePage/JawPage by delegating to platform:

Week 4:
- Delete list view setup code → use CatalogPageBase._build_ui()
- Delete refresh_catalog() → use CatalogPageBase.refresh_catalog()

Week 5:
- Delete search handling → use CatalogPageBase search_input

Week 6:
- Delete selection management → use CatalogPageBase item_selected signal

...

Week 8:
- HomePage reduced from 2,223L → ~300L (86% reduction!)

### Step 4: Verify Backward Compatibility

After each week:
```bash
python scripts/run_parity_tests.py --phase 3 --compare phase0-baseline-snapshot.json
# All tests must pass; behavior unchanged
```

---

## Risk Mitigation

### Risk 1: Platform Depth / Over-Engineering

**Problem**: Base classes become too abstract; subclasses need special handling.

**Mitigation**:
- Phase 1-2 contracts lock domain APIs; Phase 3 extracts only proven patterns
- Limit base class methods to <30 per class; use composition for complex logic
- Document extension points clearly; provide subclass examples
- Plan quarterly review gates to prune unused abstractions

### Risk 2: Adapter Accumulation

**Problem**: Legacy adapters pile up; hard to remove.

**Mitigation**:
- Adapters have explicit removal date (e.g., "Remove after Phase 4 complete")
- Each adapter documented with "Why needed", "Remove when", "Replacement"
- Quarterly cleanup pass removes expired adapters

### Risk 3: Schema Compatibility

**Problem**: New platform schema doesn't match old data; migration needed.

**Mitigation**:
- Data contracts (TOOLS_MODULE_CONTRACT.md, JAWS_MODULE_CONTRACT.md) locked in Phase 1
- Phase 3 platform inherits from these contracts; no schema changes
- Backward compatibility test: export/import 1M+ records; verify binary equivalence

---

## Success Criteria (Phase 3 Completion)

1. ✅ `CatalogPageBase`, `EditorDialogBase`, `CatalogDelegate`, `SelectorState`, `ExportSpecification` implemented and documented
2. ✅ HomePage and JawPage inherit from CatalogPageBase; all old functionality preserved
3. ✅ No regressions detected: `run_parity_tests.py --phase 3 --compare phase0-baseline.json` → all tests PASS
4. ✅ Code size reduction achieved: HomePage 2,223L → <400L; JawPage 1,423L → <400L
5. ✅ Fixtures domain drafted using platform template; <1,200 lines total code
6. ✅ Documentation complete: inheritance examples, migration guide, risk register for Phase 4+

---

## References

- [TOOLS_MODULE_CONTRACT.md](TOOLS_MODULE_CONTRACT.md) — TOOLS API locked here
- [JAWS_MODULE_CONTRACT.md](JAWS_MODULE_CONTRACT.md) — JAWS API locked here
- [TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md](TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md) — Phase tracking; Phase 3 details there
- [TOOLS_JAWS_MODULAR_OVERHAUL_RULES.md](TOOLS_JAWS_MODULAR_OVERHAUL_RULES.md) — Constraints for Phase 3 implementation
