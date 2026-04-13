# Phase 5 JAWS Migration Design: JawPage -> CatalogPageBase

**Phase**: 5 (JAWS Migration)  
**Date**: April 13, 2026  
**Target**: Refactor JawPage from 1,423L monolith to ~400-450L platform-based page  
**Status**: ✅ COMPLETE — jaw_page.py 1,423L → 558L; all 8 passes done; quality gate green  
**Constraint**: Zero behavior change, parity must remain 13/13 PASS, no schema changes, no cross-app imports  

---

## Table of Contents

1. Overview
2. Current JawPage Analysis
3. Phase 5 Target Architecture
4. New JawPage Implementation (Complete)
5. New JawCatalogDelegate Implementation (Complete)
6. Filter Pane and apply_filters Design
7. Preview Plane and Rotation Preservation
8. CRUD, Batch Operations, and Signal Strategy
9. Extraction Targets
10. Old-to-New Mapping
11. Implementation Checklist
12. Parity Test Strategy
13. Risks, Fallbacks, and Acceptance Gates
14. Appendices

---

## Overview

### Problem Statement

`ui/jaw_page.py` is still a monolithic page that combines:

- page construction
- catalog list orchestration
- filtering
- detail rendering
- detached preview handling
- selector slot workflows
- CRUD actions
- batch operations
- localization refresh

Phase 4 already proved the correct migration direction in the TOOLS domain:

- `HomePage` now inherits `CatalogPageBase`
- shared catalog behavior moved to the platform layer
- tool-specific behavior remained inside the page and support modules
- the page size dropped from 2,223L to 598L
- the abstract contract stabilized around four methods:
  - `create_delegate()`
  - `get_item_service()`
  - `build_filter_pane()`
  - `apply_filters()`

Phase 5 should repeat that exact model for the JAWS domain.

### Primary Goals

1. Convert `JawPage(QWidget)` into `JawPage(CatalogPageBase)`.
2. Reduce `ui/jaw_page.py` from 1,423L to about 400-450L.
3. Preserve all jaw-specific workflows:
   - selector slots for SP1 and SP2
   - jaw type filtering
   - spindle filtering
   - detached 3D preview
   - preview plane and rotation restoration
   - batch edit and group edit
   - CRUD operations
   - localization refresh
4. Introduce a platform-aligned `JawCatalogDelegate(CatalogDelegate)`.
5. Extract local UI builders from `jaw_page.py` into `ui/jaw_page_support/` modules.
6. Keep parity with the Phase 0 baseline and require 13/13 PASS before signoff.

### Target Outcome

| Metric | Current | Target | Notes |
|--------|---------|--------|-------|
| JawPage lines | 1,423L | 400-450L | page orchestration only |
| Delegate base | `QStyledItemDelegate` | `CatalogDelegate` | matches platform layer |
| Catalog logic duplication | high | near-zero | shared in base class |
| Preview helpers in page | mixed | minimal | delegated to support modules |
| Selector logic | preserved | preserved | controller remains jaw-specific |
| Tests | baseline 13/13 | 13/13 PASS | mandatory gate |

### Design Principle

Do not invent a new JAWS-only framework. Reuse the exact architecture already validated in Phase 4.

That means:

- platform-owned catalog refresh lifecycle
- page-owned domain state
- support-module-owned detail and preview builders
- signal-driven updates from base selection events
- minimal page code, not another large helper god module

---

## Current JawPage Analysis

### Existing Structure Summary

Current `ui/jaw_page.py` contains these responsibility groups:

1. Catalog list widget and drag payload generation
2. Top toolbar, search, filter icon, type filter, preview button
3. Sidebar navigation (`all`, `main`, `sub`, `soft`, `hard_group`)
4. Detail container and selector card composition
5. Bottom action bars
6. Selector mode activation and slot assignment coordination
7. Search/filter/view refresh logic
8. Multi-select handling and batch operations
9. Detail panel rendering
10. Detached preview management
11. CRUD actions
12. Localization re-application

### Method Inventory by Responsibility

#### 1. Construction and UI assembly

- `__init__`
- `_build_ui`
- `_build_top_filter_frame`
- `_build_main_content_layout`
- `_build_catalog_list_card`
- `_build_detail_container`
- `_build_selector_card`
- `_build_primary_bottom_bar`
- `_build_selector_bottom_bar`
- `_install_layout_event_filters`

#### 2. Module integration and filters

- `set_module_switch_handler`
- `set_module_switch_target`
- `set_master_filter`
- `set_selector_context`
- `selector_assigned_jaws_for_setup_assignment`
- `_toggle_search`
- `_set_view_mode`
- `set_view_mode`
- `_nav_mode_title`
- `_set_type_filter_value`
- `_build_type_filter_items`
- `_rebuild_filter_row`
- `_on_type_filter_changed`
- `_clear_type_filter`

#### 3. Event handling and selection

- `eventFilter`
- `_clear_selection`
- `_selected_jaw_ids`
- `selected_jaws_for_setup_assignment`
- `_on_multi_selection_changed`
- `_update_selection_count_label`
- `keyPressEvent`
- `select_jaw_by_id`
- `refresh_list`
- `on_current_item_changed`
- `on_item_double_clicked`

#### 4. Preview and detail composition

- `_clear_details`
- `_split_used_in_works`
- `_preview_model_key`
- `_set_preview_button_checked`
- `_load_preview_content`
- `_ensure_detached_preview_dialog`
- `_apply_detached_preview_default_bounds`
- `_update_detached_measurement_toggle_icon`
- `_on_detached_measurements_toggled`
- `_apply_detached_measurement_state`
- `_on_detached_preview_closed`
- `_close_detached_preview`
- `_sync_detached_preview`
- `toggle_preview_window`
- `_build_empty_details_card`
- `_build_jaw_detail_header`
- `_build_jaw_preview_card`
- `populate_details`
- `toggle_details`
- `show_details`
- `hide_details`

#### 5. CRUD and batch operations

- `_prompt_batch_cancel_behavior`
- `_batch_edit_jaws`
- `_group_edit_jaws`
- `_save_from_dialog`
- `add_jaw`
- `edit_jaw`
- `delete_jaw`
- `copy_jaw`
- `_prompt_text`

#### 6. Localization and display helpers

- `_t`
- `_localized_jaw_type`
- `_localized_spindle_side`
- `apply_localization`

### What Is Already Extracted

The current page already delegates useful behavior into `ui/jaw_page_support/`:

- `batch_actions.py`
- `detached_preview.py`
- `detail_layout_rules.py`
- `preview_rules.py`
- `selector_actions.py`
- `selector_slot_controller.py`
- `selector_widgets.py`

This is good news: Phase 5 is not a greenfield extraction. It is mostly a platform-conversion pass plus a few targeted builder extractions.

### Gaps Relative to Phase 4 Pattern

The current JawPage still differs from the Phase 4 pattern in four critical ways:

1. It does not inherit `CatalogPageBase`.
2. It owns its own list view, model, and refresh lifecycle.
3. Its delegate does not inherit `CatalogDelegate`.
4. Too much UI construction still sits inside the page file.

### Jaw-Specific Features That Must Survive Intact

These are the non-negotiables for Phase 5:

1. Multi-selection in the jaw catalog.
2. Drag payloads from jaw list to selector slots.
3. Selector slots with spindle compatibility validation.
4. Detached preview window with measurement overlays.
5. Preview transform persistence fields:
   - `preview_plane`
   - `preview_rot_x`
   - `preview_rot_y`
   - `preview_rot_z`
   - `preview_transform_mode`
   - `preview_fine_transform`
   - `preview_selected_part`
   - `preview_selected_parts`
6. View modes:
   - `all`
   - `main`
   - `sub`
   - `soft`
   - `hard_group`
7. Jaw type filter values:
   - `all`
   - `soft`
   - `hard_group`
   - `special`
8. CRUD:
   - add
   - edit
   - delete
   - copy
9. Batch edit and group edit flows.
10. Setup Manager assignment payload generation.

---

## Phase 5 Target Architecture

### Class Relationship

```text
CatalogPageBase
  └── JawPage
        ├── create_delegate()
        ├── get_item_service()
        ├── build_filter_pane()
        ├── apply_filters()
        ├── jaw_selected / jaw_deleted signals
        ├── selector integration
        ├── preview integration
        ├── CRUD and batch actions
        └── localization + display state

CatalogDelegate
  └── JawCatalogDelegate
        ├── _compute_size()
        ├── _paint_item_content()
        └── jaw-specific column logic
```

### Ownership Split

#### Platform layer owns

- search input lifecycle
- filter pane insertion into the layout
- list view creation
- model population
- selection persistence
- selection signal emission
- item delete signal emission

#### JawPage owns

- jaw-specific filters and nav modes
- current jaw state
- multi-select/batch logic
- detail panel visibility and content
- selector context
- detached preview synchronization
- jaw CRUD workflows
- localization updates

#### Support modules own

- jaw detail rendering
- top bar and bottom bar builders
- custom drag-capable list view
- detached preview behavior
- selector slot controller and widgets
- preview normalization and transform helpers

### Required New Signals

Phase 5 should add two domain-specific signals on `JawPage`:

```python
jaw_selected = Signal(str)
jaw_deleted = Signal(str)
```

Rationale:

- `CatalogPageBase` already emits `item_selected(str, int)` and `item_deleted(str)`.
- JAWS do not currently expose a `uid` in the same way TOOLS do.
- existing and future jaw-specific listeners should not need to understand generic platform signal semantics.
- `JawPage` will consume base signals internally and fan out jaw-specific signals.

Signal flow:

```text
user clicks jaw row
  -> CatalogPageBase._on_list_item_clicked()
  -> item_selected(item_id, uid)
  -> JawPage._on_item_selected_internal()
  -> current_jaw_id update
  -> detail/preview sync
  -> jaw_selected(jaw_id)

user deletes jaw
  -> JawPage.delete_jaw()
  -> jaw_service.delete_jaw(jaw_id)
  -> item_deleted(jaw_id)
  -> JawPage._on_item_deleted_internal()
  -> detail/preview cleanup
  -> jaw_deleted(jaw_id)
```

### Target File Layout After Phase 5

```text
ui/
  jaw_page.py                     ~400-450L
  jaw_catalog_delegate.py         ~180-220L
  jaw_page_support/
    __init__.py
    batch_actions.py              existing
    bottom_bars_builder.py        new
    catalog_list_widgets.py       new
    detail_layout_rules.py        existing
    detail_panel_builder.py       new
    detached_preview.py           existing, extended
    preview_rules.py              existing, extended
    selector_actions.py           existing
    selector_slot_controller.py   existing
    selector_widgets.py           existing
    topbar_builder.py             new
```

---

## New JawPage Implementation (Complete)

### Design Notes

This target implementation intentionally mirrors the current `HomePage` structure after Phase 4:

- services stored before `super().__init__()`
- abstract methods implemented early
- base signals connected in `__init__()`
- page methods limited to orchestration and domain logic
- all bulky UI builders delegated out

### Complete Target Source

```python
"""Jaw catalog page refactored onto CatalogPageBase (Phase 5)."""

from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QMessageBox,
    QWidget,
)

from shared.ui.platforms.catalog_page_base import CatalogPageBase
from ui.jaw_catalog_delegate import JawCatalogDelegate
from ui.jaw_editor_dialog import AddEditJawDialog
from ui.jaw_page_support import (
    SelectorSlotController,
    batch_edit_jaws,
    close_detached_preview,
    ensure_detached_preview_dialog,
    group_edit_jaws,
    load_preview_content,
    on_detached_measurements_toggled,
    on_detached_preview_closed,
    on_selector_cancel,
    on_selector_done,
    prompt_batch_cancel_behavior,
    set_preview_button_checked,
    sync_detached_preview,
    toggle_preview_window,
    update_detached_measurement_toggle_icon,
)
from ui.jaw_page_support.bottom_bars_builder import build_bottom_bars
from ui.jaw_page_support.catalog_list_widgets import JawCatalogListView
from ui.jaw_page_support.detail_panel_builder import populate_detail_panel
from ui.jaw_page_support.preview_rules import (
    jaw_preview_has_model_payload,
    jaw_preview_label,
    jaw_preview_measurement_overlays,
)
from ui.jaw_page_support.topbar_builder import build_filter_toolbar
from ui.selector_ui_helpers import normalize_selector_spindle, selector_spindle_label

__all__ = ["JawPage"]


class JawPage(CatalogPageBase):
    """
    JAWS catalog page using the shared catalog platform.

    Preserves jaw-specific behavior:
    - selector slots for setup assignment
    - detached 3D preview
    - jaw-type and spindle filtering
    - preview plane and rotation restore
    - CRUD and batch operations
    """

    jaw_selected = Signal(str)
    jaw_deleted = Signal(str)

    NAV_MODES = [
        ("all", "all"),
        ("main", "main"),
        ("sub", "sub"),
        ("soft", "soft"),
        ("hard_group", "hard_group"),
    ]

    def __init__(
        self,
        jaw_service,
        parent: QWidget | None = None,
        show_sidebar: bool = True,
        translate: Callable[[str, str | None], str] | None = None,
    ) -> None:
        self.jaw_service = jaw_service
        self.show_sidebar = bool(show_sidebar)
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or "")

        self.current_jaw_id: str | None = None
        self.current_view_mode = "all"

        self._details_hidden = True
        self._last_splitter_sizes: list[int] | None = None

        self._module_switch_callback = None
        self._master_filter_ids: set[str] = set()
        self._master_filter_active = False

        self._type_filter_values = ["all", "soft", "hard_group", "special"]
        self._spindle_filter_value = "all"

        self._selector_active = False
        self._selector_spindle = ""
        self._selector_panel_mode = "details"
        self._selector_assignments: dict[str, dict | None] = {"main": None, "sub": None}
        self._selector_selected_slots: set[str] = set()
        self._selector_saved_details_hidden = True
        self._selector_slot_controller = SelectorSlotController(self)

        self._detail_preview_widget = None
        self._detail_preview_model_key = None
        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._detached_preview_last_model_key = None
        self._detached_measurements_enabled = True
        self._measurement_toggle_btn = None
        self._close_preview_shortcut = None

        super().__init__(parent=parent, item_service=jaw_service, translate=self._translate)

        self.item_selected.connect(self._on_item_selected_internal)
        self.item_deleted.connect(self._on_item_deleted_internal)

        self._build_jaw_scaffold()
        self.refresh_list()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _localized_jaw_type(self, raw_type: str) -> str:
        normalized = (raw_type or "").strip().lower().replace(" ", "_")
        return self._t(f"jaw_library.jaw_type.{normalized}", raw_type)

    def _localized_spindle_side(self, raw_side: str) -> str:
        normalized = (raw_side or "").strip().lower().replace(" ", "_")
        return self._t(f"jaw_library.spindle_side.{normalized}", raw_side)

    # -----------------------------------------------------------------
    # CatalogPageBase contract
    # -----------------------------------------------------------------

    def create_delegate(self) -> QAbstractItemView:
        return JawCatalogDelegate(parent=self.list_view, translate=self._t)

    def get_item_service(self) -> Any:
        return self.jaw_service

    def build_filter_pane(self) -> QWidget:
        self.filter_toolbar = build_filter_toolbar(self)
        return self.filter_toolbar

    def apply_filters(self, filters: dict) -> list[dict]:
        search_text = str(filters.get("search") or "").strip()
        view_mode = str(filters.get("view_mode") or self.current_view_mode or "all").strip().lower()
        jaw_type = str(filters.get("jaw_type") or "all").strip().lower()
        spindle_filter = str(filters.get("spindle_filter") or "all").strip().lower()

        jaws = self.jaw_service.list_jaws(
            search_text=search_text,
            view_mode=view_mode,
            jaw_type_filter=jaw_type,
        )

        if spindle_filter != "all":
            jaws = [jaw for jaw in jaws if self._jaw_matches_spindle_filter(jaw, spindle_filter)]

        if self._selector_active:
            jaws = [jaw for jaw in jaws if self._jaw_matches_selector_spindle(jaw)]

        if self._master_filter_active:
            jaws = [
                jaw for jaw in jaws
                if str(jaw.get("jaw_id") or "").strip() in self._master_filter_ids
            ]

        return [self._catalog_item_dict(jaw) for jaw in jaws]

    # -----------------------------------------------------------------
    # Post-base UI assembly
    # -----------------------------------------------------------------

    def _build_jaw_scaffold(self) -> None:
        self.list_view.deleteLater()
        self.list_view = JawCatalogListView(self)
        self.list_view.setItemDelegate(self.create_delegate())
        self.list_view.clicked.connect(self._on_list_item_clicked)
        self.list_view.doubleClicked.connect(self._on_item_double_clicked)
        self.list_view.selectionModel().selectionChanged.connect(self._on_multi_selection_changed)
        self.layout().replaceWidget(self.layout().itemAt(2).widget(), self.list_view)

        build_bottom_bars(self)

        self.detail_container.hide()
        self.detail_header_container.hide()
        self.populate_details(None)

    # -----------------------------------------------------------------
    # Catalog model helpers
    # -----------------------------------------------------------------

    def _catalog_item_dict(self, jaw: dict) -> dict:
        jaw_id = str(jaw.get("jaw_id") or "").strip()
        return {
            "id": jaw_id,
            "uid": 0,
            "jaw_id": jaw_id,
            "jaw_type": jaw.get("jaw_type", ""),
            "spindle_side": jaw.get("spindle_side", ""),
            "clamping_diameter_text": jaw.get("clamping_diameter_text", ""),
            "clamping_length": jaw.get("clamping_length", ""),
            "notes": jaw.get("notes", ""),
            "used_in_work": jaw.get("used_in_work", ""),
            "turning_washer": jaw.get("turning_washer", ""),
            "preview_plane": jaw.get("preview_plane", "XZ"),
            "preview_rot_x": jaw.get("preview_rot_x", 0),
            "preview_rot_y": jaw.get("preview_rot_y", 0),
            "preview_rot_z": jaw.get("preview_rot_z", 0),
            "measurement_overlays": jaw.get("measurement_overlays", []),
            "stl_path": jaw.get("stl_path", ""),
            "_raw": jaw,
        }

    def _jaw_matches_spindle_filter(self, jaw: dict, spindle_filter: str) -> bool:
        side = str(jaw.get("spindle_side") or "").strip().lower()
        if spindle_filter == "main":
            return "main" in side or "both" in side or "paa" in side or "molem" in side
        if spindle_filter == "sub":
            return "sub" in side or "both" in side or "vasta" in side or "molem" in side
        return True

    def _jaw_matches_selector_spindle(self, jaw: dict) -> bool:
        if not self._selector_active:
            return True
        return self._selector_slot_controller.jaw_supports_selector_slot(jaw, self._selector_spindle)

    # -----------------------------------------------------------------
    # Signals from CatalogPageBase
    # -----------------------------------------------------------------

    def _on_item_selected_internal(self, item_id: str, _uid: int) -> None:
        self.current_jaw_id = str(item_id or "").strip() or None
        self._update_selection_count_label()

        if not self._details_hidden:
            self.populate_details(self._get_selected_jaw())

        self._sync_detached_preview(show_errors=False)

        if self.current_jaw_id:
            self.jaw_selected.emit(self.current_jaw_id)

    def _on_item_deleted_internal(self, jaw_id: str) -> None:
        if self.current_jaw_id == jaw_id:
            self.current_jaw_id = None
            self.populate_details(None)
        self._sync_detached_preview(show_errors=False)
        self.jaw_deleted.emit(jaw_id)

    def _on_item_double_clicked(self, index: QModelIndex) -> None:
        self.current_jaw_id = str(index.data(Qt.UserRole) or "").strip() or None
        if not self.current_jaw_id:
            return
        if self._details_hidden:
            self.populate_details(self._get_selected_jaw())
            self.show_details()
        else:
            self.hide_details()

    # -----------------------------------------------------------------
    # Selection and batch helpers
    # -----------------------------------------------------------------

    def _get_selected_jaw(self) -> dict | None:
        if not self.current_jaw_id:
            return None
        return self.jaw_service.get_jaw(self.current_jaw_id)

    def _selected_jaw_ids(self) -> list[str]:
        selection_model = self.list_view.selectionModel()
        if selection_model is None:
            return []
        jaw_ids: list[str] = []
        for index in selection_model.selectedIndexes():
            jaw_id = str(index.data(Qt.UserRole) or "").strip()
            if jaw_id and jaw_id not in jaw_ids:
                jaw_ids.append(jaw_id)
        return jaw_ids

    def selected_jaws_for_setup_assignment(self) -> list[dict]:
        payload: list[dict] = []
        for jaw_id in self._selected_jaw_ids():
            jaw = self.jaw_service.get_jaw(jaw_id)
            if jaw:
                payload.append({
                    "jaw_id": jaw_id,
                    "jaw_type": str(jaw.get("jaw_type") or "").strip(),
                })
        return payload

    def _on_multi_selection_changed(self, *_args) -> None:
        self._update_selection_count_label()

    def _update_selection_count_label(self) -> None:
        count = len(self._selected_jaw_ids())
        if count > 1:
            self.selection_count_label.setText(
                self._t("jaw_library.selection.count", "{count} selected", count=count)
            )
            self.selection_count_label.show()
            return
        self.selection_count_label.hide()

    def _prompt_batch_cancel_behavior(self) -> str:
        return prompt_batch_cancel_behavior(self)

    def _batch_edit_jaws(self, jaw_ids: list[str]) -> None:
        batch_edit_jaws(self, jaw_ids)

    def _group_edit_jaws(self, jaw_ids: list[str]) -> None:
        group_edit_jaws(self, jaw_ids)

    # -----------------------------------------------------------------
    # Detail and preview
    # -----------------------------------------------------------------

    def populate_details(self, jaw: dict | None) -> None:
        populate_detail_panel(self, jaw)

    def show_details(self) -> None:
        if self._selector_active:
            self._selector_slot_controller.set_selector_panel_mode("details")
            return
        self._details_hidden = False
        self.detail_container.show()
        self.detail_header_container.show()
        if not self._last_splitter_sizes:
            total = max(600, self.splitter.width())
            self._last_splitter_sizes = [int(total * 0.62), int(total * 0.38)]
        self.splitter.setSizes(self._last_splitter_sizes)
        self.list_view.viewport().update()

    def hide_details(self) -> None:
        if self._selector_active:
            self._selector_slot_controller.set_selector_panel_mode("selector")
            return
        self._details_hidden = True
        if self.detail_container.isVisible():
            self._last_splitter_sizes = self.splitter.sizes()
        self.detail_container.hide()
        self.detail_header_container.hide()
        self.splitter.setSizes([1, 0])
        self.list_view.viewport().update()

    def toggle_details(self) -> None:
        if self._details_hidden:
            jaw = self._get_selected_jaw()
            if jaw is None:
                QMessageBox.information(
                    self,
                    self._t("jaw_library.message.show_details", "Show details"),
                    self._t("jaw_library.message.select_jaw_first", "Select a jaw first."),
                )
                return
            self.populate_details(jaw)
            self.show_details()
            return
        self.hide_details()

    def _preview_model_key(self, jaw: dict | None):
        if not isinstance(jaw, dict):
            return None
        jaw_id = str(jaw.get("jaw_id") or "").strip()
        stl_path = jaw.get("stl_path")
        overlays = jaw.get("measurement_overlays", [])
        return (
            jaw_id,
            json.dumps(stl_path, ensure_ascii=False, sort_keys=True, default=str),
            json.dumps(overlays, ensure_ascii=False, sort_keys=True, default=str),
            jaw.get("preview_plane", "XZ"),
            int(jaw.get("preview_rot_x", 0) or 0),
            int(jaw.get("preview_rot_y", 0) or 0),
            int(jaw.get("preview_rot_z", 0) or 0),
            str(jaw.get("preview_transform_mode") or "translate"),
            bool(jaw.get("preview_fine_transform", False)),
        )

    def _load_preview_content(self, viewer, jaw: dict, *, label: str | None = None) -> bool:
        return load_preview_content(self, viewer, jaw, label=label)

    def _ensure_detached_preview_dialog(self) -> None:
        ensure_detached_preview_dialog(self)

    def _update_detached_measurement_toggle_icon(self, enabled: bool) -> None:
        update_detached_measurement_toggle_icon(self, enabled)

    def _on_detached_measurements_toggled(self, checked: bool) -> None:
        on_detached_measurements_toggled(self, checked)

    def _on_detached_preview_closed(self, result) -> None:
        on_detached_preview_closed(self, result)

    def _sync_detached_preview(self, show_errors: bool = False) -> bool:
        return sync_detached_preview(self, show_errors)

    def toggle_preview_window(self) -> None:
        toggle_preview_window(self)

    # -----------------------------------------------------------------
    # Selector and module integration
    # -----------------------------------------------------------------

    def set_module_switch_handler(self, callback) -> None:
        self._module_switch_callback = callback

    def set_module_switch_target(self, target: str) -> None:
        target_text = (target or "").strip().upper() or "TOOLS"
        display = (
            self._t("tool_library.module.tools", "TOOLS")
            if target_text == "TOOLS"
            else self._t("tool_library.module.jaws", "JAWS")
        )
        self.module_toggle_btn.setText(display)

    def set_master_filter(self, jaw_ids, active: bool) -> None:
        self._master_filter_ids = {str(j).strip() for j in (jaw_ids or []) if str(j).strip()}
        self._master_filter_active = bool(active) and bool(self._master_filter_ids)
        self.refresh_list()

    def set_selector_context(
        self,
        active: bool,
        spindle: str = "",
        initial_assignments: list[dict] | None = None,
    ) -> None:
        self._selector_slot_controller.set_selector_context(
            active,
            spindle=spindle,
            initial_assignments=initial_assignments,
        )
        self.refresh_list()

    def selector_assigned_jaws_for_setup_assignment(self) -> list[dict]:
        return self._selector_slot_controller.selector_assigned_jaws_for_setup_assignment()

    # -----------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------

    def _save_from_dialog(self, dlg, original_jaw_id: str | None = None) -> None:
        data = dlg.get_jaw_data()
        self.jaw_service.save_jaw(data)
        new_jaw_id = str(data["jaw_id"]).strip()
        if original_jaw_id and original_jaw_id != new_jaw_id:
            self.jaw_service.delete_jaw(original_jaw_id)
        self.current_jaw_id = new_jaw_id
        self.refresh_list()
        self.populate_details(self.jaw_service.get_jaw(new_jaw_id))

    def add_jaw(self) -> None:
        dlg = AddEditJawDialog(self, translate=self._t)
        if dlg.exec() == QDialog.Accepted:
            self._save_from_dialog(dlg)

    def edit_jaw(self) -> None:
        selected_ids = self._selected_jaw_ids()
        if not selected_ids:
            QMessageBox.information(
                self,
                self._t("jaw_library.action.edit_jaw", "Edit jaw"),
                self._t("jaw_library.message.select_jaw_first", "Select a jaw first."),
            )
            return
        if len(selected_ids) > 1:
            mode = self._prompt_batch_cancel_behavior()
            if mode == "batch":
                self._batch_edit_jaws(selected_ids)
            elif mode == "group":
                self._group_edit_jaws(selected_ids)
            return
        jaw = self.jaw_service.get_jaw(selected_ids[0])
        dlg = AddEditJawDialog(self, jaw=jaw, translate=self._t)
        if dlg.exec() == QDialog.Accepted:
            self._save_from_dialog(dlg, original_jaw_id=str(jaw.get("jaw_id") or ""))

    def delete_jaw(self) -> None:
        jaw = self._get_selected_jaw()
        if jaw is None:
            QMessageBox.information(
                self,
                self._t("jaw_library.action.delete_jaw", "Delete jaw"),
                self._t("jaw_library.message.select_jaw_first", "Select a jaw first."),
            )
            return
        jaw_id = str(jaw.get("jaw_id") or "").strip()
        if QMessageBox.question(
            self,
            self._t("jaw_library.action.delete_jaw", "Delete jaw"),
            self._t("jaw_library.message.delete_jaw_prompt", "Delete jaw {jaw_id}?", jaw_id=jaw_id),
        ) != QMessageBox.Yes:
            return
        self.jaw_service.delete_jaw(jaw_id)
        self.item_deleted.emit(jaw_id)
        self.current_jaw_id = None
        self.refresh_list()

    def copy_jaw(self) -> None:
        jaw = self._get_selected_jaw()
        if jaw is None:
            QMessageBox.information(
                self,
                self._t("jaw_library.action.copy_jaw", "Copy jaw"),
                self._t("jaw_library.message.select_jaw_first", "Select a jaw first."),
            )
            return
        copied = dict(jaw)
        copied["jaw_id"] = ""
        dlg = AddEditJawDialog(self, jaw=copied, translate=self._t)
        if dlg.exec() == QDialog.Accepted:
            self._save_from_dialog(dlg)

    # -----------------------------------------------------------------
    # Compatibility and convenience wrappers
    # -----------------------------------------------------------------

    def refresh_list(self) -> None:
        self.refresh_catalog()
        self._sync_detached_preview(show_errors=False)

    def select_jaw_by_id(self, jaw_id: str) -> None:
        self.current_jaw_id = str(jaw_id or "").strip() or None
        self.refresh_list()

    def apply_localization(self, translate: Callable[[str, str | None], str] | None = None) -> None:
        if translate is not None:
            self._translate = translate
        if hasattr(self.list_view.itemDelegate(), "set_translate"):
            self.list_view.itemDelegate().set_translate(self._t)
        self.filter_toolbar.retranslate_ui()
        self.selector_card.retranslate_ui()
        self.button_bar.retranslate_ui()
        self.refresh_list()
        self.populate_details(self._get_selected_jaw())
```

### Why This Shape Is Correct

This target page is intentionally smaller because it removes four categories of duplicate code from `jaw_page.py`:

1. explicit model creation and row population
2. manual search input lifecycle
3. list click handling for initial selection state
4. repeated filter-pane scaffolding logic

The page still owns the jaw-specific parts that should remain local:

- selector slot workflows
- preview synchronization
- CRUD and batch actions
- localization and display labels

### Target JawPage Size Breakdown

| Section | Approx lines |
|--------|--------------|
| imports and constants | 35 |
| class docstring and signals | 15 |
| `__init__` and state | 85 |
| 4 abstract methods | 35 |
| catalog helpers | 35 |
| signal handlers | 30 |
| selection helpers | 35 |
| detail and preview wrappers | 60 |
| selector/module wrappers | 35 |
| CRUD | 55 |
| localization and compatibility wrappers | 25 |
| total | ~445 |

That lands within the requested 400-450L range without stripping out valid jaw-specific orchestration.

---

## New JawCatalogDelegate Implementation (Complete)

### Why the Delegate Must Change

Current `JawCatalogDelegate` already paints deterministic rows, but it bypasses the Phase 3 platform abstraction. Phase 5 should align it with the `CatalogDelegate` contract so the JAWS domain matches TOOLS structurally.

Benefits:

1. shared card drawing rules live in one platform class
2. JAWS only provides content and sizing
3. future domains inherit the same paint architecture
4. visual state logic stays consistent across pages

### Complete Target Source

```python
"""Jaw catalog delegate implemented on the platform CatalogDelegate."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

from config import TOOL_ICONS_DIR
from shared.ui.platforms.catalog_delegate import CatalogDelegate

__all__ = ["JawCatalogDelegate", "jaw_icon_for_row"]


ICON_SIZE = 48
ICON_SLOT_W = 52
COL_SPACING = 10
BP_FULL = 620
BP_REDUCED = 390
BP_NAME_ONLY = 180

CLR_HEADER_TEXT = QColor("#2b3136")
CLR_VALUE_TEXT = QColor("#171a1d")

_ICON_OBJECT_CACHE: dict[str, QIcon] = {}


def _header_font() -> QFont:
    font = QFont()
    font.setPointSizeF(9.0)
    font.setWeight(QFont.DemiBold)
    return font


def _value_font(pt: float) -> QFont:
    font = QFont()
    font.setPointSizeF(pt)
    font.setWeight(QFont.DemiBold)
    return font


def jaw_icon_for_row(jaw: dict) -> QIcon:
    spindle_side = str(jaw.get("spindle_side") or "").strip().lower()
    filename = "jaw_sub.png" if ("sub" in spindle_side or "vasta" in spindle_side or "ala" in spindle_side) else "jaw_main.png"
    path = TOOL_ICONS_DIR / filename
    if not path.exists():
        fallback = TOOL_ICONS_DIR / "jaw_icon.png"
        path = fallback if fallback.exists() else path
    if not path.exists():
        return QIcon()
    cache_key = str(path).lower()
    if cache_key not in _ICON_OBJECT_CACHE:
        _ICON_OBJECT_CACHE[cache_key] = QIcon(str(path))
    return _ICON_OBJECT_CACHE[cache_key]


class JawCatalogDelegate(CatalogDelegate):
    ROW_HEIGHT = 74
    CARD_MARGIN_H = 6
    CARD_MARGIN_V = 2
    CARD_PADDING_H = 10
    CARD_PADDING_V = 1
    CARD_RADIUS = 8
    BORDER_INSET = 3

    CLR_CARD_BG = QColor("#ffffff")
    CLR_CARD_HOVER = QColor("#f7fbff")
    CLR_CARD_BORDER = QColor("#3e4a56")
    CLR_CARD_SELECTED_BORDER = QColor("#42a5f5")

    def __init__(self, parent=None, translate: Callable | None = None):
        super().__init__(parent)
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or "")
        self._header_font = _header_font()
        self._value_font_full = _value_font(13.4)
        self._value_font_narrow = _value_font(12.4)
        self._value_font_tight = _value_font(11.4)
        self._value_font_tiny = _value_font(10.4)

    def set_translate(self, translate: Callable) -> None:
        self._translate = translate

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _compute_size(self, option: QStyleOptionViewItem, item_dict: dict) -> QSize:
        width = option.rect.width() if option.rect.width() > 0 else 600
        return QSize(width, self.ROW_HEIGHT + self.CARD_MARGIN_V * 2)

    def _paint_item_content(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        item_dict: dict,
    ) -> None:
        full = option.rect
        card = QRect(
            full.x() + self.CARD_MARGIN_H,
            full.y() + self.CARD_MARGIN_V,
            full.width() - self.CARD_MARGIN_H * 2,
            self.ROW_HEIGHT,
        )
        content = card.adjusted(
            self.CARD_PADDING_H + self.BORDER_INSET,
            self.CARD_PADDING_V + self.BORDER_INSET,
            -(self.CARD_PADDING_H + self.BORDER_INSET),
            -(self.CARD_PADDING_V + self.BORDER_INSET),
        )

        jaw = item_dict.get("_raw", item_dict)
        card_width = card.width()
        if card_width >= BP_FULL:
            stage = "full"
        elif card_width >= BP_REDUCED:
            stage = "reduced"
        elif card_width >= BP_NAME_ONLY:
            stage = "name-only"
        else:
            stage = "icon-only"

        icon_rect = QRect(content.x(), content.y() + (content.height() - ICON_SIZE) // 2, ICON_SLOT_W, ICON_SIZE)
        icon = jaw_icon_for_row(jaw)
        pixmap = icon.pixmap(QSize(ICON_SIZE, ICON_SIZE)) if not icon.isNull() else QPixmap()
        if not pixmap.isNull():
            px = icon_rect.x() + (ICON_SLOT_W - pixmap.width()) // 2
            py = icon_rect.y() + (ICON_SIZE - pixmap.height()) // 2
            painter.drawPixmap(px, py, pixmap)

        if stage == "icon-only":
            return

        text_rect = QRect(
            icon_rect.right() + COL_SPACING,
            content.y(),
            max(40, content.right() - (icon_rect.right() + COL_SPACING)),
            content.height(),
        )

        columns = self._columns(jaw, stage)
        if stage == "name-only":
            value_font = self._value_font_narrow if card_width >= 300 else self._value_font_tight
        elif stage == "reduced":
            value_font = self._value_font_full
        elif card_width < 500:
            value_font = self._value_font_tight
        elif card_width < 620:
            value_font = self._value_font_narrow
        else:
            value_font = self._value_font_full

        painter.setPen(QPen(CLR_HEADER_TEXT))
        header_metrics = QFontMetrics(self._header_font)
        value_metrics = QFontMetrics(value_font)

        total_weight = sum(weight for _key, _header, _value, weight in columns)
        x = text_rect.x()
        for index, (_key, header, value, weight) in enumerate(columns):
            remaining = text_rect.right() - x
            column_width = remaining if index == len(columns) - 1 else max(80, int(text_rect.width() * (weight / total_weight)))
            column_rect = QRect(x, text_rect.y(), column_width, text_rect.height())

            painter.setFont(self._header_font)
            painter.setPen(QPen(CLR_HEADER_TEXT))
            painter.drawText(
                QRect(column_rect.x(), column_rect.y() + 6, column_rect.width(), 18),
                Qt.AlignLeft | Qt.AlignTop,
                header,
            )

            painter.setFont(value_font)
            painter.setPen(QPen(CLR_VALUE_TEXT))
            painter.drawText(
                QRect(column_rect.x(), column_rect.y() + 26, column_rect.width(), 28),
                Qt.AlignLeft | Qt.AlignVCenter,
                self._elide(value_metrics, value, column_rect.width()),
            )

            x += column_width + COL_SPACING

        self._paint_badges(painter, text_rect, jaw, option)

    def _columns(self, jaw: dict, stage: str) -> list[tuple[str, str, str, int]]:
        dash = "-"
        jaw_type = self._t(
            f"jaw_library.jaw_type.{(jaw.get('jaw_type') or '').strip().lower().replace(' ', '_')}",
            jaw.get("jaw_type", ""),
        )
        spindle = self._t(
            f"jaw_library.spindle_side.{(jaw.get('spindle_side') or '').strip().lower().replace(' ', '_')}",
            jaw.get("spindle_side", ""),
        )
        all_columns = [
            ("jaw_id", self._t("jaw_library.row.jaw_id", "Jaw ID"), str(jaw.get("jaw_id") or dash), 180),
            ("jaw_type", self._t("jaw_library.row.jaw_type", "Jaw type"), jaw_type or dash, 190),
            ("spindle", self._t("jaw_library.row.spindle", "Spindle"), spindle or dash, 170),
            (
                "diameter",
                self._t("jaw_library.row.clamping_diameter_multiline", "Clamping diameter"),
                str(jaw.get("clamping_diameter_text") or dash),
                170,
            ),
        ]
        if stage == "name-only":
            return [all_columns[0]]
        if stage == "reduced":
            return all_columns[:2]
        return all_columns

    def _paint_badges(self, painter: QPainter, text_rect: QRect, jaw: dict, option: QStyleOptionViewItem) -> None:
        badge_text = self._t(
            f"jaw_library.jaw_type.{(jaw.get('jaw_type') or '').strip().lower().replace(' ', '_')}",
            jaw.get("jaw_type", ""),
        )
        if not badge_text:
            return
        badge_rect = QRect(text_rect.right() - 120, text_rect.y() + 6, 110, 22)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#dfeef9") if not (option.state & QStyle.State_Selected) else QColor("#c5e0f4"))
        painter.drawRoundedRect(badge_rect, 11, 11)
        badge_font = QFont(self._header_font)
        badge_font.setPointSizeF(8.5)
        painter.setFont(badge_font)
        painter.setPen(QPen(QColor("#204864")))
        painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

    @staticmethod
    def _elide(metrics: QFontMetrics, text: str, width: int) -> str:
        return metrics.elidedText(str(text or ""), Qt.ElideRight, max(10, width - 4))
```

### Delegate Responsibilities

The Phase 5 delegate must paint these jaw-specific elements:

1. spindle-aware icon
2. jaw ID as primary label
3. jaw type badge
4. spindle text
5. clamping diameter summary

This is enough information density for the list while keeping the detail panel responsible for the long-form data.

### Why Not Keep the Old Delegate Unchanged

That would leave the JAWS domain structurally out of sync with the platform layer. The whole point of Phase 5 is to finish the migration model that Phase 4 started.

---

## Filter Pane and apply_filters Design

### Filter Requirements

JawPage needs four filter inputs available to `apply_filters()`:

1. search text
2. view mode
3. jaw type
4. spindle orientation

### Proposed Filter Pane Contract

The `build_filter_pane()` return widget should expose:

```python
frame.get_filters = lambda: {
    "view_mode": self.current_view_mode,
    "jaw_type": self.jaw_type_filter.currentData() or "all",
    "spindle_filter": self.spindle_filter.currentData() or "all",
}
```

### Why Separate `view_mode` and `spindle_filter`

Current service behavior already understands:

- `view_mode='main'`
- `view_mode='sub'`
- `view_mode='soft'`
- `view_mode='hard_group'`

But the task explicitly calls for jaw-specific `apply_filters()` including jaw type and spindle orientation.

That means the Phase 5 page should support both:

- the existing sidebar-driven mode filter
- a top-bar spindle filter for explicit spindle orientation

This is not redundant because:

- sidebar modes are broad navigation presets
- spindle filter is an orthogonal top filter usable with `all` and jaw type filters

### Proposed UI

Toolbar contents, left to right:

1. search toggle button
2. detail toggle button
3. search field when active
4. filter reset button
5. jaw type combo
6. spindle combo
7. detached preview button
8. detail header container on the far right

### Target Filter Values

#### Jaw type combo

- `all`
- `soft`
- `hard_group`
- `special`

#### Spindle combo

- `all`
- `main`
- `sub`

### `apply_filters()` Processing Order

Recommended order:

1. query service using `search_text`, `view_mode`, and `jaw_type_filter`
2. apply spindle filter in Python
3. apply selector spindle compatibility constraint
4. apply master filter IDs
5. normalize into `CatalogPageBase` item dicts

This preserves current DB query behavior while adding the new spindle filter without changing service API semantics.

### Why Not Expand the Service First

Because Phase 5 is a UI architecture migration, not a service redesign. Introducing a new service query signature would enlarge the blast radius and obscure regressions.

The minimal-risk approach is:

- keep `JawService.list_jaws()` signature unchanged
- add the extra spindle constraint in `JawPage.apply_filters()`

---

## Preview Plane and Rotation Preservation

### Current Persisted Fields

`JawService.save_jaw()` already persists these preview-specific values:

- `preview_plane`
- `preview_rot_x`
- `preview_rot_y`
- `preview_rot_z`
- `measurement_overlays`
- `preview_selected_part`
- `preview_selected_parts`
- `preview_transform_mode`
- `preview_fine_transform`

That means the persistence layer is already correct. Phase 5 only needs to preserve UI restore behavior.

### Current Gap

`ui/jaw_page_support/detached_preview.py` currently resets the preview with:

- `viewer.set_alignment_plane('XZ')`
- `viewer.reset_model_rotation()`

That is safe for generic preview initialization, but it is not enough for a design that explicitly promises preview plane and rotation parity.

### Required Phase 5 Extension

Extend `ui/jaw_page_support/preview_rules.py` with three new helpers:

```python
def jaw_preview_plane(jaw: dict) -> str:
    return str(jaw.get("preview_plane") or "XZ").strip().upper() or "XZ"

def jaw_preview_rotation(jaw: dict) -> tuple[int, int, int]:
    return (
        int(jaw.get("preview_rot_x", 0) or 0),
        int(jaw.get("preview_rot_y", 0) or 0),
        int(jaw.get("preview_rot_z", 0) or 0),
    )

def apply_jaw_preview_transform(viewer, jaw: dict) -> None:
    plane = jaw_preview_plane(jaw)
    rot_x, rot_y, rot_z = jaw_preview_rotation(jaw)
    viewer.set_alignment_plane(plane)
    viewer.set_model_rotation(rot_x, rot_y, rot_z)
```

If `StlPreviewWidget` lacks `set_model_rotation()`, then Phase 5 must use the widget’s existing equivalent transform API. The design point does not change: do not drop persisted rotation data during the refactor.

### Where Transform Restoration Runs

#### Inline preview

In `detail_panel_builder.populate_detail_panel()` after loading the model:

```python
loaded = load_preview_content(page, viewer, jaw, label=jaw_preview_label(jaw, page._t))
if loaded:
    apply_jaw_preview_transform(viewer, jaw)
    viewer.set_measurement_overlays(jaw_preview_measurement_overlays(jaw))
```

#### Detached preview

In `jaw_page_support.detached_preview.sync_detached_preview()` after successful load:

```python
apply_jaw_preview_transform(page._detached_preview_widget, jaw)
apply_detached_measurement_state(page, jaw)
```

### Model Key Must Include Transform State

The page’s `_preview_model_key()` must include not only model payload and overlays but also:

- `preview_plane`
- `preview_rot_x`
- `preview_rot_y`
- `preview_rot_z`
- `preview_transform_mode`
- `preview_fine_transform`

Without that, the detached preview cache may incorrectly skip refreshes when the selected jaw’s transform changes but the STL payload does not.

### Parity Requirement for Preview

Phase 5 is not allowed to simplify preview parity to “the model opens.”

Required parity is stricter:

1. correct model loads
2. correct plane restores
3. correct rotation restores
4. measurement overlays restore
5. selected part state remains stable
6. detached viewer shows the same logical orientation as the inline viewer

---

## CRUD, Batch Operations, and Signal Strategy

### CRUD Preservation Rules

#### Add

Must still open `AddEditJawDialog` in create mode and refresh the list after successful save.

#### Edit

Must still support:

- single selection -> edit dialog
- multi-selection -> prompt for batch or group edit

#### Delete

Must still:

- confirm deletion
- remove the row from DB
- refresh the page
- clear detail state if the current jaw was deleted
- emit both `item_deleted` and `jaw_deleted`

#### Copy

Target behavior should shift slightly closer to the tool flow used in Phase 4:

- instead of a raw prompt-only copy path, prefer reopening `AddEditJawDialog` with blank `jaw_id`
- this reduces divergent patterns between TOOLS and JAWS

If UX parity requires preserving the current prompt-based workflow exactly, keep the prompt-based path for Phase 5 and defer dialog unification to a later pass.

### Batch Operations

Batch operations stay outside the platform base. They are jaw-domain behaviors and should remain as wrappers into `ui/jaw_page_support/batch_actions.py`.

Required wrappers in `JawPage`:

- `_prompt_batch_cancel_behavior()`
- `_batch_edit_jaws()`
- `_group_edit_jaws()`

### Signal Mapping Table

| Event | Base signal | JawPage action | Domain signal |
|------|-------------|----------------|---------------|
| row click | `item_selected(id, uid)` | update `current_jaw_id`, detail sync, preview sync | `jaw_selected(jaw_id)` |
| row deletion | `item_deleted(id)` | clear detail if needed, preview cleanup | `jaw_deleted(jaw_id)` |

### Why Keep Domain Signals

`CatalogPageBase` gives the app a shared protocol. `JawPage` still benefits from exposing jaw-specific intent. That is a better boundary for external listeners than forcing them to subscribe to generic item semantics.

---

## Extraction Targets

### Extraction Goal

The page file should end up as orchestration only. Any bulky builder or widget implementation must move out.

### 1. `ui/jaw_page_support/catalog_list_widgets.py` (new)

Move:

- `_JawCatalogListView`

Target contents:

- `JawCatalogListView(QListView)`
- drag payload generation for selector MIME
- selection fallback for drag start
- ghost card pixmap creation

Why extract:

- custom drag list view is a reusable widget, not page orchestration
- makes `jaw_page.py` smaller immediately
- mirrors `home_page_support/catalog_list_widgets.py`

### 2. `ui/jaw_page_support/topbar_builder.py` (new)

Move:

- `_build_top_filter_frame`
- `_rebuild_filter_row`
- combo population helpers tied directly to toolbar widgets

Recommended exports:

- `build_filter_toolbar(page) -> QFrame`
- `retranslate_filter_toolbar(page) -> None`
- `populate_jaw_type_filter(page) -> None`
- `populate_spindle_filter(page) -> None`

Why extract:

- toolbar layout is dense and visual
- currently bloats `jaw_page.py`
- identical extraction category already used on the TOOLS side

### 3. `ui/jaw_page_support/detail_panel_builder.py` (new)

Move:

- `_clear_details`
- `_split_used_in_works`
- `_build_empty_details_card`
- `_build_jaw_detail_header`
- `_build_jaw_preview_card`
- `populate_details`
- `_lookup_setup_db_used_in_works`

Recommended exports:

- `populate_detail_panel(page, jaw) -> None`
- `build_empty_details_card(page) -> QFrame`
- `build_jaw_detail_header(page, jaw) -> QFrame`
- `build_jaw_preview_card(page, jaw) -> QWidget`

Why extract:

- this is the single biggest render block left in the page
- keeps preview layout logic near detail-grid layout rules
- mirrors `home_page_support/detail_panel_builder.py`

### 4. `ui/jaw_page_support/bottom_bars_builder.py` (new)

Move:

- `_build_primary_bottom_bar`
- `_build_selector_bottom_bar`

Recommended exports:

- `build_bottom_bars(page) -> None`
- `retranslate_bottom_bars(page) -> None`

Why extract:

- action bar construction is pure widget composition
- keeps `JawPage.__init__()` short

### 5. `ui/jaw_page_support/preview_rules.py` (extend existing)

Add:

- `jaw_preview_plane()`
- `jaw_preview_rotation()`
- `apply_jaw_preview_transform()`
- optional `jaw_preview_transform_signature()` helper

Why extend, not replace:

- module already owns jaw preview normalization
- transform logic belongs beside payload normalization

### 6. `ui/jaw_page_support/detached_preview.py` (extend existing)

Adjust:

- load inline and detached preview with transform restore
- include transform-sensitive cache key behavior
- keep measurement overlay flow unchanged

### 7. Keep Existing Selector Modules Intact

Do not over-refactor selector code in Phase 5. Current selector extraction is already reasonable:

- `selector_slot_controller.py`
- `selector_actions.py`
- `selector_widgets.py`

Only make compatibility edits required by the new `CatalogPageBase` integration.

---

## Old-to-New Mapping

### Mapping Strategy

This mapping is organized by contiguous old ranges. The goal is to show where each old responsibility lands after Phase 5.

### High-Level Mapping Summary

| Old range | Current responsibility | New location |
|----------|------------------------|--------------|
| 1-86 | imports and module setup | `jaw_page.py`, `catalog_list_widgets.py`, `detail_panel_builder.py` |
| 87-141 | `_JawCatalogListView` | `ui/jaw_page_support/catalog_list_widgets.py` |
| 143-181 | setup-db lookup helper | `ui/jaw_page_support/detail_panel_builder.py` |
| 184-229 | `JawPage.__init__` state init | `JawPage.__init__` |
| 230-240 | localization helpers | `JawPage` |
| 241-260 | `_build_ui` | split between `CatalogPageBase`, `topbar_builder.py`, `bottom_bars_builder.py`, `JawPage._build_jaw_scaffold()` |
| 261-351 | top filter frame | `ui/jaw_page_support/topbar_builder.py` |
| 352-387 | main content layout | base class layout + `JawPage._build_jaw_scaffold()` |
| 388-418 | catalog list card | base list view + `JawCatalogListView` wrapper |
| 419-454 | detail container | `JawPage._build_jaw_scaffold()` plus `detail_panel_builder.py` |
| 455-522 | selector card | stays in page or moves partially into `topbar_builder.py`/builder helper |
| 523-566 | primary bottom bar | `bottom_bars_builder.py` |
| 567-587 | selector bottom bar | `bottom_bars_builder.py` |
| 588-599 | layout event filters | `JawPage._build_jaw_scaffold()` |
| 600-634 | module switch, master filter, selector context | `JawPage` |
| 638-725 | search and filter orchestration | `topbar_builder.py` plus `JawPage.apply_filters()` |
| 728-792 | event filter | `JawPage.eventFilter()` |
| 793-855 | selection and batch helpers | `JawPage` |
| 861-1043 | detail + preview builders | `detail_panel_builder.py`, `detached_preview.py`, `preview_rules.py` |
| 1044-1112 | `populate_details` | `detail_panel_builder.py` |
| 1113-1153 | selection and refresh | `JawPage.refresh_list()`, base `refresh_catalog()` |
| 1154-1219 | detail toggle + current change | `JawPage` signal handlers |
| 1221-1323 | save/add/edit/delete/copy | `JawPage` |
| 1324-1358 | prompt helper | stays in page or moves to support if desired |
| 1359-end | `apply_localization` | `JawPage` |

### Detailed Mapping

#### Old lines 1-86

Current:

- imports
- constant helpers
- selector MIME setup

New:

- keep only page-level imports in `jaw_page.py`
- move drag-list-specific imports into `catalog_list_widgets.py`
- move detail-panel-specific imports into `detail_panel_builder.py`

Net effect:

- `jaw_page.py` import section becomes much shorter and easier to reason about

#### Old lines 87-141: `_JawCatalogListView`

Current behavior:

- multi-row drag payload generation
- MIME population
- ghost drag card

New home:

- `ui/jaw_page_support/catalog_list_widgets.py`

New page usage:

```python
self.list_view = JawCatalogListView(self)
```

#### Old lines 143-181: `_lookup_setup_db_used_in_works`

Current behavior:

- detail panel helper for “used in works” field

New home:

- `ui/jaw_page_support/detail_panel_builder.py`

Reason:

- only used by detail rendering

#### Old lines 184-229: `__init__`

Current behavior:

- state init
- direct call to `_build_ui()`
- direct `refresh_list()`

New behavior:

- state init remains
- `super().__init__()` replaces direct list/search/filter setup
- page-specific scaffold built afterward
- signals wired from base selection model

Expected reduction:

- from ~45 lines of mixed concerns to ~85 lines of explicit state plus one scaffold call

#### Old lines 230-240: `_t`, `_localized_jaw_type`, `_localized_spindle_side`

Stay in page.

Reason:

- these are cheap, local, and page-owned display utilities

#### Old lines 241-260: `_build_ui`

Current behavior:

- root layout
- toolbar
- content layout
- bottom bars
- initial state wiring

New behavior:

- `CatalogPageBase._build_ui()` supplies base layout
- `JawPage._build_jaw_scaffold()` adjusts the generic list-view scaffold into the jaw-specific shell
- builder modules create toolbar and bottom bars

#### Old lines 261-351: `_build_top_filter_frame`

Move into `topbar_builder.py`.

Phase 5 additions:

- add spindle orientation combo
- expose `get_filters()` for platform refresh flow
- keep search toggle behavior identical

#### Old lines 352-387: `_build_main_content_layout`

This logic dissolves into:

- base layout in `CatalogPageBase`
- jaw scaffold adjustment in `JawPage`
- optional sidebar builder if kept

The important design rule is that Phase 5 must stop treating the entire page layout as page-local custom infrastructure.

#### Old lines 388-418: `_build_catalog_list_card`

Most of this disappears because the base class already owns the list view.

What remains:

- replace the base list widget with `JawCatalogListView`
- apply selection mode and drag settings
- connect double-click and multi-selection signals

#### Old lines 419-454: `_build_detail_container`

Keep orchestration in the page.
Move internal detail content rendering into `detail_panel_builder.py`.

#### Old lines 455-522: `_build_selector_card`

Keep in the page for Phase 5 unless line pressure demands extraction.

Reason:

- selector slots are highly page-coupled
- controller and widgets are already extracted
- over-extracting this section now provides less value than migrating the platform boundary first

If additional reduction is still needed after Pass 4, create `selector_card_builder.py` later. It is not required for the first Phase 5 implementation.

#### Old lines 523-587: bottom bars

Move both bottom bars into `bottom_bars_builder.py`.

#### Old lines 588-599: `_install_layout_event_filters`

Keep in `JawPage`.

Reason:

- event filters operate on page-owned widgets
- this logic is orchestration, not a reusable builder concern

#### Old lines 600-634: module switch, master filter, selector context

Stay in page.

#### Old lines 638-725: search/type filter helpers

Split:

- widget-building and repopulation -> `topbar_builder.py`
- final filtering semantics -> `apply_filters()` in `JawPage`

#### Old lines 728-792: `eventFilter`

Stay in page.

Reason:

- central coordination point across selector, list, and toolbar widgets

#### Old lines 793-855: selection and batch helpers

Stay in page.

These are still part of page orchestration and are small enough after platform extraction.

#### Old lines 861-1043: detail and preview methods

Split across:

- `detail_panel_builder.py`
- `preview_rules.py`
- `detached_preview.py`

Keep only wrappers in the page.

#### Old lines 1044-1112: `populate_details`

Move fully into `detail_panel_builder.py`.

Page replacement:

```python
def populate_details(self, jaw: dict | None) -> None:
    populate_detail_panel(self, jaw)
```

#### Old lines 1113-1153: `select_jaw_by_id`, `refresh_list`

`select_jaw_by_id()` stays.

`refresh_list()` becomes a compatibility wrapper that simply calls `refresh_catalog()` and detached-preview sync.

#### Old lines 1154-1219: toggle/show/hide/details and current selection handlers

These consolidate into:

- `show_details()`
- `hide_details()`
- `toggle_details()`
- `_on_item_selected_internal()`
- `_on_item_double_clicked()`

The base signal flow replaces the old currentChanged handler as the primary selection path.

#### Old lines 1221-1323: CRUD

Stay in page.

#### Old lines 1324-1358: `_prompt_text`

Optional extraction.

Recommendation:

- leave it in `JawPage` for Phase 5 unless copy flow is rewritten to use `AddEditJawDialog`

#### Old lines 1359-end: `apply_localization`

Stay in page, but slim it down by delegating to builder `retranslate_*()` hooks.

---

## Implementation Checklist

### Pass 1: Base-Class Conversion

Objective:

- switch `JawPage` to inherit `CatalogPageBase`
- implement the four required abstract methods
- keep the page launching successfully

Tasks:

1. Change class declaration to `class JawPage(CatalogPageBase):`
2. import `CatalogPageBase`
3. add `create_delegate()`
4. add `get_item_service()`
5. add `build_filter_pane()`
6. add `apply_filters()`
7. replace manual list-refresh model code with `refresh_catalog()` path
8. keep `refresh_list()` as compatibility wrapper

Exit criteria:

- file imports cleanly
- app opens without runtime import error
- list rows populate from base refresh cycle

### Pass 2: Delegate Migration

Objective:

- align `JawCatalogDelegate` with `CatalogDelegate`

Tasks:

1. import `CatalogDelegate`
2. convert class base
3. implement `_compute_size()`
4. implement `_paint_item_content()`
5. keep current icon, badge, spindle rendering semantics
6. verify selection and hover visuals remain intact

Exit criteria:

- list paints correctly
- no row widgets introduced
- no regressions in hover/selection state

### Pass 3: Filter Pane and Navigation

Objective:

- move topbar builder logic out of the page
- preserve current search/type behavior
- add spindle orientation filtering cleanly

Tasks:

1. create `topbar_builder.py`
2. move filter toolbar build logic there
3. attach `get_filters()` to the returned frame
4. keep search-toggle UX identical
5. add spindle filter combo
6. make sidebar nav update `current_view_mode` then call `refresh_list()`
7. ensure `apply_filters()` combines view mode, jaw type, spindle filter, selector filter, and master filter in the right order

Exit criteria:

- search works
- jaw type works
- spindle filter works
- sidebar modes work
- filter reset icon behaves correctly

### Pass 4: Detail and Preview Extraction

Objective:

- shrink page size sharply by moving detail rendering out
- preserve preview plane and rotation behavior

Tasks:

1. create `detail_panel_builder.py`
2. move all bulky detail rendering there
3. move setup-work lookup helper there
4. extend `preview_rules.py` with transform helpers
5. update `detached_preview.py` to apply persisted transforms
6. update `_preview_model_key()` to include transform state
7. verify inline and detached preview parity

Exit criteria:

- page file size drops substantially
- detail panel renders correctly
- preview plane and rotation restore correctly

### Pass 5: CRUD, Batch, and Signals

Objective:

- ensure all jaw workflows still behave identically

Tasks:

1. add `jaw_selected` signal
2. add `jaw_deleted` signal
3. wire internal handlers from base signals
4. keep add/edit/delete/copy behavior intact
5. keep multi-selection batch/group edit behavior intact
6. verify selector assignment payload methods still work

Exit criteria:

- CRUD works
- batch edit works
- signals fire exactly once per action
- selector workflows unchanged

### Pass 6: Parity and Quality Gates

Objective:

- prove zero regressions

Tasks:

1. run syntax check
2. run smoke test
3. run import path checker
4. run duplicate detector
5. run module boundary checker
6. run or generate phase results for parity comparison
7. manually validate preview and selector flows that the current parity harness cannot fully automate

Exit criteria:

- all quality gates pass
- parity comparison shows zero regressions
- manual preview and selector checklist passes

### Pass 7: Cleanup, Documentation, and Signoff

Objective:

- stabilize the refactor and leave the repo consistent for future phases

Tasks:

1. remove dead imports and helpers from `jaw_page.py`
2. update `ui/jaw_page_support/__init__.py`
3. document delivered file sizes and extracted modules
4. record the phase outcome in repository notes
5. confirm no accidental wrapper modules violate AGENTS guidance

Exit criteria:

- page file is in the target range
- support modules are clearly named and responsibility-scoped
- no dead code remains in the old page

---

## Parity Test Strategy

### Baseline Reference

The repo already includes the Phase 0 baseline in `scripts/run_parity_tests.py` with 13 test IDs:

1. `1.1.add_tool`
2. `1.2.edit_tool`
3. `1.3.copy_tool`
4. `1.4.delete_tool`
5. `2.1.add_jaw`
6. `2.2.edit_jaw_preview`
7. `2.3.delete_jaw`
8. `3.1.excel_export`
9. `3.2.excel_import`
10. `3.3.db_switching`
11. `4.1.stl_preview`
12. `4.2.jaw_preview_plane`
13. `4.3.ipc_handoff`

Phase 5 acceptance requires those same 13 statuses to remain PASS.

### Important Practical Constraint

The current parity runner only writes Phase 0 baseline and can compare two result files. It does not yet execute phase-specific tests automatically.

So the real Phase 5 strategy should be two-layered:

#### Layer 1: automated repo gates

- syntax compilation
- smoke test
- import path checker
- module boundary checker
- duplicate detector

#### Layer 2: parity result capture

Generate a `phase5-jaws-results.json` file using the same test IDs and compare it with the baseline using the existing comparison mode.

### Required Phase 5 Result File Format

```json
{
  "phase": 5,
  "date": "2026-04-13",
  "tests": {
    "1.1.add_tool": {"status": "PASS", "notes": "unchanged from baseline"},
    "1.2.edit_tool": {"status": "PASS", "notes": "unchanged from baseline"},
    "1.3.copy_tool": {"status": "PASS", "notes": "unchanged from baseline"},
    "1.4.delete_tool": {"status": "PASS", "notes": "unchanged from baseline"},
    "2.1.add_jaw": {"status": "PASS", "notes": "JawPage add flow preserved"},
    "2.2.edit_jaw_preview": {"status": "PASS", "notes": "Preview plane and rotation restored"},
    "2.3.delete_jaw": {"status": "PASS", "notes": "delete flow preserved"},
    "3.1.excel_export": {"status": "PASS", "notes": "unchanged"},
    "3.2.excel_import": {"status": "PASS", "notes": "unchanged"},
    "3.3.db_switching": {"status": "PASS", "notes": "unchanged"},
    "4.1.stl_preview": {"status": "PASS", "notes": "inline + detached sync preserved"},
    "4.2.jaw_preview_plane": {"status": "PASS", "notes": "transform parity preserved"},
    "4.3.ipc_handoff": {"status": "PASS", "notes": "no protocol changes"}
  },
  "summary": {
    "total": 13,
    "passed": 13,
    "failed": 0,
    "blocked": 0
  }
}
```

### Manual Validation Checklist for the JAWS Domain

#### JAWS CRUD

1. Add a new jaw.
2. Edit a jaw.
3. Copy a jaw.
4. Delete a jaw.

#### JAWS Filtering and Selection

1. Search by jaw ID.
2. Filter by jaw type.
3. Filter by spindle orientation.
4. Switch sidebar modes.
5. Confirm selection stays stable across refreshes where possible.

#### JAWS Preview

1. Open jaw with STL.
2. Open inline detail preview.
3. Open detached preview.
4. Confirm measurement overlays render.
5. Confirm `preview_plane` restores.
6. Confirm `preview_rot_x/y/z` restore.
7. Confirm selected part state remains correct.

#### Selector Workflows

1. Activate selector mode.
2. Drag jaw to SP1.
3. Drag jaw to SP2.
4. Reject incompatible spindle drops.
5. Remove assigned jaws.
6. Confirm payload from `selector_assigned_jaws_for_setup_assignment()` is unchanged.

### Suggested Command Sequence

```powershell
python -m py_compile "Tools and jaws Library/ui/jaw_page.py"
python -m py_compile "Tools and jaws Library/ui/jaw_catalog_delegate.py"
python scripts/import_path_checker.py
python scripts/module_boundary_checker.py
python scripts/duplicate_detector.py
python scripts/smoke_test.py
python scripts/run_parity_tests.py --compare phase0-baseline.json phase5-jaws-results.json
```

### Pass Criteria

1. zero import path violations
2. zero module-boundary violations
3. zero new duplicate warnings beyond intentional existing collisions
4. smoke test passes
5. parity comparison reports zero regressions
6. manual preview and selector checklist completes without mismatch

---

## Risks, Fallbacks, and Acceptance Gates

### Main Risks

#### Risk 1: Selection model differences after replacing the list view

Why it matters:

- batch edit
- drag workflows
- current jaw state

Mitigation:

- replace the base list widget in one pass and reconnect selection hooks immediately
- verify `_selected_jaw_ids()` against extended-selection behavior before moving on

#### Risk 2: Preview transform regressions

Why it matters:

- this is specifically called out by the baseline parity suite

Mitigation:

- treat transform restoration as a first-class acceptance item, not a follow-up cleanup
- include transform fields in `_preview_model_key()`

#### Risk 3: Over-extraction producing meaningless wrapper modules

Why it matters:

- AGENTS explicitly rejects wrapper-only modules

Mitigation:

- every new support module must own real behavior or real widget composition
- no file should exist just to re-export one function without responsibility

#### Risk 4: Selector regressions during platform migration

Why it matters:

- selector mode relies on multiple event filters and list drag behavior

Mitigation:

- preserve current selector modules
- do not redesign selector behavior during Phase 5

### Fallback Strategy

If Pass 4 reveals that the detail/selector split cannot safely reach the 400-450L target without excessive risk, accept a temporary page size up to ~550L for the first working conversion, then do a follow-up reduction pass after parity is green.

That is the correct engineering tradeoff.

Behavioral parity matters more than a cosmetic line-count target.

### Final Acceptance Gates

Phase 5 is complete only when all of the following are true:

1. `JawPage` inherits `CatalogPageBase`.
2. `JawCatalogDelegate` inherits `CatalogDelegate`.
3. the four abstract methods are implemented cleanly.
4. jaw-specific preview plane and rotation remain intact.
5. selector assignment flows remain intact.
6. CRUD and batch flows remain intact.
7. quality gates pass.
8. parity remains 13/13 PASS.

---

## Appendices

### Appendix A: Minimal `topbar_builder.py` API

```python
def build_filter_toolbar(page) -> QFrame:
    """Build and return the jaw-page filter toolbar.

    Must create:
    - search_toggle
    - search
    - toggle_details_btn
    - filter_icon
    - jaw_type_filter
    - spindle_filter
    - preview_window_btn
    - detail_header_container
    - get_filters() hook on frame
    """


def retranslate_filter_toolbar(page) -> None:
    """Refresh translated labels and placeholders after language change."""
```

### Appendix B: Minimal `detail_panel_builder.py` API

```python
def populate_detail_panel(page, jaw: dict | None) -> None:
    """Clear and repopulate the jaw detail panel."""


def build_jaw_preview_card(page, jaw: dict) -> QWidget:
    """Build inline preview host and apply persisted transforms."""
```

### Appendix C: Minimal `bottom_bars_builder.py` API

```python
def build_bottom_bars(page) -> None:
    """Create the primary bottom bar and selector bottom bar on the page."""


def retranslate_bottom_bars(page) -> None:
    """Refresh bottom-bar labels after language change."""
```

### Appendix D: Page-to-Support Dependency Direction

Allowed direction:

```text
JawPage -> jaw_page_support.*
JawPage -> shared.ui.platforms.*
JawPage -> ui.jaw_catalog_delegate

jaw_page_support.* -> shared.*
jaw_page_support.* -> ui.selector_* helpers already in this app
```

Disallowed direction:

```text
shared.* -> ui.jaw_page_support.*
Setup Manager modules -> Tools and jaws Library/ui/* directly
new wrappers that only forward imports
```

### Appendix E: Recommended Delivery Order

If implementation starts immediately, the safest order is:

1. convert the delegate first
2. create the new builder modules
3. convert JawPage to the base class
4. restore preview transforms
5. run all gates

Reason:

- the delegate change is self-contained
- the builder modules reduce the page before the base-class swap
- the final platform conversion becomes mechanically simpler

### Appendix F: What Not to Change in Phase 5

Do not change:

1. database schema
2. jaw service save contract
3. selector payload shape
4. app-to-app IPC protocol
5. setup-manager-facing assignment payloads
6. import boundaries defined in AGENTS

### Appendix G: Success Summary

If this design is followed, the JAWS domain ends Phase 5 with the same architecture TOOLS now uses:

- shared platform-owned catalog behavior
- small page orchestration file
- support-module-based UI composition
- parity-preserving domain logic
- a clean base for later editor and preview improvements

That is the real objective. The line count is the result, not the strategy.