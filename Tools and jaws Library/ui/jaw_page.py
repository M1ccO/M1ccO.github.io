"""Jaw catalog page refactored onto CatalogPageBase."""

from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import QModelIndex, Qt, Signal, QTimer
from PySide6.QtWidgets import QWidget

import ui.jaw_page_support.crud_actions as _crud
import ui.jaw_page_support.detail_visibility as _detail_vis
import ui.jaw_page_support.retranslate_page as _retranslate
import ui.jaw_page_support.selection_helpers as _sel
from ui.jaw_page_support.selection_signal_handlers import (
    connect_selection_model as _connect_selection_model_impl,
    on_current_item_changed as _on_current_item_changed_impl,
    on_item_deleted_internal as _on_item_deleted_internal_impl,
    on_item_double_clicked as _on_item_double_clicked_impl,
    on_item_selected_internal as _on_item_selected_internal_impl,
    on_multi_selection_changed as _on_multi_selection_changed_impl,
    update_selection_count_label as _update_selection_count_label_impl,
)
from shared.ui.platforms.catalog_page_base import CatalogPageBase
from shared.ui.stl_preview import StlPreviewWidget
from ui.jaw_catalog_delegate import JawCatalogDelegate, ROLE_JAW_ID
from ui.jaw_page_support import (
    SelectorSlotController,
    apply_detached_measurement_state,
    apply_detached_preview_default_bounds,
    batch_edit_jaws,
    build_filter_toolbar,
    close_detached_preview,
    ensure_detached_preview_dialog,
    group_edit_jaws,
    jaw_preview_transform_signature,
    load_preview_content,
    on_detached_measurements_toggled,
    on_detached_preview_closed,
    on_selector_cancel,
    on_selector_done,
    populate_detail_panel,
    prompt_batch_cancel_behavior,
    rebuild_filter_row,
    retranslate_filter_toolbar,
    set_preview_button_checked,
    sync_detached_preview,
    toggle_preview_window,
    update_detached_measurement_toggle_icon,
    warmup_preview_engine as _warmup_preview_engine_impl,
)
from ui.jaw_page_support.event_filter import handle_jaw_page_event
from ui.jaw_page_support.page_builders import build_jaw_page_layout
from ui.selector_ui_helpers import normalize_selector_spindle, selector_spindle_label

__all__ = ['JawPage']


class JawPage(CatalogPageBase):
    jaw_selected = Signal(str)
    jaw_deleted = Signal(str)

    NAV_MODES = [
        ('all', 'all'),
        ('main', 'main'),
        ('sub', 'sub'),
        ('soft', 'soft'),
        ('hard_group', 'hard_group'),
    ]

    def __init__(
        self,
        jaw_service,
        parent=None,
        show_sidebar: bool = True,
        machine_profile=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        self.jaw_service = jaw_service
        self.show_sidebar = bool(show_sidebar)
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self.machine_profile = machine_profile

        self.current_jaw_id: str | None = None
        self.current_view_mode = 'all'
        self._details_hidden = True
        self._last_splitter_sizes: list[int] | None = None

        self._module_switch_callback = None
        self._master_filter_ids: set[str] = set()
        self._master_filter_active = False
        self._type_filter_values = ['all', 'soft', 'hard_group', 'special']

        self._selector_active = False
        self._selector_spindle = ''
        self._selector_panel_mode = 'details'
        self._selector_assignments: dict[str, dict | None] = {'main': None, 'sub': None}
        self._selector_selected_slots: set[str] = set()
        self._selector_saved_details_hidden = True
        self._selector_slot_controller = SelectorSlotController(self)
        self._initial_load_done = False
        self._initial_load_scheduled = False
        self._deferred_refresh_needed = False

        self._detail_preview_widget = None
        self._detail_preview_model_key = None
        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._detached_preview_last_model_key = None
        self._detached_measurements_enabled = True
        self._measurement_toggle_btn = None
        self._close_preview_shortcut = None
        self._inline_preview_warmup = None

        super().__init__(parent=parent, item_service=jaw_service, translate=self._translate)

        self.item_selected.connect(self._on_item_selected_internal)
        self.item_deleted.connect(self._on_item_deleted_internal)

    def _schedule_initial_load(self) -> None:
        """Schedule first visible catalog load once per page instance."""
        if self._initial_load_done or self._initial_load_scheduled:
            return
        self._initial_load_scheduled = True
        QTimer.singleShot(0, self._perform_initial_load)

    def _perform_initial_load(self) -> None:
        """Perform first catalog load after the page becomes visible."""
        self._initial_load_scheduled = False
        if self._initial_load_done or not self.isVisible():
            return
        self._initial_load_done = True
        self._deferred_refresh_needed = False
        # Warm OpenGL preview once so first detail open is smooth.
        self._warmup_preview_engine()
        self.refresh_catalog()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._initial_load_done:
            self._schedule_initial_load()
            return
        if self._deferred_refresh_needed:
            self._deferred_refresh_needed = False
            QTimer.singleShot(0, self.refresh_catalog)

    # ------------------------------------------------------------------
    # CatalogPageBase contract
    # ------------------------------------------------------------------

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _localized_jaw_type(self, raw_type: str) -> str:
        normalized = (raw_type or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.jaw_type.{normalized}', raw_type)

    def _localized_spindle_side(self, raw_side: str) -> str:
        normalized = (raw_side or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.spindle_side.{normalized}', raw_side)

    def create_delegate(self):
        return JawCatalogDelegate(parent=getattr(self, 'list_view', None), translate=self._t)

    def get_item_service(self) -> Any:
        return self.jaw_service

    def build_filter_pane(self) -> QWidget:
        return build_filter_toolbar(self)

    def apply_filters(self, filters: dict) -> list[dict]:
        search_text = str(filters.get('search') or '').strip()
        view_mode = str(filters.get('view_mode') or self.current_view_mode or 'all').strip().lower()
        jaw_type = str(filters.get('jaw_type') or 'all').strip().lower()
        spindle_filter = str(filters.get('spindle_filter') or 'all').strip().lower()

        jaws = self.jaw_service.list_jaws(
            search_text=search_text,
            view_mode=view_mode,
            jaw_type_filter=jaw_type,
        )
        if spindle_filter != 'all':
            jaws = [jaw for jaw in jaws if self._jaw_matches_spindle_filter(jaw, spindle_filter)]
        if self._selector_active:
            jaws = [jaw for jaw in jaws if self._jaw_matches_selector_spindle(jaw)]
        if self._master_filter_active:
            jaws = [jaw for jaw in jaws if str(jaw.get('jaw_id', '')).strip() in self._master_filter_ids]
        return [self._catalog_item_dict(jaw) for jaw in jaws]

    def _build_ui(self) -> None:
        build_jaw_page_layout(self)

    # ------------------------------------------------------------------
    # Model helpers
    # ------------------------------------------------------------------

    def _create_model(self):
        from PySide6.QtGui import QStandardItemModel
        return QStandardItemModel(self)

    def _connect_selection_model(self) -> None:
        _connect_selection_model_impl(self)

    def _catalog_item_dict(self, jaw: dict) -> dict:
        jaw_id = str(jaw.get('jaw_id') or '').strip()
        return {
            'id': jaw_id,
            'uid': 0,
            'jaw_id': jaw_id,
            'jaw_type': jaw.get('jaw_type', ''),
            'spindle_side': jaw.get('spindle_side', ''),
            'clamping_diameter_text': jaw.get('clamping_diameter_text', ''),
            'clamping_length': jaw.get('clamping_length', ''),
            'used_in_work': jaw.get('used_in_work', ''),
            'turning_washer': jaw.get('turning_washer', ''),
            'notes': jaw.get('notes', ''),
            'stl_path': jaw.get('stl_path', ''),
            'measurement_overlays': jaw.get('measurement_overlays', []),
            'preview_plane': jaw.get('preview_plane', 'XZ'),
            'preview_rot_x': jaw.get('preview_rot_x', 0),
            'preview_rot_y': jaw.get('preview_rot_y', 0),
            'preview_rot_z': jaw.get('preview_rot_z', 0),
            'preview_selected_part': jaw.get('preview_selected_part', -1),
            'preview_selected_parts': jaw.get('preview_selected_parts', []),
            'preview_transform_mode': jaw.get('preview_transform_mode', 'translate'),
            'preview_fine_transform': jaw.get('preview_fine_transform', False),
            '_raw': jaw,
        }

    def _catalog_item_id(self, index: QModelIndex) -> str:
        return str(index.data(ROLE_JAW_ID) or '').strip()

    def _jaw_matches_spindle_filter(self, jaw: dict, spindle_filter: str) -> bool:
        side = str(jaw.get('spindle_side') or '').strip().lower()
        if spindle_filter == 'main':
            return 'main' in side or 'both' in side or 'paa' in side or 'molem' in side
        if spindle_filter == 'sub':
            return 'sub' in side or 'both' in side or 'vasta' in side or 'molem' in side
        return True

    def _jaw_matches_selector_spindle(self, jaw: dict) -> bool:
        if not self._selector_active:
            return True
        return self._selector_slot_controller.jaw_supports_selector_slot(jaw, self._selector_spindle)

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        if handle_jaw_page_event(self, obj, event):
            return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Catalog click / selection signals
    # ------------------------------------------------------------------

    def _on_catalog_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        item_id = self._catalog_item_id(index)
        self._current_item_id = item_id or None
        self._current_item_uid = None
        self.item_selected.emit(item_id, 0)

    def _on_item_selected_internal(self, jaw_id: str, _uid: int) -> None:
        _on_item_selected_internal_impl(self, jaw_id, _uid)

    def _on_item_deleted_internal(self, jaw_id: str) -> None:
        _on_item_deleted_internal_impl(self, jaw_id)

    def on_current_item_changed(self, current: QModelIndex, previous: QModelIndex):
        _on_current_item_changed_impl(self, current, previous)

    def on_item_double_clicked(self, index: QModelIndex):
        _on_item_double_clicked_impl(self, index)

    def _on_multi_selection_changed(self, _selected, _deselected) -> None:
        _on_multi_selection_changed_impl(self, _selected, _deselected)

    def _update_selection_count_label(self) -> None:
        _update_selection_count_label_impl(self)

    # ------------------------------------------------------------------
    # Filter / view controls
    # ------------------------------------------------------------------

    def _toggle_search(self) -> None:
        show = self.search_toggle.isChecked()
        self.search_input.setVisible(show)
        self.search_toggle.setIcon(self.close_icon if show else self.search_icon)
        if not show:
            self.search_input.clear()
            self.refresh_list()
        rebuild_filter_row(self)
        for combo in (self.jaw_type_filter, self.spindle_filter):
            combo.hidePopup()
            combo.setEnabled(False)
            QTimer.singleShot(0, lambda c=combo: c.setEnabled(True))
        self._suppress_combo = True
        QTimer.singleShot(0, lambda: setattr(self, '_suppress_combo', False))
        if show:
            QTimer.singleShot(0, self.search_input.setFocus)

    def _on_filter_changed(self, _index: int) -> None:
        retranslate_filter_toolbar(self)
        self.refresh_list()

    def _clear_filters(self) -> None:
        self.jaw_type_filter.setCurrentIndex(0)
        self.spindle_filter.setCurrentIndex(0)

    def _set_view_mode(self, mode: str, refresh: bool = True) -> None:
        self.current_view_mode = mode
        for btn_mode, btn in self.view_buttons:
            btn.setProperty('primaryAction', btn_mode == mode)
            style = btn.style()
            style.unpolish(btn)
            style.polish(btn)
            btn.update()
        if refresh:
            self.refresh_list()

    def set_view_mode(self, mode: str) -> None:
        self._set_view_mode(mode, refresh=True)

    def _nav_mode_title(self, mode: str) -> str:
        mapping = {
            'all': self._t('tool_library.nav.all_jaws', 'All Jaws'),
            'main': self._t('tool_library.nav.main_spindle', 'Main Spindle'),
            'sub': self._t('tool_library.nav.sub_spindle', 'Sub Spindle'),
            'soft': self._t('jaw_library.nav.soft_jaws', 'Soft Jaws'),
            'hard_group': self._t('jaw_library.nav.hard_group', 'Hard / Spiked / Special'),
        }
        return mapping.get(mode, mode)

    # ------------------------------------------------------------------
    # Selector helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_selector_spindle(value: str | None) -> str:
        return normalize_selector_spindle(value)

    @staticmethod
    def _selector_spindle_label(spindle: str) -> str:
        return selector_spindle_label(spindle)

    def _update_selector_spindle_ui(self) -> None:
        if hasattr(self, 'selector_spindle_value_label'):
            self.selector_spindle_value_label.setText(self._selector_spindle_label(self._selector_spindle))

    def set_selector_context(
        self, active: bool, spindle: str = '', initial_assignments: list[dict] | None = None
    ) -> None:
        self._selector_slot_controller.set_selector_context(
            active, spindle=spindle, initial_assignments=initial_assignments
        )
        self.refresh_list()

    def selector_assigned_jaws_for_setup_assignment(self) -> list[dict]:
        return self._selector_slot_controller.selector_assigned_jaws_for_setup_assignment()

    def set_module_switch_handler(self, callback) -> None:
        self._module_switch_callback = callback

    def set_module_switch_target(self, target: str) -> None:
        target_text = (target or '').strip().upper() or 'TOOLS'
        display = (
            self._t('tool_library.module.tools', 'TOOLS')
            if target_text == 'TOOLS'
            else self._t('tool_library.module.jaws', 'JAWS')
        )
        self.module_toggle_btn.setText(display)
        self.module_toggle_btn.setToolTip(
            self._t('tool_library.module.switch_to_target', 'Switch to {target} module', target=display)
        )

    def set_master_filter(self, jaw_ids, active: bool) -> None:
        self._master_filter_ids = {str(j).strip() for j in (jaw_ids or []) if str(j).strip()}
        self._master_filter_active = bool(active) and bool(self._master_filter_ids)
        self.refresh_list()

    def _on_selector_cancel(self) -> None:
        on_selector_cancel(self)

    def _on_selector_done(self) -> None:
        on_selector_done(self)

    # ------------------------------------------------------------------
    # Selection state
    # ------------------------------------------------------------------

    def _clear_selection(self) -> None:
        _sel.clear_jaw_selection(self)

    def _selected_jaw_ids(self) -> list[str]:
        return _sel.selected_jaw_ids(self)

    def selected_jaws_for_setup_assignment(self) -> list[dict]:
        return _sel.selected_jaws_for_setup_assignment(self)

    def _get_selected_jaw(self) -> dict | None:
        if not self.current_jaw_id:
            return None
        return self.jaw_service.get_jaw(self.current_jaw_id)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._clear_selection()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Detail panel
    # ------------------------------------------------------------------

    def populate_details(self, jaw) -> None:
        populate_detail_panel(self, jaw)
        self._sync_detached_preview(show_errors=False)

    def show_details(self) -> None:
        _detail_vis.show_jaw_details(self)

    def hide_details(self) -> None:
        _detail_vis.hide_jaw_details(self)

    def toggle_details(self) -> None:
        _detail_vis.toggle_jaw_details(self)

    # ------------------------------------------------------------------
    # Preview delegation
    # ------------------------------------------------------------------

    def _preview_model_key(self, jaw: dict | None):
        if not isinstance(jaw, dict):
            return None
        jaw_id = str(jaw.get('jaw_id') or '').strip()
        try:
            stl_key = json.dumps(jaw.get('stl_path'), ensure_ascii=False, sort_keys=True)
        except Exception:
            stl_key = str(jaw.get('stl_path'))
        try:
            meas_key = json.dumps(jaw.get('measurement_overlays', []), ensure_ascii=False, sort_keys=True)
        except Exception:
            meas_key = str(jaw.get('measurement_overlays', []))
        return jaw_id, stl_key, meas_key, jaw_preview_transform_signature(jaw)

    def _set_preview_button_checked(self, checked: bool) -> None:
        set_preview_button_checked(self, checked)

    def _load_preview_content(self, viewer: StlPreviewWidget, jaw: dict, *, label: str | None = None) -> bool:
        return load_preview_content(self, viewer, jaw, label=label)

    def _ensure_detached_preview_dialog(self) -> None:
        ensure_detached_preview_dialog(self)

    def _apply_detached_preview_default_bounds(self) -> None:
        apply_detached_preview_default_bounds(self)

    def _update_detached_measurement_toggle_icon(self, enabled: bool) -> None:
        update_detached_measurement_toggle_icon(self, enabled)

    def _on_detached_measurements_toggled(self, checked: bool) -> None:
        on_detached_measurements_toggled(self, checked)

    def _apply_detached_measurement_state(self, jaw: dict) -> None:
        apply_detached_measurement_state(self, jaw)

    def _on_detached_preview_closed(self, result) -> None:
        on_detached_preview_closed(self, result)

    def _close_detached_preview(self) -> None:
        close_detached_preview(self)

    def _sync_detached_preview(self, show_errors: bool = False) -> bool:
        return sync_detached_preview(self, show_errors)

    def toggle_preview_window(self) -> None:
        toggle_preview_window(self)

    def _warmup_preview_engine(self) -> None:
        _warmup_preview_engine_impl(self)

    # ------------------------------------------------------------------
    # Batch editing
    # ------------------------------------------------------------------

    def _prompt_batch_cancel_behavior(self) -> str:
        return prompt_batch_cancel_behavior(self)

    def _batch_edit_jaws(self, jaw_ids: list[str]) -> None:
        batch_edit_jaws(self, jaw_ids)

    def _group_edit_jaws(self, jaw_ids: list[str]) -> None:
        group_edit_jaws(self, jaw_ids)

    # ------------------------------------------------------------------
    # Catalog refresh
    # ------------------------------------------------------------------

    def refresh_catalog(self) -> None:
        if not self._initial_load_done and not self.isVisible():
            self._deferred_refresh_needed = True
            return
        self._initial_load_done = True
        self._deferred_refresh_needed = False

        filter_state = self.filter_pane.get_filters() if hasattr(self.filter_pane, 'get_filters') else {}
        items = self.apply_filters({'search': self.search_input.text().strip(), **filter_state})

        self._item_model.blockSignals(True)
        self._item_model.clear()
        for item_dict in items:
            self._item_model.appendRow(self._create_catalog_item(item_dict))
        self._item_model.blockSignals(False)

        self._jaw_model = self._item_model
        self._connect_selection_model()
        if self._item_model.rowCount() == 0:
            self.current_jaw_id = None
            self._current_item_id = None
            self.populate_details(None)
            self._sync_detached_preview(show_errors=False)
            self.list_view.viewport().update()
            return

        self._restore_selection()
        self.list_view.doItemsLayout()
        self.list_view.viewport().update()
        self._sync_detached_preview(show_errors=False)

    def refresh_list(self) -> None:
        if not self._initial_load_done and not self.isVisible():
            self._deferred_refresh_needed = True
            return
        self.refresh_catalog()

    def select_jaw_by_id(self, jaw_id: str) -> None:
        self.current_jaw_id = jaw_id.strip() or None
        self._current_item_id = self.current_jaw_id
        self._current_item_uid = None
        self.refresh_list()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_jaw(self) -> None:
        _crud.add_jaw(self)

    def edit_jaw(self) -> None:
        _crud.edit_jaw(self)

    def delete_jaw(self) -> None:
        _crud.delete_jaw(self)

    def copy_jaw(self) -> None:
        _crud.copy_jaw(self)

    # ------------------------------------------------------------------
    # Localization
    # ------------------------------------------------------------------

    def apply_localization(self, translate: Callable[[str, str | None], str] | None = None) -> None:
        _retranslate.apply_jaw_page_localization(self, translate)
