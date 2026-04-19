"""Shared topbar helper primitives for catalog pages."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from shared.ui.helpers.icon_loader import icon_from_path


def build_filter_frame(*, parent: QWidget | None = None, left_margin: int = 56) -> tuple[QFrame, QHBoxLayout]:
    """Create the standard filter frame and layout shell."""
    frame = QFrame(parent)
    frame.setObjectName('filterFrame')
    frame.setProperty('card', True)

    layout = QHBoxLayout(frame)
    layout.setContentsMargins(left_margin, 6, 0, 6)
    layout.setSpacing(4)
    return frame, layout


def build_toolbar_title(page, text: str) -> QLabel:
    """Create the standard toolbar title label."""
    label = QLabel(text)
    label.setProperty('pageTitle', True)
    label.setStyleSheet('padding-left: 0px; padding-right: 20px;')
    return label


def build_search_toggle(icon: QIcon, on_clicked: Callable[[], None]) -> QToolButton:
    """Create the standard search toggle toolbutton."""
    btn = QToolButton()
    btn.setIcon(icon)
    btn.setIconSize(QSize(28, 28))
    btn.setCheckable(True)
    btn.setAutoRaise(True)
    btn.setProperty('topBarIconButton', True)
    btn.setFixedSize(36, 36)
    btn.clicked.connect(on_clicked)
    return btn


def build_details_toggle(icons_dir: Path, on_clicked: Callable[[], None]) -> QToolButton:
    """Create the standard details toggle toolbutton."""
    btn = QToolButton()
    btn.setIcon(icon_from_path(icons_dir / 'tooltip.svg', size=QSize(28, 28)))
    btn.setIconSize(QSize(28, 28))
    btn.setAutoRaise(True)
    btn.setProperty('topBarIconButton', True)
    btn.setProperty('secondaryAction', True)
    btn.setFixedSize(36, 36)
    btn.clicked.connect(on_clicked)
    return btn


def build_detail_header(
    close_icon: QIcon,
    title_text: str,
    on_close: Callable[[], None],
    *,
    parent: QWidget | None = None,
) -> tuple[QWidget, QLabel, QToolButton]:
    """Create the shared detail-header container shown in topbar."""
    container = QWidget(parent)
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)

    title = QLabel(title_text)
    title.setProperty('detailSectionTitle', True)
    title.setStyleSheet('padding: 0 2px 0 0; font-size: 18px;')
    row.addWidget(title)
    row.addStretch(1)

    close_btn = QToolButton()
    close_btn.setIcon(close_icon)
    close_btn.setIconSize(QSize(20, 20))
    close_btn.setAutoRaise(True)
    close_btn.setProperty('topBarIconButton', True)
    close_btn.setFixedSize(32, 32)
    close_btn.clicked.connect(on_close)
    row.addWidget(close_btn)

    return container, title, close_btn


def build_filter_reset(icons_dir: Path, on_clicked: Callable[[], None]) -> QToolButton:
    """Create the standard filter reset icon button."""
    btn = QToolButton()
    btn.setIcon(icon_from_path(icons_dir / 'filter_arrow_right.svg', size=QSize(28, 28)))
    btn.setIconSize(QSize(28, 28))
    btn.setAutoRaise(True)
    btn.setProperty('topBarIconButton', True)
    btn.setFixedSize(36, 36)
    btn.clicked.connect(on_clicked)
    return btn


def build_preview_toggle(icons_dir: Path, tooltip: str, on_clicked: Callable[[], None]) -> QToolButton:
    """Create the standard detached-preview toggle button."""
    btn = QToolButton()
    btn.setIcon(icon_from_path(icons_dir / '3d_icon.svg', size=QSize(28, 28)))
    btn.setIconSize(QSize(28, 28))
    btn.setCheckable(True)
    btn.setAutoRaise(True)
    btn.setProperty('topBarIconButton', True)
    btn.setToolTip(tooltip)
    btn.setFixedSize(36, 36)
    btn.clicked.connect(on_clicked)
    return btn


def rebuild_filter_row(layout: QHBoxLayout, search_toggle: QToolButton, details_toggle: QToolButton, search_widget, filter_reset: QToolButton, filter_widgets: list[QWidget], preview_toggle: QToolButton, detail_header: QWidget) -> None:
    """Rebuild common topbar row with caller-provided filter widgets."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)

    layout.addWidget(search_toggle)
    layout.addWidget(details_toggle)
    if search_widget.isVisible():
        layout.addWidget(search_widget, 1)
    layout.addWidget(filter_reset)
    for widget in filter_widgets:
        layout.addWidget(widget)
    layout.addWidget(preview_toggle)
    layout.addStretch(1)
    layout.addWidget(detail_header)
