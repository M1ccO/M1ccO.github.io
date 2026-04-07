# Tools and jaws Library

A local desktop application for managing CNC machining tooling and jaw chuck data. Built for shop-floor and engineering environments where a structured, searchable, importable, and exportable tool library is needed without relying on external services or cloud systems.

When used beside Setup Manager, Tool Library also acts as the master-data side of a paired desktop workflow with smooth switching between the two apps.

---

## What This Software Does

Tools and jaws Library gives you two separate, fully integrated modules in a single desktop window:

- **TOOLS** — a catalog of cutting tools, holders, inserts, drills, and mills with full component tracking
- **JAWS** — a catalog of chuck jaw sets (soft jaws, hard jaws, spiked jaws, special jaws) used across machining operations

Both modules support adding, editing, copying, deleting, searching, filtering, exporting to Excel, and importing from Excel. Both support attaching 3D STL models for live in-app preview.

---

## The TOOLS Module

### What a Tool Record Contains

A single tool record describes the full build-up of a usable cutting assembly:

| Field | Description |
|---|---|
| Tool ID | Unique identifier, e.g. `T1001` |
| Tool type | Turning, Milling, Drilling, etc. |
| Description | Free-text name, e.g. `Ulkorouhinta - 55/R1.2` |
| Geom X / Geom Z | Geometry offset values |
| Radius | Tool radius |
| Nose R / Corner R | Nose or corner radius |
| Holder code | Holder identifier + optional web link |
| Add. Element | Optional extra holder component + link |
| Insert / Drill / Mill code | Cutting component identifier + optional link |
| Add. Insert | Optional extra cutting component + link |
| Cutting type | Insert, Drill, or Mill |
| Drill nose angle | Nose angle for drill tools |
| Cutting edges | Number of cutting edges for mill tools |
| Support parts | List of additional assembly parts (name, code, link) |
| Notes | Free-text notes |
| 3D Models | One or more STL files for 3D preview |

### Tool Pages

The navigation offers four filtered views of the same tool database:

- **Tools** — the full library
- **Assemblies** — tools that have support parts or multiple 3D model parts
- **Holders** — tools that have a holder code
- **Inserts** — tools that have a cutting component code

These are not separate databases. They are filtered views.

### Tool Detail Panel

When a tool is selected and the detail panel is open:

- Header: description, tool ID, and type badge
- Info grid: Geom X, Geom Z, Radius, Nose R / Corner R in a 2-column layout, followed by full-width rows for Holder code, Add. Element, Insert code, and Add. Insert
- Notes (if present)
- **Tool components** section with clickable buttons — clicking a component button opens its stored web link in the system browser
- **Preview** section with an inline 3D STL viewer

### Linking and Component Picker

Instead of a separate holder or insert table, holder and cutting component data is stored directly inside each tool record. When editing a tool, a picker button lets you borrow codes and links from existing tool records, so common components do not need to be retyped.

---

## The JAWS Module

### What a Jaw Record Contains

| Field | Description |
|---|---|
| Jaw ID | Unique identifier |
| Jaw type | Soft jaws, Hard jaws, Spiked jaws, Special jaws |
| Spindle side | Main spindle, Sub spindle, or Both |
| Clamping diameter | Diameter range or value, e.g. `52.40 mm` or `50–58 mm` |
| Clamping length | Clamping depth value |
| Used in works | Comma-separated list of work/program IDs |
| Turning washer | Washer specification |
| Last modified | Date or revision note |
| Notes | Free-text notes |
| 3D Model | Single STL file for 3D preview |
| Preview plane | Saved alignment plane for the 3D view (XZ / XY / YZ) |
| Preview rotation | Saved X/Y/Z rotation offsets for the 3D view |

### Jaw Catalog Page

Each jaw row in the list shows four columns: **Jaw ID**, **Jaw type**, **Clamping diameter**, and **Clamping length**. Icons change by type — soft jaws and hard jaws use distinct icons.

Filtered sidebar views:

- All Jaws
- Main Spindle
- Sub Spindle
- Soft Jaws
- Hard / Spiked / Special

### Jaw Detail Panel

- Header: Jaw ID, clamping diameter, and jaw type badge
- Info grid: Jaw ID, Spindle side, Clamping diameter, Clamping length, Turning washer, Last modified
- **Used in works** — each work ID appears on its own line, separated by a divider
- Notes (if present)
- **Preview** section with an inline 3D STL viewer, automatically oriented to the saved alignment plane and rotation

### 3D Alignment Controls (Jaw Editor)

The 3D Model tab in the jaw editor provides:

- **Alignment plane** selector (XZ / XY / YZ) to orient the model to the correct base plane
- **ROT X / ROT Y / ROT Z** buttons to rotate the model in 90° steps
- **RESET ROT** to return to the base plane orientation

The chosen plane and rotation are saved with the jaw record and are automatically applied when the jaw is shown in the detail panel.

---

## 3D Preview System

Both modules use a shared self-contained 3D viewer built on [Three.js](https://threejs.org/), running inside an embedded browser panel.

- STL models are loaded locally — no internet connection is needed
- The viewer auto-orients the model to be upright and centers it on the grid
- The camera is automatically framed to the model bounding sphere
- Controls: left-drag to orbit, right-drag to pan, scroll wheel to zoom
- The JAWS module supports saving a specific alignment plane and rotation per jaw
- The TOOLS module supports multi-part assembly preview (multiple STL files loaded together)
- In the TOOLS editor, the `3D Models` tab supports gizmo-based move/rotate editing with numeric X/Y/Z fields, fine-tune mode, and transform reset controls
- Detached TOOLS preview has a top-left measurements toggle with state icons (`comment.svg` = visible, `comment_disable.svg` = hidden)
- Detached TOOLS preview no longer includes a measurement filter dropdown (show/hide only)

---

## Tool Catalog Rendering

The TOOLS module uses a high-performance **QListView + custom delegate** architecture for the catalog list:

- **QListView** with `QStandardItemModel` provides efficient row virtualization
- **ToolCatalogDelegate** uses Qt's native `QPainter` to render each row deterministically
- **No nested widgets** — all layout computed from paint coordinates; eliminates timing bugs and layout thrashing
- **Responsive stages** — rows adapt to viewport width in real-time (full → reduced → name-only → icon-only)
- **Multi-line headers** — field labels like "Nose / Corner R" render on two lines when the card is wide enough
- **Hover + selection states** — card background and border change interactively; selection border (3px) has constant inset so rows don't shift
- **Vertical centering** — text blocks are automatically centered between icon and card edge

This replaces the previous widget-based approach, fixing responsive layout stability and eliminating icon/margin drift.

---

## Excel Export and Import

### Export

Exports the library to a formatted `.xlsx` file:

- Colored header row
- Light row coloring by tool or jaw type
- Auto-sized columns
- Numeric cell formatting
- Filter row enabled

### Import

Import works in two steps:

1. Select an Excel file
2. Map the Excel column headers to application fields in a visual dialog

Two import modes:

- **Overwrite current database** — clears existing records and replaces with imported data (offers a timestamped backup first)
- **Import into new database file** — creates a fresh database from the Excel file without touching your current library

The TOOLS and JAWS modules have separate import dialogs with fields specific to each.

---

## Database Switching

From the Export / Import page you can select any `.db` file as the active library. The application immediately migrates the schema if needed and reloads all pages. This allows maintaining separate libraries (e.g., by machine, project, or operator) and switching between them without restarting.

---

## Integration with Setup Manager

Tool Library is intended to run beside the sibling Setup Manager application.

- Setup Manager reads tool and jaw master data from Tool Library in read-only mode.
- Tool Library can be opened from Setup Manager and can switch back to Setup Manager without a full re-launch when both apps are already running.
- The handoff uses local single-instance IPC plus a short fade transition in both directions so the switch feels continuous.
- Tool and jaw ownership stays in Tool Library; setup and logbook ownership stays in Setup Manager.

---

## Repository Cleanup Notes (March 2026)

The Tool Library icon set was cleaned to remove unused legacy alias files named `ToolIdentification_Small_*.png`.

Canonical icon names in active runtime are defined by config mappings and UI lookups under `assets/icons/tools`.

If you add new tool-type icons, wire them through the existing config mapping instead of introducing alternate alias filenames.

---

## How to Run

**Requirements:** Windows, Python 3.10

```powershell
python main.py
```

If you are using the included virtual environment:

```powershell
.venv\Scripts\activate
python main.py
```

If Setup Manager is started first, Tool Library may already be running hidden in the background to make switching faster.

---

## How to Build an EXE

The recommended packaging method is a PyInstaller one-folder build:

```powershell
.\build_exe.ps1
```

This script:
1. Creates a fresh build environment in `.build-venv`
2. Installs packaging dependencies from `requirements-build.txt`
3. Builds the app using `library.spec`

Output:
```
dist\Tools and jaws Library\Tools and jaws Library.exe
```

### Manual build

```powershell
py -3.10 -m venv .build-venv
.build-venv\Scripts\python.exe -m pip install --upgrade pip
.build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
.build-venv\Scripts\python.exe -m PyInstaller --noconfirm --clean library.spec
```

### Installer

If Inno Setup 6 is installed:

```powershell
.\build_installer.ps1 -AppVersion 1.0.0
```

Output is written to the `installer-dist` folder. The installer performs a per-user install (no admin rights required) under `%LOCALAPPDATA%\Programs\Tools and jaws Library`.

### First-run data location (packaged EXE)

Writable files are stored at:
```
%LOCALAPPDATA%\Tools and jaws Library\
```
This includes the active SQLite database (`databases\tool_library.db`), settings JSON, and the default Excel export path. The bundled starter database is copied here automatically on first run.

---

## Dependencies

| Package | Purpose |
|---|---|
| `PySide6` | Desktop UI framework |
| `Qt WebEngine` (via PySide6) | Embedded 3D preview browser |
| `openpyxl` | Excel import and export |
| `numpy` | Icon transparency processing |

---

## About the `.venv` Folder

The repository includes a `.venv` folder with a local Python virtual environment. This keeps the application's dependencies isolated from the system Python and ensures consistent package versions for local development. It is not part of the application logic and should be treated as environment scaffolding.

## Overview

Tools and jaws Library is a local desktop application for managing a machining tool library. It is built for storing tool records, browsing them in a visual catalog, opening detailed tool information, maintaining linked holder and cutting component data, tracking spare and support parts, and attaching 3D STL previews to complete assemblies.

The application is designed around one practical goal: keep the tool library in a format that is easy to browse, edit, copy, export to Excel, and import back into a database safely.

## What the Software Is For

This software acts as a structured library for shop-floor or engineering tooling data. A single tool record can contain:

- the main tool identity
- geometry values such as `Geom X`, `Geom Z`, radius, and nose/corner radius
- the holder used with the tool
- the cutting component used with the tool
- optional extra holder and cutting elements
- support or spare parts such as screws, clamps, shims, and sleeves
- optional 3D STL models for previewing the tool or assembly

Instead of splitting holders, inserts, and assemblies into separate databases, the application keeps everything centered around tool records and provides filtered views for different use cases.

## Main Features

- Tool catalog with icon-based rows and a detail panel
- Separate catalog views for `Tools`, `Assemblies`, `Holders`, and `Inserts`
- Add, edit, copy, and delete tool records
- Search by ID, description, holder code, cutting code, notes, and key numeric values
- Filter by tool type
- Store holder, cutting component, and support-part links
- Attach one or more STL files for 3D preview
- Export the library to Excel
- Import Excel data with manual field mapping
- Switch between SQLite database files
- Optional automatic backup before Excel overwrite import

## How the UI Is Organized

The application opens into a main window with a left navigation rail and a page area.

### Main pages

- `Tools`
  Shows the full tool library.
- `Assemblies`
  Shows tools that behave like assemblies, meaning they have support parts or multiple 3D model parts.
- `Holders`
  Shows tools that have a holder code.
- `Inserts`
  Shows tools that have a cutting component code.
- `Export`
  Handles Excel import/export and database switching.

### Tool catalog page layout

Each catalog page has three main areas:

- Top filter bar
  Contains the page title, search toggle, details toggle, tool-type filter, and detached 3D preview toggle.
- Main content area
  Contains the tool list on the left and the tool detail panel on the right.
- Bottom action bar
  Contains `COPY TOOL`, `EDIT TOOL`, `DELETE TOOL`, and `ADD TOOL`.

Current list behavior:
- horizontal scrolling is disabled for the tool list
- row cards are expected to adapt to viewport width

### Detail panel

When a tool is selected and details are shown, the detail panel displays:

- tool name, ID, and type
- geometry and component fields
- notes
- a `Tool components` section with clickable buttons for holder, cutting component, and support parts
- a `Preview` section for 3D STL display

If a component has a valid link, clicking its button opens that link in the system browser.

## The Tool Library Concept

The application is centered around a single tool record.

Each tool record can describe the full build-up of a usable tool assembly:

`Tool -> Holder -> Cutting component -> Additional parts`

This means one record can describe:

- the main tool identity
- which holder it uses
- which insert, drill, or mill it uses as the cutting component
- any extra holder or cutting elements
- support parts that belong to the assembly

The `Assemblies`, `Holders`, and `Inserts` pages are not separate databases. They are filtered views of the same tool data.

## How Linking Works

Linking in this project is field-based rather than relational.

For each tool, the database stores text fields such as:

- `holder_code` and `holder_link`
- `cutting_code` and `cutting_link`
- `holder_add_element` and `holder_add_element_link`
- `cutting_add_element` and `cutting_add_element_link`
- `support_parts` as a stored list of part entries

In practice this means:

- a tool can point to a holder by code and optional web link
- a tool can point to a cutting component by code and optional web link
- support parts are stored inside the tool record itself
- component picker dialogs can reuse component data that already exists in other tool records

So the software behaves like a linked library, but the links are stored directly inside each tool record instead of through foreign-key tables.

## Excel Import and Export

### Export

Excel export writes the main fields from the tool editor's `General` tab into a workbook named `Tools`.

The export includes:

- ID
- tool type
- description
- geometry values
- holder information
- cutting component information
- notes
- drill or mill-specific values

The exported file is formatted for readability, with:

- colored header row
- light row coloring by tool type
- auto-sized columns
- numeric formatting
- filter row enabled

### Import

Excel import works in two stages:

1. Select an Excel file.
2. Map Excel column headers to software fields in the import dialog.

The mapping dialog includes tabs for:

- general fields
- additional parts
- 3D model data

Import mode can be either:

- overwrite the current database
- create a new database file

Important practical note:

- general field import is the main supported workflow
- additional parts are safest when supplied as JSON-style list data
- 3D model data can be imported as a single file path or as JSON describing multiple STL parts

## Database Switching and Backup Safety

The application stores data in SQLite `.db` files.

### Active database

The currently used database can be changed from the `Export / Import` page by choosing another `.db` file and applying it.

### Safety during import overwrite

When importing Excel into the current database, the software:

1. asks for confirmation
2. offers to create a timestamped backup copy of the current database
3. clears the current `tools` table
4. imports the mapped tool rows

Backup files are created next to the active database file with a timestamp in the filename.

### New database import

Instead of overwriting the current database, you can import the Excel file into a brand new database file.

## How 3D Preview Works

The application supports STL preview for individual tools and multi-part assemblies.

- The detail panel can show an inline preview.
- A detached preview window can also be opened.
- The tool editor has a `3D Models` tab for assigning one or more STL files.
- Detached preview measurement visibility is controlled from a single icon toggle in the toolbar.

If more than one STL part is stored, the preview behaves like an assembly preview.

## How to Run the Software

### Expected environment

- Windows
- Python 3.10

### Main entry point

Run:

```powershell
python main.py
```

If you are using the included virtual environment, activate it first and then run `python main.py`.

## How to Build an EXE

The most reliable way to package this app is a `PyInstaller` one-folder build.

Why one-folder instead of one-file:

- `PySide6` with `Qt WebEngine` is much more reliable in `onedir`
- this app bundles local HTML/JavaScript preview files, icons, styles, and a starter SQLite database
- startup and debugging are both easier

### Recommended build command

From the project root, run:

```powershell
.\build_exe.ps1
```

That script will:

1. create a fresh build virtual environment in `.build-venv`
2. install the packaging dependencies from `requirements-build.txt`
3. build the app with `library.spec`

### Build output

The generated executable will be at:

```text
dist\Tools and jaws Library\Tools and jaws Library.exe
```

## How to Build an Installer

This project now also includes an Inno Setup installer script:

```text
library_installer.iss
```

If Inno Setup 6 is installed, build the installer with:

```powershell
.\build_installer.ps1 -AppVersion 1.0.0
```

That command expects the packaged app folder to exist here:

```text
dist\Tools and jaws Library
```

The installer output will be written here by default:

```text
installer-dist
```

The installer is configured as a per-user install and places the app under:

```text
%LOCALAPPDATA%\Programs\Tools and jaws Library
```

That avoids requiring admin rights on many machines.

## About Code Signing

You can code-sign both the packaged app and the installer, but you need a real signing identity first.

Typical options are:

- a standard or EV code-signing certificate from a trusted certificate authority
- Microsoft Artifact Signing / Trusted Signing

After you have a certificate or signing service configured, use `signtool.exe` to sign:

1. the built `dist\Tools and jaws Library\Tools and jaws Library.exe`
2. optionally other shipped `.exe` / `.dll` files
3. the final installer `.exe`

If you want Inno Setup to sign the installer and uninstaller during compile, configure a `SignTool` command and enable the commented `SignTool=` line in `library_installer.iss`.

### First-run data location for the EXE

When running as a packaged `.exe`, the app stores writable files here:

```text
%LOCALAPPDATA%\Tools and jaws Library
```

That folder contains:

- the active SQLite database in `databases\tool_library.db`
- the settings JSON file
- the default Excel export target

The bundled database from `databases\tool_library.db` is copied there automatically on first run if no user database exists.

### Manual build steps

If you prefer to do it yourself:

```powershell
py -3.10 -m venv .build-venv
.\.build-venv\Scripts\python.exe -m pip install --upgrade pip
.\.build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.build-venv\Scripts\python.exe -m PyInstaller --noconfirm --clean library.spec
```

## Dependencies

The codebase relies mainly on:

- `PySide6`
- `PySide6 Addons / Essentials`
- `Qt WebEngine` support through PySide6
- `openpyxl`

The bundled virtual environment also includes supporting packages such as:

- `numpy`
- `et_xmlfile`
- `python-dateutil`
- `six`

## About the `.venv` Folder

The repository includes a `.venv` folder, which is the project's local Python virtual environment.

Its purpose is to keep this application's Python packages separate from the rest of the machine, so the software can use its own dependency versions without relying on a global Python setup.

For normal use:

- it can be used as the project's local runtime environment
- it is not part of the application logic itself
- if it becomes outdated or machine-specific, it can be recreated from the project's dependency list later

## Project Folder Structure

```text
assets/       icons and sample STL assets
data/         SQLite connection and schema migration logic
databases/    default database files
models/       dataclass definitions for tool-related structures
preview/      local HTML/JavaScript 3D STL viewer
services/     business logic for tools, Excel, and settings
styles/       Qt stylesheet (.qss)
ui/           main window, pages, dialogs, and widgets
main.py       application startup
config.py     paths, constants, tool types, and icon mappings
```

## Future Development Ideas

- Separate holders, inserts, and assemblies into first-class entities if stronger relational data is needed
- Add a dedicated component master library instead of reusing codes from existing tools
- Add full import/export support for support parts and structured 3D model assemblies
- Store relative STL asset paths instead of machine-specific absolute paths
- Use the settings file for persistent UI preferences, recent databases, and window state
- Add validation rules for duplicate component codes and broken links
- Add packaging for easier deployment without a manual Python setup

---

## FUTURE IMPLEMENTATIONS

### JAWS Library Catalog Rebuild

The **JAWS module** (`ui/jaw_page.py`) currently uses the legacy `QListWidget` + embedded `JawRowWidget` approach that was used in TOOLS before the March 2026 refactor. It needs the same delegate-based rebuild:

**Planned changes:**
1. Create `ui/jaw_catalog_delegate.py` with `JawCatalogDelegate` class
   - Responsive row painting: full (4-column: Jaw ID, Jaw type, Clamping diameter, Clamping length) → reduced (2-column) → icon-only
   - Fixed content inset to prevent selection shift
   - Vertically centered text blocks
   - Icon painting at fixed coordinates
   - QFontMetrics-based text measurement and elision

2. Refactor `jaw_page.py` to use `QListView + QStandardItemModel + JawCatalogDelegate`
   - Remove `JawRowWidget` class (~250 lines)
   - Remove `ResponsiveJawRowWidget` class (~180 lines)
   - Update `refresh_list()` to populate `QStandardItemModel`
   - Update selection handlers to use `QModelIndex` instead of `QListWidgetItem`
   - Keep detail panel and preview logic unchanged

**Benefits:**
- Consistent UI architecture across TOOLS and JAWS modules
- Stable responsive layout without timing bugs
- Better maintainability (all row rendering in one delegate file)
- Reusable delegate pattern for future catalog pages

**Estimated scope:** ~400 lines new code, ~430 lines deleted, no schema changes

