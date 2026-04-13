"""Top toolbar builder for HomePage.

Extracted from home_page.py (Phase 10 Pass 3).
Mirrors the jaw_page_support/topbar_builder.py pattern.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from config import TOOL_ICONS_DIR

__all__ = [
    "build_tool_filter_toolbar",
    "rebuild_filter_row",
    "toggle_search",
    "clear_filters",
]


def build_tool_filter_toolbar(page) -> QFrame:
    """Build and return the filter toolbar frame for HomePage.

    Called from HomePage.build_filter_pane(). Sets up all toolbar widgets
    as page attributes and attaches get_filters() to the returned frame.
    """
    frame = QFrame()
    frame.setObjectName('filterFrame')
    frame.setProperty('card', True)

    page.filter_layout = QHBoxLayout(frame)
    page.filter_layout.setContentsMargins(56, 6, 0, 6)
    page.filter_layout.setSpacing(4)

    page.toolbar_title_label = QLabel(page.page_title)
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
        page._t(
            'tool_library.search.placeholder',
            'Search tool ID, name, dimensions, holder, insert, notes...',
        )
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

    page.detail_section_label = QLabel(page._t('tool_library.section.tool_details', 'Tool details'))
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

    page.type_filter = QComboBox()
    page.type_filter.setObjectName('topTypeFilter')
    page.type_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
    page.type_filter.setMinimumWidth(140)
    page._build_tool_type_filter_items()
    page.type_filter.currentIndexChanged.connect(page._on_filter_changed)

    page.preview_window_btn = QToolButton()
    page.preview_window_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / '3d_icon.svg')))
    page.preview_window_btn.setIconSize(QSize(28, 28))
    page.preview_window_btn.setCheckable(True)
    page.preview_window_btn.setAutoRaise(True)
    page.preview_window_btn.setProperty('topBarIconButton', True)
    page.preview_window_btn.setToolTip(page._t('tool_library.preview.toggle', 'Toggle detached 3D preview'))
    page.preview_window_btn.setFixedSize(36, 36)
    page.preview_window_btn.clicked.connect(page.toggle_preview_window)

    rebuild_filter_row(page)

    frame.get_filters = lambda: {
        'tool_head': page._selected_head_filter(),
        'tool_type': page.type_filter.currentData() or 'All',
    }
    return frame


def rebuild_filter_row(page) -> None:
    """Rebuild the filter toolbar row layout (called after search toggle or localization)."""
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
    page.filter_layout.addWidget(page.type_filter)
    page.filter_layout.addWidget(page.preview_window_btn)
    page.filter_layout.addStretch(1)
    page.filter_layout.addWidget(page.detail_header_container)


def toggle_search(page) -> None:
    """Toggle the search input bar open or closed."""
    show = page.search_toggle.isChecked()
    page.search_input.setVisible(show)
    page.search_toggle.setIcon(page.close_icon if show else page.search_icon)
    if not show:
        page.search_input.clear()
        page.refresh_list()
    rebuild_filter_row(page)
    if show:
        QTimer.singleShot(0, page.search_input.setFocus)


def clear_filters(page) -> None:
    """Reset all filter dropdowns to their default (all) state."""
    if hasattr(page, 'type_filter') and page.type_filter.count():
        page.type_filter.setCurrentIndex(0)
