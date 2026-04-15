"""Localization refresh helpers for FixturePage.

Extracted from fixture_page.py (Phase 5 Pass 8).
The single public function apply_jaw_page_localization() replaces
the large apply_localization() override in fixture_page.py.
"""

from __future__ import annotations

from typing import Callable

from ui.fixture_page_support.bottom_bars_builder import retranslate_bottom_bars
from ui.fixture_page_support.topbar_builder import retranslate_filter_toolbar

__all__ = ["apply_jaw_page_localization"]


def apply_jaw_page_localization(
    page,
    translate: Callable[[str, str | None], str] | None = None,
) -> None:
    """Refresh all user-visible strings on FixturePage after a locale change."""
    if translate is not None:
        page._translate = translate
    if hasattr(page, '_jaw_delegate'):
        page._jaw_delegate.set_translate(page._t)

    retranslate_filter_toolbar(page)
    retranslate_bottom_bars(page)

    if hasattr(page, 'selector_toggle_btn'):
        if page._selector_active and page._selector_panel_mode == 'selector':
            page.selector_toggle_btn.setText(page._t('tool_library.selector.mode_details', 'DETAILS'))
        else:
            page.selector_toggle_btn.setText(page._t('tool_library.selector.mode_selector', 'SELECTOR'))
    if hasattr(page, 'selector_hint_label'):
        page.selector_hint_label.setText(
            page._t('tool_library.selector.jaw_hint', 'Drag fixtures from the catalog to SP1 or SP2.')
        )
    if hasattr(page, 'selector_header_title_label'):
        page.selector_header_title_label.setText(page._t('jaw_library.selector.header_title', 'Fixture Selector'))
    if hasattr(page, 'selector_module_value_label'):
        page.selector_module_value_label.setText(page._t('tool_library.selector.fixtures', 'Fixtures'))
    if hasattr(page, 'selector_sp1_slot'):
        page.selector_sp1_slot.set_title(page._t('jaw_library.selector.sp1_slot', 'SP1 fixture'))
        page.selector_sp1_slot.set_drop_placeholder_text(page._t('jaw_library.selector.drop_here', 'Drop fixture here'))
    if hasattr(page, 'selector_sp2_slot'):
        page.selector_sp2_slot.set_title(page._t('jaw_library.selector.sp2_slot', 'SP2 fixture'))
        page.selector_sp2_slot.set_drop_placeholder_text(page._t('jaw_library.selector.drop_here', 'Drop fixture here'))
    if hasattr(page, 'selector_remove_btn'):
        page.selector_remove_btn.setToolTip(page._t('tool_library.selector.remove', 'Remove'))

    page._update_selector_spindle_ui()
    for mode, btn in page.view_buttons:
        btn.setText(page._nav_mode_title(mode))

    page._selector_slot_controller.refresh_selector_slots()
    page._update_selection_count_label()
    page.refresh_list()
    if page.current_jaw_id:
        page.populate_details(page.fixture_service.get_fixture(page.current_jaw_id))
    else:
        page.populate_details(None)
