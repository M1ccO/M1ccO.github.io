from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QToolButton, QVBoxLayout
from shared.ui.layout_contract import get_container_layout_contract

def build_rail_header_section(window) -> QFrame:
    """Build the rail header/title section container."""
    contract = get_container_layout_contract()
    section = QFrame()
    section.setObjectName("toolRailHeaderSection")
    layout = QVBoxLayout(section)
    layout.setContentsMargins(*contract.rail_header_inner_margins)
    layout.setSpacing(0)

    title_text = window._t("tool_library.rail_title.tools", "Tool Library")
    window.rail_title = QLabel(title_text)
    window.rail_title.setStyleSheet(
        f'color: #000000; font-size: {contract.rail_header_font_pt}pt; font-weight: 700;'
    )
    window.rail_title.setToolTip('')
    window.rail_title.setWordWrap(False)
    window.rail_title.setFixedHeight(contract.rail_header_height)
    window.rail_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    layout.addWidget(window.rail_title)
    return section


def build_head_nav_section(window) -> QFrame:
    """Build the profile-driven head-button section container."""
    contract = get_container_layout_contract()
    section = QFrame()
    section.setObjectName("toolRailHeadNavSection")
    layout = QVBoxLayout(section)
    layout.setContentsMargins(0, contract.rail_nav_section_top_inset, 0, 0)
    layout.setSpacing(8)

    window._head_nav_layout = layout
    window._head_nav_buttons = []
    window._rebuild_head_nav_buttons()
    return section


def build_footer_actions_section(window) -> QFrame:
    """Build the lower helper/actions section container."""
    contract = get_container_layout_contract()
    section = QFrame()
    section.setObjectName("toolRailFooterSection")
    section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    section.setMinimumWidth(0)
    section_layout = QVBoxLayout(section)
    section_layout.setContentsMargins(0, 0, 0, 0)
    section_layout.setSpacing(0)

    window.footer_actions = QFrame()
    window.footer_actions.setObjectName('railFooterActions')
    window.footer_actions.setProperty('launchCard', True)
    window.footer_actions.setFixedWidth(contract.rail_footer_card_width)
    window.footer_actions.setMinimumHeight(contract.rail_footer_card_min_height)
    footer_layout = QVBoxLayout(window.footer_actions)
    footer_layout.setContentsMargins(12, 12, 12, 12)
    footer_layout.setSpacing(8)

    launch_title = QLabel(window._t("tool_library.launch.title", "Kirjastot"))
    launch_title.setProperty('sectionTitle', True)
    launch_title.setAlignment(Qt.AlignHCenter)
    footer_layout.addWidget(launch_title, 0, Qt.AlignHCenter)

    launch_body = QLabel(window._t("tool_library.launch.hint", "Switch between libraries"))
    launch_body.setProperty('navHint', True)
    launch_body.setWordWrap(True)
    launch_body.setAlignment(Qt.AlignHCenter)
    launch_body.setMaximumHeight(48)
    footer_layout.addWidget(launch_body, 0, Qt.AlignHCenter)

    window.module_toggle_btn = QPushButton(window._t("tool_library.launch.jaws", "LEUAT"))
    window.module_toggle_btn.setProperty('panelActionButton', True)
    window.module_toggle_btn.setProperty('sidebarLaunchButton', True)
    window.module_toggle_btn.setMinimumWidth(154)
    window.module_toggle_btn.clicked.connect(window._on_module_toggle_clicked)
    footer_layout.addWidget(window.module_toggle_btn, 0, Qt.AlignHCenter)

    # Keep old names as aliases for API compat (pages may hold references)
    window.open_tools_btn = window.module_toggle_btn
    window.open_jaws_btn = window.module_toggle_btn

    window.master_filter_toggle = QToolButton()
    window.master_filter_toggle.setObjectName('masterFilterToggle')
    window.master_filter_toggle.setProperty('topBarIconButton', True)
    window.master_filter_toggle.setCheckable(True)
    window.master_filter_toggle.setAutoRaise(True)
    window.master_filter_toggle.setFixedSize(48, 48)
    window.master_filter_toggle.setIconSize(QSize(36, 36))
    window.master_filter_toggle.setIcon(window._icon_by_name('filter_off.svg', QSize(42, 42)))
    window.master_filter_toggle.setToolTip(window._t("tool_library.master_filter.button", "MASTER FILTER"))
    window.master_filter_toggle.setVisible(window._master_filter_enabled)
    window.master_filter_toggle.clicked.connect(window._on_master_filter_toggled)
    if window._master_filter_enabled:
        footer_layout.addWidget(window.master_filter_toggle, 0, Qt.AlignHCenter)

    window.back_to_setup_btn = QToolButton()
    window.back_to_setup_btn.setProperty('topBarIconButton', True)
    window.back_to_setup_btn.setIcon(window._icon_by_name('home_icon.svg', QSize(34, 34)))
    window.back_to_setup_btn.setIconSize(QSize(34, 34))
    window.back_to_setup_btn.setFixedSize(38, 38)
    window.back_to_setup_btn.setAutoRaise(True)
    window.back_to_setup_btn.setCursor(Qt.PointingHandCursor)
    window.back_to_setup_btn.setToolTip(window._t("tool_library.back_to_setup_tip", "Switch back to Setup Manager"))
    window.back_to_setup_btn.clicked.connect(window._back_to_setup_manager)
    footer_layout.addWidget(window.back_to_setup_btn, 0, Qt.AlignHCenter)

    window.footer_actions.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    section_layout.addStretch(1)
    section_layout.addWidget(window.footer_actions, 0, Qt.AlignHCenter | Qt.AlignBottom)
    return section