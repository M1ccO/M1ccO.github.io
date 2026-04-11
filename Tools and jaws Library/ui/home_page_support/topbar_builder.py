"""Top toolbar and catalog panel builders for HomePage."""

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QListView, QSizePolicy, QToolButton, QVBoxLayout

from ui.widgets.common import add_shadow, apply_shared_dropdown_style


def build_filter_toolbar(page, *, tool_icons_dir):
    """Create the filter/top toolbar row and bind existing page callbacks."""
    filter_frame = QFrame()
    filter_frame.setObjectName("filterFrame")
    filter_frame.setProperty("card", True)
    page.filter_layout = QHBoxLayout(filter_frame)
    # Left margin must clear the absolutely-positioned rail title from main window.
    page.filter_layout.setContentsMargins(108, 6, 0, 6)
    page.filter_layout.setSpacing(4)

    page.toolbar_title_label = QLabel(page.page_title)
    page.toolbar_title_label.setProperty("pageTitle", True)
    page.toolbar_title_label.setStyleSheet("padding-left: 0px; padding-right: 20px;")

    page.search_toggle = QToolButton()
    page.search_icon = QIcon(str(tool_icons_dir / "search_icon.svg"))
    page.close_icon = QIcon(str(tool_icons_dir / "close_icon.svg"))
    page.search_toggle.setIcon(page.search_icon)
    page.search_toggle.setIconSize(QSize(28, 28))
    page.search_toggle.setCheckable(True)
    page.search_toggle.setAutoRaise(True)
    page.search_toggle.setProperty("topBarIconButton", True)
    page.search_toggle.setFixedSize(36, 36)
    page.search_toggle.clicked.connect(page._toggle_search)

    page.toggle_details_btn = QToolButton()
    page.toggle_details_btn.setIcon(QIcon(str(tool_icons_dir / "tooltip.svg")))
    page.toggle_details_btn.setIconSize(QSize(28, 28))
    page.toggle_details_btn.setAutoRaise(True)
    page.toggle_details_btn.setProperty("topBarIconButton", True)
    page.toggle_details_btn.setProperty("secondaryAction", True)
    page.toggle_details_btn.setFixedSize(36, 36)
    page.toggle_details_btn.clicked.connect(page.toggle_details)

    page.search = QLineEdit()
    page.search.setPlaceholderText(
        page._t("tool_library.search.placeholder", "Tool ID, description, holder or cutting code")
    )
    page.search.textChanged.connect(page.refresh_list)
    page.search.setVisible(False)
    page.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    page.search.setMaximumWidth(300)

    page.filter_icon = QToolButton()
    page.filter_icon.setIcon(QIcon(str(tool_icons_dir / "filter_arrow_right.svg")))
    page.filter_icon.setIconSize(QSize(28, 28))
    page.filter_icon.setAutoRaise(True)
    page.filter_icon.setProperty("topBarIconButton", True)
    page.filter_icon.setFixedSize(36, 36)
    page.filter_icon.clicked.connect(page._clear_filter)

    page.type_filter = page._build_type_filter_widget()
    add_shadow(page.type_filter)
    page.type_filter.installEventFilter(page)
    page.type_filter.view().installEventFilter(page)
    apply_shared_dropdown_style(page.type_filter)

    page.preview_window_btn = QToolButton()
    page.preview_window_btn.setIcon(QIcon(str(tool_icons_dir / "3d_icon.svg")))
    page.preview_window_btn.setIconSize(QSize(28, 28))
    page.preview_window_btn.setAutoRaise(True)
    page.preview_window_btn.setProperty("topBarIconButton", True)
    page.preview_window_btn.setCheckable(True)
    page.preview_window_btn.setToolTip(page._t("tool_library.preview.toggle", "Toggle detached 3D preview"))
    page.preview_window_btn.setFixedSize(36, 36)
    page.preview_window_btn.clicked.connect(page.toggle_preview_window)

    page.detail_header_container = build_detail_header(page)
    page._rebuild_filter_row()
    return filter_frame


def build_detail_header(page):
    detail_header_container = QFrame()
    detail_top = QHBoxLayout(detail_header_container)
    detail_top.setContentsMargins(0, 0, 0, 0)
    detail_top.setSpacing(6)
    page.detail_section_label = QLabel(page._t("tool_library.section.tool_details", "Tool details"))
    page.detail_section_label.setProperty("detailSectionTitle", True)
    page.detail_section_label.setStyleSheet("padding: 0 2px 0 0; font-size: 18px;")
    detail_top.addWidget(page.detail_section_label)
    detail_top.addStretch(1)

    page.detail_close_btn = QToolButton()
    page.detail_close_btn.setIcon(page.close_icon)
    page.detail_close_btn.setIconSize(QSize(20, 20))
    page.detail_close_btn.setAutoRaise(True)
    page.detail_close_btn.setProperty("topBarIconButton", True)
    page.detail_close_btn.setFixedSize(32, 32)
    page.detail_close_btn.clicked.connect(page.hide_details)
    detail_top.addWidget(page.detail_close_btn)
    return detail_header_container


def build_catalog_list_panel(
    page,
    *,
    tool_list_cls,
    tool_model_cls,
    tool_delegate_cls,
):
    """Create the left catalog shell and connect selection handlers."""
    left_card = QFrame()
    left_card.setProperty("catalogShell", True)
    left_layout = QVBoxLayout(left_card)
    left_layout.setContentsMargins(0, 0, 0, 0)
    left_layout.setSpacing(10)

    page.tool_list = tool_list_cls()
    page.tool_list.setObjectName("toolCatalog")
    page.tool_list.setVerticalScrollMode(QListView.ScrollPerPixel)
    page.tool_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    page.tool_list.setSelectionMode(QListView.ExtendedSelection)
    page.tool_list.setDragEnabled(True)
    page.tool_list.setMouseTracking(True)
    page.tool_list.setStyleSheet(
        "QListView#toolCatalog { border: none; outline: none; padding: 8px; }"
        " QListView#toolCatalog::item { background: transparent; border: none; }"
    )
    page.tool_list.setSpacing(4)
    page._tool_model = tool_model_cls(page)
    page.tool_list.setModel(page._tool_model)
    page._tool_delegate = tool_delegate_cls(
        parent=page.tool_list,
        view_mode=page.view_mode,
        translate=page._t,
    )
    page.tool_list.setItemDelegate(page._tool_delegate)
    page.tool_list.selectionModel().currentChanged.connect(page._on_current_changed)
    page.tool_list.selectionModel().selectionChanged.connect(page._on_multi_selection_changed)
    page.tool_list.doubleClicked.connect(page._on_double_clicked)
    page.tool_list.installEventFilter(page)
    page.tool_list.viewport().installEventFilter(page)
    left_layout.addWidget(page.tool_list, 1)
    return left_card
