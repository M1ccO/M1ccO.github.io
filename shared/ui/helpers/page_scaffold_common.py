"""Shared scaffold helpers for catalog page layout builders."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLineEdit, QListView, QScrollArea, QSplitter, QVBoxLayout, QWidget


def build_page_root(page, *, spacing: int = 10) -> QVBoxLayout:
    """Create the standard page root layout shell."""
    root = QVBoxLayout(page)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(spacing)
    return root


def build_search_input(page) -> QLineEdit:
    """Create the standard search input wired to refresh_list."""
    search_input = QLineEdit()
    search_input.textChanged.connect(page.refresh_list)
    return search_input


def build_catalog_splitter(left: QWidget, right: QWidget) -> QSplitter:
    """Create the standard horizontal splitter for list/detail panes."""
    splitter = QSplitter(Qt.Horizontal)
    splitter.setHandleWidth(1)
    splitter.setChildrenCollapsible(False)
    splitter.addWidget(left)
    splitter.addWidget(right)
    return splitter


def build_catalog_list_shell(*, parent: QWidget | None = None) -> tuple[QFrame, QVBoxLayout]:
    """Create a card shell used by catalog list panes."""
    list_card = QFrame(parent)
    list_card.setProperty('catalogShell', True)
    list_layout = QVBoxLayout(list_card)
    list_layout.setContentsMargins(0, 0, 0, 0)
    list_layout.setSpacing(10)
    return list_card, list_layout


def apply_catalog_list_view_defaults(list_view: QListView) -> None:
    """Apply shared styling and interaction defaults for catalog list views."""
    list_view.setObjectName('toolCatalog')
    list_view.setVerticalScrollMode(QListView.ScrollPerPixel)
    list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    list_view.setEditTriggers(QListView.NoEditTriggers)
    list_view.setSelectionMode(QListView.ExtendedSelection)
    list_view.setDragEnabled(True)
    list_view.setMouseTracking(True)
    list_view.setStyleSheet(
        'QListView#toolCatalog { border: none; outline: none; padding: 8px; }'
        ' QListView#toolCatalog::item { background: transparent; border: none; }'
    )
    list_view.setSpacing(4)
    list_view.setUniformItemSizes(True)


def install_catalog_list_event_filters(list_view: QListView, page) -> None:
    """Install standard page event filters for list views."""
    list_view.installEventFilter(page)
    list_view.viewport().installEventFilter(page)


def build_detail_container_shell(
    *,
    min_width: int = 280,
    detail_spacing: int = 10,
    parent: QWidget | None = None,
) -> tuple[QWidget, QVBoxLayout, QFrame, QScrollArea, QWidget, QVBoxLayout]:
    """Create detail container + card + scroll + panel shell."""
    detail_container = QWidget(parent)
    detail_container.setMinimumWidth(min_width)

    detail_layout = QVBoxLayout(detail_container)
    detail_layout.setContentsMargins(0, 0, 0, 0)
    detail_layout.setSpacing(0)

    detail_card = QFrame(detail_container)
    detail_card.setProperty('card', True)
    detail_card_layout = QVBoxLayout(detail_card)
    detail_card_layout.setContentsMargins(0, 0, 0, 0)
    detail_card_layout.setSpacing(0)

    detail_scroll = QScrollArea(detail_card)
    detail_scroll.setObjectName('detailScrollArea')
    detail_scroll.setWidgetResizable(True)
    detail_scroll.setFrameShape(QFrame.NoFrame)
    detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    detail_panel = QWidget(detail_scroll)
    detail_panel.setObjectName('detailPanel')
    panel_layout = QVBoxLayout(detail_panel)
    panel_layout.setContentsMargins(0, 0, 0, 0)
    panel_layout.setSpacing(detail_spacing)

    detail_scroll.setWidget(detail_panel)
    detail_card_layout.addWidget(detail_scroll, 1)
    detail_layout.addWidget(detail_card, 1)

    return detail_container, detail_layout, detail_card, detail_scroll, detail_panel, panel_layout
