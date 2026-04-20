from __future__ import annotations

import logging
from time import perf_counter

from PySide6.QtGui import QStandardItem

from shared.ui.helpers.topbar_common import rebuild_filter_row
from ..jaw_catalog_delegate import ROLE_JAW_DATA, ROLE_JAW_ID
from .selector_ui_helpers import normalize_selector_spindle, selector_spindle_label
from .common import selected_rows_or_current


_LOGGER = logging.getLogger(__name__)


class JawSelectorStateMixin:
    def _trace_selector_state(self, event: str, **fields) -> None:
        payload = {
            'event': event,
            'embedded_mode': bool(getattr(self, '_embedded_mode', False)),
        }
        payload.update(fields)
        _LOGGER.info('jaw_selector.trace %s', payload)

    def _load_initial_assignments(self, initial_assignments: list[dict] | None) -> None:
        pending: list[dict] = []
        for item in initial_assignments or []:
            normalized = self._normalize_selector_jaw(item)
            if normalized is None:
                continue
            spindle = normalize_selector_spindle(item.get('spindle') or item.get('slot') or '')
            if self._selector_assignments.get(spindle) is None:
                self._selector_assignments[spindle] = normalized
            else:
                pending.append(normalized)

        for spindle in ('main', 'sub'):
            if self._selector_assignments.get(spindle) is None and pending:
                self._selector_assignments[spindle] = pending.pop(0)

    @staticmethod
    def _normalize_selector_jaw(jaw: dict | None) -> dict | None:
        if not isinstance(jaw, dict):
            return None
        jaw_id = str(jaw.get('jaw_id') or jaw.get('id') or '').strip()
        if not jaw_id:
            return None
        normalized = {
            'jaw_id': jaw_id,
            'jaw_type': str(jaw.get('jaw_type') or '').strip(),
        }
        spindle_side = str(jaw.get('spindle_side') or '').strip()
        if spindle_side:
            normalized['spindle_side'] = spindle_side
        return normalized

    @staticmethod
    def _normalize_jaw_spindle_side(value: str | None) -> str:
        raw = str(value or '').strip().lower()
        if not raw:
            return 'both'
        if raw in {'sp1', '1'}:
            return 'main'
        if raw in {'sp2', '2'}:
            return 'sub'
        if 'both' in raw or 'molem' in raw:
            return 'both'
        if 'sub' in raw or 'vasta' in raw or 'counter' in raw:
            return 'sub'
        if 'main' in raw or 'pää' in raw or 'paa' in raw:
            return 'main'
        return 'both'

    def _jaw_supports_slot(self, jaw: dict | None, slot: str) -> bool:
        side = self._normalize_jaw_spindle_side((jaw or {}).get('spindle_side') if isinstance(jaw, dict) else '')
        target = normalize_selector_spindle(slot)
        if side == 'both':
            return True
        return side == target

    def _refresh_catalog(self) -> None:
        started = perf_counter()
        search_text = self.search_input.text().strip()
        view_mode = self.view_filter.currentData() or 'all'
        delegate = self.list_view.itemDelegate()
        jaws = self.jaw_service.list_jaws(search_text=search_text, view_mode=view_mode, jaw_type_filter='All')

        self._model.clear()
        for jaw in jaws:
            item = QStandardItem()
            jaw_id = str(jaw.get('jaw_id') or '').strip()
            item.setData(jaw_id, ROLE_JAW_ID)
            item.setData(dict(jaw), ROLE_JAW_DATA)
            prewarm_icon = getattr(delegate, 'prewarm_icon_pixmap', None)
            if callable(prewarm_icon):
                prewarm_icon(dict(jaw))
            self._model.appendRow(item)
        self._trace_selector_state(
            'catalog.refresh',
            search_text=search_text,
            view_mode=view_mode,
            row_count=self._model.rowCount(),
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )

    def _refresh_slot_ui(self) -> None:
        started = perf_counter()
        self.slot_main.set_assignment(self._selector_assignments.get('main'))
        self.slot_sub.set_assignment(self._selector_assignments.get('sub'))
        self.slot_main.set_selected('main' in self._selected_slots)
        self.slot_sub.set_selected('sub' in self._selected_slots)
        self._update_remove_button()
        self._trace_selector_state(
            'slot_ui.refresh',
            main_assigned=bool(self._selector_assignments.get('main')),
            sub_assigned=bool(self._selector_assignments.get('sub')),
            selected_slots=sorted(self._selected_slots),
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )

    def _update_context_header(self) -> None:
        label = selector_spindle_label(self._current_spindle)
        self.selector_spindle_value_label.setText(label)

    def _update_remove_button(self) -> None:
        has_selected = any(self._selector_assignments.get(slot) is not None for slot in self._selected_slots)
        has_assigned = any(self._selector_assignments.get(slot) is not None for slot in ('main', 'sub'))
        self.remove_btn.setEnabled(has_selected or has_assigned)

    def _on_slot_clicked(self, slot_key: str, ctrl_pressed: bool) -> None:
        slot = normalize_selector_spindle(slot_key)
        has_assignment = self._selector_assignments.get(slot) is not None
        if not has_assignment:
            if not ctrl_pressed:
                self._selected_slots.clear()
            self._refresh_slot_ui()
            return

        if ctrl_pressed:
            if slot in self._selected_slots:
                self._selected_slots.remove(slot)
            else:
                self._selected_slots.add(slot)
        else:
            self._selected_slots = {slot}
        self._refresh_slot_ui()

    def _on_slot_dropped(self, slot_key: str, jaw: dict) -> None:
        slot = normalize_selector_spindle(slot_key)
        normalized_jaw = self._normalize_selector_jaw(jaw)
        if normalized_jaw is None:
            return
        if not self._jaw_supports_slot(normalized_jaw, slot):
            slot_widget = self.slot_main if slot == 'main' else self.slot_sub
            slot_widget.flash_invalid_drop()
            return
        self._selector_assignments[slot] = normalized_jaw
        self._selected_slots = {slot}
        self._refresh_slot_ui()

    def _assign_jaw_to_current_slot(self, jaw: dict) -> None:
        slot = self._current_spindle
        if not self._jaw_supports_slot(jaw, slot):
            slot_widget = self.slot_main if slot == 'main' else self.slot_sub
            slot_widget.flash_invalid_drop()
            return
        self._selector_assignments[slot] = dict(jaw)
        self._selected_slots = {slot}
        self._refresh_slot_ui()

    def _on_catalog_double_clicked(self, _index) -> None:
        indexes = selected_rows_or_current(self.list_view)
        if not indexes:
            return

        assigned = False
        for index in indexes:
            jaw_data = index.data(ROLE_JAW_DATA)
            normalized = self._normalize_selector_jaw(jaw_data if isinstance(jaw_data, dict) else None)
            if normalized is None:
                continue
            self._assign_jaw_to_current_slot(normalized)
            assigned = True
            break

        if assigned:
            self._refresh_slot_ui()

    def _on_catalog_double_clicked_open_detail(self, index) -> None:
        """Double-click toggles detail panel only (does not assign the jaw)."""
        jaw_data = index.data(ROLE_JAW_DATA)
        if isinstance(jaw_data, dict):
            self.current_jaw_id = str(jaw_data.get('jaw_id') or '').strip() or None
        self._sync_preview_if_open()
        if self.detail_card.isVisible():
            self._switch_to_selector_panel()
            return
        self._switch_to_detail_panel(jaw_data if isinstance(jaw_data, dict) else None)

    def _remove_selected(self) -> None:
        if self._selected_slots:
            for slot in list(self._selected_slots):
                self._selector_assignments[slot] = None
            self._selected_slots.clear()
            self._refresh_slot_ui()
            return

        self._selector_assignments[self._current_spindle] = None
        self._refresh_slot_ui()

    def _remove_by_ids(self, jaw_ids: list[str]) -> None:
        targets = {str(jaw_id).strip() for jaw_id in jaw_ids if str(jaw_id).strip()}
        if not targets:
            return
        changed = False
        for slot in ('main', 'sub'):
            jaw = self._selector_assignments.get(slot)
            jaw_id = str((jaw or {}).get('jaw_id') or '').strip() if isinstance(jaw, dict) else ''
            if jaw_id and jaw_id in targets:
                self._selector_assignments[slot] = None
                changed = True
        if changed:
            self._selected_slots.clear()
            self._refresh_slot_ui()

    # ── Toolbar helpers ────────────────────────────────────────────────────

    def _toggle_search(self) -> None:
        """Show/hide the search input and rebuild the toolbar row."""
        visible = self.search_toggle.isChecked()
        self.search_input.setVisible(visible)
        if not visible:
            self.search_input.clear()
            self._refresh_catalog()
        rebuild_filter_row(
            self._filter_layout,
            self.search_toggle,
            self.toggle_details_btn,
            self.search_input,
            self.filter_icon,
            [self.view_filter],
            self.preview_window_btn,
            self.detail_header_container,
        )
        if visible:
            self.search_input.setFocus()

    def _clear_search(self) -> None:
        """Reset search text and filter."""
        self.search_input.clear()
        if self.view_filter.count():
            self.view_filter.setCurrentIndex(0)

    # ── Detail panel toggle ───────────────────────────────────────────────

    def _toggle_detail_panel(self) -> None:
        """Toggle right panel between selector and jaw detail views."""
        if self.detail_card.isVisible():
            self._switch_to_selector_panel()
            return
        indexes = selected_rows_or_current(self.list_view)
        jaw_data: dict | None = None
        if indexes:
            jaw_data = indexes[0].data(ROLE_JAW_DATA)
        self._switch_to_detail_panel(jaw_data)

    def _switch_to_detail_panel(self, jaw_data: dict | None = None) -> None:
        """Show the detail card and populate it with jaw_data."""
        self.setUpdatesEnabled(False)
        ensure_detail_card_built = getattr(self, '_ensure_detail_card_built', None)
        if callable(ensure_detail_card_built):
            ensure_detail_card_built()
        self.selector_card.setVisible(False)
        self.detail_card.setVisible(True)
        self.detail_header_container.setVisible(True)
        rebuild_filter_row(
            self._filter_layout,
            self.search_toggle,
            self.toggle_details_btn,
            self.search_input,
            self.filter_icon,
            [self.view_filter],
            self.preview_window_btn,
            self.detail_header_container,
        )
        self._populate_jaw_detail(jaw_data)
        self.setUpdatesEnabled(True)

    def _switch_to_selector_panel(self) -> None:
        """Show the selector card; hide the detail card."""
        self.detail_card.setVisible(False)
        self.selector_card.setVisible(True)
        self.detail_header_container.setVisible(False)
        rebuild_filter_row(
            self._filter_layout,
            self.search_toggle,
            self.toggle_details_btn,
            self.search_input,
            self.filter_icon,
            [self.view_filter],
            self.preview_window_btn,
            self.detail_header_container,
        )

    def _on_catalog_item_clicked(self, index) -> None:
        """When detail panel is active, repopulate it with the clicked jaw."""
        jaw_data = index.data(ROLE_JAW_DATA)
        if isinstance(jaw_data, dict):
            self.current_jaw_id = str(jaw_data.get('jaw_id') or '').strip() or None
        self._sync_preview_if_open()
        if not self.detail_card.isVisible():
            return
        self._populate_jaw_detail(jaw_data if isinstance(jaw_data, dict) else None)

    def _populate_jaw_detail(self, jaw: dict | None) -> None:
        """Clear and rebuild the detail panel content using jaw detail builder."""
        started = perf_counter()
        ensure_detail_card_built = getattr(self, '_ensure_detail_card_built', None)
        if callable(ensure_detail_card_built):
            ensure_detail_card_built()
        from ..jaw_page_support.detail_panel_builder import populate_detail_panel
        # Clear existing content
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        populate_detail_panel(self, jaw)
        self._trace_selector_state(
            'detail.populate',
            jaw_id=str((jaw or {}).get('jaw_id') or '').strip() or None,
            has_jaw=bool(jaw),
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )

    def _prime_detail_panel_cache(self) -> None:
        """Pre-render first jaw detail payload so first open is smooth."""
        started = perf_counter()
        indexes = selected_rows_or_current(self.list_view)
        if not indexes and self._model.rowCount() > 0:
            first_index = self._model.index(0, 0)
            if first_index.isValid():
                self.list_view.setCurrentIndex(first_index)
                indexes = [first_index]
        if not indexes:
            return
        jaw_data = indexes[0].data(ROLE_JAW_DATA)
        if isinstance(jaw_data, dict):
            self.current_jaw_id = str(jaw_data.get('jaw_id') or '').strip() or None
            self._populate_jaw_detail(jaw_data)
        self._trace_selector_state(
            'detail.prime_cache',
            has_index=bool(indexes),
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )

    def _sync_preview_if_open(self) -> None:
        preview_btn = getattr(self, 'preview_window_btn', None)
        if preview_btn is not None and preview_btn.isChecked():
            self._sync_detached_preview(show_errors=False)
