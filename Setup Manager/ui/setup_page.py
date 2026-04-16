import tempfile
from typing import Callable

from PySide6.QtCore import QDate, QEvent, Qt, Signal, QSize
from PySide6.QtGui import QIcon, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDateEdit,
    QFormLayout,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.common import AutoShrinkLabel, styled_list_item_height
from ui.setup_catalog_delegate import ROLE_WORK_ID, SetupCatalogDelegate
from ui.setup_page_support.crud_actions import (
    create_work as create_setup_work,
    delete_work as delete_setup_work,
    duplicate_work as duplicate_setup_work,
    edit_work as edit_setup_work,
    preload_shared_work_editor_dialog,
)
from ui.setup_page_support.selection_helpers import (
    clear_selection as clear_setup_selection,
    on_selection_changed as on_setup_selection_changed,
    selected_work_ids,
    update_selection_count_label,
)
from ui.setup_page_support.view_helpers import (
    apply_localization as apply_setup_page_localization,
    handle_event_filter,
    handle_item_double_clicked,
    refresh_works as refresh_setup_page_works,
    sync_work_row_widths,
    toggle_search,
)
from ui.setup_page_support.logbook_actions import (
    add_log_entry as add_log_entry_action,
)
from ui.setup_page_support.setup_card_actions import view_setup_card as view_setup_card_action
try:
    from shared.ui.helpers.editor_helpers import (
        apply_shared_checkbox_style,
        create_titled_section,
        setup_editor_dialog,
    )
except ModuleNotFoundError:
    from editor_helpers import (
        apply_shared_checkbox_style,
        create_titled_section,
        setup_editor_dialog,
    )

from ui.icon_helpers import toolbar_icon_with_svg_render_fallback as _toolbar_icon_with_svg_render_fallback
from shared.data.backup_helpers import prune_backups


class SetupPage(QWidget):
    logbookChanged = Signal()
    openLibraryMasterFilterRequested = Signal(object, object)
    openLibraryWithModuleRequested = Signal(object, object, str)  # tool_ids, jaw_ids, module
    libraryLaunchContextChanged = Signal(object)

    def __init__(
        self,
        work_service,
        logbook_service,
        draw_service,
        print_service,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self.work_service = work_service
        self.logbook_service = logbook_service
        self.draw_service = draw_service
        self.print_service = print_service
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or "")

        self.drawings_enabled = True  # updated by main_window from preferences
        self.current_work_id = None
        self.latest_entries_by_work = {}
        self._search_visible = False
        self._min_list_panel_width = 340
        self._last_mouse_button = None  # Track mouse button for double-click handling
        self._work_editor_preload_done = False
        self._row_headers = {
            "work_id": self._t("setup_page.row.work_id", "Work ID"),
            "drawing": self._t("setup_page.row.drawing", "Drawing"),
            "description": self._t("setup_page.row.description", "Description"),
            "last_run": self._t("setup_page.row.last_run", "Last run"),
        }

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        controls_frame = QFrame()
        controls_frame.setProperty("topBarContainer", True)
        controls = QHBoxLayout(controls_frame)
        controls.setContentsMargins(8, 6, 8, 6)
        controls.setSpacing(8)

        self.search_icon = _toolbar_icon_with_svg_render_fallback("search_icon", 28)
        self.close_icon = _toolbar_icon_with_svg_render_fallback("close_icon", 28)

        self.search_toggle_btn = QToolButton()
        self.search_toggle_btn.setProperty("topBarIconButton", True)
        self.search_toggle_btn.setCheckable(True)
        self.search_toggle_btn.setToolTip(self._t("setup_page.search_toggle_tip", "Show/hide search"))
        self.search_toggle_btn.setIcon(self.search_icon)
        self.search_toggle_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.search_toggle_btn.setIconSize(QSize(28, 28))
        self.search_toggle_btn.setFixedSize(36, 36)
        self.search_toggle_btn.setAutoRaise(True)
        self.search_toggle_btn.clicked.connect(self._toggle_search)
        controls.addWidget(self.search_toggle_btn)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self._t("setup_page.search_placeholder", "Search works..."))
        self.search_input.textChanged.connect(self.refresh_works)
        self.search_input.setVisible(False)
        self.search_input.setFixedWidth(220)
        controls.addWidget(self.search_input)

        self._init_action_buttons()

        controls.addStretch(1)
        controls.addWidget(self.print_btn)
        controls.addWidget(self.make_logbook_entry_btn)
        root.addWidget(controls_frame)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("setupWorkSplitter")
        splitter.setHandleWidth(1)
        self.work_list = QListView()
        self.work_list.setObjectName("setupWorkList")
        self.work_list.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.work_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.work_list.setSpacing(0)
        self.work_list.setSelectionMode(QListView.ExtendedSelection)
        self.work_list.setMouseTracking(True)
        self.work_list.setUniformItemSizes(True)
        self.work_list.setStyleSheet(
            "QListView#setupWorkList { border: none; outline: none; padding: 8px; }"
            " QListView#setupWorkList::item { background: transparent; border: none; }"
        )
        self._work_model = QStandardItemModel(self)
        self._work_delegate = SetupCatalogDelegate(
            self.work_list,
            headers=self._row_headers,
            compact_mode=False,
        )
        self.work_list.setModel(self._work_model)
        self.work_list.setItemDelegate(self._work_delegate)
        # Keep keyboard selection and mouse selection paths aligned.
        self.work_list.selectionModel().currentChanged.connect(self._on_selection_changed)
        self.work_list.selectionModel().selectionChanged.connect(self._on_multi_selection_changed)
        self.work_list.doubleClicked.connect(self._on_item_double_clicked)
        self.work_list.installEventFilter(self)
        self.work_list.viewport().installEventFilter(self)

        list_shell = QFrame()
        list_shell.setObjectName("setupWorkShell")
        list_shell.setProperty("catalogShell", True)
        list_shell_layout = QVBoxLayout(list_shell)
        list_shell_layout.setContentsMargins(0, 0, 8, 0)
        list_shell_layout.setSpacing(0)
        list_shell_layout.addWidget(self.work_list)

        list_shell_container = QWidget()
        list_shell_container_layout = QVBoxLayout(list_shell_container)
        list_shell_container_layout.setContentsMargins(0, 0, 0, 0)
        list_shell_container_layout.setSpacing(0)
        list_shell_container_layout.addWidget(list_shell)
        list_shell_container.setMinimumWidth(self._min_list_panel_width)
        splitter.addWidget(list_shell_container)

        splitter.setChildrenCollapsible(False)
        splitter.setCollapsible(0, False)
        root.addWidget(splitter, 1)

        self._build_bottom_button_bar(root)

        self.refresh_works()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _init_action_buttons(self):
        self.make_logbook_entry_btn = QPushButton(self._t("setup_page.make_logbook_entry", "Make logbook entry"))
        self.make_logbook_entry_btn.setProperty("panelActionButton", True)
        self.make_logbook_entry_btn.setProperty("secondaryAction", True)
        self.make_logbook_entry_btn.setFixedHeight(30)
        self.make_logbook_entry_btn.setFixedWidth(260)
        self.make_logbook_entry_btn.clicked.connect(self.add_log_entry)

        self.new_btn = QPushButton(self._t("setup_page.new_work", "New Work"))
        self.edit_btn = QPushButton(self._t("setup_page.edit_work", "Edit Work"))
        self.delete_btn = QPushButton(self._t("setup_page.delete_work", "Delete Work"))
        self.copy_btn = QPushButton(self._t("setup_page.duplicate", "Duplicate"))
        self.print_btn = QPushButton(self._t("setup_page.view_setup_card", "View Setup Card"))
        self.print_btn.setProperty("panelActionButton", True)
        self.print_btn.setProperty("secondaryAction", True)
        self.print_btn.setFixedHeight(30)
        self.print_btn.setFixedWidth(260)

        self.new_btn.clicked.connect(self.create_work)
        self.edit_btn.clicked.connect(self.edit_work)
        self.delete_btn.clicked.connect(self.delete_work)
        self.copy_btn.clicked.connect(self.duplicate_work)
        self.print_btn.clicked.connect(self.view_setup_card)

    def _build_bottom_button_bar(self, root_layout: QVBoxLayout):
        button_bar = QFrame()
        button_bar.setProperty("bottomBar", True)
        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(10, 10, 10, 6)
        button_layout.setSpacing(8)
        button_layout.addStretch(1)

        self.new_btn.setProperty("panelActionButton", True)
        self.new_btn.setProperty("primaryAction", True)
        self.edit_btn.setProperty("panelActionButton", True)
        self.copy_btn.setProperty("panelActionButton", True)
        self.delete_btn.setProperty("panelActionButton", True)
        self.delete_btn.setProperty("dangerAction", True)

        self.selection_count_label = QLabel("")
        self.selection_count_label.setProperty("detailHint", True)
        self.selection_count_label.setStyleSheet("background: transparent; border: none;")
        self.selection_count_label.hide()
        button_layout.addWidget(self.selection_count_label, 0, Qt.AlignBottom)
        button_layout.addWidget(self.new_btn, 0, Qt.AlignBottom)
        button_layout.addWidget(self.edit_btn, 0, Qt.AlignBottom)
        button_layout.addWidget(self.delete_btn, 0, Qt.AlignBottom)
        button_layout.addWidget(self.copy_btn, 0, Qt.AlignBottom)
        root_layout.addWidget(button_bar)

    def apply_localization(self, translate: Callable[[str, str | None], str] | None = None):
        apply_setup_page_localization(self, translate)

    def refresh_works(self):
        refresh_setup_page_works(self)

    def _selected_work_id(self):
        index = self.work_list.currentIndex()
        return index.data(ROLE_WORK_ID) if index.isValid() else None

    def _selected_work_ids(self) -> list[str]:
        return selected_work_ids(self)

    def _on_multi_selection_changed(self, _selected, _deselected):
        self._update_selection_count_label()

    def _update_selection_count_label(self):
        update_selection_count_label(self)

    def _batch_edit_works(self, work_ids: list[str]):
        from ui.setup_page_support.batch_actions import batch_edit_works
        batch_edit_works(self, work_ids)

    def _group_edit_works(self, work_ids: list[str]):
        from ui.setup_page_support.batch_actions import group_edit_works
        group_edit_works(self, work_ids)

    def _toggle_search(self):
        toggle_search(self)

    def eventFilter(self, obj, event):
        handle_event_filter(self, obj, event)
        return super().eventFilter(obj, event)

    def _clear_selection(self):
        clear_setup_selection(self)

    def _on_selection_changed(self, current, _previous):
        on_setup_selection_changed(self, current)

    def _on_item_double_clicked(self, item):
        handle_item_double_clicked(self, item)

    def _set_selected_card(self, work_id):
        # Delegate paints selected state from model/current index; this keeps repaint explicit.
        _ = work_id
        self.work_list.viewport().update()

    def _sync_work_row_widths(self):
        sync_work_row_widths(self)

    # ------------------------------------------------------------------
    # CRUD actions
    # ------------------------------------------------------------------

    def create_work(self):
        create_setup_work(self)

    def edit_work(self):
        edit_setup_work(self)

    def delete_work(self):
        delete_setup_work(self)

    def duplicate_work(self):
        duplicate_setup_work(self)

    def add_log_entry(self):
        add_log_entry_action(self)

    def view_setup_card(self):
        view_setup_card_action(self)

    def preload_work_editor_dialog(self):
        if self._work_editor_preload_done:
            return
        preload_shared_work_editor_dialog(self)
        self._work_editor_preload_done = True

