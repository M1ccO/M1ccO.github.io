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
    frame, page.filter_layout = build_filter_frame()
    page.toolbar_title_label = build_toolbar_title(page, page.page_title)

    page.search_icon = QIcon(str(TOOL_ICONS_DIR / 'search_icon.svg'))
    page.close_icon = QIcon(str(TOOL_ICONS_DIR / 'close_icon.svg'))

    page.search_toggle = build_search_toggle(page.search_icon, page._toggle_search)

    page.search_input.setPlaceholderText(
        page._t(
            'tool_library.search.placeholder',
            'Search tool ID, name, dimensions, holder, insert, notes...',
        )
    )
    page.search_input.setVisible(False)

    page.toggle_details_btn = build_details_toggle(TOOL_ICONS_DIR, page.toggle_details)

    page.detail_header_container, page.detail_section_label, page.detail_close_btn = build_detail_header(
        page.close_icon,
        page._t('tool_library.section.tool_details', 'Tool details'),
        page.hide_details,
    )

    page.filter_icon = build_filter_reset(TOOL_ICONS_DIR, page._clear_filters)

    page.type_filter = QComboBox()
    page.type_filter.setObjectName('topTypeFilter')
    page.type_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
    page.type_filter.setMinimumWidth(140)
    page._build_tool_type_filter_items()
    page.type_filter.currentIndexChanged.connect(page._on_filter_changed)
    apply_shared_dropdown_style(page.type_filter)

    page.preview_window_btn = build_preview_toggle(
        TOOL_ICONS_DIR,
        page._t('tool_library.preview.toggle', 'Toggle detached 3D preview'),
        page.toggle_preview_window,
    )

    rebuild_filter_row(page)

    frame.get_filters = lambda: {
        'tool_head': page._selected_head_filter(),
        'tool_type': page.type_filter.currentData() or 'All',
    }
    return frame


def rebuild_filter_row(page) -> None:
    """Rebuild the filter toolbar row layout (called after search toggle or localization)."""
    _rebuild_filter_row_common(
        page.filter_layout,
        page.search_toggle,
        page.toggle_details_btn,
        page.search_input,
        page.filter_icon,
        [page.type_filter],
        page.preview_window_btn,
        page.detail_header_container,
    )


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
