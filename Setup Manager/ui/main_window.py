from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_TITLE,
    NAV_ITEMS,
    STYLE_PATH,
    SHARED_UI_PREFERENCES_PATH,
    I18N_DIR,
    TOOL_ICONS_DIR,
    TOOL_LIBRARY_EXE_CANDIDATES,
    TOOL_LIBRARY_MAIN_PATH,
    TOOL_LIBRARY_PROJECT_DIR,
    TOOL_LIBRARY_SERVER_NAME,
)


from ui.drawing_page import DrawingPage
from ui.logbook_page import LogbookPage
from ui.setup_page import SetupPage
from shared.services.ui_preferences_service import UiPreferencesService
from shared.services.localization_service import LocalizationService
from ui.widgets.common import clear_focused_dropdown_on_outside_click
from ui.main_window_support import (
    allow_set_foreground,
    build_compatibility_report_bundle,
    launch_tool_library,
    on_setup_launch_context_changed,
    open_jaws_library_action,
    open_preferences_action,
    open_tool_library_action,
    resolve_compatibility_target_path,
    show_compatibility_report_dialog,
    send_request_with_retry,
    send_to_tool_library,
    update_launch_actions,
    update_navigation_labels,
)
from shared.ui.main_window_helpers import (
    current_window_rect,
    fade_in as _shared_fade_in,
    fade_out_and as _shared_fade_out_and,
    get_active_theme_palette,
    is_interactive_widget_click,
)
class MainWindow(QMainWindow):
    # Emitted when the user requests a live configuration switch.
    # The argument is the target config_id string.
    config_switch_requested = Signal(str)

    def __init__(self, work_service, logbook_service, draw_service, print_service,
                 machine_config_svc=None):
        super().__init__()
        self.work_service = work_service
        self.logbook_service = logbook_service
        self.draw_service = draw_service
        self.print_service = print_service
        self.machine_config_svc = machine_config_svc
        # Set True before close() during a live config switch to suppress
        # the app.quit() call in closeEvent.
        self._suppress_quit = False
        self.ui_preferences_service = UiPreferencesService(
            SHARED_UI_PREFERENCES_PATH,
            include_setup_db_path=True,
        )
        self.ui_preferences = self.ui_preferences_service.load()
        self.localization = LocalizationService(I18N_DIR)
        self.localization.set_language(self.ui_preferences.get("language", "en"))
        if hasattr(self.print_service, "set_translator"):
            self.print_service.set_translator(self._t)

        self.setWindowTitle(self._t("setup_manager.window_title", APP_TITLE))
        self.resize(1360, 840)

        # Hidden Tool Library preload state.  This is intentionally conservative
        # to avoid transient flashes while modal dialogs (e.g. Work Editor)
        # are opening/closing.
        self._tool_library_preload_completed = False
        self._tool_library_preload_retries = 0
        self._tool_library_preload_max_retries = 24
        self._tool_library_preload_scheduled = False

        self._build_ui()
        self._apply_style()
        QApplication.instance().installEventFilter(self)
        QTimer.singleShot(2000, self._preload_tool_library_background)

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self.localization.t(key, default, **kwargs)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            clear_focused_dropdown_on_outside_click(obj, self)
            self._clear_active_page_selection_on_background_click(obj)
        return super().eventFilter(obj, event)

    def _clear_active_page_selection_on_background_click(self, obj):
        if is_interactive_widget_click(obj, self):
            return
        page = self.stack.currentWidget() if hasattr(self, 'stack') else None
        if page is not None:
            self._clear_page_selection(page)

    def _clear_page_selection(self, page: QWidget):
        clear_fn = getattr(page, '_clear_selection', None) or getattr(page, 'clear_selection', None)
        if callable(clear_fn):
            clear_fn()
            return
        for view in page.findChildren(QAbstractItemView):
            try:
                view.clearSelection()
            except Exception:
                pass

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 12, 0)
        root.setSpacing(0)

        self.nav_rail = QFrame()
        self.nav_rail.setProperty("navRail", True)
        self.nav_rail.setFixedWidth(210)
        nav_layout = QVBoxLayout(self.nav_rail)
        nav_layout.setContentsMargins(12, 14, 12, 14)
        nav_layout.setSpacing(8)

        self.rail_title_label = QLabel(self._t("setup_manager.rail_title", "Setup Manager"))
        self.rail_title_label.setStyleSheet("color: #000000; font-size: 16pt; font-weight: 700;")
        self.rail_title_label.setWordWrap(True)
        nav_layout.addWidget(self.rail_title_label)

        self.nav_buttons = []
        for idx, item_name in enumerate(NAV_ITEMS):
            button = self._build_nav_button(idx, item_name)
            nav_layout.addWidget(button)
            self.nav_buttons.append(button)

        nav_layout.addStretch(1)
        nav_layout.addWidget(self._build_launch_card())

        root.addWidget(self.nav_rail)

        self._initialize_pages()
        root.addWidget(self.stack, 1)

        self._initialize_status_bar()

        self._set_page(0)

    def _build_nav_button(self, index: int, fallback_text: str) -> QPushButton:
        key = (
            "setup_manager.nav.setups"
            if index == 0
            else "setup_manager.nav.drawings"
            if index == 1
            else "setup_manager.nav.logbook"
        )
        button = QPushButton(self._t(key, fallback_text))
        button.setProperty("navButton", True)
        button.clicked.connect(lambda checked=False, i=index: self._set_page(i))
        return button

    def _build_launch_card(self) -> QFrame:
        launch_card = QFrame()
        launch_card.setProperty("launchCard", True)
        launch_layout = QVBoxLayout(launch_card)
        launch_layout.setContentsMargins(12, 12, 12, 12)
        launch_layout.setSpacing(8)

        self.launch_title = QLabel(self._t("setup_manager.launch.title", "Master Data"))
        self.launch_title.setProperty("sectionTitle", True)
        self.launch_body = QLabel(
            self._t(
                "setup_manager.launch.default_body",
                "Open Tool Library or Jaws Library. Select a work in Setup to open filtered data.",
            )
        )
        self.launch_body.setWordWrap(True)
        self.launch_body.setProperty("navHint", True)

        self.open_tools_btn = QPushButton(self._t("setup_manager.open_tool_library", "Open Tool Library"))
        self.open_tools_btn.setProperty("panelActionButton", True)
        self.open_tools_btn.setProperty("sidebarLaunchButton", True)
        self.open_tools_btn.setMinimumWidth(154)
        self.open_tools_btn.clicked.connect(lambda: open_tool_library_action(self))

        self.open_jaws_btn = QPushButton(self._t("setup_manager.open_jaws_library", "Open Jaws Library"))
        self.open_jaws_btn.setProperty("panelActionButton", True)
        self.open_jaws_btn.setProperty("sidebarLaunchButton", True)
        self.open_jaws_btn.setMinimumWidth(154)
        self.open_jaws_btn.clicked.connect(lambda: open_jaws_library_action(self))

        self.preferences_btn = QToolButton()
        self.preferences_btn.setProperty("topBarIconButton", True)
        self.preferences_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / "menu_icon.svg")))
        self.preferences_btn.setIconSize(QSize(30, 30))
        self.preferences_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.preferences_btn.setFixedSize(38, 38)
        self.preferences_btn.setAutoRaise(True)
        self.preferences_btn.setToolTip(self._t("common.preferences", "Preferences"))
        self.preferences_btn.clicked.connect(lambda: open_preferences_action(self))

        launch_layout.addWidget(self.launch_title)
        launch_layout.addWidget(self.launch_body)
        launch_layout.addWidget(self.open_tools_btn)
        launch_layout.addWidget(self.open_jaws_btn)
        launch_layout.addWidget(self.preferences_btn, 0, Qt.AlignHCenter)
        return launch_card

    def _initialize_pages(self):
        self.stack = QStackedWidget()
        self.setup_page = SetupPage(
            self.work_service,
            self.logbook_service,
            self.draw_service,
            self.print_service,
            translate=self._t,
        )
        self.drawing_page = DrawingPage(self.draw_service, translate=self._t)
        self.logbook_page = LogbookPage(self.logbook_service, self.work_service, translate=self._t)

        self.setup_page.logbookChanged.connect(self.logbook_page.refresh_entries)
        self.logbook_page.logbookChanged.connect(self.setup_page.refresh_works)
        self.setup_page.openLibraryMasterFilterRequested.connect(self._open_tool_library_with_master_filter)
        self.setup_page.openLibraryWithModuleRequested.connect(self._open_tool_library_with_master_filter)
        # Keep launch-card state in sync with selection changes from SetupPage.
        self.setup_page.libraryLaunchContextChanged.connect(
            lambda context: on_setup_launch_context_changed(self, context)
        )
        self.setup_page.libraryLaunchContextChanged.connect(self.drawing_page.set_setup_context)

        self._launch_context = {
            "selected": False,
            "work_id": "",
            "drawing_id": "",
            "drawing_path": "",
            "description": "",
            "tool_ids": [],
            "jaw_ids": [],
            "has_tools": False,
            "has_jaws": False,
            "has_data": False,
        }
        self.drawing_page.set_setup_context(self._launch_context)
        update_launch_actions(self)
        self.setup_page.drawings_enabled = self.ui_preferences.get("enable_drawings_tab", True)

        self.stack.addWidget(self.setup_page)
        self.stack.addWidget(self.drawing_page)
        self.stack.addWidget(self.logbook_page)

    def _initialize_status_bar(self):
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self._status_bar = status_bar
        db_name = Path(self.work_service.db.path).name
        source_status = self.draw_service.get_reference_source_status()
        tool_state = (
            Path(source_status["tool_db_path"]).name
            if source_status["tool_db_exists"]
            else self._t("setup_manager.status.missing", "missing")
        )
        jaw_state = (
            Path(source_status["jaw_db_path"]).name
            if source_status["jaw_db_exists"]
            else self._t("setup_manager.status.missing", "missing")
        )
        self._status_data = {
            "setup_db": db_name,
            "tool_db": tool_state,
            "jaw_db": jaw_state,
        }
        self._update_status_message()

    # ------------------------------------------------------------------
    # Tool Library launcher helpers
    # ------------------------------------------------------------------

    def _send_to_tool_library(self, payload: dict) -> bool:
        """Send an IPC message to a running Tool Library instance. Returns True on success."""
        return send_to_tool_library(TOOL_LIBRARY_SERVER_NAME, payload)

    def _launch_tool_library(self, extra_args: list = None) -> bool:
        """Start the Tool Library process. Returns True on success."""
        return launch_tool_library(
            TOOL_LIBRARY_MAIN_PATH,
            TOOL_LIBRARY_EXE_CANDIDATES,
            TOOL_LIBRARY_PROJECT_DIR,
            extra_args,
        )

    def _preload_tool_library_background(self):
        """Launch Tool Library hidden in background so selectors open instantly."""
        if self._tool_library_preload_completed:
            return

        app = QApplication.instance()
        active_modal = app.activeModalWidget() if app is not None else None
        if active_modal is not None or not self.isVisible() or self.isMinimized():
            # Defer while the UI is in a transition/modal state to avoid first-open
            # flashes of hidden/preloaded windows.
            if self._tool_library_preload_retries < self._tool_library_preload_max_retries:
                self._tool_library_preload_retries += 1
                if not self._tool_library_preload_scheduled:
                    self._tool_library_preload_scheduled = True
                    QTimer.singleShot(700, self._retry_tool_library_preload)
            return

        if self._send_to_tool_library({"show": False}):
            self._tool_library_preload_completed = True
            return  # already running

        if self._launch_tool_library(["--hidden"]):
            self._tool_library_preload_completed = True

    def _retry_tool_library_preload(self):
        self._tool_library_preload_scheduled = False
        self._preload_tool_library_background()

    def _fade_out_and(self, callback):
        _shared_fade_out_and(self, callback)

    def fade_in(self):
        _shared_fade_in(self)

    def _current_window_rect(self) -> tuple[int, int, int, int]:
        return current_window_rect(self)

    def _complete_tool_library_handoff(self):
        # Centralize hide/opacity reset so IPC and process-launch paths stay in sync.
        self.hide()
        self.setWindowOpacity(1.0)

    def _open_tool_library_together(self):
        # Legacy external hook retained for backward compatibility.
        """Backward-compatible helper that opens Tool Library tools module without filters."""
        self._open_tool_library_module("tools")

    def _open_tool_library_module(self, module: str):
        """Open Tool Library with no master filter and focus the requested module."""
        x, y, width, height = self._current_window_rect()

        # Grant the Tool Library process permission to take foreground focus.
        allow_set_foreground()

        # Preferred path: IPC to the already-running (hidden) Tool Library.
        # This is fastest and preserves an already warmed process.
        payload = {
            "geometry": f"{x},{y},{width},{height}",
            "show": True,
            "clear_master_filter": True,
            "module": "jaws" if module == "jaws" else "tools",
            "tools_db_path": str(self.draw_service.tool_db_path),
            "jaws_db_path": str(self.draw_service.jaw_db_path),
        }
        if self._send_to_tool_library(payload):
            self._fade_out_and(self._complete_tool_library_handoff)
            return

        # Fallback: launch a new Tool Library process.
        # We still retry IPC shortly after launch to push intended module/filter state.
        args = ["--geometry", f"{x},{y},{width},{height}"]
        if self._launch_tool_library(args):
            self._send_request_with_retry(
                payload,
                on_success=lambda: self._fade_out_and(self._complete_tool_library_handoff),
            )
            return

        QMessageBox.warning(
            self,
            self._t("setup_manager.library_unavailable.title", "Tool Library unavailable"),
            self._t(
                "setup_manager.library_unavailable.body",
                "Could not find a launchable Tool Library executable or source entry point.",
            ),
        )

    def _open_tool_library_separate(self):
        # Legacy external hook retained for backward compatibility.
        """Backward-compatible helper that now opens Jaws module without filters."""
        self._open_tool_library_module("jaws")

    def _open_tool_library_deep_link(self, kind: str, item_id: str):
        # Deep links bypass IPC filter-state setup and open directly by item ID.
        """Open Tool Library and navigate directly to a specific jaw or tool."""
        x, y, width, height = self._current_window_rect()
        if kind == "jaw":
            args = ["--geometry", f"{x},{y},{width},{height}", "--open-jaw", item_id] if item_id else []
        else:
            args = ["--geometry", f"{x},{y},{width},{height}", "--open-tool", item_id] if item_id else []
        if not self._launch_tool_library(args):
            QMessageBox.warning(
                self,
                self._t("setup_manager.library_unavailable.title", "Tool Library unavailable"),
                self._t(
                    "setup_manager.library_unavailable.body",
                    "Could not find a launchable Tool Library executable or source entry point.",
                ),
            )

    def _open_tool_library_with_master_filter(self, tool_ids, jaw_ids, module: str = "tools"):
        """Open Tool Library in launch-scoped master filter mode."""
        raw_tools = [str(t).strip() for t in (tool_ids or []) if str(t).strip()]
        raw_jaws = [str(j).strip() for j in (jaw_ids or []) if str(j).strip()]
        safe_tools = list(raw_tools)
        safe_jaws = list(raw_jaws)

        # Keep module filtering strict even when one side has no linked IDs.
        # The Tool/Jaw pages treat empty filter lists as "show all", so we
        # pass a guaranteed non-matching sentinel to force an empty result set.
        no_match_id = "__NO_MATCH_LINKED_ITEMS__"
        selected_module = "jaws" if module == "jaws" else "tools"
        if not safe_tools:
            safe_tools = [no_match_id]
        if not safe_jaws:
            safe_jaws = [no_match_id]

        # Keep the warning tied to user intent (explicitly selected module with no links).
        if selected_module == "tools" and tool_ids is not None and not raw_tools:
            safe_tools = [no_match_id]
            QMessageBox.information(
                self,
                self._t("setup_manager.viewer.title", "Viewer"),
                self._t("setup_manager.viewer.no_tools", "No tools selected for this work."),
            )
        if selected_module == "jaws" and jaw_ids is not None and not raw_jaws:
            QMessageBox.information(
                self,
                self._t("setup_manager.viewer.title", "Viewer"),
                self._t("setup_manager.viewer.no_jaws", "No jaws selected for this work."),
            )

        x, y, width, height = self._current_window_rect()
        allow_set_foreground()

        # Preferred path: IPC to the already-running Tool Library.
        payload = {
            "geometry": f"{x},{y},{width},{height}",
            "show": True,
            "master_filter_tools": safe_tools,
            "master_filter_jaws": safe_jaws,
            "master_filter_active": True,
            "module": selected_module,
            "tools_db_path": str(self.draw_service.tool_db_path),
            "jaws_db_path": str(self.draw_service.jaw_db_path),
        }
        if self._send_to_tool_library(payload):
            self._fade_out_and(self._complete_tool_library_handoff)
            return

        # Fallback: launch a new Tool Library process.
        args = [
            "--geometry", f"{x},{y},{width},{height}",
            "--master-filter-tools", ",".join(safe_tools),
            "--master-filter-jaws", ",".join(safe_jaws),
            "--master-filter-active", "1",
        ]
        if self._launch_tool_library(args):
            self._send_request_with_retry(
                payload,
                on_success=lambda: self._fade_out_and(self._complete_tool_library_handoff),
            )
            return

        QMessageBox.warning(
            self,
            self._t("setup_manager.library_unavailable.title", "Tool Library unavailable"),
            self._t(
                "setup_manager.library_unavailable.body",
                "Could not find a launchable Tool Library executable or source entry point.",
            ),
        )

    def _send_request_with_retry(
        self,
        payload: dict,
        attempts: int = 36,
        delay_ms: int = 300,
        on_success=None,
        on_failed=None,
    ):
        """Retry IPC shortly after launching Tool Library so module/filter payload is applied.

        Tool Library startup can race with the first IPC attempt; this helper smooths over
        that timing window without blocking the UI thread.
        """
        send_request_with_retry(
            self._send_to_tool_library,
            payload,
            attempts=attempts,
            delay_ms=delay_ms,
            on_success=on_success,
            on_failed=on_failed,
        )

    def _check_setup_db_compatibility(self, database_path: str):
        target_path, path_error = resolve_compatibility_target_path(database_path)
        if path_error is not None:
            QMessageBox.warning(
                self,
                self._t("preferences.database.compatibility.title", "Compatibility Check"),
                self._t(
                    path_error["message_key"],
                    path_error["default"],
                    **path_error["kwargs"],
                ),
            )
            return

        try:
            # Bundle includes both the computed compatibility report and human-readable
            # DB path summary text used in the dialog.
            bundle = build_compatibility_report_bundle(
                target_path,
                self.draw_service,
                self.work_service._row_to_work,
                self._t,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._t("preferences.database.compatibility.title", "Compatibility Check"),
                self._t(
                    "preferences.database.compatibility.failed",
                    "Could not read the selected Setup database:\n{error}",
                    error=str(exc),
                ),
            )
            return

        show_compatibility_report_dialog(
            self,
            title=self._t("preferences.database.compatibility.title", "Compatibility Check"),
            summary=bundle["report"]["summary"],
            informative=bundle["informative"],
            details=bundle["report"]["details"],
            has_issues=bundle["report"]["has_issues"],
        )

    def _refresh_localized_labels(self):
        # Keep text refresh order stable: shell labels first, then child pages, then stateful
        # launch/status text that depends on current context and translated strings.
        self.setWindowTitle(self._t("setup_manager.window_title", APP_TITLE))
        if hasattr(self, "rail_title_label"):
            self.rail_title_label.setText(self._t("setup_manager.rail_title", "Setup Manager"))
        if hasattr(self, "launch_title"):
            self.launch_title.setText(self._t("setup_manager.launch.title", "Master Data"))
        if hasattr(self, "open_tools_btn"):
            self.open_tools_btn.setText(self._t("setup_manager.open_tool_library", "Open Tool Library"))
        if hasattr(self, "open_jaws_btn"):
            self.open_jaws_btn.setText(self._t("setup_manager.open_jaws_library", "Open Jaws Library"))
        if hasattr(self, "preferences_btn"):
            self.preferences_btn.setToolTip(self._t("common.preferences", "Preferences"))
        update_navigation_labels(self)
        if hasattr(self, "setup_page") and hasattr(self.setup_page, "apply_localization"):
            self.setup_page.apply_localization(self._t)
        if hasattr(self, "drawing_page") and hasattr(self.drawing_page, "apply_localization"):
            self.drawing_page.apply_localization(self._t)
        if hasattr(self, "logbook_page") and hasattr(self.logbook_page, "apply_localization"):
            self.logbook_page.apply_localization(self._t)
        self._update_status_message()
        update_launch_actions(self)

    def _update_status_message(self):
        if not hasattr(self, "_status_bar") or not hasattr(self, "_status_data"):
            return
        self._status_bar.showMessage(
            self._t(
                "setup_manager.status.message",
                "Setup DB: {setup_db} | Tool DB: {tool_db} | Jaw DB: {jaw_db}",
                setup_db=self._status_data.get("setup_db", ""),
                tool_db=self._status_data.get("tool_db", ""),
                jaw_db=self._status_data.get("jaw_db", ""),
            )
        )

    def _build_ui_preference_overrides(self) -> str:
        palette = get_active_theme_palette(self.ui_preferences)
        font_family = self.ui_preferences.get("font_family", "Segoe UI").replace("'", "\\'")
        return (
            "/* Runtime UI preference overrides */\n"
            f"* {{ font-family: '{font_family}'; }}\n"
            # window background
            "QMainWindow,\n"
            "QWidget#appRoot,\n"
            "QFrame[navRail=\"true\"],\n"
            "QFrame[bottomBar=\"true\"],\n"
            "QFrame[topBarContainer=\"true\"] {\n"
            f"    background-color: {palette['window_bg']};\n"
            "}\n"
            # catalog / surface
            "QFrame#setupWorkShell,\n"
            "QListView#toolCatalog,\n"
            "QListView#toolCatalog::viewport,\n"
            "QListView#setupWorkList,\n"
            "QListView#setupWorkList::viewport,\n"
            "QListWidget#toolCatalog,\n"
            "QListWidget#toolCatalog::viewport,\n"
            "QListWidget#setupWorkList,\n"
            "QListWidget#setupWorkList::viewport,\n"
            "QListWidget#drawingList,\n"
            "QListWidget#drawingList::viewport {\n"
            f"    background-color: {palette['surface_bg']};\n"
            "}\n"
            # info boxes / detail fields
            "QFrame[detailField=\"true\"],\n"
            "QFrame[detailField=\"true\"][detailHeroField=\"true\"] {\n"
            f"    background-color: {palette['info_box_bg']};\n"
            "}\n"
            # input field focus ring
            "QLineEdit:focus,\n"
            "QTextEdit:focus {\n"
            f"    border: 1px solid {palette['accent']};\n"
            "}\n"
            # card selection borders
            "QFrame[toolListCard=\"true\"][selected=\"true\"],\n"
            "QFrame[toolListCard=\"true\"][selected=\"true\"]:hover,\n"
            "QFrame[workCard=\"true\"][selected=\"true\"],\n"
            "QFrame[workCard=\"true\"][selected=\"true\"]:hover {\n"
            f"    border: 2px solid {palette['accent']};\n"
            "}\n"
            # miniAssignmentCard static rule uses QDialog[workEditorDialog] ancestor (spec 0,3,2)
            # so this runtime rule must match that specificity to win at equal spec + last-defined
            "QDialog[workEditorDialog=\"true\"] QFrame[miniAssignmentCard=\"true\"][selected=\"true\"],\n"
            "QDialog[workEditorDialog=\"true\"] QFrame[miniAssignmentCard=\"true\"][selected=\"true\"]:hover {\n"
            f"    border: 2px solid {palette['accent']};\n"
            "}\n"
            "QFrame[selectorDropTarget=\"true\"][activeDropTarget=\"true\"] {\n"
            f"    border: 2px solid {palette['accent']};\n"
            "}\n"
            # icon-only buttons — lighter hover tint, distinct from full button hover
            "QToolButton[topBarIconButton=\"true\"]:hover {\n"
            f"    background-color: {palette['icon_hover_bg']};\n"
            "}\n"
            "QToolButton[topBarIconButton=\"true\"]:pressed {\n"
            f"    background-color: {palette['accent_light']};\n"
            "}\n"
            # primary action buttons — themed gradient (spec 1: plain buttons)
            "QPushButton {\n"
            f"    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {palette['accent_light']}, stop:1 {palette['accent']});\n"
            "}\n"
            "QPushButton:hover {\n"
            f"    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {palette['accent']}, stop:1 {palette['accent_hover']});\n"
            "}\n"
            "QPushButton:pressed {\n"
            f"    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {palette['accent_hover']}, stop:1 {palette['accent_pressed']});\n"
            "}\n"
            # spec-21 overrides for hardcoded gradients in static QSS that the
            # spec-1 QPushButton rule above cannot reach:
            #   [navButton][active]                — active nav rail item
            #   [panelActionButton][primaryAction] — compact primary panel button
            "QPushButton[navButton=\"true\"][active=\"true\"],\n"
            "QPushButton[panelActionButton=\"true\"][primaryAction=\"true\"] {\n"
            f"    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {palette['accent_light']}, stop:1 {palette['accent']});\n"
            f"    border: 1px solid {palette['accent_pressed']};\n"
            "}\n"
            "QPushButton[navButton=\"true\"][active=\"true\"]:hover,\n"
            "QPushButton[panelActionButton=\"true\"][primaryAction=\"true\"]:hover {\n"
            f"    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {palette['accent']}, stop:1 {palette['accent_hover']});\n"
            "}\n"
            "QPushButton[navButton=\"true\"][active=\"true\"]:pressed,\n"
            "QPushButton[panelActionButton=\"true\"][primaryAction=\"true\"]:pressed {\n"
            f"    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {palette['accent_hover']}, stop:1 {palette['accent_pressed']});\n"
            "}\n"
        )

    def _set_page(self, index):
        # Guard: block navigation to disabled drawings page
        if index == 1 and not self.ui_preferences.get("enable_drawings_tab", True):
            return
        self.stack.setCurrentIndex(index)
        for idx, button in enumerate(self.nav_buttons):
            button.setProperty("active", idx == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def showEvent(self, event):
        """Reload shared preferences when window is shown to sync with Tool Library."""
        super().showEvent(event)
        self.ui_preferences = self.ui_preferences_service.load()
        self.localization.set_language(self.ui_preferences.get("language", "en"))

    def closeEvent(self, event):
        """Save window geometry when closing for restoration on next launch."""
        if not self._suppress_quit:
            x, y, width, height = self._current_window_rect()
            geom_file = Path(self.work_service.db.path).parent / ".window_geometry"
            try:
                geom_file.write_text(f"{x},{y},{width},{height}")
            except Exception:
                pass
        super().closeEvent(event)
        if not self._suppress_quit:
            app = QApplication.instance()
            if app is not None:
                app.quit()

    def _apply_style(self):
        try:
            def _resolve_asset_urls(qss: str) -> str:
                assets_dir = (Path(STYLE_PATH).parent.parent / "assets").resolve().as_posix()
                return qss.replace('url("assets/', f'url("{assets_dir}/').replace("url('assets/", f"url('{assets_dir}/")

            style_dir = Path(STYLE_PATH).parent
            modules_dir = style_dir / "modules"
            merged = []
            if modules_dir.is_dir():
                for module_path in sorted(modules_dir.glob("*.qss")):
                    try:
                        merged.append(_resolve_asset_urls(module_path.read_text(encoding="utf-8")))
                    except Exception:
                        pass
            if merged:
                self.setStyleSheet("\n".join(merged) + "\n\n" + self._build_ui_preference_overrides())
            else:
                qss = _resolve_asset_urls(Path(STYLE_PATH).read_text(encoding="utf-8"))
                self.setStyleSheet(qss + "\n\n" + self._build_ui_preference_overrides())
        except Exception:
            pass

