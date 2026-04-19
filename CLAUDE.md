# NTX Setup Manager — Agent Blueprint

**Last verified: 2026-04-19. Branch: codex/before-shared-styles.**

Read this file completely before touching any code. It supersedes all other .md files where they conflict.

---

## 1. Workspace Layout

```
NTX Setup Manager/          ← workspace root
  Setup Manager/            ← setup workflow app
  Tools and jaws Library/   ← tool/jaw master-data app
  shared/                   ← canonical cross-app code
  tests/                    ← all tests (both apps)
  scripts/                  ← quality gate scripts
  docs/                     ← system docs
  architecture-map.json     ← machine-readable ownership/dependency map
```

Two separate PySide6 apps run side-by-side and talk via `QLocalSocket` IPC. They share no runtime process — only `shared/` code.

---

## 2. Entry Points

| App | Entry | IPC server name |
|---|---|---|
| Tools and jaws Library | `Tools and jaws Library/main.py` | Library's named socket server |
| Setup Manager | `Setup Manager/main.py` | Setup Manager's callback socket |

Launch both: `run.bat` from workspace root.  
Launch Library standalone: `.venv\Scripts\python.exe "Tools and jaws Library\main.py"`  
Launch Setup Manager standalone: `.venv\Scripts\python.exe "Setup Manager\main.py"`

Python: 3.12 or 3.13. Venv at workspace root.

---

## 3. User Language → Technical Translation

**ALWAYS look up the file before editing. Do not guess.**

| User says | Technical meaning | Primary file(s) |
|---|---|---|
| "Tool Library" / "Tool Catalog" | `HomePage` — tool catalog page | `Tools and jaws Library/ui/home_page.py` |
| "Jaw Library" / "Jaw Catalog" | `JawPage` — jaw catalog page | `Tools and jaws Library/ui/jaw_page.py` |
| "Tool Selector" | `ToolSelectorDialog` — opens from Setup Manager | `Tools and jaws Library/ui/selectors/tool_selector_dialog.py` |
| "Jaw Selector" | `JawSelectorDialog` — opens from Setup Manager | `Tools and jaws Library/ui/selectors/jaw_selector_dialog.py` |
| "Add/Edit Tool dialog" | `ToolEditorDialog` | `Tools and jaws Library/ui/tool_editor_dialog.py` + `ui/tool_editor_support/` |
| "Add/Edit Jaw dialog" | `JawEditorDialog` | `Tools and jaws Library/ui/jaw_editor_dialog.py` + `ui/jaw_editor_support/` |
| "Detail panel" / "Tool details" | Right-side detail panel | `Tools and jaws Library/ui/home_page_support/detail_panel_builder.py` |
| "Jaw detail panel" | Right-side jaw detail panel | `Tools and jaws Library/ui/jaw_page_support/detail_panel_builder.py` |
| "Filter bar" / "Search bar" | Top toolbar + filter dropdowns | `Tools and jaws Library/ui/home_page_support/topbar_builder.py` (tools) · `ui/jaw_page_support/topbar_builder.py` (jaws) |
| "Bottom bar" / "action buttons" (ADD/EDIT/DELETE) | `build_bottom_bars` | `Tools and jaws Library/ui/home_page_support/page_builders.py` · `ui/jaw_page_support/page_builders.py` |
| "CANCEL / DONE buttons" (selector) | Selector bottom bar | `Tools and jaws Library/ui/selectors/common.py` → `build_selector_bottom_bar` |
| "Selector panel" / "assignment panel" / "drag-drop zone" | Selector card inside selector dialogs | `Tools and jaws Library/ui/selectors/tool_selector_dialog.py` → `_build_selector_card()` |
| "SP1 / SP2 slots" (jaws) | `JawAssignmentSlot` widgets | `Tools and jaws Library/ui/jaw_page_support/selector_widgets.py` |
| "Mini tool cards" / "assignment rows" | `MiniAssignmentCard` | `shared/ui/cards/mini_assignment_card.py` |
| "Tool list / catalog list" | `ToolCatalogListView` — drag-enabled QListView | `Tools and jaws Library/ui/home_page_support/catalog_list_widgets.py` |
| "Jaw list / catalog list" | `JawCatalogListView` — drag-enabled QListView | `Tools and jaws Library/ui/jaw_page_support/catalog_list_widgets.py` |
| "Tool card" / "catalog card" | `ToolCatalogDelegate` — item renderer | `Tools and jaws Library/ui/tool_catalog_delegate.py` |
| "Jaw card" / "catalog card" (jaws) | `JawCatalogDelegate` | `Tools and jaws Library/ui/jaw_catalog_delegate.py` |
| "Setup Manager" | Setup workflow app | `Setup Manager/` |
| "Work Editor" | Work editor dialog — family-selected | `Setup Manager/ui/work_editor_factory.py` · `Setup Manager/ui/work_editor_dialog.py` + `ui/work_editor_support/` |
| "Setup page" / "Works list" | `SetupPage` — main list of setups | `Setup Manager/ui/setup_page.py` + `ui/setup_page_support/` |
| "Logbook" | `LogbookPage` | `Setup Manager/ui/logbook_page.py` |
| "Drawings" | `DrawingPage` | `Setup Manager/ui/drawing_page.py` + `ui/drawing_page_support/` |
| "IPC" / "selector callback" | `QLocalSocket` IPC between apps | `Tools and jaws Library/ui/main_window.py` → `_send_selector_result_payload` |
| "Main window" (Library app) | `MainWindow` — app shell, selector lifecycle, IPC | `Tools and jaws Library/ui/main_window.py` |
| "STL preview" / "3D preview" | STL viewer widget + detached window | `shared/ui/stl_preview.py` · page `detached_preview.py` modules |

---

## 4. Architecture — Two Apps + Shared

### Tools and jaws Library

Owns all tool and jaw master data. Source of truth for metadata.

```
Tools and jaws Library/
  main.py                          ← bootstrap, IPC server, service graph
  config.py                        ← paths, DB locations, icon mappings
  services/
    tool_service.py                ← ToolService CRUD
    jaw_service.py                 ← JawService CRUD
    export_service.py              ← Excel I/O
  data/
    migrations/
      tools_migrations.py          ← tool schema migrations (additive-only)
      jaws_migrations.py           ← jaw schema migrations (additive-only)
  ui/
    main_window.py                 ← shell, nav, selector session, IPC
    home_page.py                   ← thin orchestrator (~567L), CatalogPageBase
    jaw_page.py                    ← thin orchestrator (~565L), CatalogPageBase
    home_page_support/             ← 17 active modules (tools domain)
    jaw_page_support/              ← 18 active modules (jaws domain)
    tool_editor_dialog.py          ← EditorDialogBase subclass
    tool_editor_support/           ← component pickers, rules, payload codec
    jaw_editor_dialog.py
    jaw_editor_support/
    tool_catalog_delegate.py       ← CatalogDelegate (card renderer)
    jaw_catalog_delegate.py
    selectors/
      tool_selector_dialog.py      ← standalone tool selector dialog
      tool_selector_layout.py
      tool_selector_state.py
      tool_selector_payload.py
      jaw_selector_dialog.py       ← standalone jaw selector dialog
      jaw_selector_layout.py
      jaw_selector_state.py
      jaw_selector_payload.py
      common.py                    ← SelectorDialogBase, build_selector_bottom_bar
    measurement_editor_dialog.py   ← ~1381L orchestrator
    measurement_editor/
      coordinators/                ← list_manager, pick_coordinator, distance/diameter editors, preview
      models/                      ← measurement dataclasses + registry
      forms/                       ← form builder helpers
      utils/                       ← coordinate math
    selector_mime.py               ← MIME constants + encode/decode
    selector_state_helpers.py      ← bucket normalization, target key helpers
    selector_ui_helpers.py         ← spindle label helpers
```

**Selector IPC entry point**: `MainWindow._open_selector_dialog_for_session()` at L~1100 in `Tools and jaws Library/ui/main_window.py`.

Key IPC methods on `MainWindow`:
- `_open_selector_dialog_for_session()` L~1100
- `_on_selector_dialog_submit()` L~1145
- `_on_selector_dialog_cancel()` L~1137
- `_send_selector_result_payload()` L~1159
- `_clear_selector_session()` L~1060
- `_back_to_setup_manager()` L~973

### Setup Manager

Owns setup/workflow data. Does NOT own tool/jaw metadata — reads it through resolvers.

```
Setup Manager/
  main.py                          ← bootstrap, live machine-config switch, IPC
  config.py                        ← paths, DB locations
  services/
    work_service.py
    logbook_service.py
    draw_service.py
    print_service.py               ← PDF rendering, resolver-primary for tool/jaw data
    setup_card_policy.py           ← machine-profile-aware content policy (presentation only)
    preload_manager.py             ← PreloadManager singleton — services + preview engine warmup
    selector_session.py            ← SelectorSessionCoordinator — session state machine
  models/
  data/
  ui/
    main_window.py
    setup_page.py + setup_page_support/
    work_editor_factory.py         ← USE THIS to open Work Editor (not dialog directly)
    machine_family_runtime.py      ← machine-family resolver for routing/editor selection
    work_editor_dialog.py          ← shared base dialog (do not use as entry for new code)
    work_editor_support/
      embedded_selector_host.py    ← thin mount/detach (WorkEditorSelectorHost)
      selector_parity_factory.py   ← widget builder, preload-aware DB reuse
      selector_adapter.py          ← pure utility: apply selector results
      selector_provider.py         ← pure utility: resolve selector defaults/targets
      selector_state.py            ← pure utility: selector state helpers
      selectors.py
      ordered_tool_list.py         ← WorkEditorOrderedToolList
      tools_tab_builder.py
      zero_points.py
      jaw_selector_panel.py
      tool_picker_dialog.py
      model.py                     ← WorkEditorPayloadAdapter (schema bridging only)
      machining_center.py
      tab_builders.py
      dragdrop_widgets.py
      ...
    logbook_page.py
    drawing_page.py + drawing_page_support/
    preferences_dialog.py          ← Machines tab owns live-switch UI
    machine_config_dialog.py       ← MachineConfigDialog (Edit + New modes)
    main_window_support/
      preload_controller.py
      preferences_actions.py       ← reads pending_switch_config_id after exec()
      ...
```

**Work Editor caller rule**: Use `Setup Manager/ui/work_editor_factory.py` and `machine_family_runtime.py` as entry points — NOT `work_editor_dialog.py` directly.

### Shared (`shared/`)

```
shared/
  models/
    tool.py                        ← Tool dataclass
    jaw.py                         ← Jaw dataclass
  services/
    localization_service.py        ← i18n
    ui_preferences_service.py      ← app preferences (includes show_shared_db_notice)
    machine_config_service.py      ← MachineConfigService — multi-machine CRUD
  data/
    model_paths.py                 ← normalize_model_path_for_storage
    base_database.py
    backup_helpers.py
  selector/
    payloads.py                    ← ToolSelectionPayload, JawSelectionPayload, SelectionBatch
  ui/
    stl_preview.py                 ← STL 3D preview widget
    theme.py
    preferences_dialog_base.py
    bootstrap_visual.py
    preview_bridge_adapter.py
    platforms/
      catalog_page_base.py         ← CatalogPageBase — inherit for new catalog pages
      editor_dialog_base.py        ← EditorDialogBase — inherit for new editors
      catalog_delegate.py          ← CatalogDelegate — inherit for card renderers
      selector_state.py            ← SelectorState — filter FSM
      export_specification.py      ← ExportSpecification — Excel I/O
    helpers/
      editor_helpers.py            ← style_panel_action_button, create_titled_section, etc.
      page_scaffold_common.py      ← build_page_root, build_catalog_splitter
      dragdrop_helpers.py          ← build_text_drag_ghost, clear_selection_on_blank_click
      common_widgets.py
      editor_table.py
      topbar_common.py
      selection_common.py
      icon_loader.py
      window_geometry_memory.py
      detached_preview_common.py
    cards/
      mini_assignment_card.py      ← MiniAssignmentCard (used in selector assignment lists)
    resolvers/
      contracts.py                 ← ResolvedTool, ResolvedJaw frozen dataclasses; Protocols
      library_backed.py            ← LibraryBackedToolResolver, LibraryBackedJawResolver
      registry.py                  ← get_resolver("tool"/"jaw"), set_resolver
    selectors/
      base_selector_widget.py
      tool_selector_widget.py
      jaw_selector_widget.py
      fixture_selector_widget.py
```

---

## 5. Canonical Import Paths

**ALWAYS use these. No legacy paths.**

```python
# Services
from shared.services.localization_service import ...
from shared.services.ui_preferences_service import ...
from shared.services.machine_config_service import MachineConfigService, MachineConfig

# Models
from shared.models.tool import Tool
from shared.models.jaw import Jaw

# Data
from shared.data.model_paths import normalize_model_path_for_storage

# Selector payloads
from shared.selector.payloads import ToolSelectionPayload, JawSelectionPayload, SelectionBatch, ToolBucket, SpindleKey

# Resolvers
from shared.ui.resolvers import get_resolver, set_resolver
from shared.ui.resolvers.contracts import ResolvedTool, ResolvedJaw

# Platform layer (use for new domain work)
from shared.ui.platforms.catalog_page_base import CatalogPageBase
from shared.ui.platforms.editor_dialog_base import EditorDialogBase
from shared.ui.platforms.catalog_delegate import CatalogDelegate
from shared.ui.platforms.selector_state import SelectorState
from shared.ui.platforms.export_specification import ExportSpecification

# UI helpers
from shared.ui.helpers.editor_helpers import style_panel_action_button, create_titled_section
from shared.ui.helpers.page_scaffold_common import build_page_root, build_catalog_splitter
from shared.ui.helpers.dragdrop_helpers import build_text_drag_ghost
from shared.ui.helpers.common_widgets import ...
from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
from shared.ui.stl_preview import StlPreviewWidget
```

**Forbidden legacy paths (never use):**
```python
from shared.editor_helpers import ...        # → shared.ui.helpers.editor_helpers
from shared.model_paths import ...           # → shared.data.model_paths
from shared.editor_table import ...          # → shared.ui.helpers.editor_table
from shared.mini_assignment_card import ...  # → shared.ui.cards.mini_assignment_card
```

---

## 6. Import Boundary Rules (Hard Rules)

- **No cross-app imports**: Setup Manager must not import from `Tools and jaws Library/` and vice versa.
- **No TOOLS↔JAWS coupling**: `ui/home_page_support/` must not import `ui/jaw_page_support/` and vice versa.
- **No cross-domain service coupling**: `tool_service.py` must not import `jaw_service.py` and vice versa.
- **No importing tool_editor_support from jaw_editor_dialog** unless logic is proven reusable.
- **Use `shared.*`** for any code used by both apps.
- **Migrations are additive-only** — never remove or rename existing columns.

**Validation**: `python scripts/import_path_checker.py` and `python scripts/module_boundary_checker.py`

---

## 7. Data Flow — Selector Workflow

### IPC Flow (Setup Manager → Library → back)

```
Setup Manager sends open_selector JSON → Library QLocalSocket server
  MainWindow._open_selector_dialog_for_session()
    opens ToolSelectorDialog or JawSelectorDialog
  User selects → DONE
    dialog on_submit → _on_selector_dialog_submit()
      _send_selector_result_payload()
        Library connects to Setup Manager callback socket
          sends result JSON payload
```

### Resolver Data Flow (canonical direction)

```
Libraries (authoritative metadata)
  → Selector fetch
    → normalized SelectionBatch payload
      → Work Editor assignment state
        → Setup Card rendering
```

**Rule**: All display labels must flow through the resolver. No component reads library DB directly for display.

### Resolver API

```python
resolver = get_resolver("tool")  # or "jaw"
resolved = resolver.resolve_tool(tool_id, bucket=ToolBucket.MAIN)
# Returns ResolvedTool | None  (never crashes on unknown IDs)
```

`ResolvedTool` fields: `tool_id`, `display_name`, `icon_key`, `pot_number`, `metadata`, `library_rev`  
`ResolvedJaw` fields: `jaw_id`, `display_name`, `icon_key`, `spindle`, `metadata`, `library_rev`

Resolver is **singleton per process** via `get_resolver()`. LRU cache 2048 entries. Cache keyed by `(id, bucket/spindle, library_rev)`. Never mutates library data.

---

## 8. Selector Session State Machine

`Setup Manager/services/selector_session.py` — `SelectorSessionCoordinator`

```
IDLE → OPENING → ACTIVE → CLOSING → IDLE
           ↓
       CANCELLED → IDLE
```

**Only permitted transitions:**
- `IDLE → OPENING` (request_open)
- `OPENING → ACTIVE` (mark_mount_complete)
- `OPENING → CANCELLED` (cancel during open)
- `ACTIVE → CLOSING` (confirm or cancel)
- `CLOSING → IDLE` (mark_teardown_complete)
- `CANCELLED → IDLE` (teardown complete)

**Forbidden**: `IDLE→ACTIVE`, `ACTIVE→IDLE`, `CLOSING→ACTIVE`, any re-entry except full teardown to IDLE.

**Single-session invariant**: Second `request_open` while state != IDLE raises `SelectorSessionBusyError`.

Trace log: `Setup Manager/temp/selector_session_trace.log`

---

## 9. Payload Schema

`shared/selector/payloads.py`

```python
class ToolBucket(str, Enum):
    MAIN = "main"; SUB = "sub"; UPPER = "upper"; LOWER = "lower"

class SpindleKey(str, Enum):
    MAIN = "main"; SUB = "sub"

@dataclass(frozen=True)
class ToolSelectionPayload:
    bucket: ToolBucket
    head_key: str
    tool_id: str
    source_library_rev: int
    selected_at: datetime

@dataclass(frozen=True)
class JawSelectionPayload:
    spindle: SpindleKey
    jaw_id: str
    source_library_rev: int
    selected_at: datetime

@dataclass(frozen=True)
class SelectionBatch:
    tools: tuple[ToolSelectionPayload, ...]
    jaws: tuple[JawSelectionPayload, ...]
    session_id: UUID
    # .is_empty property
```

**Rules**: Payloads contain IDs only — no display names, no icons, no Qt types. Must be picklable.

---

## 10. Machine Configuration System

`shared/services/machine_config_service.py` — `MachineConfigService`

Each machine config bundles: name, `machine_profile_key`, setup DB path, optional tools/jaws DB paths, `last_used_at`.

Storage: `.runtime/machine_configurations.json`

```python
@dataclass
class MachineConfig:
    id: str                  # "config_ntx2500_a3b4c5" — stable
    name: str                # user-editable
    machine_profile_key: str # e.g. "ntx_2sp_2h" — drives UI tab set
    setup_db_path: str
    tools_db_path: str       # "" = app default
    jaws_db_path: str        # "" = app default
    last_used_at: str        # ISO-8601 UTC
```

Live switch flow: `PreferencesDialog` → `preferences_actions.py` reads `_pending_switch_config_id` → `MainWindow.config_switch_requested` signal → `main.py._do_live_switch()` — recreates all services and a new MainWindow without restart.

**Known machine_profile_key values**: `ntx_2sp_2h` (NTX 2-spindle 2-head), `lathe_2sp_3h` (Lathe 2-spindle 3-head).

---

## 11. Databases

| File | Owner | Dev path |
|---|---|---|
| `tool_library.db` | Library | `Tools and jaws Library/databases/` |
| `jaws_library.db` | Library | `Tools and jaws Library/databases/` |
| `setup_manager.db` | Setup Manager | `Setup Manager/databases/` or `.runtime/configs/<config_id>/` |

All SQLite. Schema created/migrated at startup. Migrations are idempotent.

**Multi-config**: Multiple configs may point to the same DB path (shared DB). Shared DB detection via `MachineConfigService.configs_sharing_path(path, exclude_id)`.

---

## 12. Style Ownership

**Do not delete a legacy color owner until shared compiler/property path produces identical visual result.**

| Surface | Owner before shared compiler | Semantic token |
|---|---|---|
| Setup Manager main window shell | `Setup Manager/styles/modules/10-base.qss` + `main_window.py:_build_ui_preference_overrides` | `page_bg` |
| Setup Manager work list viewport | `styles/modules/60-catalog.qss` + runtime override | `row_area_bg` |
| Setup Manager work cards | `styles/modules/60-catalog.qss` + `setup_catalog_delegate.py` | `card_bg`, `accent`, `border_strong` |
| Tool Library shell | `Tools and jaws Library/styles/modules/10-base.qss` + override | `page_bg` |
| Tool/Jaw catalog viewport | `Tools and jaws Library/styles/modules/60-catalog.qss` + override | `row_area_bg` |
| Tool catalog cards | `tool_catalog_delegate.py` + `60-catalog.qss` | `card_bg`, `accent`, `border_strong` |
| Standalone selector outer dialog | `Tools and jaws Library/ui/selectors/common.py` paintEvent | `page_bg` |
| Work Editor dialog | stylesheet inheritance + fallback disk load + QSS modules | `editor_bg` |
| Editor sections | `shared/ui/helpers/editor_helpers.py` + QSS group-box rules | `section_bg`, `editor_bg`, `border` |

**High-risk inline style locations:**
- `shared/ui/helpers/editor_helpers.py`
- `Tools and jaws Library/ui/selectors/common.py`
- `Tools and jaws Library/ui/measurement_editor/forms/shared_sections.py`
- `Tools and jaws Library/ui/measurement_editor_dialog.py`
- `Setup Manager/ui/work_editor_dialog.py`

Current branch (`codex/before-shared-styles`) is pre-shared-style-compiler. Do not assume a shared theme compiler exists yet.

---

## 13. PreloadManager

`Setup Manager/services/preload_manager.py` — `PreloadManager` singleton.

```python
from Setup Manager.services.preload_manager import get_preload_manager
pm = get_preload_manager()
pm.tool_service    # ToolService backed by preload DB
pm.jaw_service     # JawService backed by preload DB
pm.fixture_service # FixtureService backed by preload DB
```

Wired in `Setup Manager/main.py`: `initialize(draw_service)` after `DrawService` construction.

`selector_parity_factory.py` reuses preload-owned DB connections (skips duplicate open when `_owned_by_preload=True`).

Preview warmup deduplication: factory skips local warmup if preload manager already armed preview engine.

---

## 14. Modular Platform Status (all complete)

All 10 phases of the Tools and Jaws Library platform overhaul are COMPLETE as of April 2026.

| Phase | Status |
|---|---|
| 0 — Baseline & Freeze Rules | COMPLETE |
| 1 — Domain Module Contracts | COMPLETE |
| 2 — Module Governance Artifacts | COMPLETE |
| 3 — Shared Module Platform Layer | COMPLETE |
| 4 — TOOLS Migration | COMPLETE |
| 5 — JAWS Migration | COMPLETE |
| 6 — Data/Migration Segmentation | COMPLETE |
| 7 — AI-Agent Hardening | COMPLETE |
| 8 — Legacy Coupling Retirement | COMPLETE |
| 9 — Future Domain Template | COMPLETE |

Work Editor / Selector architecture refactor (7 workstreams): all COMPLETE. See `WORK_EDITOR_SELECTOR_ARCHITECTURE_BLUEPRINT.md` for detail.

**Test count as of 2026-04-18**: 212 passing, 0 failing.

---

## 15. Adding New Domain (Template)

Use platform layer as base. Target ~1,000 lines total.

```
model: shared.models.<domain>.py
service: <app>/services/<domain>_service.py
page: <app>/ui/<domain>_page.py  (inherits CatalogPageBase)
editor: <app>/ui/<domain>_editor_dialog.py  (inherits EditorDialogBase)
delegate: <app>/ui/<domain>_catalog_delegate.py  (inherits CatalogDelegate)
export: shared/ui/platforms/export_specification.py
migrations: <app>/data/migrations/<domain>_migrations.py
```

After adding: register extension class in `Tools and jaws Library/docs/module-extension-points.json`.

---

## 16. Shim Policy

- Every shim needs removal note in header, owner, and target phase/date.
- Import-forwarding shims: one cleanup cycle maximum.
- New feature work must not target shim paths.
- **Removal gate**: zero import references + import-path checker passes + smoke test passes + quality gate passes.
- Track in `Tools and jaws Library/docs/deprecations.json`. Find active shims: `grep -r "ADAPTER:\|SHIM:" .`

---

## 17. Quality Gate

Run before merging:

```bat
python scripts/run_quality_gate.py          ← all 7 checks
python scripts/import_path_checker.py       ← no legacy path violations
python scripts/module_boundary_checker.py   ← no cross-domain coupling
python scripts/module_extension_checker.py  ← extension subclass registry
python scripts/smoke_test.py
python scripts/duplicate_detector.py        ← baseline: 9 (pre-existing intentional collision)
python scripts/run_parity_tests.py
```

CI: `.github/workflows/quality-gate.yml`

Tests:

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use `QT_QPA_PLATFORM=offscreen` — no display required. All use in-memory SQLite.

**Test files:**

| File | What it covers |
|---|---|
| `tests/test_selector_contracts.py` | PayloadSchema, ResolvedTypes, Registry, LibraryBackedResolver (27 tests) |
| `tests/test_selector_session.py` | SelectorSessionCoordinator — all states, transitions, force shutdown (28 tests) |
| `tests/test_preload_manager.py` | PreloadManager — init, refresh, shutdown, listeners, fixture_service (18 tests) |
| `tests/test_priority1_targeted.py` | ToolService/JawService filters, migration idempotence, localization, selector_mime, filter_coordinator |
| `tests/test_shared_regressions.py` | Shared UI component regressions, localization merge behavior |
| `tests/test_print_service_resolver_fallback.py` | print_service resolver-primary paths (9 tests) |
| `tests/test_work_editor_resolver_fallback.py` | Work Editor resolver fallback (6 tests) |
| `tests/test_selector_adapter_phase6.py` | selector_adapter pure utility behavior |
| `tests/test_selector_host_phase6.py` | WorkEditorSelectorHost thin mount/detach |
| `tests/test_work_editor_embedded_selector.py` | embedded selector submit dispatch |
| `tests/test_work_editor_style_inheritance.py` | style inheritance |
| `tests/test_work_editor_launch_parent.py` | launch/parent wiring |

---

## 18. DEV_MODE / IS_FROZEN

Both `config.py` files:
```python
IS_FROZEN = getattr(sys, 'frozen', False)
DEV_MODE   = not IS_FROZEN
```

`DEV_MODE=True` → `logging.DEBUG` (stdout + `app.log`).  
`DEV_MODE=False` → `logging.WARNING`.

Log location (source run): `Tools and jaws Library/app.log` / `Setup Manager/app.log`

---

## 19. Known Gaps (Accepted Trade-offs)

- **Cross-process resolver invalidation**: Tool Library is a separate process. No IPC listener for library writes in Setup Manager. Resolver caches bumped on natural sync points (Work Editor open, MainWindow re-show). May serve stale data if user edits library and immediately re-opens Work Editor without returning to main window. Acceptable.
- **UID-based tool resolution not in resolver**: `_resolve_tool_reference_for_assignment` tries `get_tool_ref_by_uid` first (draw_service only). Resolver resolves by `tool_id` only.
- **`MachineConfigService._save()` not atomic**: No temp-file rename. Crash mid-write corrupts JSON.
- **Path comparison is string-based**: `configs_sharing_path` does not normalize paths. `C:\foo\bar.db` and `c:/foo/bar.db` would not match.

---

## 20. Architecture Source Files

| File | Purpose |
|---|---|
| `architecture-map.json` | Machine-readable ownership/dependency map |
| `Tools and jaws Library/docs/module-registry.json` | Module ownership + maturity registry |
| `Tools and jaws Library/docs/architecture-decisions.json` | Architecture Decision Records |
| `Tools and jaws Library/docs/deprecations.json` | Deprecation + shim tracker |
| `Tools and jaws Library/docs/module-index.md` | Module entrypoint index |
| `Tools and jaws Library/docs/module-extension-points.json` | Registered extension subclasses |
| `Tools and jaws Library/docs/module-public-api-manifests.json` | Public API surface |
| `Tools and jaws Library/docs/module-change-checklists.json` | Per-module change checklists |
| `Setup Manager/WORK_EDITOR_REFACTOR_STATUS.md` | Work Editor refactor progress |
| `Tools and jaws Library/PHASE11_SHARED_SUPPORT_STATUS.md` | Phase 11 status |
| `WORK_EDITOR_SELECTOR_ARCHITECTURE_BLUEPRINT.md` | Full selector/resolver architecture (read before touching selector code) |
| `STYLE_OWNERSHIP_MAP.md` | Style owner traces (read before touching QSS/colors) |
| `docs/machine-config-system.md` | Multi-machine config system full spec |
| `docs/shim-retirement-policy.md` | Shim retirement rules |
| `Tools and jaws Library/docs/TOOLS_MODULE_CONTRACT.md` | TOOLS domain API contract |
| `Tools and jaws Library/docs/JAWS_MODULE_CONTRACT.md` | JAWS domain API contract |

---

## 21. Agent Rules Summary

1. Map user language to files using Section 3 before editing.
2. Use canonical `shared.*` imports only (Section 5).
3. Respect all import boundaries (Section 6).
4. Data flows Library → resolver → Work Editor → Setup Card. Never reverse.
5. Do not make Work Editor own tool/jaw metadata.
6. Do not add cache layers. Use `get_resolver()`.
7. Do not add selector lifecycle logic outside `SelectorSessionCoordinator`.
8. Open Work Editor through `work_editor_factory.py`, not `work_editor_dialog.py` directly.
9. Style changes: check `STYLE_OWNERSHIP_MAP.md` first. Do not delete legacy owners until replacement is verified.
10. Migrations: additive-only. Never remove or rename columns.
11. New domains: use `CatalogPageBase`, `EditorDialogBase`, `CatalogDelegate`, `ExportSpecification`.
12. Run `python scripts/run_quality_gate.py` before declaring done.
13. Do not start with local quick fixes when the issue is structural — read `WORK_EDITOR_SELECTOR_ARCHITECTURE_BLUEPRINT.md` first.
