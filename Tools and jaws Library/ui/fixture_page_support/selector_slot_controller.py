"""Selector-slot compatibility helpers for FixturePage."""

from __future__ import annotations

from .selector_actions import (
    apply_selector_slot_selection,
    update_selector_remove_button,
    update_selector_spindle_ui,
)
from ui.selector_state_helpers import (
    default_selector_splitter_sizes,
    normalize_selector_mode,
    prune_selected_slots,
    slot_assignments_state,
    toggle_selector_slot_selection,
)
from ui.selector_ui_helpers import normalize_selector_spindle


class SelectorSlotController:
    def __init__(self, page):
        self._page = page

    @staticmethod
    def normalize_selector_fixture(fixture: dict | None) -> dict | None:
        if not isinstance(fixture, dict):
            return None
        # Selector payloads still arrive with either fixture_id or the older generic id key.
        fixture_id = str(fixture.get('fixture_id') or fixture.get('id') or '').strip()
        if not fixture_id:
            return None
        normalized = {
            'fixture_id': fixture_id,
            'fixture_type': str(fixture.get('fixture_type') or '').strip(),
        }
        fixture_kind = str(fixture.get('fixture_kind') or '').strip()
        if fixture_kind:
            normalized['fixture_kind'] = fixture_kind
        return normalized

    @staticmethod
    def normalize_fixture_kind_for_slot(value: str | None) -> str:
        raw = str(value or '').strip().lower()
        if not raw:
            return 'both'
        if raw in {'sp1', '1'}:
            return 'main'
        if raw in {'sp2', '2'}:
            return 'sub'
        if 'both' in raw or 'molem' in raw:
            return 'both'
        # Preserve localized and human-readable spindle labels from older selector payloads.
        if 'sub' in raw or 'vasta' in raw or 'counter' in raw:
            return 'sub'
        if 'main' in raw or 'p\u00e4\u00e4' in raw or 'paa' in raw:
            return 'main'
        return 'both'

    def fixture_supports_selector_slot(self, fixture: dict | None, slot: str) -> bool:
        side = self.normalize_fixture_kind_for_slot((fixture or {}).get('fixture_kind') if isinstance(fixture, dict) else '')
        target = normalize_selector_spindle(slot)
        if side == 'both':
            return True
        return side == target

    def selector_assignments_from_initial(self, initial_assignments: list[dict] | None) -> dict[str, dict | None]:
        assignments = slot_assignments_state(None)
        pending: list[dict] = []
        for item in initial_assignments or []:
            if not isinstance(item, dict):
                continue
            normalized = self.normalize_selector_fixture(item)
            if normalized is None:
                continue
            spindle = normalize_selector_spindle(item.get('spindle') or item.get('slot') or '')
            if spindle in assignments and assignments.get(spindle) is None:
                assignments[spindle] = normalized
            else:
                pending.append(normalized)
        for slot in ('main', 'sub'):
            if assignments.get(slot) is None and pending:
                assignments[slot] = pending.pop(0)
        return assignments

    def refresh_selector_slots(self) -> None:
        page = self._page
        if not hasattr(page, 'selector_sp1_slot'):
            return
        page._selector_assignments = slot_assignments_state(page._selector_assignments)
        page.selector_sp1_slot.set_assignment(page._selector_assignments.get('main'))
        page.selector_sp2_slot.set_assignment(page._selector_assignments.get('sub'))
        page._selector_selected_slots = prune_selected_slots(page._selector_selected_slots, page._selector_assignments)
        apply_selector_slot_selection(page)
        update_selector_remove_button(page)

    def on_selector_slot_clicked(self, slot_key: str, ctrl_pressed: bool) -> None:
        page = self._page
        slot = normalize_selector_spindle(slot_key)
        has_assignment = page._selector_assignments.get(slot) is not None
        page._selector_selected_slots = toggle_selector_slot_selection(
            page._selector_selected_slots,
            slot,
            has_assignment=has_assignment,
            ctrl_pressed=ctrl_pressed,
        )
        apply_selector_slot_selection(page)
        update_selector_remove_button(page)

    def on_selector_fixture_dropped(self, slot_key: str, fixture: dict) -> None:
        page = self._page
        normalized_slot = normalize_selector_spindle(slot_key)
        normalized_fixture = self.normalize_selector_fixture(fixture)
        if normalized_fixture is not None and not self.fixture_supports_selector_slot(normalized_fixture, normalized_slot):
            slot_widget = page.selector_sp1_slot if normalized_slot == 'main' else page.selector_sp2_slot
            if slot_widget is not None:
                slot_widget.flash_invalid_drop()
            return
        page._selector_assignments[normalized_slot] = normalized_fixture
        page._selector_selected_slots = {normalized_slot} if normalized_fixture is not None else set()
        self.refresh_selector_slots()

    def remove_selected_selector_fixtures(self) -> None:
        page = self._page
        if not page._selector_selected_slots:
            return
        for slot in list(page._selector_selected_slots):
            page._selector_assignments[slot] = None
        page._selector_selected_slots.clear()
        self.refresh_selector_slots()

    def remove_selector_fixtures_by_ids(self, fixture_ids: list[str]) -> None:
        page = self._page
        targets = {str(fixture_id).strip() for fixture_id in fixture_ids if str(fixture_id).strip()}
        if not targets:
            return
        changed = False
        for slot_key in ('main', 'sub'):
            fixture = page._selector_assignments.get(slot_key)
            fixture_id = str((fixture or {}).get('fixture_id') or '').strip() if isinstance(fixture, dict) else ''
            if fixture_id and fixture_id in targets:
                page._selector_assignments[slot_key] = None
                changed = True
        if changed:
            page._selector_selected_slots.clear()
            self.refresh_selector_slots()

    def set_selector_panel_mode(self, mode: str) -> None:
        page = self._page
        if not page._selector_active:
            page._selector_panel_mode = 'details'
            if hasattr(page, 'selector_toggle_btn'):
                page.selector_toggle_btn.setChecked(False)
            if hasattr(page, 'selector_card'):
                page.selector_card.setVisible(False)
            if hasattr(page, 'detail_card'):
                page.detail_card.setVisible(True)
            return

        target_mode = normalize_selector_mode(mode)
        page._selector_panel_mode = target_mode
        page._details_hidden = False
        page.detail_container.show()
        page.detail_header_container.show()
        if not page._last_splitter_sizes:
            page._last_splitter_sizes = default_selector_splitter_sizes(page.splitter.width())
        page.splitter.setSizes(page._last_splitter_sizes)

        if target_mode == 'details':
            page.detail_card.setVisible(True)
            page.selector_card.setVisible(False)
            if hasattr(page, '_detail_container_layout'):
                page._detail_container_layout.setStretch(0, 1)
                page._detail_container_layout.setStretch(1, 0)
            page.detail_section_label.setText(page._t('jaw_library.section.details', 'Fixture details'))
            page.selector_toggle_btn.setChecked(False)
            page.selector_toggle_btn.setText(page._t('tool_library.selector.mode_selector', 'SELECTOR'))
            return

        page.detail_card.setVisible(False)
        page.selector_card.setVisible(True)
        if hasattr(page, '_detail_container_layout'):
            page._detail_container_layout.setStretch(0, 0)
            page._detail_container_layout.setStretch(1, 1)
        page.detail_section_label.setText(page._t('tool_library.selector.selection_title', 'Selection'))
        page.selector_toggle_btn.setChecked(True)
        page.selector_toggle_btn.setText(page._t('tool_library.selector.mode_details', 'DETAILS'))

    def set_selector_context(
        self,
        active: bool,
        spindle: str = '',
        initial_assignments: list[dict] | None = None,
    ) -> None:
        page = self._page
        was_active = page._selector_active
        page._selector_active = bool(active)
        page._selector_spindle = normalize_selector_spindle(spindle)
        update_selector_spindle_ui(page)
        page.selector_toggle_btn.setVisible(page._selector_active)
        page.toggle_details_btn.setEnabled(not page._selector_active)
        page.button_bar.setVisible(not page._selector_active)
        page.selector_bottom_bar.setVisible(page._selector_active)

        if page._selector_active:
            if not was_active:
                page._selector_saved_details_hidden = page._details_hidden
            page._selector_assignments = self.selector_assignments_from_initial(initial_assignments)
            page._selector_selected_slots.clear()
            self.refresh_selector_slots()
            self.set_selector_panel_mode('selector')
            return

        page._details_hidden = page._selector_saved_details_hidden
        page._selector_assignments = slot_assignments_state(None)
        page._selector_selected_slots.clear()
        self.refresh_selector_slots()
        self.set_selector_panel_mode('details')
        page.detail_section_label.setText(page._t('jaw_library.section.details', 'Fixture details'))
        if page._details_hidden:
            page.detail_container.hide()
            page.detail_header_container.hide()
            page.splitter.setSizes([1, 0])
            return

        page.detail_container.show()
        page.detail_header_container.show()
        if not page._last_splitter_sizes:
            page._last_splitter_sizes = default_selector_splitter_sizes(page.splitter.width())
        page.splitter.setSizes(page._last_splitter_sizes)

    def selector_assigned_fixtures_for_setup_assignment(self) -> list[dict]:
        page = self._page
        payload: list[dict] = []
        for slot in ('main', 'sub'):
            normalized = self.normalize_selector_fixture(page._selector_assignments.get(slot))
            if normalized is not None:
                payload.append({**normalized, 'slot': slot})
        return payload


