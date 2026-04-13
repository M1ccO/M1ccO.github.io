"""Top toolbar builders for JawPage."""

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
from ui.widgets.common import apply_shared_dropdown_style


def populate_jaw_type_filter(page) -> None:
    current = page.jaw_type_filter.currentData() if page.jaw_type_filter.count() else 'all'
    page.jaw_type_filter.blockSignals(True)
    page.jaw_type_filter.clear()
    page.jaw_type_filter.addItem(page._t('jaw_library.filter.all', 'All'), 'all')
    page.jaw_type_filter.addItem(page._t('jaw_library.filter.soft_jaws', 'Soft Jaws'), 'soft')
    page.jaw_type_filter.addItem(page._t('jaw_library.filter.hard_spiked', 'Spike/Hard Jaws'), 'hard_group')
    page.jaw_type_filter.addItem(page._t('jaw_library.filter.special_jaws', 'Special Jaws'), 'special')
    _set_combo_value(page.jaw_type_filter, current if current in page._type_filter_values else 'all')
    page.jaw_type_filter.blockSignals(False)


def populate_spindle_filter(page) -> None:
    current = page.spindle_filter.currentData() if page.spindle_filter.count() else 'all'
    profile = getattr(page, 'machine_profile', None)
    profile_spindles = []
    if isinstance(profile, dict):
        profile_spindles = profile.get('spindles') or []
    elif profile is not None:
        profile_spindles = getattr(profile, 'spindles', ()) or ()

    spindle_keys: list[str] = []
    for spindle in profile_spindles:
        if isinstance(spindle, dict):
            key = str(spindle.get('key') or '').strip().lower()
        else:
            key = str(getattr(spindle, 'key', '') or '').strip().lower()
        if key and key not in spindle_keys:
            spindle_keys.append(key)
    if not spindle_keys:
        spindle_keys = ['main', 'sub']

    page.spindle_filter.blockSignals(True)
    page.spindle_filter.clear()
    page.spindle_filter.addItem(page._t('jaw_library.filter.spindle_all', 'All spindles'), 'all')
    for spindle_key in spindle_keys:
        if spindle_key == 'main':
            label = page._t('jaw_library.filter.main_spindle', 'Main spindle')
        elif spindle_key == 'sub':
            label = page._t('jaw_library.filter.sub_spindle', 'Sub spindle')
        else:
            label = spindle_key.upper()
        page.spindle_filter.addItem(label, spindle_key)
    allowed = {'all', *spindle_keys}
    _set_combo_value(page.spindle_filter, current if current in allowed else 'all')
    page.spindle_filter.blockSignals(False)


def build_filter_toolbar(page) -> QFrame:
    filter_frame, page.filter_layout = build_filter_frame()

    page.toolbar_title_label = build_toolbar_title(page, page._t('tool_library.rail_title.jaws', 'Jaws Library'))

    page.search_icon = QIcon(str(TOOL_ICONS_DIR / 'search_icon.svg'))
    page.close_icon = QIcon(str(TOOL_ICONS_DIR / 'close_icon.svg'))

    page.search_toggle = build_search_toggle(page.search_icon, page._toggle_search)

    page.search_input.setPlaceholderText(
        page._t('jaw_library.search.placeholder', 'Search jaw ID, type, spindle, diameter, work, washer or notes')
    )
    page.search_input.setVisible(False)

    page.toggle_details_btn = build_details_toggle(TOOL_ICONS_DIR, page.toggle_details)

    page.detail_header_container, page.detail_section_label, page.detail_close_btn = build_detail_header(
        page.close_icon,
        page._t('jaw_library.section.details', 'Jaw details'),
        page.hide_details,
    )

    page.filter_icon = build_filter_reset(TOOL_ICONS_DIR, page._clear_filters)

    page.jaw_type_filter = QComboBox()
    page.jaw_type_filter.setObjectName('topTypeFilter')
    page.jaw_type_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
    page.jaw_type_filter.setMinimumWidth(80)
    page.jaw_type_filter.setProperty('dropdownSizeProfile', 'compact')
    page.jaw_type_filter.currentIndexChanged.connect(page._on_filter_changed)
    apply_shared_dropdown_style(page.jaw_type_filter)
    page.jaw_type_filter.installEventFilter(page)
    page.jaw_type_filter.view().installEventFilter(page)

    page.spindle_filter = QComboBox()
    page.spindle_filter.setObjectName('topSpindleFilter')
    page.spindle_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
    page.spindle_filter.setMinimumWidth(120)
    page.spindle_filter.setProperty('dropdownSizeProfile', 'compact')
    page.spindle_filter.currentIndexChanged.connect(page._on_filter_changed)
    apply_shared_dropdown_style(page.spindle_filter)
    page.spindle_filter.installEventFilter(page)
    page.spindle_filter.view().installEventFilter(page)

    page.preview_window_btn = build_preview_toggle(
        TOOL_ICONS_DIR,
        page._t('tool_library.preview.toggle', 'Toggle detached 3D preview'),
        page.toggle_preview_window,
    )

    populate_jaw_type_filter(page)
    populate_spindle_filter(page)
    rebuild_filter_row(page)

    filter_frame.get_filters = lambda: {
        'view_mode': page.current_view_mode,
        'jaw_type': page.jaw_type_filter.currentData() or 'all',
        'spindle_filter': page.spindle_filter.currentData() or 'all',
    }
    return filter_frame


def rebuild_filter_row(page) -> None:
    _rebuild_filter_row_common(
        page.filter_layout,
        page.search_toggle,
        page.toggle_details_btn,
        page.search_input,
        page.filter_icon,
        [page.jaw_type_filter, page.spindle_filter],
        page.preview_window_btn,
        page.detail_header_container,
    )


def retranslate_filter_toolbar(page) -> None:
    page.toolbar_title_label.setText(page._t('tool_library.rail_title.jaws', 'Jaws Library'))
    page.search_input.setPlaceholderText(
        page._t('jaw_library.search.placeholder', 'Search jaw ID, type, spindle, diameter, work, washer or notes')
    )
    page.detail_section_label.setText(
        page._t('tool_library.selector.selection_title', 'Selection')
        if page._selector_active and page._selector_panel_mode == 'selector'
        else page._t('jaw_library.section.details', 'Jaw details')
    )
    page.preview_window_btn.setToolTip(page._t('tool_library.preview.toggle', 'Toggle detached 3D preview'))
    populate_jaw_type_filter(page)
    populate_spindle_filter(page)
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
    active = (page.jaw_type_filter.currentData() or 'all') != 'all' or (page.spindle_filter.currentData() or 'all') != 'all'
    icon_name = 'filter_off.svg' if active else 'filter_arrow_right.svg'
    page.filter_icon.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))


__all__ = [
    'build_filter_toolbar',
    'populate_jaw_type_filter',
    'populate_spindle_filter',
    'rebuild_filter_row',
    'retranslate_filter_toolbar',
]