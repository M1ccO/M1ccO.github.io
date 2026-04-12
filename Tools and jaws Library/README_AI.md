# Tools and jaws Library — Developer and AI Reference

This document is the authoritative technical reference for AI agents and developers working on this codebase. Read it in full before modifying any files.

---

## System Overview

Tools and jaws Library is a PySide6 desktop application for managing CNC tooling data. It has two independent modules — **TOOLS** and **JAWS** — each with its own database table, service layer, UI page, editor dialog, and export page. Both modules share the same 3D STL preview system.

Tech stack:
- **PySide6** (Qt for Python)
- **SQLite** via `sqlite3` (no ORM)
- **Three.js** STL viewer in `QWebEngineView`
- **openpyxl** for Excel I/O
- **numpy** for icon transparency
- **Python 3.10**, **Windows**

---

## High-Level Architecture

```
main.py
 └── MainWindow (ui/main_window.py)
 ├── HomePage ×4 (ui/home_page.py) — TOOLS module
 │ └── ToolService (services/tool_service.py)
 │ └── Database (data/database.py) → tools table
 ├── JawPage (ui/jaw_page.py) — JAWS module
 │ └── JawService (services/jaw_service.py)
 │ └── JawDatabase (data/jaw_database.py) → jaws table
 ├── ExportPage (ui/export_page.py) — TOOLS export/import
 └── JawExportPage (ui/jaw_export_page.py) — JAWS export/import

Shared:
 StlPreviewWidget (ui/stl_preview.py)
 └── QWebEngineView → preview/index.html + viewer.js
```

**Key design choices:**
- No ORM, no controller layer, no foreign keys
- Most behavior lives directly in UI classes
- Service classes operate on plain Python dicts
- SQLite files are interchangeable; the app migrates schema on open
- 3D preview is fully self-contained (bundled Three.js, no CDN)

---

## Entry Point: `main.py`

- Creates `QApplication`
- Shows startup progress dialog
- handles single-instance IPC requests from Setup Manager or another Tool Library launch
- Instantiates `Database`, `ToolService`, `ExportService`, `SettingsService`, `JawDatabase`, `JawService`
- Warms up `StlPreviewWidget` (pre-loads the web engine)
- Creates and shows `MainWindow`

`Database(DB_PATH)` runs schema creation/migration on startup. If the tools table is empty, `ToolService._seed_if_empty()` inserts a sample tool `T1001`.

---

## Configuration: `config.py`

Canonical source for:
- Application paths (`APP_DIR`, `DB_PATH`, `ASSETS_DIR`, `TOOL_ICONS_DIR`, etc.)
- Stylesheet path
- Default export path
- Tool type lists
- Icon mapping tables used by runtime UI

Always use `config.py` for paths rather than hardcoding them elsewhere.

Cleanup note (March 2026):
- Legacy `ToolIdentification_Small_*.png` icon aliases were removed.
- Keep using mapped canonical icon names from config/runtime lookups.

---

## Database Layer

### `data/database.py`

Thin `sqlite3` wrapper for the TOOLS database.
- Opens connection with `row_factory = sqlite3.Row`
- Calls `create_or_migrate_schema()` immediately on init

### `data/jaw_database.py`

Identical pattern for the JAWS database.
- Opens connection (separate `.db` file)
- Calls `migrate_jaws_schema()` on init

### `data/migrations.py`

The single file that owns all schema creation and migration logic for both databases.

#### `tools` table columns

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Tool ID |
| `tool_type` | TEXT | Turning / Milling / Drilling / etc. |
| `description` | TEXT | Free-text name |
| `geom_x`, `geom_z` | REAL | Geometry offsets |
| `radius`, `nose_corner_radius` | REAL | Radius values |
| `holder_code`, `holder_link` | TEXT | Holder identity and URL |
| `holder_add_element`, `holder_add_element_link` | TEXT | Extra holder part |
| `cutting_type` | TEXT | Insert / Drill / Mill |
| `cutting_code`, `cutting_link` | TEXT | Cutting component identity and URL |
| `cutting_add_element`, `cutting_add_element_link` | TEXT | Extra cutting part |
| `notes` | TEXT | Free-text notes |
| `drill_nose_angle` | REAL | Drill-specific |
| `mill_cutting_edges` | INTEGER | Mill-specific |
| `spare_parts` | TEXT | Legacy (mirrors `notes`) |
| `geometry_profiles` | TEXT | JSON; stored but not surfaced in UI |
| `support_parts` | TEXT | JSON array of `{name, code, link}` |
| `stl_path` | TEXT | Single path string or JSON array of `{name, file, color}` |

#### `jaws` table columns

| Column | Type | Notes |
|---|---|---|
| `jaw_id` | TEXT PK | Jaw identifier |
| `jaw_type` | TEXT | Soft jaws / Hard jaws / Spiked jaws / Special jaws |
| `spindle_side` | TEXT | Main spindle / Sub spindle / Both |
| `clamping_diameter_text` | TEXT | Human-readable diameter value |
| `clamping_length` | TEXT | Clamping depth |
| `used_in_work` | TEXT | Comma-separated work/program IDs |
| `turning_washer` | TEXT | Washer specification |
| `last_modified` | TEXT | Date or revision note |
| `notes` | TEXT | Free-text notes |
| `stl_path` | TEXT | Path to a single STL file |
| `preview_plane` | TEXT | Saved alignment plane: `XZ` / `XY` / `YZ` |
| `preview_rot_x` | INTEGER | Saved rotation around X axis (degrees, 0–359) |
| `preview_rot_y` | INTEGER | Saved rotation around Y axis (degrees, 0–359) |
| `preview_rot_z` | INTEGER | Saved rotation around Z axis (degrees, 0–359) |

**Migration strategy:** additive only — `ALTER TABLE ADD COLUMN` for new columns, never dropping existing ones. Compatibility migrations handle legacy `shim_code`/`screw_code`/`assembly_parts` → `support_parts`, `spare_parts` → `notes`, and `cutting_type` inference.

---

## Service Layer

### `services/tool_service.py`

CRUD for the `tools` table.

- `list_tools(search, view_mode, type_filter)` — SQL search + Python-side `_view_match()` filter
- `get_tool(id)` — single row as dict
- `save_tool(tool_dict)` — upsert via `INSERT ... ON CONFLICT DO UPDATE`; mirrors `notes` into `spare_parts` for backward compat
- `delete_tool(id)`
- `copy_tool(source_id, new_id, new_description)` — full clone with new identity
- `_seed_if_empty()` — inserts sample tool `T1001` if table is empty

Important: `geometry_profiles` and `support_parts` are serialized/deserialized as JSON strings. `stl_path` is stored verbatim (overloaded: may be a plain path string or a JSON array string).

### `services/jaw_service.py`

CRUD for the `jaws` table.

- `list_jaws(search, view_mode, jaw_type_filter)` — SQL search over jaw fields
- `get_jaw(jaw_id)` → dict
- `save_jaw(jaw_dict)` — upsert; persists `preview_plane`, `preview_rot_x/y/z`
- `delete_jaw(jaw_id)`

No copy operation for jaws. No seeding.

### `services/export_service.py`

Handles Excel I/O for TOOLS via `openpyxl`.

- `GENERAL_FIELDS` — ordered list of `(internal_name, display_label)` pairs for the export
- `export_to_excel(tools, path)` — writes styled `.xlsx`; colored headers, row banding, auto-column widths, numeric formatting, filter row
- `read_excel_headers(path)` — returns first-row column names
- `import_tools(path, mapping, defaults)` — maps Excel columns to tool fields by the user mapping; returns list of tool dicts

Import type handling: REAL fields use `float()`, INTEGER fields use `int()`, JSON fields use `json.loads()`.

### `services/settings_service.py`

Simple JSON file read/write. Currently instantiated but not actively wired to runtime UI behavior. Treat as scaffolding.

---

## UI Layer

### `ui/main_window.py`

Top-level shell.

- Builds the animated left navigation rail (`QStackedWidget` + hover-reveal animation)
- Creates four `HomePage` instances (home / assemblies / holders / inserts) plus `JawPage`, `ExportPage`, `JawExportPage`
- Switches active page via nav rail
- Handles database switching: opens new `Database`, migrates schema, creates new `ToolService`, injects into all TOOLS pages, closes old connection
- switches back to Setup Manager through `QLocalSocket` IPC when requested
- applies a short fade-out animation before cross-app handoff
- Applies global QSS stylesheet from `styles/library_style.qss`

Database switching does NOT affect the JAWS database — jaws have their own separate database file path.

## Cross-App Switching

Tool Library participates in a paired Windows workflow with Setup Manager.

- `TOOL_LIBRARY_SERVER_NAME` accepts JSON IPC payloads for show/geometry/deep-link requests.
- Setup Manager is contacted through `SETUP_MANAGER_SERVER_NAME` when the user clicks the return button.
- Foreground handoff depends on the sender calling `AllowSetForegroundWindow(...)` before the IPC message.
- Receiver-side activation uses Qt activation first and Win32 `SetForegroundWindow(...)` as a fallback.
- Fade-out runs on the sending window before hide; fade-in runs on the receiving window after show.

Preserve this IPC-first path. Launching a fresh process should remain a fallback, not the normal transition.

Current integration notes (March 2026):
- Setup Manager can open Tool Library with launch-scoped master filters for linked tools/jaws
- Tool Library supports clearing previous master-filter state when opening in normal mode
- external IPC payloads can update geometry, deep-link target, and master-filter state
- tool list horizontal scrolling is intentionally disabled; row widgets should fit viewport width

### `ui/home_page.py`

The largest and most behavior-heavy file. Reused for all four TOOLS views with different `view_mode` values.

**Structure:**
- Top filter bar: page title, search toggle, details toggle, 3D preview toggle, type filter combo
- Content: `QSplitter` with tool list (left) and detail panel (right)
- Bottom action bar: COPY TOOL / EDIT TOOL / DELETE TOOL / ADD TOOL

**View modes:** `home`, `assemblies`, `holders`, `inserts` — filtered in `_view_match()`.

**Tool list:** `QListView` with `QStandardItemModel` and custom `ToolCatalogDelegate`. No nested widgets — all row painting is done by the delegate using QPainter.

- **ToolCatalogDelegate** (`ui/tool_catalog_delegate.py`) — responsible for rendering all rows
  - `paint()` — draws card background, border (1px normal / 3px selected), icon at fixed coordinates, text columns with responsive wrapping
  - `sizeHint()` — returns fixed `74px` height + vertical margins
  - Responsive stages computed from card width:
    - **Full** (≥620px): all columns displayed (Tool ID, Tool name, Geom X, Geom Z, Radius, Nose/Corner R)
    - **Reduced** (≥390px): Tool ID and Tool name only
    - **Name-only** (≥240px): Tool name only
    - **Icon-only** (<240px): icon only
  - Multi-line headers: "Nose / Corner R" renders as two lines when width allows
  - Vertical centering: text block centered between icon and card edge
  - Constant border inset (3px) — selection border change does not shift content
  - `_paint_description()` — word-wrap and two-line fitting for tool names in reduced/name-only stages
  - `_cached_pixmap()` — icon pixmap cache by tool_type

- Data roles stored in model:
  - `ROLE_TOOL_ID = Qt.UserRole` — tool id string
  - `ROLE_TOOL_DATA = Qt.UserRole + 1` — full tool dict
  - `ROLE_TOOL_ICON = Qt.UserRole + 2` — tool icon QIcon

- Key methods:
  - `refresh_list()` — clears model, populates from `tool_service.list_tools()`, restores previous selection
  - `_on_current_changed(current, previous)` — handles selection change; updates detail pane if visible
  - `_on_double_clicked(index)` — handles double-click (expand details or edit with Ctrl)
  - `select_tool_by_id(tool_id)` — programmatically select a tool
  - `_clear_selection()` — clear selection and close details
  - `eventFilter()` — detect empty-area clicks to clear selection

**Detail panel layout** (built in `populate_details()`):
1. Header: description, tool ID, type badge
2. Info grid (4-column `QGridLayout`):
 - Row 0: Geom X (cols 0–1) | Geom Z (cols 2–3)
 - Row 1: Radius (cols 0–1) | Nose R / Corner R (cols 2–3)
 - Rows 2+: Holder code, Add. Element, Insert/Drill/Mill code, Add. Insert — each full-width (cols 0–3)
 - Notes — full-width below those
3. Tool components panel (clickable buttons)
4. STL preview panel

Note: **Tool type is NOT shown as a separate field box** — it appears as the badge in the header only.

**Component buttons:** clicking opens the stored link via `QDesktopServices.openUrl()`. Component picker dialog mines all existing tool records for autocomplete.

**3D preview:**
- `_build_preview_panel()` creates `StlPreviewWidget`
- `_load_preview_content()` detects single-path vs JSON array in `stl_path`
- Detached preview window tracks current selection
- Detached preview toolbar uses a single measurements toggle button + label (no filter dropdown)
- Measurements toggle icon state: `comment.svg` (enabled) / `comment_disable.svg` (disabled)
- Detached preview dialog/toolbar use dedicated style properties: `detachedPreviewDialog` and `detachedPreviewToolbar`

### `ui/jaw_page.py`

**STATUS:** Still uses the legacy `QListWidget` + embedded row widgets. Needs rebuild matching the TOOLS delegate architecture (see FUTURE IMPLEMENTATIONS below).

Mirrors `home_page.py` in structure but for jaws.

**Jaw row card** (`JawRowWidget`): 4-column card — Jaw ID | Jaw type | Clamping diameter | Clamping length. Row height 112px. Icon is type-specific (`soft_jaw.png` at 52×52 for Soft/Hard jaws, `hard_jaw.png` at 48×48 for Spiked/Special). Icons use numpy-based white-pixel transparency removal (`_load_transparent_icon()`).

**Sidebar views:** All Jaws / Main Spindle / Sub Spindle / Soft Jaws / Hard,Spiked,Special.

**Detail panel** (`populate_details()`):
1. Header: Jaw ID, clamping diameter, jaw type badge
2. Info grid (4-column): Jaw ID (left), Spindle side (right), Clamping diameter (left), Clamping length (right), Turning washer (left), Last modified (right)
3. Used in works — full-width; splits `used_in_work` by comma, each value on its own line with 1px `QFrame` separators
4. Notes — full-width
5. STL preview — built with `StlPreviewWidget`; applies saved `preview_plane` and `preview_rot_x/y/z` immediately after load

Note: **Jaw type is NOT shown as a detail field box** — it appears only as the badge in the header.

**Preview orientation restore in detail panel:**
```python
viewer = StlPreviewWidget()
viewer.load_stl(stl_path, label=jaw.get('jaw_id', 'Jaw'))
viewer.set_alignment_plane(jaw.get('preview_plane', 'XZ'))
for axis, key in (('x', 'preview_rot_x'), ('y', 'preview_rot_y'), ('z', 'preview_rot_z')):
    deg = int(jaw.get(key, 0) or 0) % 360
    if deg:
        viewer.rotate_model(axis, deg)
```

### `ui/jaw_editor_dialog.py`

Add/Edit dialog for jaw records. Two tabs: **General** and **3D Model**.

**General tab:** Scrollable card layout matching Tool Editor style — `QScrollArea` containing `editorFieldCard` frames in a single-column `QGridLayout`. Fields: Jaw ID, Jaw type, Spindle side, Clamping diameter, Clamping length, Used in works, Turning washer, Last modified, Notes. Combos for Jaw type and Spindle side use `QSizePolicy.Fixed` with `min=180, max=240`.

**3D Model tab:**
- STL file path + BROWSE button
- Alignment plane combo (XZ / XY / YZ)
- ROT X / ROT Y / ROT Z buttons (each +90°)
- RESET ROT button
- `StlPreviewWidget` — auto-updates on `stl_path.editingFinished` and after BROWSE
- No manual PREVIEW button

**Preview state persistence:**
- `_preview_rotation_steps = {'x': 0, 'y': 0, 'z': 0}` tracks cumulative rotation
- `_load_jaw()` restores saved `preview_plane` + rotation steps from the jaw dict
- `get_jaw_data()` returns `preview_plane`, `preview_rot_x/y/z` alongside all other fields

### `ui/tool_editor_dialog.py`

Add/Edit dialog for tool records. Four tabs: **General**, **Components**, **Spare Parts**, **3D Models**.

- General tab: tool fields + holder/cutting picker buttons + drill/mill conditional fields
- Components tab: `PartsTable` storing `[{role, label, code, link, group}, ...]`; grouping controls
- Spare Parts tab: `PartsTable` storing `[{name, code, link, component_key, group}, ...]`; component linking
- 3D Models tab: `PartsTable` storing `[{name, file, color}, ...]`; live preview via `StlPreviewWidget.load_parts()`
- 3D Models tab also includes a transform row below the preview (mode toggle, fine toggle, XYZ values, reset)
- Transform snapshots are synchronized from the preview before save to avoid stale zero-value saves

**Modular structure (April 2026 refactor):** The dialog has been reduced to a thin coordinator (~970 lines). Tab construction and several self-contained responsibilities were extracted into `tool_editor_support/` modules. See `TOOL_EDITOR_REFACTOR.md` for the full log.

Key support modules:

| Module | Class / exports | Responsibility |
|---|---|---|
| `component_picker_dialog.py` | `ComponentPickerDialog` | Searchable picker for borrowing component data from existing tools |
| `spare_parts_table_coordinator.py` | `SparePartsTableCoordinator` | Spare parts table row management + debounced component dropdown refresh |
| `component_linking_dialog.py` | `ComponentLinkingDialog` | Modal for linking selected spare rows to a component |
| `general_tab.py` | `build_general_tab` | General tab widget construction |
| `components_tab.py` | `build_components_tab`, `build_spare_parts_tab` | Components + Spare Parts tab construction |
| `models_tab.py` | `build_models_tab` | 3D Models tab construction |
| `payload_adapter.py` | `ToolEditorPayloadAdapter` | Load/collect tool data to/from dialog widgets |
| `tool_type_rules.py` | field-state helpers | Determines which fields are visible per tool type |
| `detail_layout_rules.py` | `build_tool_type_layout_update` | Computes layout transitions for tool type changes |
| `measurement_rules.py` | normalize helpers | Normalizes XYZ/float/distance-space text values |
| `transform_rules.py` | transform dict helpers | Compacts/expands transform dicts |
| `components.py` | component query helpers | Mines existing tools for known component entries |

Component picker scans all existing tool records and deduplicates `(kind, name, code, link)` tuples.

### `ui/export_page.py`

For TOOLS: database selection and Excel I/O.

- Database switching: select `.db` file → `MainWindow._switch_database()` is called
- Excel export: calls `ExportService.export_to_excel()`
- Excel import: opens `ImportMappingDialog` → collects column mapping → calls `ExportService.import_tools()` → overwrites table or creates new DB
- Overwrite mode: confirmation dialog + optional timestamped backup copy

### `ui/jaw_export_page.py`

For JAWS: Excel I/O only (jaws use a fixed database path, no switching UI).

- Uses `JawImportMappingDialog` — a jaw-specific subclass showing only jaw fields (not tool fields), validates `jaw_id` not `id`
- GENERAL_FIELDS for jaws: jaw_id, jaw_type, spindle_side, clamping_diameter_text, clamping_length, used_in_work ("Used in works:"), turning_washer, last_modified, notes, stl_path

### `ui/stl_preview.py`

Python wrapper around the Three.js viewer.

**State fields:**
- `_alignment_plane: str` — current plane (`'XZ'` default)
- `_rotation_deg: dict` — cumulative `{x, y, z}` rotation in degrees

**Public API:**
- `load_stl(path, label)` — load single STL file
- `load_parts(parts)` — load multi-part assembly (`[{name, file, color}]`)
- `clear()` — unload current model
- `set_alignment_plane(plane)` — calls `window.setAlignmentPlane(plane)` in JS; also stores in `_alignment_plane`
- `rotate_model(axis, degrees)` — calls `window.rotateModel(axis, degrees)` in JS; accumulates into `_rotation_deg`
- `reset_model_rotation()` — calls `window.resetModelRotation()` in JS; zeros `_rotation_deg`
- `_apply_preview_transform_state()` — re-applies current `_alignment_plane` + `_rotation_deg` after any model load

**Load sequence:** `_on_load_finished()` calls `_apply_preview_transform_state()` after the viewer HTML has initialized.

### `ui/widgets/common.py`

- `AutoShrinkLabel` — QLabel that shrinks font size when text would overflow
- `BorderOnlyComboItemDelegate` — QStyledItemDelegate that renders combo items with border-only highlight
- `add_shadow()` — adds a subtle QGraphicsDropShadowEffect to a widget

---

## 3D Preview System

### Files

```
preview/
  index.html        — viewer shell, HUD with centered hint overlay
  viewer.js         — Three.js scene, loaders, window API
  viewer.css        — viewer styles, HUD layout
  three.module.js   — bundled Three.js
  OrbitControls.js  — orbit camera controls
  STLLoader.js      — STL geometry loader
```

### Viewer behavior (`viewer.js`)

- Loads STL via `STLLoader` using a `file://` URL
- Auto-orients the longest axis to be vertical, seats model on grid
- Scales grid to model footprint, frames camera to bounding sphere
- Supports single-model and multi-part assembly display
- State vars: `alignmentPlane` (string), `manualRotation` (THREE.Vector3)
- `applyAlignmentPlane(object)` — applies extra rotation based on plane: XZ=default, XY=rotateX(-90°), YZ=rotateZ(90°)
- `applyModelTransformAndFrame(refit)` — consolidated: orient + plane + manual rotation + grid fit + optional camera reframe
- Camera drag/click separation guards selection so orbit/pan drags do not clear selected parts
- Fine/regular transform modes use snapped increments (translation: 1.0 mm / 0.1 mm, rotation: 1.0° / 0.1°)

**Window API (callable from Python via `runJavaScript`):**
- `window.setAlignmentPlane(plane)` — change alignment plane and re-apply
- `window.rotateModel(axis, degrees)` — add rotation and re-apply
- `window.resetModelRotation()` — zero manual rotation and re-apply

### `stl_path` overload

`stl_path` is a dual-purpose field in the `tools` table:
- **Plain string** — path to a single STL file → loaded with `load_stl()`
- **JSON array string** — `[{"name": ..., "file": ..., "color": ...}, ...]` → loaded with `load_parts()`

`_load_preview_content()` in `home_page.py` tries `json.loads()` first; falls back to plain path. **Do not break this overload** when modifying the preview system.

Jaws use only plain string `stl_path` (single model). No JSON array support needed for jaws.

---

## Styling System

All visual styling is driven by Qt property-based CSS in `styles/library_style.qss`.

Key property names used throughout the codebase:

| Property | Used on |
|---|---|
| `toolListCard` | Row card frames in both tool and jaw lists |
| `toolCardHeader` | Column header labels in row cards |
| `toolCardValue` | Column value labels in row cards |
| `toolCardColumn` | Column wrapper widgets in row cards |
| `detailField` | Individual field boxes in detail panels |
| `detailFieldKey` | Field label inside a `detailField` |
| `detailValue` | Field value text |
| `detailFieldValue` | Additional styling for field value text |
| `detailHeroTitle` | Large title text in detail header |
| `detailHeader` | Header frame in detail panels and editors |
| `toolBadge` | Type badge label in headers |
| `editorFieldCard` | Individual field boxes in editor dialogs |
| `editorFieldsHost` | Grid host widget inside editor tabs |
| `subCard` | Nested card frame |
| `card` | Primary card frame |
| `panelActionButton` | Standard buttons |
| `primaryAction` | Blue/highlight button variant |
| `dangerAction` | Red/destructive button variant |
| `diagramPanel` | Preview area background frame |
| `pageTitle` | Page title label |
| `detailSectionTitle` | Section heading inside panels |

---

## Selection and Navigation Rules

- Clicking empty space in a list clears selection
- `Escape` clears selection
- Double-click opens or closes the detail panel
- `Ctrl + double-click` opens the edit dialog
- Detail panel is hidden by default; shown when toggled or opened from double-click
- Detail panel is repopulated from fresh data whenever selection changes while visible
- Detached preview (TOOLS only) closes itself if no valid model data exists

---

## Database Switching (TOOLS)

`MainWindow._switch_database()`:
1. Opens selected `.db` via `Database`
2. Runs schema migration
3. Creates new `ToolService`
4. Injects service into all four `HomePage` instances and `ExportPage`
5. Refreshes all pages
6. Closes old connection
7. If new DB is empty, `ToolService._seed_if_empty()` inserts sample tool `T1001`

JAWS do not participate in database switching. They always use their own fixed database path.

---

## Excel Import Safety

Overwrite import (`ExportPage.import_excel()`):
1. Confirmation dialog
2. Optional timestamped backup of current `.db` file
3. `DELETE FROM tools`
4. Loop: `save_tool()` for each imported row

New-database import:
1. Open/create target DB
2. Migrate schema
3. `ToolService._seed_if_empty()` seeds sample if empty
4. Immediately `DELETE FROM tools` (removes the seed)
5. Loop: `save_tool()` for each imported row

**Known gap:** `support_parts` text that is not valid JSON is silently discarded (becomes empty list).

---

## Known Fragile Areas

| Area | Risk |
|---|---|
| `stl_path` in tools | Dual-use field (plain path or JSON array); must be preserved |
| `spare_parts` | Legacy column; `save_tool()` mirrors `notes` into it for compat |
| `geometry_profiles` | Stored but never surfaced in UI; do not remove |
| `SettingsService` | Instantiated but not wired to any runtime behavior |
| `models/tool.py` | Contains dataclasses but app uses plain dicts instead |
| `HomePage` | Extremely behavior-dense; list, selection, details, preview, and CRUD all converge here |
| `AddEditToolDialog` | Serializes support parts and 3D models as JSON; careful with save/load symmetry |
| `migrations.py` | Protects compatibility with existing `.db` files across users; additive only |

---

## Recommended Verification Checklist After Major Edits

- Open app, switch between TOOLS and JAWS pages
- Add a tool, edit it, copy it, delete it
- Add a jaw, edit it (set alignment plane + rotation), delete it
- Verify detail panel shows correct 3D orientation for a jaw with saved rotation
- Export TOOLS to Excel; export JAWS to Excel
- Import TOOLS from Excel into new DB; import into current DB with backup
- Open inline 3D preview for a tool with a multi-part model
- Open inline 3D preview for a jaw; confirm orientation matches editor
- Switch to another database file
- Search in both modules

---

## Coding Style Conventions

- Direct PySide6 code; minimal abstraction
- Service methods receive and return plain dicts
- UI helper methods live inside the UI class that uses them
- JSON text storage for list-like fields (`support_parts`, `geometry_profiles`, `stl_path` assembly)
- Property-based styling only — do not use `setStyleSheet()` for anything that should be overrideable from QSS
- Field names must stay aligned across: database column, service dict key, editor widget name, export field label, import mapping key

## System Architecture

The application is a PySide6 desktop client with a thin service/data layer and a single SQLite-backed record model.

High-level flow:

1. `main.py` starts `QApplication`, shows a progress dialog, creates core services, warms up the 3D preview widget, and opens the main window.
2. `ui.main_window.MainWindow` builds the navigation shell and hosts all top-level pages in a `QStackedWidget`.
3. `ui.home_page.HomePage` is reused for four filtered catalog views: `home`, `assemblies`, `holders`, and `inserts`.
4. `ui.tool_editor_dialog.AddEditToolDialog` edits a single tool record.
5. `ui.export_page.ExportPage` handles database switching and Excel import/export.
6. `services.tool_service.ToolService` is the main persistence layer for CRUD on tool records.
7. `data.database.Database` opens SQLite and runs schema creation/migration immediately.
8. `ui.stl_preview.StlPreviewWidget` wraps a local HTML/Three.js viewer inside `QWebEngineView`.

The project is intentionally simple: there is no ORM, no controller layer, and no separate API. Most behavior lives directly in the UI classes, with `ToolService` and `ExportService` acting as helper layers.

## Design Philosophy

The design is pragmatic and UI-first.

Key architectural choices:

- One main table, `tools`, holds almost everything.
- Derived views are favored over separate normalized tables.
- SQLite files are treated as interchangeable libraries.
- Import/export is designed for operator control, not silent automation.
- The 3D preview is local and self-contained, using bundled viewer files rather than external web dependencies.

This means the project is easy to move and easy to inspect, but it also means relationships are denormalized and several meanings are carried by naming conventions and JSON-in-text fields.

## Local Environment

The repository includes a local virtual environment in `.venv/`.

Purpose:

- keep project dependencies isolated from the system Python
- bundle the exact runtime packages used by the app
- make it easier to run the desktop app locally without reinstalling dependencies each time

Observed package set in the bundled environment includes at least:

- `PySide6`
- `PySide6 Addons`
- `PySide6 Essentials`
- `openpyxl`
- `numpy`

Important caution:

- `.venv` is environment scaffolding, not application source
- future agents should usually ignore `.venv` when analyzing or editing the codebase
- the environment may not be portable if the base Python path in `.venv/pyvenv.cfg` no longer exists on the current machine

## Main Entry Point

`main.py`

Responsibilities:

- create `QApplication`
- show startup progress UI
- instantiate `Database`, `ToolService`, `ExportService`, and `SettingsService`
- warm up `StlPreviewWidget`
- create and show `MainWindow`

Important behavior:

- `Database(DB_PATH)` will create or migrate the schema on startup
- `ToolService(db)` will seed a sample tool if the database is empty

## Major Modules

### `config.py`

Central constants:

- application paths
- default database path
- settings path
- stylesheet path
- export default path
- tool type lists
- icon mapping tables
- navigation item names

This file is the canonical source for path conventions and tool type choices.

### `data/database.py`

Very small wrapper around `sqlite3`.

Responsibilities:

- open connection
- set `row_factory` to `sqlite3.Row`
- call schema migration

There is no connection pooling or transaction abstraction beyond `with conn:`.

### `data/migrations.py`

Owns schema creation and compatibility migrations.

Current schema revolves around a single `tools` table with columns for:

- core tool identity
- geometry values
- holder fields
- cutting component fields
- notes
- drill/mill-specific numeric fields
- legacy `spare_parts`
- JSON text fields for `geometry_profiles` and `support_parts`
- `stl_path`

Notable migration behavior:

- adds missing columns with `ALTER TABLE`
- migrates legacy `shim_code`, `screw_code`, and `assembly_parts` into `support_parts`
- copies legacy `spare_parts` into `notes` when needed
- infers `cutting_type` for older rows

Important compatibility detail:

- `spare_parts` is now effectively legacy, but `ToolService.save_tool()` still mirrors `notes` into `spare_parts`

### `services/tool_service.py`

The main CRUD layer.

Responsibilities:

- seed a default sample record if database is empty
- normalize JSON-backed fields to Python lists
- list tools with search and type filtering
- get a single tool
- save tool data with upsert behavior
- delete tool
- copy tool

Important behavior:

- `save_tool()` uses a single `INSERT ... ON CONFLICT(id) DO UPDATE`
- `geometry_profiles` and `support_parts` are serialized as JSON strings
- `stl_path` is stored verbatim as a string
- `copy_tool()` clones the full record, changes the ID, optionally changes description, and saves it as a new record

### `services/export_service.py`

Handles Excel I/O through `openpyxl`.

Responsibilities:

- define exportable general fields
- read Excel headers
- import rows from mapped headers
- export rows to a styled workbook

Current scope:

- export is focused on the General tab fields
- import can also map `support_parts` and `stl_path`
- `geometry_profiles` exists in `IMPORT_DEFAULTS` but is not exposed in the import dialog UI

Important caveat:

- despite the import dialog label saying `Support parts (JSON or text)`, the actual parser only accepts JSON lists for `support_parts`; non-JSON text falls back to an empty list

### `services/settings_service.py`

Simple JSON file load/save helper.

Current reality:

- the service is instantiated
- the repository includes `library_settings.json`
- current UI code does not actively use it for runtime behavior

Treat this as scaffolding for future persistence rather than an actively wired subsystem.

### `ui/main_window.py`

Top-level shell.

Responsibilities:

- build central window
- build animated left navigation rail
- create the four `HomePage` variants and one `ExportPage`
- switch active page
- apply QSS stylesheet
- switch active database and rebind page services

Important behavior:

- `ASSEMBLIES`, `HOLDERS`, and `INSERTS` are all `HomePage` instances with different `view_mode` values
- switching databases creates a new `Database` and a new `ToolService`, then injects that service into all pages
- old database connections are closed after successful switch

### `ui/home_page.py`

This is the core user-facing page and contains a large share of the application's behavior.

Responsibilities:

- build the catalog page shell
- manage search/filter controls
- populate the list
- manage current selection
- open and close detail panel
- display tool details
- display clickable component links
- manage detached 3D preview
- launch add/edit/copy/delete workflows

View modes:

- `home`: full tool list
- `holders`: tools with non-empty `holder_code`
- `inserts`: tools with non-empty `cutting_code`
- `assemblies`: tools with support parts or multi-part 3D model data

Search/filter behavior:

- text search is passed to `ToolService.list_tools()`
- the SQL search matches ID, description, holder code, cutting code, notes, and several numeric fields rendered as strings
- tool type filter is exact-match on `tool_type`
- view mode filtering happens after data retrieval in `_view_match()`

Detail panel behavior:

- built dynamically every time selection changes while details are visible
- includes header, info grid, notes, components section, and preview section
- component buttons open stored links via `QDesktopServices.openUrl()`

### `ui/tool_editor_dialog.py`

Dialog for creating and editing one tool record.

Tabs:

- `General`
- `Additional Parts`
- `3D Models`

General tab:

- collects core tool fields
- holder and cutting code rows include a picker button
- drill/mill-specific fields are shown based on selected `cutting_type`

Additional Parts tab:

- uses `PartsTable`
- stores rows as `[{name, code, link}, ...]`

3D Models tab:

- also uses `PartsTable`
- stores rows as `[{name, file, color}, ...]`
- updates preview live through `StlPreviewWidget.load_parts()`
- includes a transform row for gizmo editing (move/rotate mode, fine toggle, XYZ fields, reset)
- transform values are pulled from viewer snapshots before serialization on save

Component picker behavior:

- `_iter_known_components()` scans every existing tool record
- it extracts holder, cutting, extra, and support entries from those records
- it deduplicates by `(kind, name, code, link)`
- selected entry is copied into the current editor fields

Important data-model detail:

- this is not a foreign-key relation picker
- it is a convenience picker over denormalized data already stored in tool records

### `ui/export_page.py`

Handles two operational concerns:

- database selection and switching
- Excel import/export

The import mapping dialog:

- visually connects Excel headers to software fields
- enforces one-to-one header mapping
- lets the user choose between overwrite and new-database import

Safety behavior:

- overwrite import asks for confirmation
- overwrite import offers optional backup creation
- backups are timestamped copies created beside the active `.db`

### `ui/stl_preview.py`

Qt wrapper for the local web-based viewer.

Responsibilities:

- host `preview/index.html` in `QWebEngineView`
- pass local STL file URLs into JavaScript
- support either a single STL model or an assembly list
- provide fallback error text when viewer or file loading fails

Important behavior:

- `load_stl()` expects a single file path
- `load_parts()` expects a list of `{name, file, color}` dicts
- wheel behavior is customized so normal scrolling can still scroll the surrounding Qt page unless zoom mode is enabled

### `preview/`

Self-contained 3D viewer assets.

Files:

- `index.html`
- `viewer.js`
- `viewer.css`
- bundled `three.module.js`, `OrbitControls.js`, `STLLoader.js`

Viewer behavior in `viewer.js`:

- creates a local Three.js scene
- loads STL geometry via `STLLoader`
- auto-orients the model so the longest axis becomes vertical
- seats the object on the grid
- scales the grid to the object footprint
- frames the camera to the model bounding sphere
- supports both single-model and multi-part assembly display

## UI Logic and Rules

### Navigation

- left rail buttons switch `QStackedWidget` pages
- nav reveal is animated on hover

### Selection rules

- clicking empty space in the list clears selection
- `Escape` also clears selection
- double-click opens or closes details
- `Ctrl + double-click` opens edit dialog

### Details panel rules

- hidden by default
- only shown when explicitly toggled or opened from double-click
- repopulated from fresh data on selection changes if already visible

### Preview rules

- detached preview is tied to current selection
- if no valid model data exists, the detached preview closes itself
- inline detail preview and detached preview both use the same loader logic
- camera drag for orbit/pan should not clear current 3D part selection

### Editor rules

- `Tool ID` is required
- numeric fields are parsed locally and raise `ValueError` on invalid input
- drill and mill extra fields are only saved for matching `cutting_type`
- active edits are committed on tab switch or save by clearing focus

## Database Logic and Safety Mechanisms

### Database type

- SQLite
- one main table: `tools`

### Schema strategy

- create-if-missing
- additive migration for missing columns
- compatibility migration for older fields

### Database switching

`MainWindow._switch_database()`:

- opens the selected file through `Database`
- runs schema creation/migration
- creates a new `ToolService`
- swaps page references to the new service
- refreshes UI pages
- closes the old connection

Important side effect:

- if the selected database is empty, `ToolService` seeds sample tool `T1001`

### Import overwrite safety

`ExportPage.import_excel()` in overwrite mode:

- asks for destructive confirmation
- optionally creates timestamped backup
- deletes all rows from `tools`
- saves imported tools through `ToolService.save_tool()`

### Import new-database mode

- creates/open target DB
- runs schema/migration
- `ToolService` may seed the sample tool first
- code immediately deletes all rows from `tools`
- imported rows are then saved

This is safe, but it is worth knowing when debugging import behavior.

## Excel Import Mapping System

### Exported fields

`ExportService.GENERAL_FIELDS` defines the human-facing Excel columns. Export currently matches the General tab, not the full internal record shape.

### Import pipeline

1. `read_excel_headers()` reads the first row of the workbook.
2. `ImportMappingDialog` collects the user's column mapping.
3. `import_tools()` iterates rows and builds tool dicts from mapped headers.
4. Imported dicts are passed into `ToolService.save_tool()`.

### Type handling

- float fields: parsed with `float(...)`
- int fields: parsed with `int(...)`
- `support_parts` and `geometry_profiles`: parsed as JSON lists
- all other mapped fields: stored as stripped strings

### 3D model import behavior

`stl_path` is treated as plain text during Excel import.

This is intentional because the rest of the app supports both:

- a plain STL path string
- a JSON string describing multiple model parts

### Gaps to remember

- the import dialog does not expose `geometry_profiles`
- support-part text that is not valid JSON is effectively discarded

## 3D Preview System

Data path:

1. editor stores model rows in the `3D Models` tab
2. dialog serializes that list into `stl_path` as JSON
3. `HomePage._load_preview_content()` tries to `json.loads(stl_path)`
4. if parsed result is a list, it loads an assembly
5. if parsed result is a string, or JSON parsing fails, it treats `stl_path` as a single STL file path

This means `stl_path` is overloaded:

- historical single-model string
- current multi-part JSON array

That overload is important and fragile. Preserve it unless you are deliberately migrating the format everywhere.

Detached preview measurement controls (TOOLS):
- top-left toolbar contains icon toggle + "Measurements" label only
- icon reflects state (`comment.svg` / `comment_disable.svg`)
- measurement filter dropdown has been removed

## How Records Link to Each Other

There are no foreign keys between tools, holders, inserts, or spare parts.

Instead:

- the tool record embeds holder and cutting component fields directly
- support parts are stored as JSON inside the tool row
- UI component pickers mine existing tool rows to help reuse codes and links

So relationships are semantic, not relational.

Derived page meanings:

- `Holders` page: tools that happen to have holder data
- `Inserts` page: tools that happen to have cutting component data
- `Assemblies` page: tools that have support parts or multiple 3D parts

Do not assume these are separate entity types in the database.

## COPY TOOL Feature

Implemented in `ToolService.copy_tool()` and called from `HomePage.copy_tool()`.

Behavior:

- fetch source tool
- reject if source does not exist
- reject if new ID already exists
- clone full tool payload
- replace `id`
- optionally replace `description`
- save cloned record with normal upsert path

Implications:

- support parts and 3D model data are copied too
- copied tool keeps the same holder/cutting links and STL references
- because STL references may be absolute file paths, copied tools can inherit machine-specific paths

## Safely Editing This Project

### Rules to follow

- Preserve the single-table storage model unless you are intentionally doing a broad migration.
- Keep backward compatibility for `stl_path` accepting both plain strings and JSON arrays.
- Keep backward compatibility for legacy `spare_parts` during saves/migrations unless you also migrate all readers.
- Be careful with `ToolService._seed_if_empty()` because it affects empty-database behavior across app startup and database switching.
- Treat `HomePage`, `AddEditToolDialog`, and `ExportPage` as behavior-heavy modules. Small UI changes often affect data flow.
- Verify whether a field is truly in use before removing it. `geometry_profiles` is stored but not surfaced; `SettingsService` exists but is not wired.
- If you change import/export fields, update both `ExportService` and `ImportMappingDialog`.
- If you change preview data format, update editor save/load, detail preview, detached preview, and Excel import behavior together.

### Recommended verification after edits

- open the app and switch pages
- add a tool and edit it
- copy a tool
- delete a tool
- export to Excel
- import from Excel into a new DB
- import into current DB with backup
- open inline and detached 3D preview
- switch to another database file

## Coding Style Expectations

The existing codebase favors:

- direct, readable PySide code
- low abstraction
- practical helper methods inside UI classes
- service methods that operate on plain dicts
- JSON text storage for list-like fields

When modifying code:

- keep naming aligned with current field names
- avoid introducing a heavy framework or ORM
- prefer incremental changes over architectural rewrites
- preserve current UI terminology because it is user-facing and repeated across multiple screens

## Fragile or Important Areas

- `ui/home_page.py`
  Central behavior hub; list refresh, selection, details, preview, and CRUD all meet here.
- `ui/tool_editor_dialog.py`
  Serializes important fields, including support parts and 3D model JSON.
- `services/tool_service.py`
  Owns save format and copy behavior.
- `data/migrations.py`
  Protects compatibility with existing `.db` files.
- `stl_path`
  Name suggests one path, but current code uses it for single-path and assembly JSON.
- `support_parts`
  JSON-backed and reused in multiple UI flows.
- `SettingsService`
  Present but currently inactive; easy to misread as already-integrated behavior.

Also note:

- `models/tool.py` contains dataclasses but the active app mostly uses plain dicts instead
- `_browse_model_file_for_row()` exists in the editor but is not currently wired into the model table UI

## Future Expansion Ideas

- Introduce first-class tables for holders, cutting components, and parts if true relational reuse becomes necessary
- Add a dedicated asset-management layer for STL files, including relative-path storage and validation
- Expand Excel import/export to include full support-part and multi-model structures in a more user-friendly format
- Persist UI settings such as active database, window geometry, selected page, and filter preferences
- Add automated link validation and missing-file detection for STL paths
- Add tests around migrations and import/export because those are the most data-sensitive paths

---

## FUTURE IMPLEMENTATIONS

### JAWS Library Catalog Rebuild (March 2026+)

**Status:** `ui/jaw_page.py` still uses the legacy `QListWidget` + embedded `JawRowWidget` approach. Needs the same delegate-based rebuild that was completed for the TOOLS module in March 2026.

**Motivation:** The TOOLS rebuild eliminated responsive layout instability by replacing nested widgets with delegate-based painting. This same architecture should be applied to JAWS for consistency and robustness.

**Scope:**

1. **New file:** `ui/jaw_catalog_delegate.py`
   - `JawCatalogDelegate(QStyledItemDelegate)` — renders jaw rows via QPainter
   - Layout constants: `ROW_HEIGHT`, `ICON_SIZE`, `ICON_SLOT_W`, responsive breakpoints (`BP_FULL`, `BP_REDUCED`, `BP_NAME_ONLY`)
   - Data roles: `ROLE_JAW_ID`, `ROLE_JAW_DATA`, `ROLE_JAW_ICON`
   - `paint()` method:
     - Card background, border (1px normal / 3px selected), constant inset
     - Icon at fixed coordinates
     - Responsive stages: full (4 columns: Jaw ID, Jaw type, Clamping diameter, Clamping length) → reduced (2 columns) → icon-only
     - Vertically centered text block
     - Multi-line header support (if needed for wider labels)
   - `sizeHint()` method: fixed row height + vertical margins
   - `_paint_description()` — word-wrap fitting for jaw type/diameter columns if needed
   - `_cached_pixmap()` — icon pixmap cache by jaw_type

2. **Refactor:** `ui/jaw_page.py`
   - Remove `JawRowWidget` class (~250 lines)
   - Remove `ResponsiveJawRowWidget` class (~180 lines)
   - Update imports: add `QListView`, `QStandardItemModel`, `JawCatalogDelegate`, etc.
   - Replace `self.jaw_list = QListWidget()` with `QListView + QStandardItemModel + JawCatalogDelegate`
   - Rewrite `refresh_list()` to populate `QStandardItemModel` instead of `QListWidget`
   - Create/rename signal handlers:
     - `_on_current_changed(current: QModelIndex, previous: QModelIndex)` — update selection, populate detail pane
     - `_on_double_clicked(index: QModelIndex)` — handle double-click (expand/collapse details)
   - Update `select_jaw_by_id()` to use `QStandardItemModel` API
   - Update `_clear_selection()` to use `selectionModel().clearSelection()`
   - Update `eventFilter()` to use `indexAt()` instead of `itemAt()`
   - Update `_update_row_type_visibility()` to call `viewport().update()` if needed
   - Detail panel, preview, editor, and export logic remain unchanged

3. **Testing points:**
   - List refresh and filter behavior
   - Row selection (single click, double click, keyboard, Escape)
   - Detail pane open/close on selection change
   - Responsive width transitions (full → reduced → icon-only)
   - Inline and detached 3D preview
   - Excel export/import
   - Database switching

**Estimated effort:**
- ~310 lines new delegate code
- ~430 lines deleted from jaw_page.py (old row widget classes)
- ~150 lines modified in jaw_page.py (refresh, selection, event handlers)
- ~3–4 hours of work including testing

**Timeline:** Post-TOOLS stabilization. Can be done independently after TOOLS rebuild approval.

