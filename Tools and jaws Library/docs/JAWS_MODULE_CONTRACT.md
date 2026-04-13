# JAWS Domain Module Contract

**Status**: Phase 1 Draft (April 13, 2026)  
**Format**: Markdown + YAML  
**Purpose**: Machine-readable contract defining JAWS module public API, data shapes, lifecycle, and extension points for Phase 2+ governance and Phase 3+ platform integration

> **For AI Agents**: This contract parallels TOOLS but adds jaw-specific concerns: spindle filtering, preview plane orientation (XZ/XY/YZ), preview rotation persistence, clamping geometry, and turning washer variants.

---

## Module Identity

**Name**: JAWS  
**Owner**: Tools and jaws Library app  
**Purpose**: Manage spindle adapter (chuck) master data; pair with tools for composite work setups

**Included Scope**:
- Jaw CRUD (add, edit, delete, copy)
- Jaw search/filtering (by spindle type, spindle side)
- Preview plane state management (XZ/XY/YZ orientation)
- Preview rotation persistence (rotate_x, rotate_y, rotate_z angles)
- Catalog page UI (browse, select, batch actions)
- Editor dialog UI (form, validation, spindle-side locking)
- STL model linking and 3D preview with plane/rotation

**Excluded Scope**:
- Tool management (TOOLS module)
- Machine setup orchestration (Setup Manager)
- Fixture/attachment management (future modules)
- Shared UI patterns (shared.ui module)

---

## Public API

### Services

**`JawService(db)`** — CRUD layer for jaw records

```python
class JawService:
    def __init__(self, db):
        """Initialize with database; seed if empty."""
    
    def list_jaws(self, search_text='', spindle_type='All', spindle_side='Main') -> List[dict]:
        """Query records matching filters. Returns list of normalized jaw dicts."""
    
    def get_jaw(self, jaw_id: str) -> dict | None:
        """Fetch single jaw by ID."""
    
    def get_jaw_by_uid(self, uid: int) -> dict | None:
        """Fetch single jaw by unique row ID."""
    
    def save_jaw(self, jaw: dict, allow_duplicate: bool = False) -> int:
        """Create/update jaw; returns uid."""
    
    def delete_jaw(self, jaw_id: str) -> None:
        """Delete all versions of jaw with given ID."""
    
    def copy_jaw(self, source_id: str, new_id: str, new_description: str = '') -> int:
        """Clone jaw; returns new uid."""
    
    def jaw_id_exists(self, jaw_id: str, exclude_uid: int | None = None) -> bool:
        """Check if jaw ID exists."""
    
    def get_jaws_for_spindle(self, spindle_side: str) -> List[dict]:
        """Get all jaws compatible with main/sub spindle."""
```

### UI Components

**`JawPage(QWidget)`** — Catalog page for jaws

```python
class JawPage(QWidget):
    jaw_selected = Signal(str, int)  # (jaw_id, uid)
    jaw_deleted = Signal(str)  # (jaw_id)
    
    def __init__(self, parent=None, jaw_service=None, translate=None):
        """Initialize with service injection."""
    
    def refresh_catalog(self) -> None:
        """Reload and render jaw list."""
    
    def get_selected_jaws(self) -> List[dict]:
        """Return currently selected jaw dicts."""
    
    def get_preview_plane(self) -> str:
        """Return current preview plane (XZ | XY | YZ)."""
    
    def set_preview_plane(self, plane: str) -> None:
        """Set and persist preview plane orientation."""
    
    def get_preview_rotation(self) -> Tuple[float, float, float]:
        """Return preview rotation (x, y, z degrees)."""
    
    def set_preview_rotation(self, rx: float, ry: float, rz: float) -> None:
        """Set and persist preview rotation."""
```

**`AddEditJawDialog(QDialog)`** — Edit dialog for jaws

```python
class AddEditJawDialog(QDialog):
    accepted = Signal()
    
    def __init__(self, parent=None, jaw=None, jaw_service=None, translate=None, 
                 spindle_side_locked=None, batch_label=None, group_edit_mode=False, 
                 group_count=None):
        """Initialize with jaw data (or empty dict for new).
        
        Args:
            spindle_side_locked: If set (Main or Sub), disable spindle side selection.
        """
    
    def get_jaw_data(self) -> dict:
        """Return edited jaw record as dict."""
```

### Models

**`Jaw`** — Shared data class (from `shared.models.jaw`)

```python
@dataclass
class Jaw:
    id: str                                  # Required: unique ID
    uid: int                                 # Required: row ID
    spindle_orientation: str                 # Required: main or sub
    spindle_side: str                        # Required: 1, 2, or mixed (multi-piece)
    jaw_type: str                            # Required: category
    description: str = ""
    clamping_diameter: float = 0.0           # Chuck bore diameter (mm)
    clamping_range_min: float = 0.0          # Min clamping range (mm)
    clamping_range_max: float = 0.0          # Max clamping range (mm)
    jaw_piece_thickness: float = 0.0
    used_in_works: List[str] = field(default_factory=list)  # Work IDs from Setup Manager
    turning_washer: str = ""                 # Blank, None, or specific code
    turning_washer_thickness: float = 0.0
    turning_washer_od: float = 0.0
    preview_plane: str = "XZ"                # XZ | XY | YZ (default XZ for turning)
    preview_rot_x: float = 0.0               # Rotation about X axis (degrees)
    preview_rot_y: float = 0.0               # Rotation about Y axis (degrees)
    preview_rot_z: float = 0.0               # Rotation about Z axis (degrees)
    stl_path: str | List[dict] = ""          # Path or JSON array of models
    default_pot: str = ""                    # Storage location
    last_modified: str = ""                  # ISO timestamp
```

### Exports

**`__all__`** from `services.jaw_service`:
- `JawService`

**`__all__`** from `ui.jaw_page`:
- `JawPage`

**`__all__`** from `ui.jaw_editor_dialog`:
- `AddEditJawDialog`

**`__all__`** from `shared.models.jaw`:
- `Jaw`

---

## Data Contract

### Example Jaw Record

```python
{
    "id": "J001",
    "uid": 7,
    "spindle_orientation": "main",
    "spindle_side": "1",
    "jaw_type": "3-Jaw Power Chuck",
    "description": "Ø100 3-Jaw Self-Centering",
    "clamping_diameter": 100.0,
    "clamping_range_min": 0.0,
    "clamping_range_max": 100.0,
    "jaw_piece_thickness": 15.0,
    "used_in_works": ["W0051", "W0055"],
    "turning_washer": "TW001",
    "turning_washer_thickness": 2.5,
    "turning_washer_od": 102.0,
    "preview_plane": "XZ",
    "preview_rot_x": 0.0,
    "preview_rot_y": 0.0,
    "preview_rot_z": 0.0,
    "stl_path": "/models/jaws/J001.stl",
    "default_pot": "POT_J01",
    "last_modified": "2026-04-10T14:22:33"
}
```

### Field Types

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | str | ✓ | Unique or versioned by uid |
| uid | int | ✓ | Auto-generated primary key |
| spindle_orientation | str | ✓ | main or sub |
| spindle_side | str | ✓ | 1, 2, or mixed |
| jaw_type | str | ✓ | Member of ALL_JAW_TYPES |
| clamping_diameter | float | | Chuck bore (mm) |
| clamping_range_min/max | float | | Min/max clamping (mm) |
| used_in_works | List[str] | | Work IDs from Setup Manager |
| turning_washer | str | | TW code or empty |
| preview_plane | str | | XZ (default) or XY or YZ |
| preview_rot_x/y/z | float | | Rotation angles (degrees) |
| stl_path | str or List[dict] | | Single path or JSON array |

### Preview Plane Semantics

**XZ Plane** (default for turning):
- View from +Y looking toward origin
- X-axis horizontal (chuck bore left-right)
- Z-axis vertical (spindle axis)
- Best for traditional chuck view in turning lathe

**XY Plane**:
- View from +Z looking toward origin
- X-axis horizontal
- Y-axis vertical
- Best for end-view (facing operations)

**YZ Plane**:
- View from +X looking toward origin
- Y-axis horizontal
- Z-axis vertical
- Best for side view (milling operations)

---

## Lifecycle

### Initialization

```python
# 1. Create service
db = JawDatabase(db_path)
jaw_service = JawService(db)

# 2. Create page
jaw_page = JawPage(
    parent=main_window,
    jaw_service=jaw_service,
    translate=lambda key: i18n_dict.get(key, key)
)

# 3. Connect signals
jaw_page.jaw_selected.connect(on_jaw_selected)
jaw_page.jaw_deleted.connect(on_jaw_deleted)

# 4. Restore preview state (from settings or DB)
jaw_page.set_preview_plane("XZ")
jaw_page.set_preview_rotation(0.0, 15.0, 0.0)
```

### User Interaction Flow

1. **Browse**: User enters JawPage; `refresh_catalog()` loads jaws
2. **View 3D**: User rotates or planes preview; signals state change
3. **Select**: User clicks jaw; `jaw_selected` signal emitted; state persists
4. **Edit**: User clicks Edit; `AddEditJawDialog` created with selected jaw
5. **Constrain Spindle**: If edited from a work context, spindle_side locked
6. **Save**: Dialog accepts; `get_jaw_data()` returns edited dict; `jaw_service.save_jaw()` called
7. **Refresh**: `jaw_page.refresh_catalog()` updates UI; preview plane/rotation restored
8. **Shutdown**: Preview state written to settings or DB

### Shutdown

- JawPage disconnects signals, persists preview plane/rotation to settings
- JawService closes DB connection

---

## Import Rules

### Allowed Imports

```python
# Config
from config import ALL_JAW_TYPES, JAW_ICONS_DIR, JAW_MODELS_ROOT_DEFAULT

# Canonical shared
from shared.ui.helpers.editor_helpers import setup_editor_dialog
from shared.ui.stl_preview import StlPreviewWidget
from shared.models.jaw import Jaw
from shared.data.model_paths import normalize_model_path_for_storage

# App-local
from ui.jaw_catalog_delegate import JawCatalogDelegate
from ui.jaw_page_support.spindle_filter_pane import SpindleFilterPane
```

### Forbidden Imports

```python
# ❌ Cross-app coupling
from Setup Manager.ui.main_window import MainWindow

# ❌ TOOLS coupling
from services.tool_service import ToolService
from ui.home_page import HomePage

# ❌ Legacy paths
from shared.editor_helpers import ...  # Use shared.ui.helpers.editor_helpers
from shared.model_paths import ...     # Use shared.data.model_paths
```

---

## Extension Points (Phase 3+)

### For Service Inheritance

Phase 3 will create `CatalogServiceBase`. JawService will inherit (same as ToolService):

```python
class JawService(CatalogServiceBase):
    def list_jaws(self, search_text='', spindle_type='All', spindle_side='Main') -> List[dict]:
        # Override with jaw-specific filtering, including spindle_side
        return self.list_items(search_text, filters={'type': spindle_type, 'side': spindle_side})
    
    def get_jaws_for_spindle(self, spindle_side: str) -> List[dict]:
        # Jaw-specific method: filter by spindle compatibility
        return self.list_jaws(spindle_side=spindle_side)
```

### For Dialog Subclassing

Phase 3 will create `EditorDialogBase`. AddEditJawDialog will inherit:

```python
class AddEditJawDialog(EditorDialogBase):
    def __init__(self, ..., spindle_side_locked=None):
        super().__init__(...)
        self.spindle_side_locked = spindle_side_locked  # Jaw-specific constraint
    
    def build_schema(self) -> dict:
        schema = {...}  # Jaw-specific fields
        if self.spindle_side_locked:
            # Disable spindle side field
            schema['spindle_side']['enabled'] = False
        return schema
    
    def validate_record(self, record_dict) -> bool:
        # Jaw-specific validation
        if record_dict['clamping_diameter'] <= 0:
            return False
        return True
```

### For Page Orchestration

Phase 3 will create `CatalogPageBase`. JawPage will inherit (with preview plane/rotation extensions):

```python
class JawPage(CatalogPageBase):
    preview_plane_changed = Signal(str)  # Jaw-specific signal
    preview_rotation_changed = Signal(float, float, float)  # Jaw-specific
    
    def create_delegate(self):
        return JawCatalogDelegate()
    
    def get_preview_plane(self) -> str:
        # Jaw-specific extension point
        return self._preview_plane
    
    def set_preview_plane(self, plane: str) -> None:
        # Jaw-specific extension point
        self._preview_plane = plane
        self._persist_preview_state()
        self.preview_plane_changed.emit(plane)
```

---

## Acceptance Tests (Phase 1)

### API Verification

```python
# Verify all public methods exist
from services.jaw_service import JawService
assert hasattr(JawService, 'list_jaws')
assert hasattr(JawService, 'save_jaw')
assert hasattr(JawService, 'get_jaws_for_spindle')
# ... etc for each method in contract

# Verify signals exist
from ui.jaw_page import JawPage
assert hasattr(JawPage, 'jaw_selected')
assert hasattr(JawPage, 'jaw_deleted')
assert hasattr(JawPage, 'get_preview_plane')
assert hasattr(JawPage, 'set_preview_plane')
```

### Data Contract Verification

```python
# Verify saved jaw record contains all required fields
jaw = {
    'id': 'J001',
    'spindle_orientation': 'main',
    'spindle_side': '1',
    'jaw_type': '3-Jaw',
    'clamping_diameter': 100.0,
    'preview_plane': 'XZ'
}
uid = jaw_service.save_jaw(jaw)
fetched = jaw_service.get_jaw_by_uid(uid)
assert fetched is not None
assert fetched['id'] == 'J001'
assert fetched['preview_plane'] == 'XZ'
```

### Preview State Verification

```python
# Verify preview plane and rotation persistence
jaw_page.set_preview_plane('XY')
jaw_page.set_preview_rotation(45.0, 30.0, 0.0)
assert jaw_page.get_preview_plane() == 'XY'
rx, ry, rz = jaw_page.get_preview_rotation()
assert abs(rx - 45.0) < 0.01
assert abs(ry - 30.0) < 0.01
# ... verify state persists across refresh
jaw_page.refresh_catalog()
assert jaw_page.get_preview_plane() == 'XY'
```

### Spindle-Side Lock Verification

```python
# Verify AddEditJawDialog respects spindle_side_locked
dialog = AddEditJawDialog(
    jaw={'id': 'J001', 'spindle_side': '1'},
    spindle_side_locked='1'
)
# spindle_side field should be read-only or disabled
assert dialog.get_jaw_data()['spindle_side'] == '1'  # Cannot be changed
```

### Import Compliance

```bash
python scripts/import_path_checker.py
# Exit code 0: No import violations
```

---

## References

- [TOOLS_JAWS_MODULAR_OVERHAUL_RULES.md](TOOLS_JAWS_MODULAR_OVERHAUL_RULES.md) — Constraints for modifications
- [TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md](TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md) — Phase tracking
- [AGENTS.md](../../AGENTS.md) — Canonical import rules
