# AI Agent Command Brief

Last updated: 2026-04-12

## Situation

The repository is healthier than the previous baseline:
- `python scripts/run_quality_gate.py` passes.
- `python scripts/import_path_checker.py` passes.
- Cross-app duplicate collisions are down to `7`.
- Shared consolidation has already started:
  - `shared/ui/bootstrap_visual.py`
  - `shared/data/base_database.py`
  - stronger `shared/ui/helpers/common_widgets.py`

The next gains are not broad rewrites. They are targeted responsibility extractions from the biggest remaining UI coordinators, plus a few careful shared consolidations.

## Rules of Engagement

1. Read first:
   - `AGENTS.md`
   - `architecture-map.json`
   - `docs/duplicate-reduction-plan.md`
   - `docs/shim-retirement-policy.md`
   - `TODO_AI_REFACTOR.md`
   - `Setup Manager/WORK_EDITOR_REFACTOR_STATUS.md`
2. Preserve behavior:
   - no schema changes
   - no file format changes
   - no IPC protocol changes
   - no user-visible workflow changes
3. Never create direct imports between the two apps.
4. Only move code into `shared/` when it is clearly canonical and cross-app reusable.
5. Prefer one coherent responsibility slice per pass.
6. Validation after every pass:
   - `python -m py_compile <touched files>`
   - `python scripts/import_path_checker.py`
   - `python scripts/duplicate_detector.py`
   - `python scripts/run_quality_gate.py`

## Current Largest Remaining Targets

1. `Tools and jaws Library/ui/measurement_editor_dialog.py`
2. `Tools and jaws Library/ui/home_page.py`
3. `Tools and jaws Library/ui/jaw_page.py`
4. `Setup Manager/ui/setup_page.py`
5. `Setup Manager/ui/drawing_page.py`

---

## Work Package Alpha

### Objective
Reduce `Tools and jaws Library/ui/measurement_editor_dialog.py` aggressively but safely, using the already-existing `ui/measurement_editor/` package.

### Why this is first
- It is the largest remaining app file.
- It already has the best support-package shape:
  - `ui/measurement_editor/controllers/`
  - `ui/measurement_editor/forms/`
  - `ui/measurement_editor/models/`
  - `ui/measurement_editor/utils/`
  - `ui/measurement_editor/bridge/`

### Primary file
- `Tools and jaws Library/ui/measurement_editor_dialog.py`

### Existing support paths to extend
- `Tools and jaws Library/ui/measurement_editor/controllers/`
- `Tools and jaws Library/ui/measurement_editor/forms/`
- `Tools and jaws Library/ui/measurement_editor/bridge/`

### Safe seams
1. Form builders:
   - `_build_distance_form`
   - `_build_diameter_form`
   - `_build_radius_form`
   - `_build_angle_form`
   - `_build_xyz_header_row`
   - `_build_measurement_type_picker`
2. Measurement registry / list orchestration:
   - `_ensure_measurement_uid`
   - `_measurement_kind_order`
   - `_hidden_list_for_kind`
   - `_active_measurement_kind`
   - `_selected_measurement_meta`
   - `_find_item_by_uid`
   - `_clear_current_measurement_refs`
   - `_rebuild_measurement_all_list`
   - `_update_selected_measurement_name_in_all_list`
   - `_on_all_measurement_selected`
   - `_add_measurement_of_kind`
   - `_show_add_measurement_type_picker`
3. Distance workflow cluster:
   - methods around `_commit_distance_edit`
   - adjust mode / nudge / overlay logic
   - start-pick / measured-value update flow
4. Diameter workflow cluster:
   - methods around `_commit_diameter_edit`
   - adjust mode / geometry target / offset handling
   - pick/start/autostart behavior

### Keep inside dialog
- preview widget ownership
- signal wiring
- lifecycle / `accept()`
- final `get_measurements()`

### Suggested destination modules
- `forms/distance_form.py`
- `forms/diameter_form.py`
- `forms/radius_form.py`
- `forms/angle_form.py`
- `controllers/measurement_registry.py`
- `controllers/distance_workflow.py`
- `controllers/diameter_workflow.py`

### Do not do in same pass
- Do not redesign measurement data structures.
- Do not rename payload keys.
- Do not merge distance/diameter behavior into one abstraction.

---

## Work Package Bravo

### Objective
Continue reducing `Setup Manager/ui/setup_page.py` into `ui/setup_page_support/`.

### Primary file
- `Setup Manager/ui/setup_page.py`

### Existing support paths
- `Setup Manager/ui/setup_page_support/detail_fields.py`
- `Setup Manager/ui/setup_page_support/detail_rendering.py`
- `Setup Manager/ui/setup_page_support/library_context.py`

### Safe seams
1. Embedded widget/dialog classes:
   - `ToolNameCardWidget`
   - `WorkRowWidget`
   - `LogEntryDialog`
2. Batch and backup workflow:
   - `_prune_backups`
   - `_create_db_backup`
   - `_prompt_batch_cancel_behavior`
   - `_batch_edit_works`
   - `_group_edit_works`
3. Remaining detail refresh orchestration:
   - `_refresh_details`
   - anything still formatting or rendering cards inline
4. Toolbar/icon helpers:
   - `_toolbar_icon`
   - `_toolbar_icon_with_svg_render_fallback`

### Suggested destination modules
- `setup_page_support/row_widgets.py`
- `setup_page_support/log_entry_dialog.py`
- `setup_page_support/batch_actions.py`
- `setup_page_support/icon_helpers.py`

### Keep inside page
- page lifecycle
- page selection state
- library handoff actions
- work CRUD entry points

---

## Work Package Charlie

### Objective
Reduce `Setup Manager/ui/drawing_page.py` into a real support package, not just `pdf_viewer_widgets.py`.

### Primary file
- `Setup Manager/ui/drawing_page.py`

### Existing support path
- `Setup Manager/ui/drawing_page_support/pdf_viewer_widgets.py`

### Safe seams
1. Viewer builders:
   - `_build_list_panel`
   - `_build_viewer_panel`
   - `_build_viewer_zoom_overlay`
   - `_build_pdf_toolbar`
2. Search controller logic:
   - `_toggle_pdf_search`
   - `_reapply_search_text`
   - `_focus_first_search_result`
   - `_on_search_model_changed`
   - `_step_search_result`
   - `_refresh_search_overlay`
   - `_focus_search_result`
   - `_update_search_status`
3. Focus/context mode logic:
   - `set_setup_context`
   - `_focus_mode_active`
   - `_focus_selected_in_app`
   - `_dismiss_focus_viewer`
   - `_update_context_labels`
4. Viewer navigation/zoom logic:
   - `_effective_zoom_factor`
   - `_fit_width`
   - `_fit_page`
   - `_step_zoom`
   - `_jump_page`
   - `_go_to_page`

### Suggested destination modules
- `drawing_page_support/viewer_builders.py`
- `drawing_page_support/search_controller.py`
- `drawing_page_support/focus_context.py`
- `drawing_page_support/navigation.py`

### Keep inside page
- document/search model ownership
- selected drawing state
- page/widget lifecycle

---

## Work Package Delta

### Objective
Continue reducing `Tools and jaws Library/ui/home_page.py` with focused extractions into `ui/home_page_support/`.

### Primary file
- `Tools and jaws Library/ui/home_page.py`

### Existing support paths already available
- `home_page_support/bottom_bars_builder.py`
- `home_page_support/catalog_list_widgets.py`
- `home_page_support/components_panel_builder.py`
- `home_page_support/detached_preview.py`
- `home_page_support/detail_fields_builder.py`
- `home_page_support/detail_layout_rules.py`
- `home_page_support/preview_panel_builder.py`
- `home_page_support/selector_actions.py`
- `home_page_support/selector_assignment_state.py`
- `home_page_support/selector_card_builder.py`
- `home_page_support/topbar_builder.py`

### Safe seams
1. Selector normalization/state model:
   - `_selector_tool_key`
   - `_normalize_selector_tool`
   - `_selector_spindle_label`
   - `_normalize_selector_head_value`
   - `_normalize_selector_spindle_value`
   - `_normalize_tool_spindle_orientation`
   - `_tool_matches_selector_spindle`
   - bucket/target storage methods
2. Filter/head/type logic:
   - `_rebuild_filter_row`
   - `_selected_head_filter`
   - `_build_tool_type_filter_items`
   - `bind_external_head_filter`
   - `set_head_filter_value`
3. Detail-panel construction:
   - `_clear_details`
   - `_build_placeholder_details`
   - `populate_details`
   - component panel builders still in-page
4. Export/copy/delete dialog helpers:
   - `_prompt_text`
   - `_confirm_yes_no`

### Suggested destination modules
- `home_page_support/selector_model.py`
- `home_page_support/filter_state.py`
- `home_page_support/detail_panels.py`
- `home_page_support/dialog_helpers.py`

### Keep inside page
- page lifecycle
- current selection state
- service calls
- add/edit/delete/export entry points

---

## Work Package Echo

### Objective
Continue reducing `Tools and jaws Library/ui/jaw_page.py`.

### Primary file
- `Tools and jaws Library/ui/jaw_page.py`

### Existing support paths
- `jaw_page_support/detail_layout_rules.py`
- `jaw_page_support/preview_rules.py`
- `jaw_page_support/selector_actions.py`
- `jaw_page_support/selector_slot_controller.py`
- `jaw_page_support/selector_widgets.py`

### Safe seams
1. Detached preview workflow:
   - `_ensure_detached_preview_dialog`
   - `_apply_detached_preview_default_bounds`
   - `_update_detached_measurement_toggle_icon`
   - `_on_detached_measurements_toggled`
   - `_apply_detached_measurement_state`
   - `_on_detached_preview_closed`
   - `_close_detached_preview`
   - `_sync_detached_preview`
2. Top-level builder sections:
   - `_build_top_filter_frame`
   - `_build_main_content_layout`
   - `_build_catalog_list_card`
   - `_build_detail_container`
   - `_build_selector_card`
   - `_build_primary_bottom_bar`
   - `_build_selector_bottom_bar`
3. Batch/backup helpers:
   - `_prune_backups`
   - `_create_db_backup`
   - `_prompt_batch_cancel_behavior`
   - `_batch_edit_jaws`
   - `_group_edit_jaws`

### Suggested destination modules
- `jaw_page_support/detached_preview.py`
- `jaw_page_support/layout_builders.py`
- `jaw_page_support/batch_actions.py`

### Keep inside page
- selection state
- service calls
- add/edit/delete/copy entry points

---

## Work Package Foxtrot

### Objective
Evaluate a new shared candidate: generic drag/drop assignment list primitives.

### Primary comparison files
- `Setup Manager/ui/work_editor_support/dragdrop_widgets.py`
- `Tools and jaws Library/ui/home_page_support/catalog_list_widgets.py`

### Observation
These are not fully identical, but they share a clear shape:
- drag-enabled assignment list widget
- remove-drop button
- translucent ghost pixmap rendering
- selection clearing on blank click

### Recommended approach
Do not force a full merge yet.

Extract the lowest-risk common pieces first:
1. shared ghost-pixmap builder helper
2. shared blank-click deselection helper
3. optional shared base class for remove-drop buttons if MIME handling can stay injected

### Suggested destination modules
- `shared/ui/helpers/dragdrop_helpers.py`
- or `shared/ui/helpers/assignment_dragdrop.py`

### Do not do yet
- Do not unify MIME payload encoding/decoding across apps unless the payloads are intentionally made canonical.

---

## Work Package Golf

### Objective
Treat both `main_window.py` files as a later shared-shell target, not an immediate one.

### Primary files
- `Setup Manager/ui/main_window.py`
- `Tools and jaws Library/ui/main_window.py`

### Shared-looking responsibilities
- fade helpers
- current window rect helpers
- localized label refresh patterns
- preference override CSS generation
- background-click deselection behavior

### Why not first
- window/module navigation behavior is more coupled to app ownership than the page/dialog work.
- better payoff comes after page/dialog monoliths are reduced.

### Recommendation
Create a future task only after Alpha through Echo are materially advanced.

---

## Work Package Hotel

### Objective
Be careful with shared database consolidation.

### Current state
- Shared base exists:
  - `shared/data/base_database.py`

### Recommendation
Pause major DB refactors unless there is a clearly neutral primitive to extract.

### Allowed
- connection lifecycle helpers
- row_factory setup
- parent-directory ensure logic

### Not allowed
- schema merging
- migration merging
- app-domain CRUD merging

---

## Command Priorities

1. Alpha: `measurement_editor_dialog.py`
2. Bravo: `setup_page.py`
3. Charlie: `drawing_page.py`
4. Delta: `home_page.py`
5. Echo: `jaw_page.py`
6. Foxtrot: shared drag/drop primitives
7. Golf: main window shared-shell helpers
8. Hotel: database primitives only if justified

## Reporting Format For Every Agent

Each agent should report:
- objective completed
- exact responsibility extracted
- files changed/added
- why the boundary is safe
- validation commands run
- risks or deferred follow-up

## Stop Conditions

Stop and escalate if:
- a change would alter payload shape or schema
- a shared extraction would force cross-app imports
- a refactor would require shims longer than one cleanup cycle
- duplicate baseline would increase without clear justification
