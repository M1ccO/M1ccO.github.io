"""Top toolbar builders for FixturePage."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QComboBox, QFrame, QSizePolicy

from config import TOOL_ICONS_DIR
from shared.ui.helpers.topbar_common import (
    build_detail_header,
    build_details_toggle,
    build_filter_frame,
    build_filter_reset,
    build_preview_toggle,
    build_search_toggle,
    build_toolbar_title,
    rebuild_filter_row as _rebuild_filter_row_common,
)
from shared.ui.helpers.icon_loader import icon_from_path
from ui.widgets.common import apply_shared_dropdown_style


def populate_fixture_type_filter(page) -> None:
    current = page.fixture_type_filter.currentData() if page.fixture_type_filter.count() else 'all'
    try:
        fixture_types = page.fixture_service.list_fixture_types(page.current_view_mode)
    except Exception:
        fixture_types = []

    page._type_filter_values = ['all', *fixture_types]
    page.fixture_type_filter.blockSignals(True)
    page.fixture_type_filter.clear()
    page.fixture_type_filter.addItem(page._t('fixture_library.filter.all_types', 'All types'), 'all')
    for fixture_type in fixture_types:
        page.fixture_type_filter.addItem(fixture_type, fixture_type)
    _set_combo_value(page.fixture_type_filter, current if current in page._type_filter_values else 'all')
    page.fixture_type_filter.blockSignals(False)


def build_filter_toolbar(page) -> QFrame:
    filter_frame, page.filter_layout = build_filter_frame()

    page.toolbar_title_label = build_toolbar_title(page, page._t('tool_library.rail_title.fixtures', 'Fixtures Library'))

    page.search_icon = icon_from_path(TOOL_ICONS_DIR / 'search_icon.svg', size=QSize(28, 28))
    page.close_icon = icon_from_path(TOOL_ICONS_DIR / 'close_icon.svg', size=QSize(20, 20))

    page.search_toggle = build_search_toggle(page.search_icon, page._toggle_search)

    page.search_input.setPlaceholderText(
        page._t('fixture_library.search.placeholder', 'Search fixture ID, type, kind, diameter, work or notes')
    )
    page.search_input.setVisible(False)

    page.toggle_details_btn = build_details_toggle(TOOL_ICONS_DIR, page.toggle_details)

    page.detail_header_container, page.detail_section_label, page.detail_close_btn = build_detail_header(
        page.close_icon,
        page._t('fixture_library.section.details', 'Fixture details'),
        page.hide_details,
    )

    page.filter_icon = build_filter_reset(TOOL_ICONS_DIR, page._clear_filters)

    page.fixture_type_filter = QComboBox()
    page.fixture_type_filter.setObjectName('topTypeFilter')
    page.fixture_type_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
    page.fixture_type_filter.setMinimumWidth(80)
    page.fixture_type_filter.setProperty('dropdownSizeProfile', 'compact')
    page.fixture_type_filter.currentIndexChanged.connect(page._on_filter_changed)
    apply_shared_dropdown_style(page.fixture_type_filter)
    page.fixture_type_filter.installEventFilter(page)
    page.fixture_type_filter.view().installEventFilter(page)

    page.preview_window_btn = build_preview_toggle(
        TOOL_ICONS_DIR,
        page._t('tool_library.preview.toggle', 'Toggle detached 3D preview'),
        page.toggle_preview_window,
    )

    populate_fixture_type_filter(page)
    rebuild_filter_row(page)

    filter_frame.get_filters = lambda: {
        'view_mode': page.current_view_mode,
        'fixture_type': page.fixture_type_filter.currentData() or 'all',
    }
    return filter_frame


def rebuild_filter_row(page) -> None:
    _rebuild_filter_row_common(
        page.filter_layout,
        page.search_toggle,
        page.toggle_details_btn,
        page.search_input,
        page.filter_icon,
        [page.fixture_type_filter],
        page.preview_window_btn,
        page.detail_header_container,
    )


def retranslate_filter_toolbar(page) -> None:
    page.toolbar_title_label.setText(page._t('tool_library.rail_title.fixtures', 'Fixtures Library'))
    page.search_input.setPlaceholderText(
        page._t('fixture_library.search.placeholder', 'Search fixture ID, type, kind, diameter, work or notes')
    )
    page.detail_section_label.setText(
        page._t('tool_library.selector.selection_title', 'Selection')
        if page._selector_active and page._selector_panel_mode == 'selector'
        else page._t('fixture_library.section.details', 'Fixture details')
    )
    page.preview_window_btn.setToolTip(page._t('tool_library.preview.toggle', 'Toggle detached 3D preview'))
    populate_fixture_type_filter(page)
    _update_filter_icon(page)
    rebuild_filter_row(page)


def _set_combo_value(combo: QComboBox, value: str) -> None:
    for index in range(combo.count()):
        if combo.itemData(index) == value:
            combo.setCurrentIndex(index)
            return
    if combo.count():
        combo.setCurrentIndex(0)


def _update_filter_icon(page) -> None:
    active = (page.fixture_type_filter.currentData() or 'all') != 'all'
    icon_name = 'filter_off.svg' if active else 'filter_arrow_right.svg'
    page.filter_icon.setIcon(icon_from_path(TOOL_ICONS_DIR / icon_name, size=QSize(28, 28)))


__all__ = [
    'build_filter_toolbar',
    'populate_fixture_type_filter',
    'rebuild_filter_row',
    'retranslate_filter_toolbar',
]
