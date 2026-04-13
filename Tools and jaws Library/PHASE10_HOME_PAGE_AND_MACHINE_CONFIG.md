# Phase 10: home_page.py Completion + Machine Config Foundation

**As of**: April 13, 2026
**Branch**: codex/before-shared-styles
**Status**: Part A COMPLETE — Part B NOT STARTED

---

## GOAL

### Part A — home_page.py Final Extraction (COMPLETE)

Bring `home_page.py` to structural parity with `jaw_page.py`. The JAWS pattern uses 18 focused support modules with `jaw_page.py` at 558L. After Phases 0–9 TOOLS was still 1,333L with only 4 support modules.

**Target**: home_page.py ≤ 580L, all logic in focused support modules.

### Part B — Machine Config Foundation (NOT STARTED)

Make machine profiles a runtime-selectable concept. Currently `NTX_MACHINE_PROFILE` is a hardcoded frozen dataclass. Head/spindle filter options are hardcoded strings in three separate places.

**Target**: Profile registry + shared preference key + filter builders read from active profile. Only one profile exists now (2SP+2H), but architecture becomes extensible without code changes.

---

## RULES

1. **No behavior change** — Part A is structural only. Every extracted function must produce identical output to the inlined code it replaced.
2. **Thin delegation pattern** — Method bodies in home_page.py become single-line calls: `return _impl(self, ...)`. No logic stays in the class wrapper.
3. **`__all__` on every module** — Each support module declares its public API.
4. **Import cleanup after each pass** — Remove unused Qt/stdlib imports from home_page.py after each extraction. Verify with py_compile before moving on.
5. **Quality gate must stay green** — `python scripts/run_quality_gate.py` exits 0 (6 checks) and 7/7 regression tests pass after every pass.
6. **JAWS page untouched during Part A** — Only home_page.py and home_page_support/ are modified in Part A.
7. **Part B: backward-compatible profile registry** — `NTX_MACHINE_PROFILE` stays as an alias. `load_profile(key)` falls back to default if key unknown.
8. **Part B: no DB schema changes** — Profile selection is UI/preferences only. Tool and Jaw records are unchanged.

---

## STATUS

### Part A — Extraction Passes

| Pass | Module Created / Extended | Methods Extracted | Lines Saved | Status |
|------|--------------------------|-------------------|-------------|--------|
| 1 | `detail_visibility.py` | `show_details`, `hide_details`, `toggle_details` | ~40L | ✅ DONE |
| 1 | `selection_helpers.py` | `_get_selected_tool`, `_selected_tool_uids`, `_restore_selection_by_uid` | ~30L | ✅ DONE |
| 1 | `event_filter.py` | `eventFilter`, `_refresh_elided_group_title` | ~50L | ✅ DONE |
| 1 | `retranslate_page.py` | `apply_localization`, `_build_tool_type_filter_items`, `_localized_tool_type`, `_tool_id_display_value` | ~60L | ✅ DONE |
| 2 | `crud_actions.py` | `add_tool`, `edit_tool`, `delete_tool`, `copy_tool` | ~80L | ✅ DONE |
| 2 | `topbar_filter_state.py` | `_selected_head_filter`, `bind_external_head_filter`, `set_head_filter_value` | ~40L | ✅ DONE |
| 3 | `topbar_builder.py` | `build_filter_pane`, `_rebuild_filter_row`, `_toggle_search`, `_clear_filters` | ~130L | ✅ DONE |
| 4 | `page_builders.py` | `_build_ui`, `_build_catalog_list_card`, `_build_detail_container`, `_build_bottom_bars` | ~230L | ✅ DONE |
| 5 | `selector_context.py` | `_normalize_selector_tool`, `_selector_tool_key`, `_selector_target_key`, `_selector_current_target_key`, `_tool_matches_selector_spindle`, `selected_tools_for_setup_assignment`, `selector_assignment_buckets_for_setup_assignment`, `selector_current_target_for_setup_assignment`, `set_selector_context`, `selector_assigned_tools_for_setup_assignment` | ~117L | ✅ DONE |
| 6 | `detached_preview.py` (extended) | `_warmup_preview_engine` | ~20L | ✅ DONE |
| 7 | Quality gate verification | — | — | ✅ PASS (6/6 checks, 7/7 tests) |

**home_page.py line count progression**:
- Start: **1,333L**
- After Pass 4: **851L**
- After Pass 5: **734L**
- After Pass 6: **716L** ← current

**home_page_support/ modules** (all files):
- `__init__.py`
- `crud_actions.py` ← Pass 2
- `detail_fields_builder.py` (pre-existing)
- `detail_layout_rules.py` (pre-existing)
- `detail_panel_builder.py` (pre-existing)
- `detail_visibility.py` ← Pass 1
- `detached_preview.py` (pre-existing, extended Pass 6)
- `event_filter.py` ← Pass 1
- `page_builders.py` ← Pass 4
- `retranslate_page.py` ← Pass 1
- `selection_helpers.py` ← Pass 1
- `selector_context.py` ← Pass 5
- `topbar_builder.py` ← Pass 3
- `topbar_filter_state.py` ← Pass 2

---

### Part B — Machine Config Foundation

#### Steps

| Step | File(s) | Change | Status |
|------|---------|--------|--------|
| 1 | `Setup Manager/machine_profiles.py` | Add `PROFILE_REGISTRY`, `DEFAULT_PROFILE_KEY`, `load_profile(key)` helper; keep `NTX_MACHINE_PROFILE` alias | ✅ DONE |
| 2 | `shared/services/ui_preferences_service.py` | Add `machine_profile_key` field + `get_machine_profile_key()` / `set_machine_profile_key(key)` | ✅ DONE |
| 3 | `Setup Manager/ui/work_editor_dialog.py` | Load profile via `load_profile(ui_preferences.get_machine_profile_key())` instead of direct import | ✅ DONE |
| 4 | `Setup Manager/ui/preferences_dialog.py` | Add machine profile selector dropdown (single option for now); persist via `UiPreferencesService` | ✅ DONE |
| 5 | `Tools and jaws Library/ui/home_page_support/topbar_filter_state.py` | Accept optional `machine_profile`; build head filter options from `profile.heads` | ✅ DONE |
| 6 | `Tools and jaws Library/ui/jaw_page_support/topbar_builder.py` | Update `populate_spindle_filter()` to accept optional `machine_profile`; options from `profile.spindles` | ✅ DONE |
| 7 | `Tools and jaws Library/ui/main_window.py` | Load profile from shared preferences on startup; pass to HomePage and JawPage | ✅ DONE |
| 8 | Quality gate | Run `run_quality_gate.py` — must exit 0 | ✅ PASS |

#### Key Files for Part B
- `Setup Manager/machine_profiles.py` — frozen dataclass source; add registry here
- `Setup Manager/ui/work_editor_dialog.py` lines ~157-161 — current direct profile import
- `shared/services/ui_preferences_service.py` — shared prefs; add `machine_profile_key`
- `.runtime/shared_ui_preferences.json` — runtime prefs file (gains `machine_profile_key` key)
- `Tools and jaws Library/ui/jaw_page_support/topbar_builder.py` — spindle filter hardcoded
- `Tools and jaws Library/ui/main_window.py` lines ~46-200 — startup init

#### Acceptance Criteria (Part B)
- Profile selection in preferences persists across app restart
- Both apps (Setup Manager + Tools Library) read profile from `shared_ui_preferences.json`
- Current behavior is identical (only one profile exists, no visible change)
- Architecture is extensible: adding a second profile requires only adding to `PROFILE_REGISTRY` + no filter-builder changes

---

## NEXT ACTION

Part B implementation is complete for the current single-profile rollout. Next action: add localization keys for machine-profile labels if custom naming is needed.
