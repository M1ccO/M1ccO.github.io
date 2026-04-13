# TOOLS Domain Module Contract

**Status**: Phase 1 Draft (April 13, 2026)  
**Format**: YAML + Markdown  
**Purpose**: Machine-readable contract defining TOOLS module public API, data shapes, lifecycle, and extension points for Phase 2+ governance and Phase 3+ platform integration

> **For AI Agents**: This contract is your API specification. Implement against these interfaces; do not guess patterns from code.

---

## Module Identity

**Name**: TOOLS  
**Owner**: Tools and jaws Library app  
**Purpose**: Manage CNC tool master data (cutting tools, holders, inserts, drills, mills)

**Included Scope**:
- Tool CRUD (add, edit, delete, copy)
- Tool search/filtering (by type, head, spindle)
- Catalog page UI (browse, select, batch actions)
- Editor dialog UI (form, validation, serialization)
- STL model linking and 3D preview
- Excel export/import

**Excluded Scope**:
- Jaw/spindle management (JAWS module)
- Machine setup orchestration (Setup Manager)
- Custom machine profiles (future module)
- Shared UI patterns (shared.ui module)

---

## Public API

### Services

**`ToolService(db)`** — CRUD layer for tool records

```python
class ToolService:
    def __init__(self, db):
        """Initialize with database; seed if empty."""
    
    def list_tools(self, search_text='', tool_type='All', tool_head='HEAD1') -> List[dict]:
        """Query records matching filters. Returns list of normalized tool dicts."""
    
    def get_tool(self, tool_id: str) -> dict | None:
        """Fetch single tool by ID."""
    
    def get_tool_by_uid(self, uid: int) -> dict | None:
        """Fetch single tool by unique row ID."""
    
    def save_tool(self, tool: dict, allow_duplicate: bool = False) -> int:
        """Create/update tool; returns uid."""
    
    def delete_tool(self, tool_id: str) -> None:
        """Delete all versions of tool with given ID."""
    
    def copy_tool(self, source_id: str, new_id: str, new_description: str = '') -> int:
        """Clone tool; returns new uid."""
    
    def tcode_exists(self, tool_id: str, exclude_uid: int | None = None) -> bool:
        """Check if tool ID exists."""
```

### UI Components

**`HomePage(QWidget)`** — Catalog page for tools

```python
class HomePage(QWidget):
    tool_selected = Signal(str, int)  # (tool_id, uid)
    tool_deleted = Signal(str)  # (tool_id)
    
    def __init__(self, parent=None, tool_service=None, translate=None):
        """Initialize with service injection."""
    
    def refresh_catalog(self) -> None:
        """Reload and render tool list."""
    
    def get_selected_tools(self) -> List[dict]:
        """Return currently selected tool dicts."""
```

**`AddEditToolDialog(QDialog)`** — Edit dialog for tools

```python
class AddEditToolDialog(QDialog):
    accepted = Signal()
    
    def __init__(self, parent=None, tool=None, tool_service=None, translate=None, 
                 batch_label=None, group_edit_mode=False, group_count=None):
        """Initialize with tool data (or empty dict for new)."""
    
    def get_tool_data(self) -> dict:
        """Return edited tool record as dict."""
```

### Models

**`Tool`** — Shared data class (from `shared.models.tool`)

```python
@dataclass
class Tool:
    id: str                                  # Required: unique ID
    uid: int                                 # Required: row ID
    tool_head: str                           # Required: HEAD1 or HEAD2
    spindle_orientation: str                 # Required: main or sub
    tool_type: str                           # Required: category
    description: str = ""
    geom_x: float = 0.0                      # X geometry (mm)
    geom_z: float = 0.0                      # Z geometry (mm)
    b_axis_angle: float = 0.0
    radius: float = 0.0                      # Nose radius (mm)
    nose_corner_radius: float = 0.0
    holder_code: str = ""
    holder_link: str = ""
    holder_add_element: str = ""
    holder_add_element_link: str = ""
    cutting_type: str = ""                   # Insert, Solid, Drill
    cutting_code: str = ""
    cutting_link: str = ""
    cutting_add_element: str = ""
    cutting_add_element_link: str = ""
    notes: str = ""
    drill_nose_angle: float = 0.0
    mill_cutting_edges: int = 0
    geometry_profiles: List[dict] = field(default_factory=list)  # Variants
    support_parts: List[dict] = field(default_factory=list)      # Additional parts
    component_items: List[dict] = field(default_factory=list)    # Holder-insert links
    measurement_overlays: List[dict] = field(default_factory=list)
    stl_path: str | List[dict] = ""          # Path or JSON array of models
    default_pot: str = ""                    # Storage location
```

### Exports

**`__all__`** from `services.tool_service`:
- `ToolService`

**`__all__`** from `ui.home_page`:
- `HomePage`

**`__all__`** from `ui.tool_editor_dialog`:
- `AddEditToolDialog`

**`__all__`** from `shared.models.tool`:
- `Tool`, `AdditionalPart`, `GeometryProfile`

---

## Data Contract

### Example Tool Record

```python
{
    "id": "T001",
    "uid": 42,
    "tool_head": "HEAD1",
    "spindle_orientation": "main",
    "tool_type": "O.D Turning",
    "description": "63° Carbide Insert Turning Tool",
    "geom_x": 12.5,
    "geom_z": -5.25,
    "b_axis_angle": 90.0,
    "radius": 0.8,
    "nose_corner_radius": 0.4,
    "holder_code": "PCLNL2020K09",
    "holder_link": "https://example.com/PCLNL2020K09.pdf",
    "holder_add_element": "Clamp Block",
    "holder_add_element_link": "",
    "cutting_type": "Insert",
    "cutting_code": "CNMG120408",
    "cutting_link": "https://example.com/CNMG120408.pdf",
    "cutting_add_element": "",
    "cutting_add_element_link": "",
    "notes": "Use coating AC; min depth 0.5mm",
    "drill_nose_angle": 0.0,
    "mill_cutting_edges": 0,
    "geometry_profiles": "[{\"variant\":\"H1\",\"h_code\":\"H1\",\"b_axis\":\"B0\",\"spindle\":\"Main\",\"description\":\"Standard\"}]",
    "support_parts": "[{\"name\":\"Coolant Block\",\"code\":\"CB001\",\"group\":\"Mounted\"}]",
    "component_items": "[{\"holder\":\"PCLNL2020K09\",\"insert\":\"CNMG120408\",\"order\":0}]",
    "measurement_overlays": "[{\"name\":\"X Offset\",\"x\":10.5,\"y\":20.0}]",
    "stl_path": "/models/tools/T001.stl",
    "default_pot": "POT_01"
}
```

### Field Types

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | str | ✓ | Unique or versioned by uid |
| uid | int | ✓ | Auto-generated primary key |
| tool_head | str | ✓ | HEAD1 or HEAD2 |
| spindle_orientation | str | ✓ | main or sub |
| tool_type | str | ✓ | Member of ALL_TOOL_TYPES |
| geom_x, geom_z | float | | Geometry offsets (mm) |
| radius, nose_corner_radius | float | | Nose radius (mm) |
| holder_code, cutting_code | str | | Component references |
| geometry_profiles | List[dict] | | JSON string when stored |
| support_parts | List[dict] | | JSON string when stored |
| component_items | List[dict] | | JSON string when stored |
| stl_path | str or List[dict] | | Single path or JSON array |

---

## Lifecycle

### Initialization

```python
# 1. Create service
db = ToolDatabase(db_path)
tool_service = ToolService(db)

# 2. Create page
home_page = HomePage(
    parent=main_window,
    tool_service=tool_service,
    translate=lambda key: i18n_dict.get(key, key)
)

# 3. Connect signals
home_page.tool_selected.connect(on_tool_selected)
home_page.tool_deleted.connect(on_tool_deleted)
```

### User Interaction Flow

1. **Browse**: User enters HomePage; `refresh_catalog()` loads tools
2. **Select**: User clicks tool; `tool_selected` signal emitted
3. **Edit**: User clicks Edit; `AddEditToolDialog` created with selected tool
4. **Save**: Dialog accepts; `get_tool_data()` returns edited dict; `tool_service.save_tool()` called
5. **Refresh**: `home_page.refresh_catalog()` updates UI

### Shutdown

- HomePage disconnects signals, closes detached previews
- ToolService closes DB connection

---

## Import Rules

### Allowed Imports

```python
# Config
from config import ALL_TOOL_TYPES, TOOL_ICONS_DIR, TOOL_MODELS_ROOT_DEFAULT

# Canonical shared
from shared.ui.helpers.editor_helpers import setup_editor_dialog
from shared.ui.stl_preview import StlPreviewWidget
from shared.models.tool import Tool
from shared.data.model_paths import normalize_model_path_for_storage

# App-local
from ui.tool_catalog_delegate import ToolCatalogDelegate
from ui.tool_editor_support.component_picker_dialog import ComponentPickerDialog
```

### Forbidden Imports

```python
# ❌ Cross-app coupling
from Setup Manager.ui.work_editor_dialog import AddEditWorkDialog

# ❌ JAWS coupling
from services.jaw_service import JawService
from ui.jaw_page import JawPage

# ❌ Legacy paths
from shared.editor_helpers import ...  # Use shared.ui.helpers.editor_helpers
from shared.model_paths import ...     # Use shared.data.model_paths
```

---

## Extension Points (Phase 3+)

### For Service Inheritance

Phase 3 will create `CatalogServiceBase`. ToolService will inherit:

```python
class CatalogServiceBase:
    def list_items(self, search_text='', filters=None) -> List[dict]: ...
    def get_item(self, item_id: str) -> dict | None: ...
    def save_item(self, item: dict) -> int: ...
    def delete_item(self, item_id: str) -> None: ...
    def copy_item(self, source_id: str, new_id: str) -> int: ...

class ToolService(CatalogServiceBase):
    def list_tools(self, search_text='', tool_type='All', tool_head='HEAD1') -> List[dict]:
        # Override with tool-specific filtering
        return self.list_items(search_text, filters={'type': tool_type, 'head': tool_head})
```

### For Dialog Subclassing

Phase 3 will create `EditorDialogBase`. AddEditToolDialog will inherit:

```python
class EditorDialogBase(QDialog):
    def get_record_data(self) -> dict: ...
    def load_record(self, record_dict) -> None: ...
    def accept(self) -> None: ...  # with validation
    
    # Override points:
    def build_schema(self) -> dict: ...  # Define fields
    def validate_record(self, record_dict) -> bool: ...  # Domain validation
    def on_field_changed(self, field_name) -> None: ...  # Cross-field logic

class AddEditToolDialog(EditorDialogBase):
    def build_schema(self) -> dict:
        return {...}  # Tool-specific fields
    
    def validate_record(self, record_dict) -> bool:
        # Tool-specific validation
        return record_dict['tool_head'] in ['HEAD1', 'HEAD2']
```

### For Page Orchestration

Phase 3 will create `CatalogPageBase`. HomePage will inherit:

```python
class CatalogPageBase(QWidget):
    item_selected = Signal(str, int)  # (item_id, uid)
    item_deleted = Signal(str)  # (item_id)
    
    def refresh_catalog(self) -> None: ...
    def get_selected_items(self) -> List[dict]: ...
    def apply_batch_action(self, action, items) -> None: ...

class HomePage(CatalogPageBase):
    def create_delegate(self):
        return ToolCatalogDelegate()
    
    def on_item_selected(self, item_id, uid):
        # Display tool-specific detail panel
        pass
```

---

## Acceptance Tests (Phase 1)

### API Verification

```python
# Verify all public methods exist
from services.tool_service import ToolService
assert hasattr(ToolService, 'list_tools')
assert hasattr(ToolService, 'save_tool')
# ... etc for each method in contract

# Verify signals exist
from ui.home_page import HomePage
assert hasattr(HomePage, 'tool_selected')
assert hasattr(HomePage, 'tool_deleted')
```

### Data Contract Verification

```python
# Verify saved tool record contains all required fields
tool = {'id': 'T001', 'tool_head': 'HEAD1', 'spindle_orientation': 'main', 'tool_type': 'Turning'}
uid = tool_service.save_tool(tool)
fetched = tool_service.get_tool_by_uid(uid)
assert fetched is not None
assert fetched['id'] == 'T001'
```

### UI Interaction Verification

```python
# Verify HomePage emits signals correctly
selected_tools = []
home_page.tool_selected.connect(lambda tid, uid: selected_tools.append(tid))
# ... user selects tool in UI
assert len(selected_tools) > 0
```

### Import Compliance

```bash
python scripts/import_path_checker.py
# Exit code 0: No import violations
```

---

## References

- [PHASE11_SHARED_SUPPORT_RULES.md](../PHASE11_SHARED_SUPPORT_RULES.md) — Constraints for modifications
- [PHASE11_SHARED_SUPPORT_STATUS.md](../PHASE11_SHARED_SUPPORT_STATUS.md) — Phase tracking
- [AGENTS.md](../../AGENTS.md) — Canonical import rules
