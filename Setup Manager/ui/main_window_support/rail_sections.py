from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QToolButton, QVBoxLayout
from shared.ui.layout_contract import get_container_layout_contract

def build_rail_header_section(window) -> QFrame:
    """Build the header/title section container for the left rail."""
    contract = get_container_layout_contract()
    section = QFrame()
    section.setObjectName("setupRailHeaderSection")
    layout = QVBoxLayout(section)
    layout.setContentsMargins(*contract.rail_header_inner_margins)
    layout.setSpacing(0)

    title_text = window._t("setup_manager.rail_title", "Setup Manager")
    window.rail_title_label = QLabel(title_text)
    window.rail_title_label.setStyleSheet(
        f"color: #000000; font-size: {contract.rail_header_font_pt}pt; font-weight: 700;"
    )
    window.rail_title_label.setToolTip("")
    window.rail_title_label.setWordWrap(False)
    window.rail_title_label.setFixedHeight(contract.rail_header_height)
    window.rail_title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    layout.addWidget(window.rail_title_label)
    return section


def build_primary_nav_section(
    window,
    *,
    nav_items: list[str],
    on_nav_click: Callable[[int], None],
) -> QFrame:
    """Build the primary nav-button section container for the left rail."""
    contract = get_container_layout_contract()
    section = QFrame()
    section.setObjectName("setupRailPrimaryNavSection")
    layout = QVBoxLayout(section)
    layout.setContentsMargins(0, contract.rail_nav_section_top_inset, 0, 0)
    layout.setSpacing(8)

    window.nav_buttons = []
    for index, fallback_text in enumerate(nav_items):
        key = (
            "setup_manager.nav.setups"
            if index == 0
            else "setup_manager.nav.drawings"
            if index == 1
            else "setup_manager.nav.logbook"
        )
        button = QPushButton(window._t(key, fallback_text))
        button.setProperty("navButton", True)
        button.clicked.connect(lambda checked=False, i=index: on_nav_click(i))
        layout.addWidget(button)
        window.nav_buttons.append(button)

    return section


def build_footer_actions_section(
    window,
    *,
    tool_icons_dir,
    on_open_tools: Callable[[], None],
    on_open_jaws: Callable[[], None],
    on_open_preferences: Callable[[], None],
) -> QFrame:
    """Build the lower helper/actions section container for the left rail."""
    contract = get_container_layout_contract()
    section = QFrame()
    section.setObjectName("setupRailFooterSection")
    section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    section.setMinimumWidth(0)
    section_layout = QVBoxLayout(section)
    section_layout.setContentsMargins(0, 0, 0, 0)
    section_layout.setSpacing(0)

    launch_card = QFrame()
    launch_card.setProperty("launchCard", True)
    launch_card.setFixedWidth(contract.rail_footer_card_width)
    launch_card.setMinimumHeight(contract.rail_footer_card_min_height)
    launch_layout = QVBoxLayout(launch_card)
    launch_layout.setContentsMargins(12, 12, 12, 12)
    launch_layout.setSpacing(8)

    window.launch_title = QLabel(window._t("setup_manager.launch.title", "Master Data"))
    window.launch_title.setProperty("sectionTitle", True)
    window.launch_title.setAlignment(Qt.AlignHCenter)
    window.launch_body = QLabel(
        window._t(
            "setup_manager.launch.default_body",
            "Open Tool Library or Jaws Library. Select a work in Setup to open filtered data.",
        )
    )
    window.launch_body.setWordWrap(True)
    window.launch_body.setProperty("navHint", True)
    window.launch_body.setAlignment(Qt.AlignHCenter)

    window.open_tools_btn = QPushButton(window._t("setup_manager.open_tool_library", "Open Tool Library"))
    window.open_tools_btn.setProperty("panelActionButton", True)
    window.open_tools_btn.setProperty("sidebarLaunchButton", True)
    window.open_tools_btn.setMinimumWidth(154)
    window.open_tools_btn.clicked.connect(on_open_tools)

    window.open_jaws_btn = QPushButton(window._t("setup_manager.open_jaws_library", "Open Jaws Library"))
    window.open_jaws_btn.setProperty("panelActionButton", True)
    window.open_jaws_btn.setProperty("sidebarLaunchButton", True)
    window.open_jaws_btn.setMinimumWidth(154)
    window.open_jaws_btn.clicked.connect(on_open_jaws)

    window.preferences_btn = QToolButton()
    window.preferences_btn.setProperty("topBarIconButton", True)
    window.preferences_btn.setIcon(QIcon(str(Path(tool_icons_dir) / "menu_icon.svg")))
    window.preferences_btn.setIconSize(QSize(30, 30))
    window.preferences_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
    window.preferences_btn.setFixedSize(38, 38)
    window.preferences_btn.setAutoRaise(True)
    window.preferences_btn.setToolTip(window._t("common.preferences", "Preferences"))
    window.preferences_btn.clicked.connect(on_open_preferences)

    launch_layout.addWidget(window.launch_title, 0, Qt.AlignHCenter)
    launch_layout.addWidget(window.launch_body, 0, Qt.AlignHCenter)
    launch_layout.addWidget(window.open_tools_btn, 0, Qt.AlignHCenter)
    launch_layout.addWidget(window.open_jaws_btn, 0, Qt.AlignHCenter)
    launch_layout.addWidget(window.preferences_btn, 0, Qt.AlignHCenter)

    launch_card.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    section_layout.addStretch(1)
    section_layout.addWidget(launch_card, 0, Qt.AlignHCenter | Qt.AlignBottom)
    return section