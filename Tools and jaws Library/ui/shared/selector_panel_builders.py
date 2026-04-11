from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from shared.editor_helpers import style_icon_action_button, style_panel_action_button


def build_selector_card_shell(
    *,
    spacing: int = 6,
) -> tuple[QFrame, QScrollArea, QWidget, QVBoxLayout]:
    """Create the shared selector card -> scroll -> panel shell."""
    selector_card = QFrame()
    selector_card.setProperty("card", True)
    selector_card.setProperty("selectorContext", True)
    selector_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    selector_card.setVisible(False)

    selector_scroll = QScrollArea()
    selector_scroll.setWidgetResizable(True)
    selector_scroll.setFrameShape(QFrame.NoFrame)
    selector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    selector_panel = QWidget()
    selector_panel.setProperty("selectorPanel", True)
    selector_panel.setMinimumWidth(0)
    selector_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    selector_layout = QVBoxLayout(selector_panel)
    selector_layout.setContentsMargins(10, 10, 10, 10)
    selector_layout.setSpacing(spacing)
    return selector_card, selector_scroll, selector_panel, selector_layout


def build_selector_info_header(
    *,
    title_text: str,
    left_badge_text: str,
    right_badge_text: str,
    fixed_height_policy: bool = False,
) -> tuple[QFrame, QLabel, QLabel, QLabel]:
    """Build the common selector info header with centered title and two badges."""
    selector_info_header = QFrame()
    selector_info_header.setProperty("detailHeader", True)
    selector_info_header.setProperty("selectorInfoHeader", True)
    if fixed_height_policy:
        selector_info_header.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    selector_info_layout = QVBoxLayout(selector_info_header)
    selector_info_layout.setContentsMargins(14, 14, 14, 12)
    selector_info_layout.setSpacing(4)

    title_row = QHBoxLayout()
    title_row.setContentsMargins(0, 0, 0, 0)
    title_row.setSpacing(0)
    title_row.addStretch(1)
    selector_header_title_label = QLabel(title_text)
    selector_header_title_label.setProperty("selectorInfoTitle", True)
    selector_header_title_label.setAlignment(Qt.AlignCenter)
    title_row.addWidget(selector_header_title_label, 0, Qt.AlignCenter)
    title_row.addStretch(1)
    selector_info_layout.addLayout(title_row)

    badge_row = QHBoxLayout()
    badge_row.setContentsMargins(0, 0, 0, 0)
    badge_row.setSpacing(10)
    left_badge_label = QLabel(left_badge_text)
    left_badge_label.setProperty("toolBadge", True)
    badge_row.addWidget(left_badge_label, 0, Qt.AlignLeft)
    badge_row.addStretch(1)
    right_badge_label = QLabel(right_badge_text)
    right_badge_label.setProperty("toolBadge", True)
    badge_row.addWidget(right_badge_label, 0, Qt.AlignRight)
    selector_info_layout.addLayout(badge_row)

    return selector_info_header, selector_header_title_label, left_badge_label, right_badge_label


def build_selector_toggle_button(
    *,
    text: str,
    on_clicked: Callable[[], None] | None = None,
) -> QPushButton:
    toggle_btn = QPushButton(text)
    toggle_btn.setProperty("panelActionButton", True)
    toggle_btn.setFixedHeight(30)
    toggle_btn.setMinimumWidth(120)
    toggle_btn.setMaximumWidth(140)
    toggle_btn.setCheckable(True)
    toggle_btn.setChecked(True)
    toggle_btn.setVisible(False)
    if on_clicked is not None:
        toggle_btn.clicked.connect(on_clicked)
    style_panel_action_button(toggle_btn)
    return toggle_btn


def build_selector_hint_label(
    *,
    text: str,
    multiline: bool = False,
) -> QLabel:
    hint_label = QLabel(text)
    hint_label.setWordWrap(multiline)
    hint_label.setProperty("detailHint", True)
    if not multiline:
        hint_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hint_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hint_label.setFixedHeight(24)
        hint_label.setStyleSheet("margin: 0px; padding: 0px; background: transparent;")
    return hint_label


def build_selector_actions_row(*, spacing: int = 4) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(spacing)
    return row


def apply_selector_icon_button(
    button: QPushButton,
    *,
    icon_path,
    tooltip: str,
    danger: bool = False,
) -> None:
    style_icon_action_button(button, icon_path, tooltip, danger=danger)
