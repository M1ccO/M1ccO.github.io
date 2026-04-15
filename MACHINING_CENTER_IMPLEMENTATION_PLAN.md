# Machining Center Implementation Plan

## Phase Status

| Phase | Title | Status |
|-------|-------|--------|
| 1 | Machine Profile — MC definition + wizard | 🟢 COMPLETE |
| 2 | Fixture Library (DB, service, page, editor) | 🟡 IN PROGRESS |
| 2b | Fixture Selector Dialog (multi-select, IPC) | 🟢 COMPLETE |
| 3 | Work Editor — Raw Part redesign | 🟢 COMPLETE |
| 4 | Work Editor — Zero Points tab for MC | 🟡 IN PROGRESS |
| 5 | Navigation Tools ↔ Fixtures, hide JAWS for MC | 🟡 IN PROGRESS |

## Current Implementation Snapshot (2026-04-15)

Completed in code:
- Fixture selector dialog added in Tools Library and routed through selector IPC.
- Setup Manager Work Editor now opens fixture selector sessions for machining-center operations.
- Machining-center operations now persist through `mc_operation_count` and `mc_operations`.
- Raw Part redesign is implemented with Bar / Square / Custom modes.
- Machining-center Zeros tab now renders operation cards with per-operation offsets, axis inputs, sub-program, and fixture selection.

Still pending:
- End-to-end selector validation in the live UI workflow.
- Final review of MC-specific navigation behavior and any remaining polish around hiding lathe-only affordances.

## Phase 1 — COMPLETE (2026-04-15)

Implemented:
- `MachineProfile` extended with `axis_count`, `fourth_axis_letter`, `fifth_axis_letter`, `has_turning_option`.
- `MachineHeadProfile` extended with `is_machining_center_head`.
- Three new presets registered: `machining_center_3ax`, `machining_center_4ax`, `machining_center_5ax`.
- Helper `apply_machining_center_overrides()` and `is_machining_center()` added.
- `MachineSetupWizard`: enabled Machining Center radio; new `_MachiningCenterConfigPage` (axis count, axis-letter inputs, turning option); navigation skips lathe pages when MC chosen; `selected_mc_overrides()` returns overrides.
- `UiPreferencesService` persists `mc_fourth_axis_letter`, `mc_fifth_axis_letter`, `mc_has_turning_option`, with `get_machining_center_overrides()` / `set_machining_center_overrides()` helpers.
- `Setup Manager/main.py` and `machine_config_dialog.py` persist MC overrides when the wizard is used.
- `WorkEditorDialog` applies overrides when loading the profile at dialog construction.

## Overview

This document describes the full implementation plan for adding Machining Center support to the NTX Setup Manager workspace. It covers five major areas:

1. Machine Profile — Machining Center profile definition and axis configuration
2. Fixture Library — new domain parallel to Jaws Library, with Parts/Assemblies dual-side
3. Fixture Selector — multi-select selector dialog opened from Work Editor
4. Work Editor — Raw Part redesign and Zero Points redesign for Machining Center
5. Navigation — cross-library navigation between Tools and Fixtures

All changes must respect existing architecture: profile-driven UI, additive-only DB migrations, canonical `shared.*` imports, and the CatalogPageBase / EditorDialogBase / SelectorDialogBase platform layer.

---

## Phase 1 — Machine Profile: Machining Center Definition

### 1.1 New Profile Fields in `shared/machine_profiles.py`

Add new fields to `MachineProfile`:

```python
# Machining center axis config
axis_count: int = 3                  # 3, 4, or 5
fourth_axis_letter: str = "C"        # meaningful when axis_count >= 4
fifth_axis_letter: str = "B"         # meaningful when axis_count == 5
has_turning_option: bool = False     # enables lathe tool types in Tool Library
```

Add to `MachineHeadProfile` (for machining center heads):

```python
is_machining_center_head: bool = False
```

### 1.2 New Profile Entries

Define the first Machining Center profile in `PROFILE_REGISTRY`:

```python
"machining_center_3ax": MachineProfile(
    key="machining_center_3ax",
    name="Machining Center — 3 Axis",
    machine_type="machining_center",
    spindles=(),          # no spindle concept for machining center
    heads=(MachineHeadProfile(
        key="HEAD1",
        label_default="HEAD1",
        head_type="milling",
        allows_rotating_tools=True,
        allows_b_axis=False,
        ...
        is_machining_center_head=True,
    ),),
    axis_count=3,
    fourth_axis_letter="C",
    fifth_axis_letter="B",
    has_turning_option=False,
    use_op_terminology=True,   # use OP10/OP20/OP30 terminology
    supports_sub_pickup=False,
    supports_print_pots=False,
    supports_zero_xy_toggle=False,
),
```

Additional profiles to register: `machining_center_4ax`, `machining_center_5ax`. These can be registered immediately and selected later by the wizard.

### 1.3 Machine Setup Wizard Extension

File: `Setup Manager/ui/machine_setup_wizard.py` (or wherever the wizard lives)

- Enable the Machining Center radio button (currently disabled).
- When Machining Center is selected, show a second panel with:
  - **Axis count** radio group: 3-axis / 4-axis / 5-axis
  - **Fourth axis letter** QLineEdit (default `C`) — appears when 4-axis or 5-axis selected
  - **Fifth axis letter** QLineEdit (default `B`) — appears only when 5-axis selected
  - **Turning option** QCheckBox — "Enable turning tools in Tool Library"
- The wizard maps the selections to the correct profile key (or stores the axis/turning flags in `app_config` as supplementary keys if profiles remain fixed presets).

**Decision point:** Either create fixed profiles per combination (3ax/4ax/5ax × turning/not-turning = 6 variants), or store `axis_count`, `fourth_axis_letter`, `fifth_axis_letter`, and `has_turning_option` as separate `app_config` keys that are loaded alongside the base profile key at startup. The second approach is more flexible.

Recommended: store the base key `machining_center` plus supplementary config keys:
```
app_config: machine_profile_key = "machining_center"
app_config: mc_axis_count = "3"
app_config: mc_fourth_axis_letter = "C"
app_config: mc_fifth_axis_letter = "B"
app_config: mc_has_turning_option = "0"
```

Then `UiPreferencesService` reads all of these and constructs the effective `MachineProfile` at startup. This keeps the profile registry clean while allowing user-customised configurations.

### 1.4 Preferences Dialog

File: `Setup Manager/ui/preferences_dialog.py`

- The read-only machine profile display should show the effective profile with axis count, e.g., "Machining Center — 5 Axis (B+C, Turning)".
- "Configure Machine..." still opens the wizard.

---

## Phase 2 — Fixture Library

### Progress (2026-04-15)

- ✅ `fixtures` table + `fixtures_migrations.py` (Parts/Assemblies, preview fields, `assembly_part_ids`)
- ✅ `FixtureDatabase`, `FixtureService` with kind filter + assembly id list normalization
- ✅ `FIXTURES_DB_PATH` resolved via machine-config (fallback `<jaws_db>/fixtures_library.db`)
- ✅ `FixturePage`, `FixtureCatalogDelegate`, `FixtureEditorDialog`, fixture_page_support/* cloned from jaws
- ✅ `Tools and jaws Library/main.py` constructs `fixture_service` and passes it to `MainWindow`
- ✅ `MainWindow.__init__` accepts `fixture_service`; `FixturePage` added to `self.stack`
- ✅ Fixture nav items + module switch handler (`_apply_module_mode('fixtures')`)
- ✅ `_switch_fixtures_database()` for machine-config DB swap
- ✅ Standalone `FixtureSelectorDialog` added and routed from `MainWindow._open_selector_dialog_for_session()`
- 🔲 Parts/Assemblies two-sided switcher on `FixturePage` (analogous to HEAD1/HEAD2)
- 🔲 Final MC-only navigation cleanup and validation pass

The Fixture Library is a new domain that mirrors Jaws Library architecture. It lives in `Tools and jaws Library/` alongside TOOLS and JAWS. It is **not** a rename of Jaws — both can coexist. The library is only active when the active machine profile is `machine_type == "machining_center"`.

### 2.1 Database Domain

New SQLite table in the Library DB (additive migration in `Tools and jaws Library/data/migrations/`):

**`fixtures` table:**
```sql
CREATE TABLE fixtures (
    fixture_id TEXT PRIMARY KEY,
    fixture_kind TEXT NOT NULL,   -- 'part' | 'assembly'
    name TEXT,
    fixture_type TEXT,            -- user-defined type label
    notes TEXT,
    stl_paths TEXT DEFAULT '[]',  -- JSON array of {name, file, color, offsets}
    last_modified TEXT,
    -- assembly-only fields:
    part_ids TEXT DEFAULT '[]'    -- JSON array of fixture_id refs (for assemblies)
);
```

New migration module: `Tools and jaws Library/data/migrations/fixture_migrations.py`

### 2.2 Fixture Service

New file: `Tools and jaws Library/services/fixture_service.py`

Same contract as `jaw_service.py`:
- `get_all_fixtures(kind=None)` → list of dicts, optionally filtered by `fixture_kind`
- `get_fixture(fixture_id)` → dict
- `add_fixture(data)` → new id
- `update_fixture(fixture_id, data)` → bool
- `delete_fixture(fixture_id)` → bool
- `get_parts_for_assembly(assembly_id)` → list of part dicts

### 2.3 Fixture Library Page

New file: `Tools and jaws Library/ui/fixture_page.py` (inherits `CatalogPageBase`)

Support folder: `Tools and jaws Library/ui/fixture_page_support/`

Start by copying `jaw_page_support/` as the base and adjusting labels. The key structural difference: the page has **two sides** — Parts and Assemblies — switchable via a toggle button at the top (same pattern as HEAD1/HEAD2 switch in Tools tab).

```
fixture_page_support/
  page_builders.py          ← layout with Parts/Assemblies toggle at top
  topbar_builder.py         ← search + filter (fixture_type filter instead of jaw_type)
  catalog_list_widgets.py   ← FixtureCatalogListView
  detail_panel_builder.py   ← fixture detail panel (different fields per Parts/Assemblies)
  detail_layout_rules.py
  detail_visibility.py
  crud_actions.py           ← add / edit / delete fixture
  selection_helpers.py
  selection_signal_handlers.py
  bottom_bars_builder.py
  event_filter.py
  detached_preview.py
  retranslate_page.py
  preview_rules.py
```

**Parts side:**
- Shows fixtures where `fixture_kind == 'part'`
- Fields: fixture_id, name, fixture_type, notes, stl_paths, last_modified
- Same card layout as jaws

**Assemblies side:**
- Shows fixtures where `fixture_kind == 'assembly'`
- Fields: fixture_id, name, fixture_type, notes, part_ids (list of linked parts), stl_paths, last_modified
- Card shows linked part count
- Assembly editor allows: picking parts from the Parts catalog (like component picker in tool editor), and optionally uploading assembly-level STL models (or inheriting from parts)

### 2.4 Fixture Catalog Delegate

New file: `Tools and jaws Library/ui/fixture_catalog_delegate.py` (inherits `CatalogDelegate`)

Renders fixture cards. For assemblies, shows a small "N parts" badge.

### 2.5 Fixture Editor Dialog

New file: `Tools and jaws Library/ui/fixture_editor_dialog.py` (inherits `EditorDialogBase`)

Support folder: `Tools and jaws Library/ui/fixture_editor_support/`

**General tab fields (Parts):**
- `fixture_id` (QLineEdit)
- `fixture_kind` (read-only label: "Part")
- `name` (QLineEdit)
- `fixture_type` (QLineEdit) — user-defined label
- `notes` (QTextEdit)
- `last_modified` (QLineEdit)

**General tab fields (Assemblies):**
- `fixture_id`, `name`, `fixture_type`, `notes`, `last_modified` — same as parts
- **Parts section**: a list of linked part IDs with add/remove controls. Clicking "Add Part" opens a mini part-picker dialog (similar to `component_picker_dialog.py`)
- Assembly STL option: "Use individual part models" checkbox. When unchecked, shows standard 3D models tab for uploading assembly-level STLs.

**Models tab:** Same as jaw editor — STL paths, colors, transforms, preview.

### 2.6 Main Window Integration

File: `Tools and jaws Library/ui/main_window.py`

- Add `fixture_page` as a third page alongside `home_page` and `jaw_page`.
- Fixture page is shown/hidden based on `machine_profile.machine_type == "machining_center"`.
- Navigation: When on TOOLS page and machine type is machining center, show a "FIXTURES →" nav button (mirroring the existing TOOLS ↔ JAWS navigation). When on FIXTURES page, show "← TOOLS" and vice versa.
- The existing JAWS page remains available for lathe machines; FIXTURES page is available for machining center machines.

### 2.7 Fixture Selector Dialog

New file: `Tools and jaws Library/ui/selectors/fixture_selector_dialog.py`

Opened by Setup Manager via IPC when the Work Editor Zeros tab triggers SELECT FIXTURES.

Key differences from `JawSelectorDialog`:
- **Multi-select**: user can select multiple fixtures (parts and/or assemblies) per operation.
- No spindle-slot concept. Instead: a simple selected-list panel on the right.
- Filter options: "Show Parts", "Show Assemblies", "Show All" (radio or toggle buttons).
- Submit payload: list of selected `fixture_id` values.

Payload format returned to Setup Manager:
```json
{
  "mode": "fixtures",
  "operation_key": "OP10",
  "fixture_ids": ["FIX001", "FIX002", "ASM003"]
}
```

### Progress (2026-04-15)

- ✅ `Tools and jaws Library/ui/selectors/fixture_selector_dialog.py`
- ✅ Tools Library selector session parsing now accepts `selector_mode = fixtures`
- ✅ `MainWindow` routes fixture selector sessions and returns selection payloads
- ✅ Setup Manager bridge accepts `kind = fixtures` and dispatches callback payloads to Work Editor
- 🔲 Manual end-to-end validation of open → select → return flow

---

## Phase 3 — Work Editor: Raw Part Redesign

### Progress (2026-04-15)

- ✅ General tab now supports `Bar`, `Square`, and `Custom` raw-part modes
- ✅ Added raw-part fields and stacked mode-specific editors in `tab_builders.py`
- ✅ Payload adapter load/save updated for `raw_part_kind`, square dimensions, and custom fields
- ✅ Additive DB fields added for the redesigned raw-part data

### 3.1 Changes in `tab_builders.py` — General Tab

Current: Three QLineEdit fields for OD, ID, Length (bar stock assumed).

New: Dropdown (QComboBox) for raw part type, followed by dynamic fields.

**Raw part types:**
- `Bar` — OD, ID, Length inputs (same as current)
- `Square` — Width, Height, Length inputs
- `Custom` — Name/Type (QLineEdit, user-defined), then measurement fields: user can add arbitrary named measurements via a small editable table

When dropdown value changes, the measurement area below it is swapped out (hide/show widget groups or use a QStackedWidget).

**Custom type:**
- No default values — all fields blank, user fills them in
- At minimum: Name/Type field + at least one measurement row
- Row format: Label | Value | Unit (QLineEdit × 3 per row) with Add Row / Remove Row buttons

### 3.2 Storage Impact

New fields in `works` payload (additive):
```
raw_part_type: str        -- "bar" | "square" | "custom" (default "bar" for existing works)
raw_part_name: str        -- used when type == "custom"
raw_part_measurements: str -- JSON array of {label, value, unit} for custom type
```

Existing `raw_part_od`, `raw_part_id`, `raw_part_length` remain for bar type backward compat. For square: reuse `raw_part_od` = width, `raw_part_id` = height, `raw_part_length` = length (or add explicit fields — explicit is cleaner).

Recommended: add `raw_part_width`, `raw_part_height` as new columns; keep `raw_part_od`, `raw_part_id`, `raw_part_length` for bar. Existing works default to `raw_part_type = "bar"` via migration.

---

## Phase 4 — Work Editor: Zero Points Tab Redesign (Machining Center)

### Progress (2026-04-15)

- ✅ Machining-center profiles now branch to a dedicated operation-based Zeros tab
- ✅ Operation cards render work offset, per-axis inputs, sub-program, and fixture summary
- ✅ `SELECT FIXTURES` now opens the standalone Fixture selector for the targeted operation
- ✅ `mc_operation_count` and `mc_operations` are persisted through the payload adapter and work service
- ✅ Additive DB columns added to the `works` table for machining-center operations
- 🔲 Live UI selector round-trip validation still pending

This is the largest Work Editor change. The Zero Points tab for machining center profiles is substantially different from lathe profiles.

### 4.1 Operation Count Control

At the top of the Zeros tab, for machining center profiles only:

```
Operations: [QSpinBox, min=1, max=20, default=1]
```

When the value changes, the zero-point groups below are rebuilt to match the count. Each operation gets its own group/card.

State: `dialog._mc_operation_count: int` (persisted in work payload as `mc_operation_count`).

### 4.2 Per-Operation Group Layout

Each operation (e.g., OP10, OP20, OP30…) renders as a titled group box containing:

**Programs subsection:**
- Main program input (first operation only, or always visible — TBD based on workflow)
- Sub-program input per operation

**Coordinate inputs:**
- G-code coordinate system selector (QComboBox: G54, G55, G56, G57, G58, G59, G59.1…)
- Axis inputs: X, Y, Z (always), plus C-axis input if `axis_count >= 4`, plus B-axis input if `axis_count == 5`
- Axis letters shown are pulled from `machine_profile.fourth_axis_letter` and `machine_profile.fifth_axis_letter`

**Fixture section:**
- Label: "Fixtures for this operation:"
- A compact list of selected fixtures (fixture ID + name, one per line)
- Button: `SELECT FIXTURES` → opens Fixture Selector dialog via IPC

### 4.3 Programs Section (Machining Center)

For machining center profiles, the NC Programs group at the top of the Zeros tab becomes:
- Main program input (single, global for the work)
- Sub-program inputs: one per operation, labeled "OP10 sub-program", "OP20 sub-program", etc.

This mirrors the current head-based sub-program structure but keyed by operation index instead of head key.

### 4.4 Storage Schema Changes (Additive)

New columns in `works` table:
```sql
mc_operation_count INTEGER DEFAULT 1,
mc_operations TEXT DEFAULT '[]'
-- JSON array of operation objects:
-- [{
--   "op_key": "OP10",
--   "coord": "G54",
--   "x": "", "y": "", "z": "",
--   "fourth_axis": "",   -- C by default
--   "fifth_axis": "",    -- B by default
--   "sub_program": "",
--   "fixture_ids": []
-- }, ...]
```

This is a clean break from the lathe-specific `head1_main_z` / `head2_sub_z` field names. The `WorkEditorPayloadAdapter` will handle the lathe vs machining center branching at load/save time.

### 4.5 SELECT FIXTURES Button Flow

1. User clicks `SELECT FIXTURES` on a specific operation group.
2. Setup Manager sends an IPC request to Tools/Fixtures Library: `mode=fixtures, operation_key=OP10, current_fixture_ids=[...]`.
3. Tools Library opens `FixtureSelectorDialog` pre-loaded with current selections.
4. User selects fixtures, clicks DONE.
5. Tools Library sends result payload back via IPC.
6. Setup Manager updates `dialog._mc_operations[op_index]["fixture_ids"]`.
7. The operation group's fixture list refreshes to show selected fixtures.

IPC message format extension (new mode alongside existing `tools` / `jaws`):
```json
{ "mode": "fixtures", "operation_key": "OP10", "fixture_ids": [] }
```

---

## Phase 5 — Navigation Between Tools and Fixtures

### Progress (2026-04-15)

- ✅ Tools Library now resolves and loads a dedicated fixtures DB
- ✅ Tool Library main window can switch between `tools`, `jaws`, and `fixtures` modes
- ✅ For machining-center profiles, module toggling now routes Tools ↔ Fixtures
- 🔲 Final pass still needed to confirm all lathe-only navigation affordances stay hidden for MC in every entry path

### 5.1 Tools Library → Fixtures Library Button

File: `Tools and jaws Library/ui/main_window.py`

When the active machine profile is `machine_type == "machining_center"`:
- The navigation bar shows a "FIXTURES" tab/button alongside "TOOLS"
- Clicking it switches to the Fixture Library page
- The existing JAWS tab is hidden (machining center machines don't use jaws)

When profile is lathe:
- TOOLS and JAWS tabs visible, FIXTURES tab hidden

This toggle is handled at startup and on `machine_profile_key` change (via the mirrored shared prefs).

### 5.2 Filtered View from Setup Manager

When Setup Manager opens the library in filtered mode (i.e., from the Work Editor tools button), the same filter-session IPC protocol applies. For machining center works, Setup Manager should open the library in `fixtures` mode instead of `jaws` mode.

The selector session payload from Setup Manager specifies `mode`. The library's `MainWindow._open_selector_dialog_for_session()` branches on `mode == "fixtures"` to open `FixtureSelectorDialog`.

---

## Implementation Order

The phases should be implemented in this order to avoid blocked dependencies:

| Step | Work | Depends on |
|---|---|---|
| 1 | Add axis config fields to `MachineProfile` dataclass | — |
| 2 | Add machining center profiles to `PROFILE_REGISTRY` | Step 1 |
| 3 | Enable machining center option in Machine Setup Wizard | Step 2 |
| 4 | `fixtures` DB table migration | — |
| 5 | `FixtureService` | Step 4 |
| 6 | `FixturePage` + support folder (Parts side only first) | Step 5 |
| 7 | `FixtureEditorDialog` (Parts only first) | Step 5 |
| 8 | Main window navigation for Fixtures page | Step 6 |
| 9 | Fixture Catalog Delegate | Step 6 |
| 10 | Assemblies side of FixturePage + editor | Steps 6, 7 |
| 11 | `FixtureSelectorDialog` (multi-select) | Steps 5, 8 |
| 12 | Work Editor — Raw Part dropdown redesign | — |
| 13 | Work Editor — Zero Points tab operation-count redesign | Steps 2, 11 |
| 14 | Work Editor payload adapter — machining center branching | Step 13 |
| 15 | DB migration for work table new columns | Step 14 |

---

## Architecture Decisions and Constraints

### What Must Not Change
- Lathe profiles and their existing Work Editor behavior are not touched. Machining center adds new code paths; it does not modify lathe paths.
- `jaws` table and jaw service remain independent of fixtures.
- All imports follow canonical `shared.*` paths.
- Migrations are strictly additive — no column drops, no data transformations.

### What Must Be Shared
- `FixturePage` inherits `CatalogPageBase` (same as `HomePage` and `JawPage`).
- `FixtureEditorDialog` inherits `EditorDialogBase`.
- `FixtureSelectorDialog` inherits `SelectorDialogBase`.
- The selector IPC protocol is extended, not replaced.

### Open Design Questions (Decide Before Implementing)
1. **Machining center profile keys**: Fixed presets per axis count vs. one base key + supplementary `app_config` entries. Recommendation: supplementary config keys for flexibility.
2. **Raw part custom measurements**: Simple name-value-unit table vs. a free-form notes field. Recommendation: table, since it feeds eventual PDF output.
3. **Fixture selector multi-select UX**: Checkbox list vs. drag-to-panel. Recommendation: checkbox list in the catalog (simpler, avoids drag-drop complexity).
4. **Assembly STL strategy**: Inherit from parts vs. separate upload vs. both. Recommendation: both options available, controlled per assembly.
5. **Operation key format**: Numeric index (`0, 1, 2`) vs. string (`OP10, OP20, OP30`). Recommendation: string with auto-increment in steps of 10, user-editable label.

---

## Files Created or Modified

### `shared/`
- `shared/machine_profiles.py` — add `axis_count`, `fourth_axis_letter`, `fifth_axis_letter`, `has_turning_option` fields + machining center profiles

### `Tools and jaws Library/`
- `data/migrations/fixture_migrations.py` — new: `fixtures` table migration
- `services/fixture_service.py` — new: full fixture CRUD
- `ui/fixture_page.py` — new: orchestrator inheriting CatalogPageBase
- `ui/fixture_page_support/` — new: 14+ support modules (cloned from jaw_page_support, adjusted)
- `ui/fixture_catalog_delegate.py` — new: card renderer
- `ui/fixture_editor_dialog.py` — new: editor dialog
- `ui/fixture_editor_support/` — new: general_tab.py, models_tab.py, assembly_parts_tab.py
- `ui/selectors/fixture_selector_dialog.py` — new: multi-select selector dialog
- `ui/selectors/fixture_selector_layout.py` — new
- `ui/selectors/fixture_selector_state.py` — new
- `ui/selectors/fixture_selector_payload.py` — new
- `ui/main_window.py` — modified: add fixture page, fixture mode IPC branch, navigation toggle

### `Setup Manager/`
- `ui/machine_setup_wizard.py` — modified: enable machining center option, axis config panel
- `ui/preferences_dialog.py` — modified: display effective machining center config
- `ui/work_editor_support/tab_builders.py` — modified: raw part dropdown, MC zero tab
- `ui/work_editor_support/model.py` — modified: MC payload fields, operation array
- `ui/work_editor_support/tools_tab_builder.py` — minor: turning option awareness for tool type filter
- `data/migrations/` — modified: add `mc_operation_count`, `mc_operations`, `raw_part_type`, `raw_part_name`, `raw_part_measurements`, `raw_part_width`, `raw_part_height` columns to `works` table

---

## Validation Checklist (Per Step)

After each step, run from repo root:
```
python scripts/run_quality_gate.py
```

Domain-specific checks after Fixture Library steps:
1. Fixture page loads and shows Parts/Assemblies toggle
2. Adding a Part round-trips through editor and appears in catalog
3. Creating an Assembly with linked Parts saves and reloads correctly
4. Fixture Selector opens from Work Editor, multi-select works, payload returns correctly
5. Tools ↔ Fixtures navigation works when machine type is machining center
6. JAWS tab is hidden when machine type is machining center
7. Lathe profile works are unaffected (regression test)
8. Machining center work saves and reloads all operation data correctly

Validation completed so far:
- ✅ Targeted module import check passed (`imports_ok`)
- ✅ Repository smoke test passed (`smoke-test: OK`)
- 🔲 Manual selector validation still pending
