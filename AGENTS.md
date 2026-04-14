# AGENTS

## Goal
This repository is optimized for deterministic AI-assisted coding. Always prefer canonical shared modules and avoid introducing duplicate implementations across apps.

---

## User Language → Technical Translation

When the user says something conversational, map it to the right file before touching anything.

| User says… | Technical meaning | Primary file(s) |
|---|---|---|
| "Tool Library" / "Tool Catalog" | `HomePage` — the tool catalog browsing page | `Tools and jaws Library/ui/home_page.py` |
| "Jaw Library" / "Jaw Catalog" | `JawPage` — the jaw catalog browsing page | `Tools and jaws Library/ui/jaw_page.py` |
| "Tool Selector" | `ToolSelectorDialog` — standalone dialog that opens when Setup Manager requests tool selection | `Tools and jaws Library/ui/selectors/tool_selector_dialog.py` |
| "Jaw Selector" | `JawSelectorDialog` — standalone dialog for jaw selection | `Tools and jaws Library/ui/selectors/jaw_selector_dialog.py` |
| "Add/Edit Tool dialog" | `ToolEditorDialog` — the tool CRUD form | `Tools and jaws Library/ui/tool_editor_dialog.py` + `ui/tool_editor_support/` |
| "Add/Edit Jaw dialog" | `JawEditorDialog` — the jaw CRUD form | `Tools and jaws Library/ui/jaw_editor_dialog.py` + `ui/jaw_editor_support/` |
| "Detail panel" / "Tool details" | Right-side detail panel built by `build_detail_container` | `Tools and jaws Library/ui/home_page_support/detail_panel_builder.py` |
| "Jaw detail panel" | Right-side detail panel for jaws | `Tools and jaws Library/ui/jaw_page_support/detail_panel_builder.py` |
| "Filter bar" / "Search bar" | Top toolbar with search input + filter dropdowns | `Tools and jaws Library/ui/home_page_support/topbar_builder.py` (tools) · `ui/jaw_page_support/topbar_builder.py` (jaws) |
| "Bottom bar" / "action buttons" (ADD/EDIT/DELETE) | `build_bottom_bars` — the action button strip at page bottom | `Tools and jaws Library/ui/home_page_support/page_builders.py` · `ui/jaw_page_support/page_builders.py` |
| "CANCEL / DONE buttons" (in selector) | Bottom bar inside selector dialogs | `Tools and jaws Library/ui/selectors/common.py` → `build_selector_bottom_bar` |
| "Selector panel" / "assignment panel" / "drag-drop zone" | Selector card built inside selector dialogs | `Tools and jaws Library/ui/selectors/tool_selector_dialog.py` → `_build_selector_card()` |
| "SP1 / SP2 slots" (jaws) | `JawAssignmentSlot` widgets in jaw selector | `Tools and jaws Library/ui/jaw_page_support/selector_widgets.py` |
| "Mini tool cards" / "assignment rows" | `MiniAssignmentCard` items in the assignment list | `shared/ui/cards/mini_assignment_card.py` |
| "Tool list / catalog list" | `ToolCatalogListView` — drag-enabled QListView | `Tools and jaws Library/ui/home_page_support/catalog_list_widgets.py` |
| "Jaw list / catalog list" | `JawCatalogListView` — drag-enabled QListView | `Tools and jaws Library/ui/jaw_page_support/catalog_list_widgets.py` |
| "Tool card" / "catalog card" (rendering) | `ToolCatalogDelegate` — custom item renderer | `Tools and jaws Library/ui/tool_catalog_delegate.py` |
| "Jaw card" / "catalog card" (jaws) | `JawCatalogDelegate` | `Tools and jaws Library/ui/jaw_catalog_delegate.py` |
| "Setup Manager" | The setup workflow app (separate process) | `Setup Manager/` |
| "Work Editor" | `WorkEditorDialog` — the main work editing dialog in Setup Manager | `Setup Manager/ui/work_editor_dialog.py` + `ui/work_editor_support/` |
| "Setup page" / "Works list" | `SetupPage` — the main list of setups/works | `Setup Manager/ui/setup_page.py` + `ui/setup_page_support/` |
| "Logbook" | `LogbookPage` | `Setup Manager/ui/logbook_page.py` |
| "Drawings" | `DrawingPage` | `Setup Manager/ui/drawing_page.py` + `ui/drawing_page_support/` |
| "IPC" / "selector callback" / "sends selection back" | `QLocalSocket`-based IPC between Setup Manager and Tools/Jaws Library | `Tools and jaws Library/ui/main_window.py` → `_send_selector_result_payload` · Setup Manager receives in its socket server |
| "Main window" (Tools/Jaws app) | `MainWindow` — app shell, selector session lifecycle, IPC | `Tools and jaws Library/ui/main_window.py` |
| "STL preview" / "3D preview" | STL viewer widget + detached window | `shared/ui/stl_preview.py` · page `detached_preview.py` modules |

---

## Navigation Map — Where to Go for Common Edits

### Tool Selector (the dialog that opens from Setup Manager)
```
Tools and jaws Library/ui/selectors/
  tool_selector_dialog.py      ← full dialog: catalog, assignment panel, DONE/CANCEL
  tool_selector_layout.py      ← layout helpers for the dialog
  tool_selector_state.py       ← assignment state management
  tool_selector_payload.py     ← payload encoding/decoding
  common.py                    ← SelectorDialogBase, build_selector_bottom_bar
```
Entry point: `MainWindow._open_selector_dialog_for_session()` →  
`Tools and jaws Library/ui/main_window.py:1100`

### Jaw Selector (the dialog that opens from Setup Manager)
```
Tools and jaws Library/ui/selectors/
  jaw_selector_dialog.py       ← full dialog: catalog, SP1/SP2 slots, DONE/CANCEL
  jaw_selector_layout.py
  jaw_selector_state.py
  jaw_selector_payload.py
  common.py
```
Entry point: same `MainWindow._open_selector_dialog_for_session()` branch for `mode == 'jaws'`

### Tool Library (catalog page — browse, search, filter tools)
```
Tools and jaws Library/ui/
  home_page.py                              ← thin orchestrator; start here
  home_page_support/
    page_builders.py                        ← overall layout (splitter, detail container, bottom bar)
    topbar_builder.py                       ← search input, filter dropdowns
    filter_coordinator.py                   ← applies active filters to tool list
    topbar_filter_state.py                  ← head-filter binding state
    catalog_list_widgets.py                 ← ToolCatalogListView (drag-enabled)
    detail_panel_builder.py                 ← right-side tool detail panel content
    detail_layout_rules.py                  ← which fields appear for each tool type
    detail_visibility.py                    ← show/hide detail panel
    crud_actions.py                         ← add / edit / delete / copy tool
    selection_helpers.py                    ← get_selected_tool, selected_tool_uids
    selection_signal_handlers.py            ← item_selected / item_deleted handlers
    runtime_actions.py                      ← refresh_catalog, select_tool_by_id
    selector_context.py                     ← selector mode state (used minimally now)
    selector_widgets.py                     ← ToolAssignmentListWidget, ToolSelectorRemoveDropButton
    event_filter.py                         ← keyboard/mouse event handling
    detached_preview.py                     ← STL detached preview window
    retranslate_page.py                     ← i18n refresh + tool type filter items
    link_actions.py                         ← part_clicked (component link handler)
```

### Jaw Library (catalog page — browse, search, filter jaws)
```
Tools and jaws Library/ui/
  jaw_page.py                               ← thin orchestrator; start here
  jaw_page_support/
    page_builders.py                        ← overall layout
    topbar_builder.py                       ← search, view-mode filter
    catalog_list_widgets.py                 ← JawCatalogListView (drag-enabled)
    detail_panel_builder.py                 ← right-side jaw detail panel
    detail_layout_rules.py
    detail_visibility.py
    crud_actions.py                         ← add / edit / delete jaw
    batch_actions.py                        ← multi-select operations
    selection_helpers.py
    selection_signal_handlers.py
    selector_actions.py                     ← legacy page-level selector helpers (less used now)
    selector_slot_controller.py             ← SP1/SP2 slot state in catalog page (legacy)
    selector_widgets.py                     ← JawAssignmentSlot, SelectorRemoveDropButton
    bottom_bars_builder.py                  ← ADD/EDIT/DELETE + selector bottom bar
    event_filter.py
    detached_preview.py
    retranslate_page.py
    preview_rules.py
```

### Tool Editor (add / edit tool dialog)
```
Tools and jaws Library/ui/
  tool_editor_dialog.py                     ← dialog shell; EditorDialogBase subclass
  tool_editor_support/
    general_tab.py                          ← General tab fields (ID, type, dimensions)
    components_tab.py                       ← Components tab
    components.py                           ← component data helpers
    models_tab.py                           ← 3D models tab
    component_picker_dialog.py              ← pick a component from catalog
    component_linking_dialog.py             ← link component to tool
    spare_parts_table_coordinator.py        ← spare parts widget logic
    tool_type_rules.py                      ← field visibility rules by tool type
    measurement_rules.py                    ← measurement field rules
    transform_rules.py                      ← model transform rules
    detail_layout_rules.py
    general_tab.py
    payload_codec.py                        ← encode/decode tool dict ↔ form fields
```

### Jaw Editor (add / edit jaw dialog)
```
Tools and jaws Library/ui/
  jaw_editor_dialog.py                      ← dialog shell
  jaw_editor_support/
    models_tab.py                           ← 3D models tab
```

### Measurement Editor (measurement definitions for tools/jaws)
```
Tools and jaws Library/ui/
  measurement_editor_dialog.py              ← dialog orchestrator; builds forms, wires coordinators
  measurement_editor/
    coordinators/
      list_manager.py                       ← MeasurementListManager — list CRUD, selection, kind filtering
      pick_coordinator.py                   ← PickCoordinator — pick_target / dist_pick_stage /
                                              diam_pick_stage state + point-picked dispatch
      distance_editor.py                    ← DistanceEditor — distance edit model, two-point pick
      diameter_editor.py                    ← DiameterEditor — diameter edit model, center/edge pick
      axis_overlay.py                       ← AxisOverlay — axis-pick overlay hint on preview
      preview_coordinator.py                ← PreviewCoordinator — preview_sync bridge
    models/                                 ← distance, diameter, radius, angle dataclasses + registry
    forms/                                  ← form builder helpers (read-only during refactor)
    utils/                                  ← coordinates, axis_math
```

### Main Window — Selector Session Lifecycle (IPC + dialog orchestration)
```
Tools and jaws Library/ui/main_window.py
  _open_selector_dialog_for_session()   L~1100  ← opens ToolSelectorDialog or JawSelectorDialog
  _on_selector_dialog_submit()          L~1145  ← receives result from dialog DONE
  _on_selector_dialog_cancel()          L~1137  ← handles dialog CANCEL
  _send_selector_result_payload()       L~1159  ← sends result back to Setup Manager via IPC
  _clear_selector_session()             L~1060  ← closes dialogs, resets state
  _close_selector_dialogs()             L~1085  ← safe close of open selector dialogs
  _back_to_setup_manager()              L~973   ← hides this window, shows Setup Manager
```

### Shared Selector Infrastructure
```
Tools and jaws Library/ui/
  selector_mime.py                          ← MIME type constants + encode/decode helpers
  selector_state_helpers.py                 ← bucket normalization, target key helpers
  selector_ui_helpers.py                    ← spindle label, normalize_selector_spindle
  shared/selector_panel_builders.py         ← build_selector_card_shell, build_selector_info_header,
                                               build_selector_toggle_button, build_selector_actions_row
```

### Shared Platform / Base Classes
```
shared/ui/platforms/
  catalog_page_base.py                      ← CatalogPageBase (HomePage + JawPage inherit this)
  editor_dialog_base.py                     ← EditorDialogBase (tool/jaw editors)
  catalog_delegate.py                       ← CatalogDelegate (base for item renderers)
  selector_state.py                         ← SelectorState (pure-Python filter FSM)
  export_specification.py                   ← ExportSpecification (Excel I/O)

shared/ui/
  helpers/editor_helpers.py                 ← style_panel_action_button, create_titled_section, etc.
  helpers/page_scaffold_common.py           ← build_page_root, build_catalog_splitter, etc.
  helpers/dragdrop_helpers.py               ← build_text_drag_ghost, clear_selection_on_blank_click
  cards/mini_assignment_card.py             ← MiniAssignmentCard (used in selector assignment lists)
  stl_preview.py                            ← STL 3D preview widget
```

### Setup Manager
```
Setup Manager/
  main.py                                   ← app entry point
  ui/
    main_window.py                          ← app shell
    setup_page.py + setup_page_support/    ← works/setups list
    work_editor_dialog.py + work_editor_support/  ← work editor (large dialog)
    logbook_page.py                         ← logbook
    drawing_page.py + drawing_page_support/ ← drawings
    preferences_dialog.py
  services/
    work_service.py                         ← CRUD for works/setups
    logbook_service.py
    draw_service.py
    print_service.py
  models/                                   ← Setup Manager-specific models
  data/                                     ← migrations, DB access
```

---

## Workspace Layout
- `Setup Manager/` — setup/workflow app
- `Tools and jaws Library/` — tool/jaw library app
- `shared/` — canonical cross-app modules

## Canonical Shared Paths
- Services:
  - `shared.services.localization_service`
  - `shared.services.ui_preferences_service`
- Models:
  - `shared.models.tool`
  - `shared.models.jaw`
- UI:
  - `shared.ui.stl_preview`
  - `shared.ui.preferences_dialog_base`
  - `shared.ui.helpers.editor_helpers`
  - `shared.ui.helpers.common_widgets`
  - `shared.ui.helpers.editor_table`
  - `shared.ui.cards.mini_assignment_card`
- Platform Layer (Phases 3-9, all COMPLETE — use these for any new domain work):
  - `shared.ui.platforms.catalog_page_base` — `CatalogPageBase` abstract page orchestrator
  - `shared.ui.platforms.editor_dialog_base` — `EditorDialogBase` schema-driven editor
  - `shared.ui.platforms.catalog_delegate` — `CatalogDelegate` abstract card renderer
  - `shared.ui.platforms.selector_state` — `SelectorState` pure-Python filter state machine
  - `shared.ui.platforms.export_specification` — `ExportSpecification` domain-neutral Excel I/O
- Data:
  - `shared.data.model_paths`

## Import Rules
- Allowed: canonical `shared.*` imports and app-local imports for app-specific domains.
- Disallowed:
  - Legacy shared paths (e.g. `shared.editor_helpers`, `shared.model_paths`, `shared.editor_table`, `shared.mini_assignment_card`)
  - Cross-app imports from one app directly into the other app.
  - New wrapper modules that only forward imports unless temporary and explicitly marked.
  - Importing from `ui/home_page_support/` inside JAWS domain code (or vice versa).
  - Importing `tool_editor_support/` from `jaw_editor_dialog.py` unless logic is proven reusable.

## Intentional Boundaries (Do Not Merge)
- App-specific migration domains: `Tools and jaws Library/data/migrations/` package (tools_migrations.py + jaws_migrations.py)
- App-specific runtime config in each app `config.py`
- Setup-specific jaw default behavior in `Setup Manager/models/jaw.py`
- TOOLS and JAWS remain separate database domains (no merged table — out of scope)

## Validation Commands
- Full quality gate (6 checks):
  - `python scripts/run_quality_gate.py`
- Individual checks:
  - `python scripts/import_path_checker.py`
  - `python scripts/module_boundary_checker.py`
  - `python scripts/smoke_test.py`
  - `python scripts/duplicate_detector.py`
  - `python scripts/run_parity_tests.py`

## Architecture Source Of Truth
- Machine-readable ownership/dependency map: `architecture-map.json`
- Module ownership + maturity registry: `Tools and jaws Library/docs/module-registry.json`
- Architecture Decision Records: `Tools and jaws Library/docs/architecture-decisions.json`
- Deprecation + shim tracker: `Tools and jaws Library/docs/deprecations.json`
- Module entrypoint index: `Tools and jaws Library/docs/module-index.md`
- AI agent contribution guide: `Tools and jaws Library/docs/ai-agent-contribution-guide.md`
- Work Editor refactor progress/status: `Setup Manager/WORK_EDITOR_REFACTOR_STATUS.md`
- Shared support goals: `Tools and jaws Library/PHASE11_SHARED_SUPPORT_GOALS.md`
- Shared support rules: `Tools and jaws Library/PHASE11_SHARED_SUPPORT_RULES.md`
- Shared support status: `Tools and jaws Library/PHASE11_SHARED_SUPPORT_STATUS.md`

## Modular Platform Overhaul — STATUS (as of April 13, 2026)

All 10 phases COMPLETE. The Tools and Jaws Library has been fully migrated to the platform layer.

| Phase | Title | Status |
|-------|-------|--------|
| 0 | Baseline & Freeze Rules | 🟢 COMPLETE |
| 1 | Domain Module Contracts | 🟢 COMPLETE |
| 2 | Module Governance Artifacts | 🟢 COMPLETE |
| 3 | Shared Module Platform Layer | 🟢 COMPLETE |
| 4 | TOOLS Migration (Pilot) | 🟢 COMPLETE — home_page.py 2,223L → 700L |
| 5 | JAWS Migration | 🟢 COMPLETE — jaw_page.py 1,423L → 558L |
| 6 | Data/Migration Segmentation | 🟢 COMPLETE — migrations.py → migrations/ package |
| 7 | AI-Agent Hardening | 🟢 COMPLETE |
| 8 | Legacy Coupling Retirement | 🟢 COMPLETE — adapters, shims, duplicate modules retired |
| 9 | Future Domain Template | 🟢 COMPLETE — Fixtures example domain verified |

**Post-overhaul file layout (Tools and jaws Library)**:
- `ui/home_page.py` — thin orchestrator (~583L), inherits `CatalogPageBase`
- `ui/jaw_page.py` — thin orchestrator (~524L), inherits `CatalogPageBase`
- `ui/home_page_support/` — 17 active modules including detail builders, filter/runtime/link coordinators, page builders, selector context, topbar builder, detached preview, and selection handlers
- `ui/jaw_page_support/` — 18 active modules including topbar builder, detail/bottom-bar builders, selector modules, page builders, detached preview, selection helpers, and selection signal handlers
- `ui/tool_editor_support/` — `component_picker_dialog.py`, `spare_parts_table_coordinator.py`, `component_linking_dialog.py`, `measurement_rules.py`, `transform_rules.py`
- `ui/selectors/` — `ToolSelectorDialog`, `JawSelectorDialog` (standalone selector dialogs, post-Phase-10)
- `data/migrations/` — package with `tools_migrations.py` + `jaws_migrations.py` (backward-compatible)

**Adding a new domain**: Use `shared.ui.platforms.*` as the base (CatalogPageBase, EditorDialogBase, CatalogDelegate, ExportSpecification). Target ~1,000 lines total (model + service + page + editor + export spec + migrations).

## Temporary Shim Policy
- Temporary compatibility shims must include a removal note and target date/phase.
- Shims should be removed in the next cleanup cycle once all call sites are migrated.
- Track all shims in `docs/deprecations.json` with explicit removal targets.
- Search for `ADAPTER:` and `SHIM:` comments to find all active bridges.

## Ongoing Refactor Tracking
- For behavior-preserving reduction of `Setup Manager/ui/work_editor_dialog.py`, follow:
  - `Setup Manager/WORK_EDITOR_REFACTOR_STATUS.md`
- For support-layer convergence tracking (Phase 11), see:
  - `Tools and jaws Library/PHASE11_SHARED_SUPPORT_STATUS.md`
- Keep refactor passes small and responsibility-scoped.
