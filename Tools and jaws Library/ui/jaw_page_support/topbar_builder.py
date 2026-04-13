"""Top toolbar builders for JawPage."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget

from config import TOOL_ICONS_DIR
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
    filter_frame = QFrame()
    filter_frame.setObjectName('filterFrame')
    filter_frame.setProperty('card', True)

    page.filter_layout = QHBoxLayout(filter_frame)
    page.filter_layout.setContentsMargins(56, 6, 0, 6)
    page.filter_layout.setSpacing(4)

    page.toolbar_title_label = QLabel(page._t('tool_library.rail_title.jaws', 'Jaws Library'))
    page.toolbar_title_label.setProperty('pageTitle', True)
    page.toolbar_title_label.setStyleSheet('padding-left: 0px; padding-right: 20px;')

    page.search_icon = QIcon(str(TOOL_ICONS_DIR / 'search_icon.svg'))
    page.close_icon = QIcon(str(TOOL_ICONS_DIR / 'close_icon.svg'))

    page.search_toggle = QToolButton()
    page.search_toggle.setIcon(page.search_icon)
    page.search_toggle.setIconSize(QSize(28, 28))
    page.search_toggle.setCheckable(True)
    page.search_toggle.setAutoRaise(True)
    page.search_toggle.setProperty('topBarIconButton', True)
    page.search_toggle.setFixedSize(36, 36)
    page.search_toggle.clicked.connect(page._toggle_search)

    page.search_input.setPlaceholderText(
        page._t('jaw_library.search.placeholder', 'Search jaw ID, type, spindle, diameter, work, washer or notes')
    )
    page.search_input.setVisible(False)

    page.toggle_details_btn = QToolButton()
    page.toggle_details_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / 'tooltip.svg')))
    page.toggle_details_btn.setIconSize(QSize(28, 28))
    page.toggle_details_btn.setAutoRaise(True)
    page.toggle_details_btn.setProperty('topBarIconButton', True)
    page.toggle_details_btn.setProperty('secondaryAction', True)
    page.toggle_details_btn.setFixedSize(36, 36)
    page.toggle_details_btn.clicked.connect(page.toggle_details)

    page.detail_header_container = QWidget()
    detail_top = QHBoxLayout(page.detail_header_container)
    detail_top.setContentsMargins(0, 0, 0, 0)
    detail_top.setSpacing(6)

    page.detail_section_label = QLabel(page._t('jaw_library.section.details', 'Jaw details'))
    page.detail_section_label.setProperty('detailSectionTitle', True)
    page.detail_section_label.setStyleSheet('padding: 0 2px 0 0; font-size: 18px;')
    detail_top.addWidget(page.detail_section_label)
    detail_top.addStretch(1)

    page.detail_close_btn = QToolButton()
    page.detail_close_btn.setIcon(page.close_icon)
    page.detail_close_btn.setIconSize(QSize(20, 20))
    page.detail_close_btn.setAutoRaise(True)
    page.detail_close_btn.setProperty('topBarIconButton', True)
    page.detail_close_btn.setFixedSize(32, 32)
    page.detail_close_btn.clicked.connect(page.hide_details)
    detail_top.addWidget(page.detail_close_btn)

    page.filter_icon = QToolButton()
    page.filter_icon.setIcon(QIcon(str(TOOL_ICONS_DIR / 'filter_arrow_right.svg')))
    page.filter_icon.setIconSize(QSize(28, 28))
    page.filter_icon.setAutoRaise(True)
    page.filter_icon.setProperty('topBarIconButton', True)
    page.filter_icon.setFixedSize(36, 36)
    page.filter_icon.clicked.connect(page._clear_filters)

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

    page.preview_window_btn = QToolButton()
    page.preview_window_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / '3d_icon.svg')))
    page.preview_window_btn.setIconSize(QSize(28, 28))
    page.preview_window_btn.setCheckable(True)
    page.preview_window_btn.setAutoRaise(True)
    page.preview_window_btn.setProperty('topBarIconButton', True)
    page.preview_window_btn.setToolTip(page._t('tool_library.preview.toggle', 'Toggle detached 3D preview'))
    page.preview_window_btn.setFixedSize(36, 36)
    page.preview_window_btn.clicked.connect(page.toggle_preview_window)

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
    while page.filter_layout.count():
        item = page.filter_layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)

    page.filter_layout.addWidget(page.search_toggle)
    page.filter_layout.addWidget(page.toggle_details_btn)
    if page.search_input.isVisible():
        page.filter_layout.addWidget(page.search_input, 1)
    page.filter_layout.addWidget(page.filter_icon)
    page.filter_layout.addWidget(page.jaw_type_filter)
    page.filter_layout.addWidget(page.spindle_filter)
    page.filter_layout.addWidget(page.preview_window_btn)
    page.filter_layout.addStretch(1)
    page.filter_layout.addWidget(page.detail_header_container)


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