## ToolCatalogDelegate Design Document

### Overview

`ToolCatalogDelegate` is a tool domain-specific renderer that inherits from `shared.ui.platforms.catalog_delegate.CatalogDelegate`. It implements the platform's abstract methods `_paint_item_content()` and `_compute_size()` to render tool catalog items as rounded cards with:

- **Responsive layout**: icon-only → name-only → reduced → full (4 stages based on card width)
- **Tool-specific content**: icon + tool_id + description + numeric geometry fields
- **Preserved rendering logic**: 100% compatible with existing home_page.py card rendering
- **Platform inheritance**: Selection/hover state, background color, border styling inherited from base
- **Font hierarchy**: Headers (9pt DemiBold) + values (13.5pt down to 10.5pt depending on stage)
- **Icon caching**: Tool type → pixmap mapping with transparent border normalization and mirroring for sub-spindles

### Class Architecture

```
CatalogDelegate (shared/ui/platforms/catalog_delegate.py)
    ↓ inherits
ToolCatalogDelegate (tools_and_jaws_library/ui/tool_catalog_delegate_v2.py)
    ├─ Abstract Methods:
    │   ├─ _paint_item_content(painter, option, item_dict) [IMPLEMENTED]
    │   └─ _compute_size(option, item_dict) [IMPLEMENTED]
    └─ Tool-Specific Helpers:
        ├─ _build_columns()       → responsive column list
        ├─ _paint_columns()       → header + value rendering
        ├─ _paint_description()   → intelligent line wrapping
        ├─ _cached_pixmap()       → icon pixmap cache
        └─ _normalized_icon_pixmap() → transparent border crop + scale
```

### Design Decisions

#### 1. Platform Layer Inheritance Model

**Why inherit from CatalogDelegate?**
- Base class handles all state management (selection, hover, focus)
- Base class manages card background, border color, border width
- Base class provides deterministic rect-based layout contract
- Subclass focuses only on domain-specific content rendering

**Mapping: Base Class → Delegate**
| Base Method | What It Does | How Used in ToolCatalogDelegate |
|-------------|-------------|--------------------------------|
| `paint()` | Save painter state, draw card bg+border, calls `_paint_item_content()` | Not touched (inherited) |
| `sizeHint()` | Calls `_compute_size()` to get QSize | Subclass implements to return ROW_HEIGHT |
| `_get_background_color()` | Returns hover/normal bg color | Inherited (CLR_CARD_HOVER, CLR_CARD_BG) |
| `_get_border_color()` | Returns border color (selected/normal) | Inherited (CLR_CARD_SELECTED_BORDER) |
| `_get_item_data()` | Extracts item dict from model | Inherited (Qt.UserRole + 1) |

**Result**: ToolCatalogDelegate focuses purely on `_paint_item_content()` + `_compute_size()` without reimplementing card styling or state management.

#### 2. Content Rendering Pipeline

```python
paint(painter, option, index)  # BASE CLASS
  ├─ Save painter state
  ├─ Get item_dict from model
  ├─ Draw card background + border  # BASE CLASS
  ├─ Create content rectangle (inside card with padding)
  ├─ CALL: _paint_item_content(painter, option, item_dict)  # TOOL SUBCLASS
  │   ├─ 1. Calculate responsive stage (full/reduced/name-only/icon-only)
  │   ├─ 2. Paint icon (with mirroring for sub-spindles)
  │   ├─ 3. Build column list based on stage and view_mode
  │   ├─ 4. Layout columns with weight-based width distribution
  │   ├─ 5. Paint columns (headers + values) with responsive fonts
  │   └─ 6. Handle description wrapping (2-line with ' - ' priority split)
  └─ Restore painter state
```

#### 3. Responsive Stage System

```
Card Width (px)     Stage          Content                      Font Size
─────────────────   ────────────   ─────────────────────────   ───────────
< 180               icon-only      icon only                    —
180-389             name-only      icon + description (wrap)    12.5pt
390-859             reduced        icon + id + name             13.5pt
≥ 860               full           icon + id + name + geom      13.5pt
```

**Mapping: Old Constants to New**
- `BP_FULL = 860` (was hardcoded in old paint logic)
- `BP_REDUCED = 390` (via len(cols) check in old code)
- `BP_NAME_ONLY = 180` (implicit via layout failures)
- `BP_ICON_ONLY = 0` (fallback when card too narrow)

**Implementation**: `_build_columns()` returns filtered column tuples based on stage; responsive fonts chosen in `_paint_columns()`.

#### 4. Column Weight-Based Layout

Columns are distributed proportionally by weight percent:

```python
# Example: 'home' view with 860px available text space
all_cols = [
    ('tool_id',    'Tool ID',   value, weight=100),  # 10% of space
    ('tool_name',  'Tool name', value, weight=270),  # 27% of space
    ('geom_x',     'Geom X',    value, weight=110),  # 11% of space
    ('geom_z',     'Geom Z',    value, weight=110),  # 11% of space
]
total_weight = 590
col_width = (text_width * weight) / total_weight  # e.g., 172px for tool_id
```

**Mapping: Old → New**
- Old code: `COLUMNS_BY_MODE` dict of per-view column lists → New: `_build_columns()` method
- Old code: `col_rects` computation via nested loop → New: Same logic preserved in `_paint_columns()`
- Old code: Weight allocation via `weight` tuple field → New: Same tuple structure + distribution formula

#### 5. Description Line Wrapping Algorithm

Three-tiered fallback (preserves exact home_page.py logic):

```python
1. If text fits on one line → paint one line (elided)
2. If ' - ' separator exists → split on it (e.g., "Model A - blue variant")
3. Word-wrap to two lines (greedy first-line fitting)
```

**Line step**: 78% of `QFontMetrics.height()` for more compact wrapped text (from `WRAPPED_LINE_STEP_FACTOR`).

**Mapping: Old → New**
- Old: `_description_line_count()` in old delegate → New: `_paint_description()` integrated logic
- Old: Two-line rendering in old delegate → New: Same wrapping algorithm in `_paint_description()`
- Old: Wrapped line step factor → New: `WRAPPED_LINE_STEP_FACTOR = 0.78` preserved

#### 6. Icon Caching and Normalization

```python
_cached_pixmap(icon, tool_type, mirrored=False) -> QPixmap
  ├─ Key: f"{tool_type}|{'mirrored' if mirrored else 'normal'}"
  ├─ Lookup in dict cache
  ├─ If miss:
  │   ├─ icon.pixmap(ICON_SIZE, ICON_SIZE) → QPixmap
  │   ├─ _normalized_icon_pixmap() → crop transparent borders + scale
  │   ├─ Apply mirror transform if sub-spindle (spindle_orientation='sub')
  │   └─ Cache entry
  └─ Return cached QPixmap
```

**Sub-spindle Mirroring**: If `spindle_orientation` ∈ {sub, subspindle, counter_spindle}, apply horizontal flip via `QTransform().scale(-1, 1)`.

**Mapping: Old → New**
- Old: `_cached_pixmap()` in old delegate → New: Same implementation preserved
- Old: `_normalized_icon_pixmap()` in old delegate → New: Same transparent-border cropping algorithm
- Old: Icon loading via `tool_icon_for_type()` → New: Util function extracted (can be reused)

### Public API

#### Initialization
```python
delegate = ToolCatalogDelegate(
    parent=list_view,
    view_mode='home',  # or 'holders', 'inserts', 'assemblies'
    translate=lambda key, default=None, **kw: localized_string
)
```

#### Configuration
```python
delegate.set_view_mode('assemblies')
delegate.set_translate(new_translate_fn)
```

#### Model Integration
Model items must store data in roles:
```python
item = QStandardItem()
item.setData(tool_dict, ROLE_TOOL_DATA)      # Dict with id, description, geom_x, etc.
item.setData(tool_id_str, ROLE_TOOL_ID)      # String tool ID
item.setData(tool_icon_obj, ROLE_TOOL_ICON)  # QIcon object
model.appendRow(item)
list_view.setItemDelegate(delegate)
```

#### Provided Constants
```python
# Data roles
ROLE_TOOL_ID = Qt.UserRole
ROLE_TOOL_DATA = Qt.UserRole + 1
ROLE_TOOL_ICON = Qt.UserRole + 2
ROLE_TOOL_UID = Qt.UserRole + 3

# Layout
ICON_SIZE = 40
ICON_SLOT_W = 48
COL_SPACING = 10
BP_FULL, BP_REDUCED, BP_NAME_ONLY = 860, 390, 180

# Colors
CLR_HEADER_TEXT = QColor('#2b3136')
CLR_VALUE_TEXT = QColor('#171a1d')
```

### Preserved Rendering Logic Checklist

✅ **Icon rendering**
- Icon loading via `tool_icon_for_type()`
- Pixmap caching with transparent border normalization
- Mirroring for sub-spindle tools
- Vertical centering with `ICON_VISUAL_OFFSET_Y`

✅ **Column layout**
- Weight-based proportional distribution
- Responsive stage breakpoints (full/reduced/name-only/icon-only)
- View-mode-specific column filtering (home/holders/inserts/assemblies)
- Column spacing and text rect insets

✅ **Text rendering**
- Font hierarchy (9pt headers, 13.5-10.5pt values)
- Responsive font sizing (full/narrow/tight/tiny)
- Header + value vertical alignment with bias offsets
- Multi-line header support (e.g., "Nose /\nCorner R")

✅ **Description wrapping**
- One-line fitting with elision
- Two-line priority split on ' - ' separator
- Word-wrap fallback with greedy first-line fitting
- Wrapped line step factor (78%) for tighter appearance

✅ **Tool-specific field logic**
- Nose angle vs. corner radius based on tool type
- Drill angle handling with legacy field compatibility
- Tapping pitch display
- Turning vs. milling tool type differentiation

✅ **Type-specific columns**
- 'home': tool_id + name + geom_x + geom_z
- 'holders': tool_id + holder_code + name
- 'inserts': tool_id + insert_code + name
- 'assemblies': tool_id + name + support_parts_count + stl_count

### Integration with home_page.py

**Migration path** (Phase 4 work):

1. **Old flow** (current home_page.py):
   ```python
   # Line 500+: old custom delegate
   delegate = old_ToolCatalogDelegate(view_mode='home', translate=self._t)
   self.tool_list.setItemDelegate(delegate)
   ```

2. **New flow** (after Phase 4 migration):
   ```python
   # Import from new location
   from ui.tool_catalog_delegate_v2 import ToolCatalogDelegate
   
   # Instantiate new inheriting delegate
   delegate = ToolCatalogDelegate(view_mode='home', translate=self._t)
   self.tool_list.setItemDelegate(delegate)
   # → Rendering identical, no UI changes needed
   ```

**Data flow remains identical**:
```
HomePage._refresh_list()
  ├─ Loads tool list from service
  └─ For each tool:
      ├─ Create QStandardItem
      ├─ item.setData(tool_dict, ROLE_TOOL_DATA)
      ├─ item.setData(tool_icon, ROLE_TOOL_ICON)
      └─ model.appendRow(item)
```

No changes to data roles or model population — delegate is pure painter abstraction.

### Size Estimation

- **Implementation**: ~180 lines
  - Class definition + docstring: 30L
  - Init + config methods: 20L
  - Abstract method implementations: 40L
  - Column building + painting: 70L
  - Icon caching: 20L

- **Comparison to old delegate**: 
  - Old tool_catalog_delegate.py: ~650 lines (includes multiple view modes, complex legacy logic)
  - New ToolCatalogDelegate (v2): ~180 lines (inherits card styling, state management from base)
  - **Reduction**: ~470 lines (72% smaller) via inheritance and extraction

### Testing Strategy

**Unit tests** (would validate):
1. `_compute_size()` returns correct height for all stages
2. `_paint_item_content()` renders without exceptions
3. `_build_columns()` returns correct column lists per view_mode and stage
4. Icon caching works and returns consistent pixmaps
5. Description wrapping chooses correct split points

**Integration tests** (with home_page.py):
1. Delegate respects selection/hover state (inherited from base)
2. Icons render correctly (type-specific + mirroring)
3. Responsive stages trigger at correct breakpoints
4. Column weights distribute width proportionally
5. Wrapped descriptions fit in constrained spaces
6. Parity smoke test: replace old delegate → identical rendered output

### Future Extensions

**View modes support** (orthogonal to delegate):
- New mode columns added to `_build_columns()` method
- No subclass needed for new view modes

**Selection interaction** (inherited from base):
- Click to select (handled by QItemDelegate base)
- Right-click context menu (via home_page.py signal connections)
- Keyboard navigation (via QListView model)

**State persistence** (platform-level):
- Selection state preserved by base class
- Column width distribution via responsive breakpoints (no manual resize)
- View mode tracked as HomePage member (no delegate state)

### References

- Base class: `shared/ui/platforms/catalog_delegate.py` (245L)
- Old implementation: `Tools and jaws Library/ui/tool_catalog_delegate.py` (650L)
- Integration point: `Tools and jaws Library/ui/home_page.py` (2,223L)
- Phase 4 design: `Tools and jaws Library/PHASE_4_MIGRATION_DESIGN.md` (4,200L)
- Platform plan: Root `AGENTS.md` § Phase 3 platform layer
