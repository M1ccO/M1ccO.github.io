import ctypes
import json
from pathlib import Path
import sqlite3
import shutil
import sys

from PySide6.QtCore import QEvent, QProcess, QTimer, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
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


def _allow_set_foreground():
    """Grant any process permission to call SetForegroundWindow (Windows)."""
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(ctypes.wintypes.DWORD(-1))
    except Exception:
        pass
from ui.drawing_page import DrawingPage
from ui.logbook_page import LogbookPage
from ui.preferences_dialog import PreferencesDialog
from ui.setup_page import SetupPage
from services.localization_service import LocalizationService
from services.ui_preferences_service import UiPreferencesService
from ui.widgets.common import add_shadow, clear_focused_dropdown_on_outside_click
try:
    from shared.editor_helpers import create_titled_section, setup_editor_dialog
except ModuleNotFoundError:
    from editor_helpers import create_titled_section, setup_editor_dialog


THEME_PALETTES = {
    "classic": {
        "surface_bg": "rgba(205, 212, 238, 0.97)",
        "detail_box_bg": "rgba(232, 240, 250, 0.98)",
    },
    "graphite": {
        "surface_bg": "rgba(168, 179, 198, 0.98)",
        "detail_box_bg": "rgba(207, 217, 233, 0.98)",
    },
}


class MainWindow(QMainWindow):
    def __init__(self, work_service, logbook_service, draw_service, print_service):
        super().__init__()
        self.work_service = work_service
        self.logbook_service = logbook_service
        self.draw_service = draw_service
        self.print_service = print_service
        self.ui_preferences_service = UiPreferencesService(SHARED_UI_PREFERENCES_PATH)
        self.ui_preferences = self.ui_preferences_service.load()
        self.localization = LocalizationService(I18N_DIR)
        self.localization.set_language(self.ui_preferences.get("language", "en"))
        if hasattr(self.print_service, "set_translator"):
            self.print_service.set_translator(self._t)

        self.setWindowTitle(self._t("setup_manager.window_title", APP_TITLE))
        self.resize(1360, 840)

        self._build_ui()
        self._apply_style()
        QApplication.instance().installEventFilter(self)

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self.localization.t(key, default, **kwargs)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            clear_focused_dropdown_on_outside_click(obj, self)
            self._clear_active_page_selection_on_background_click(obj)
        return super().eventFilter(obj, event)

    def _clear_active_page_selection_on_background_click(self, obj):
        if not isinstance(obj, QWidget) or obj.window() is not self:
            return

        widget = obj
        while widget is not None:
            # Skip interactive widgets and splitters
            if isinstance(widget, (QAbstractButton, QComboBox, QLineEdit, QAbstractItemView, QSplitter)):
                return
            widget = widget.parentWidget()

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
            key = (
                "setup_manager.nav.setups"
                if idx == 0
                else "setup_manager.nav.drawings"
                if idx == 1
                else "setup_manager.nav.logbook"
            )
            button = QPushButton(self._t(key, item_name))
            button.setProperty("navButton", True)
            button.clicked.connect(lambda checked=False, i=idx: self._set_page(i))
            nav_layout.addWidget(button)
            self.nav_buttons.append(button)

        nav_layout.addStretch(1)

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
        self.open_tools_btn.clicked.connect(self._open_tool_library_action)
        self.open_jaws_btn = QPushButton(self._t("setup_manager.open_jaws_library", "Open Jaws Library"))
        self.open_jaws_btn.setProperty("panelActionButton", True)
        self.open_jaws_btn.setProperty("sidebarLaunchButton", True)
        self.open_jaws_btn.setMinimumWidth(154)
        self.open_jaws_btn.clicked.connect(self._open_jaws_library_action)
        self.preferences_btn = QToolButton()
        self.preferences_btn.setProperty("topBarIconButton", True)
        self.preferences_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / "menu_icon.svg")))
        self.preferences_btn.setIconSize(QSize(30, 30))
        self.preferences_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.preferences_btn.setFixedSize(38, 38)
        self.preferences_btn.setAutoRaise(True)
        self.preferences_btn.setToolTip(self._t("common.preferences", "Preferences"))
        self.preferences_btn.clicked.connect(self._open_preferences)
        launch_layout.addWidget(self.launch_title)
        launch_layout.addWidget(self.launch_body)
        launch_layout.addWidget(self.open_tools_btn)
        launch_layout.addWidget(self.open_jaws_btn)
        launch_layout.addWidget(self.preferences_btn, 0, Qt.AlignHCenter)
        nav_layout.addWidget(launch_card)

        root.addWidget(self.nav_rail)

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
        self.setup_page.libraryLaunchContextChanged.connect(self._on_setup_launch_context_changed)
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
        self._update_launch_actions()
        self.setup_page.drawings_enabled = self.ui_preferences.get("enable_drawings_tab", True)

        self.stack.addWidget(self.setup_page)
        self.stack.addWidget(self.drawing_page)
        self.stack.addWidget(self.logbook_page)
        root.addWidget(self.stack, 1)

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

        self._set_page(0)

    # ------------------------------------------------------------------
    # Tool Library launcher helpers
    # ------------------------------------------------------------------

    def _send_to_tool_library(self, payload: dict) -> bool:
        """Send an IPC message to a running Tool Library instance. Returns True on success."""
        sock = QLocalSocket()
        sock.connectToServer(TOOL_LIBRARY_SERVER_NAME)
        if not sock.waitForConnected(300):
            return False
        try:
            sock.write(json.dumps(payload).encode("utf-8"))
            sock.flush()
            sock.waitForBytesWritten(300)
        except Exception:
            return False
        finally:
            sock.disconnectFromServer()
        return True

    def _launch_tool_library(self, extra_args: list = None) -> bool:
        """Start the Tool Library process. Returns True on success."""
        args = list(extra_args or [])

        def _is_safe_exe_target(exe_path: Path) -> bool:
            try:
                resolved = exe_path.resolve()
                current = Path(sys.executable).resolve()
            except Exception:
                return False
            if not resolved.exists() or resolved == current:
                return False
            return "tool library" in resolved.name.lower()

        if TOOL_LIBRARY_MAIN_PATH.exists() and not getattr(sys, "frozen", False):
            candidates = []
            candidates.append(str(Path(sys.executable)))
            py_cmd = shutil.which("python")
            if py_cmd:
                candidates.append(py_cmd)
            py_launcher = shutil.which("py")
            if py_launcher:
                candidates.append(py_launcher)

            for candidate in candidates:
                cmd_args = [str(TOOL_LIBRARY_MAIN_PATH)] + args
                if Path(candidate).name.lower() == "py.exe" or Path(candidate).name.lower() == "py":
                    cmd_args = ["-3", str(TOOL_LIBRARY_MAIN_PATH)] + args
                if QProcess.startDetached(candidate, cmd_args, str(TOOL_LIBRARY_PROJECT_DIR)):
                    return True

        for exe_path in TOOL_LIBRARY_EXE_CANDIDATES:
            if _is_safe_exe_target(exe_path):
                if QProcess.startDetached(str(exe_path), args, str(exe_path.parent)):
                    return True
        return False

    def _fade_out_and(self, callback):
        """Immediately run *callback* without transition animation."""
        if getattr(self, '_fade_anim', None) is not None:
            self._fade_anim.stop()
        self._fade_anim = None
        self.setWindowOpacity(1.0)
        callback()

    def fade_in(self):
        """Show fully visible without transition animation."""
        if getattr(self, '_fade_anim', None) is not None:
            self._fade_anim.stop()
        self._fade_anim = None
        self.setWindowOpacity(1.0)

    def _current_window_rect(self) -> tuple[int, int, int, int]:
        """Return the actual on-screen window rectangle, including snap placement."""
        try:
            rect = ctypes.wintypes.RECT()
            hwnd = int(self.winId())
            if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        except Exception:
            pass
        geom = self.frameGeometry()
        return geom.x(), geom.y(), geom.width(), geom.height()

    def _open_tool_library_together(self):
        """Backward-compatible helper that opens Tool Library tools module without filters."""
        self._open_tool_library_module("tools")

    def _open_tool_library_module(self, module: str):
        """Open Tool Library with no master filter and focus the requested module."""
        x, y, width, height = self._current_window_rect()

        # Grant the Tool Library process permission to take foreground focus.
        _allow_set_foreground()

        # Preferred path: IPC to the already-running (hidden) Tool Library.
        payload = {
            "geometry": f"{x},{y},{width},{height}",
            "show": True,
            "clear_master_filter": True,
            "module": "jaws" if module == "jaws" else "tools",
        }
        if self._send_to_tool_library(payload):
            def _finish_handoff():
                self.hide()
                self.setWindowOpacity(1.0)
            self._fade_out_and(_finish_handoff)
            return

        # Fallback: launch a new Tool Library process.
        args = ["--geometry", f"{x},{y},{width},{height}"]
        if self._launch_tool_library(args):
            self._send_request_with_retry(payload)
            def _finish_launch():
                self.hide()
                self.setWindowOpacity(1.0)
            self._fade_out_and(_finish_launch)
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
        """Backward-compatible helper that now opens Jaws module without filters."""
        self._open_tool_library_module("jaws")

    def _open_tool_library_deep_link(self, kind: str, item_id: str):
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
        safe_tools = [str(t).strip() for t in (tool_ids or []) if str(t).strip()]
        safe_jaws = [str(j).strip() for j in (jaw_ids or []) if str(j).strip()]

        # Keep module filtering strict even when one side has no linked IDs.
        # The Tool/Jaw pages treat empty filter lists as "show all", so we
        # pass a guaranteed non-matching sentinel to force an empty result set.
        no_match_id = "__NO_MATCH_LINKED_ITEMS__"
        selected_module = "jaws" if module == "jaws" else "tools"
        if not safe_tools:
            safe_tools = [no_match_id]
        if not safe_jaws:
            safe_jaws = [no_match_id]

        if selected_module == "tools" and tool_ids is not None and not [str(t).strip() for t in (tool_ids or []) if str(t).strip()]:
            safe_tools = [no_match_id]
            QMessageBox.information(
                self,
                self._t("setup_manager.viewer.title", "Viewer"),
                self._t("setup_manager.viewer.no_tools", "No tools selected for this work."),
            )
        if selected_module == "jaws" and jaw_ids is not None and not [str(j).strip() for j in (jaw_ids or []) if str(j).strip()]:
            QMessageBox.information(
                self,
                self._t("setup_manager.viewer.title", "Viewer"),
                self._t("setup_manager.viewer.no_jaws", "No jaws selected for this work."),
            )

        x, y, width, height = self._current_window_rect()
        _allow_set_foreground()

        # Preferred path: IPC to the already-running Tool Library.
        payload = {
            "geometry": f"{x},{y},{width},{height}",
            "show": True,
            "master_filter_tools": safe_tools,
            "master_filter_jaws": safe_jaws,
            "master_filter_active": True,
            "module": selected_module,
        }
        if self._send_to_tool_library(payload):
            def _finish_handoff():
                self.hide()
                self.setWindowOpacity(1.0)
            self._fade_out_and(_finish_handoff)
            return

        # Fallback: launch a new Tool Library process.
        args = [
            "--geometry", f"{x},{y},{width},{height}",
            "--master-filter-tools", ",".join(safe_tools),
            "--master-filter-jaws", ",".join(safe_jaws),
            "--master-filter-active", "1",
        ]
        if self._launch_tool_library(args):
            self._send_request_with_retry(payload)
            def _finish_launch():
                self.hide()
                self.setWindowOpacity(1.0)
            self._fade_out_and(_finish_launch)
            return

        QMessageBox.warning(
            self,
            self._t("setup_manager.library_unavailable.title", "Tool Library unavailable"),
            self._t(
                "setup_manager.library_unavailable.body",
                "Could not find a launchable Tool Library executable or source entry point.",
            ),
        )

    def _send_request_with_retry(self, payload: dict, attempts: int = 12, delay_ms: int = 200):
        """Retry IPC shortly after launching Tool Library so module/filter payload is applied."""
        if self._send_to_tool_library(payload):
            return
        if attempts <= 1:
            return
        QTimer.singleShot(delay_ms, lambda: self._send_request_with_retry(payload, attempts - 1, delay_ms))

    def _set_launch_button_variant(self, button: QPushButton, primary: bool):
        button.setProperty("primaryAction", bool(primary))
        button.setProperty("secondaryAction", not bool(primary))
        button.style().unpolish(button)
        button.style().polish(button)

    def _on_setup_launch_context_changed(self, context):
        self._launch_context = dict(context or {})
        self._update_launch_actions()

    def _update_navigation_labels(self):
        drawings_enabled = self.ui_preferences.get("enable_drawings_tab", True)
        for idx, button in enumerate(getattr(self, "nav_buttons", [])):
            if idx == 0:
                text = self._t("setup_manager.nav.setups", "SETUPS")
                button.setVisible(True)
            elif idx == 1:
                key = "setup_manager.nav.show_drawing" if self._launch_context.get("selected") else "setup_manager.nav.drawings"
                default = "SHOW DRAWING" if self._launch_context.get("selected") else "DRAWINGS"
                text = self._t(key, default)
                button.setVisible(drawings_enabled)
                button.setEnabled(drawings_enabled)
                button.setToolTip("" if drawings_enabled else self._t("preferences.drawings_tab_disabled_hint", "Drawings tab is disabled in Preferences."))
            else:
                text = self._t("setup_manager.nav.logbook", "LOGBOOK")
                button.setVisible(True)
            button.setText(text)

    def _update_launch_actions(self):
        selected = bool(self._launch_context.get("selected"))
        self._update_navigation_labels()
        if selected:
            work_id = str(self._launch_context.get("work_id") or "").strip()
            self.launch_body.setText(
                self._t(
                    "setup_manager.launch.selected_body",
                    "Selected work {work_id}: open filtered Tool Library and Jaws Library views.",
                    work_id=work_id,
                )
                if work_id
                else self._t(
                    "setup_manager.launch.selected_body_no_id",
                    "Selected work: open filtered Tool Library and Jaws Library views.",
                )
            )
            self._set_launch_button_variant(self.open_tools_btn, True)
            self._set_launch_button_variant(self.open_jaws_btn, True)
        else:
            self.launch_body.setText(
                self._t(
                    "setup_manager.launch.default_body",
                    "Open Tool Library or Jaws Library. Select a work in Setup to open filtered data.",
                )
            )
            self._set_launch_button_variant(self.open_tools_btn, False)
            self._set_launch_button_variant(self.open_jaws_btn, False)

    def _open_tool_library_action(self):
        if self._launch_context.get("selected"):
            if not self._launch_context.get("has_data"):
                QMessageBox.information(
                    self,
                    self._t("setup_manager.viewer.title", "Viewer"),
                    self._t("setup_manager.viewer.no_links", "No jaw/tool links were found for this setup."),
                )
                return
            self._open_tool_library_with_master_filter(
                self._launch_context.get("tool_ids") or [],
                self._launch_context.get("jaw_ids") or [],
                module="tools",
            )
            return
        self._open_tool_library_module("tools")

    def _open_jaws_library_action(self):
        if self._launch_context.get("selected"):
            tool_ids = self._launch_context.get("tool_ids") or []
            jaw_ids = self._launch_context.get("jaw_ids") or []
            if not jaw_ids:
                QMessageBox.information(
                    self,
                    self._t("setup_manager.viewer.title", "Viewer"),
                    self._t("setup_manager.viewer.no_jaw_links", "Selected work has no jaw links."),
                )
                return
            self._open_tool_library_with_master_filter(tool_ids, jaw_ids, module="jaws")
            return
        self._open_tool_library_module("jaws")

    def _open_preferences(self):
        dialog = PreferencesDialog(
            self.ui_preferences,
            self._t,
            parent=self,
            active_db_path=str(getattr(self.work_service.db, "path", "") or ""),
            on_check_compatibility=self._check_setup_db_compatibility,
        )
        if dialog.exec() != PreferencesDialog.Accepted:
            return

        previous_language = self.ui_preferences.get("language", "en")
        previous_setup_db = str(self.ui_preferences.get("setup_db_path", "") or "").strip()
        self.ui_preferences = self.ui_preferences_service.save(dialog.preferences_payload())
        self.localization.set_language(self.ui_preferences.get("language", "en"))
        if hasattr(self.print_service, "set_translator"):
            self.print_service.set_translator(self._t)
        self._apply_style()
        self._refresh_localized_labels()

        # If currently on drawings page and it was just disabled, switch away
        if self.stack.currentIndex() == 1 and not self.ui_preferences.get("enable_drawings_tab", True):
            self._set_page(0)
        self.setup_page.drawings_enabled = self.ui_preferences.get("enable_drawings_tab", True)

        QMessageBox.information(
            self,
            self._t("preferences.saved_title", "Preferences"),
            self._t("preferences.saved_body", "Preferences saved."),
        )
        if self.ui_preferences.get("language", "en") != previous_language:
            QMessageBox.information(
                self,
                self._t("preferences.restart_title", "Restart Required"),
                self._t("preferences.restart_body", "Language changes will be applied after restarting the app."),
            )
        current_setup_db = str(self.ui_preferences.get("setup_db_path", "") or "").strip()
        if current_setup_db != previous_setup_db:
            QMessageBox.information(
                self,
                self._t("preferences.restart_title", "Restart Required"),
                self._t(
                    "preferences.restart_db_body",
                    "Database path changes will be applied after restarting the app.",
                ),
            )

    def _check_setup_db_compatibility(self, database_path: str):
        target_path = Path(str(database_path or "").strip()).expanduser()
        if not str(target_path).strip():
            QMessageBox.warning(
                self,
                self._t("preferences.database.compatibility.title", "Compatibility Check"),
                self._t("preferences.database.compatibility.empty_path", "No Setup database path was provided."),
            )
            return
        if not target_path.exists():
            QMessageBox.warning(
                self,
                self._t("preferences.database.compatibility.title", "Compatibility Check"),
                self._t(
                    "preferences.database.compatibility.missing_path",
                    "The selected Setup database was not found:\n{path}",
                    path=str(target_path),
                ),
            )
            return

        tool_refs = self.draw_service.list_tool_refs(force_reload=True, dedupe_by_id=False)
        jaw_refs = self.draw_service.list_jaw_refs(force_reload=True)
        tool_ids = {str(item.get("id") or "").strip() for item in tool_refs if str(item.get("id") or "").strip()}
        tool_uids = {
            int(item.get("uid")): item
            for item in tool_refs
            if item.get("uid") is not None and str(item.get("uid")).strip()
        }
        jaw_ids = {str(item.get("id") or "").strip() for item in jaw_refs if str(item.get("id") or "").strip()}

        try:
            conn = sqlite3.connect(str(target_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM works ORDER BY work_id COLLATE NOCASE ASC").fetchall()
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
        finally:
            try:
                conn.close()
            except Exception:
                pass

        works = [self.work_service._row_to_work(row) for row in rows]

        total_works = len(works)
        fully_resolved = 0
        works_with_issues = 0
        jaw_match_count = 0
        tool_uid_match_count = 0
        tool_id_fallback_count = 0
        missing_jaw_count = 0
        missing_tool_count = 0
        issue_lines = []

        for work in works:
            work_id = str(work.get("work_id") or "").strip() or "(no work ID)"
            local_missing = []

            for label, jaw_id in (
                (self._t("work_editor.ref.main_jaw", "Main jaw"), str(work.get("main_jaw_id") or "").strip()),
                (self._t("work_editor.ref.sub_jaw", "Sub jaw"), str(work.get("sub_jaw_id") or "").strip()),
            ):
                if not jaw_id:
                    continue
                if jaw_id in jaw_ids:
                    jaw_match_count += 1
                else:
                    missing_jaw_count += 1
                    local_missing.append(f"{label}: {jaw_id}")

            for head_label, assignments in (
                (self._t("work_editor.ref.head1_tool", "Head 1 tool"), work.get("head1_tool_assignments") or []),
                (self._t("work_editor.ref.head2_tool", "Head 2 tool"), work.get("head2_tool_assignments") or []),
            ):
                for assignment in assignments:
                    tool_id = str((assignment or {}).get("tool_id") or "").strip()
                    raw_uid = (assignment or {}).get("tool_uid")
                    matched = False
                    if raw_uid is not None and str(raw_uid).strip():
                        try:
                            if int(raw_uid) in tool_uids:
                                tool_uid_match_count += 1
                                matched = True
                        except Exception:
                            pass
                    if not matched and tool_id and tool_id in tool_ids:
                        tool_id_fallback_count += 1
                        matched = True
                    if not matched and tool_id:
                        missing_tool_count += 1
                        uid_text = f" [uid {raw_uid}]" if raw_uid is not None and str(raw_uid).strip() else ""
                        local_missing.append(f"{head_label}: {tool_id}{uid_text}")

            if local_missing:
                works_with_issues += 1
                issue_lines.append(f"{work_id}: " + "; ".join(local_missing))
            else:
                fully_resolved += 1

        summary = self._t(
            "preferences.database.compatibility.summary",
            "Works checked: {total}\nFully resolved: {resolved}\nWorks with issues: {issues}\n\nJaw matches: {jaw_matches}\nTool matches by UID: {tool_uid_matches}\nTool matches by ID fallback: {tool_id_fallbacks}\nMissing jaws: {missing_jaws}\nMissing tools: {missing_tools}",
            total=total_works,
            resolved=fully_resolved,
            issues=works_with_issues,
            jaw_matches=jaw_match_count,
            tool_uid_matches=tool_uid_match_count,
            tool_id_fallbacks=tool_id_fallback_count,
            missing_jaws=missing_jaw_count,
            missing_tools=missing_tool_count,
        )

        informative = self._t(
            "preferences.database.compatibility.informative",
            "Setup DB: {setup_db}\nTool DB: {tool_db}\nJaw DB: {jaw_db}",
            setup_db=str(target_path),
            tool_db=str(self.draw_service.tool_db_path),
            jaw_db=str(self.draw_service.jaw_db_path),
        )
        self._show_compatibility_report_dialog(
            title=self._t("preferences.database.compatibility.title", "Compatibility Check"),
            summary=summary,
            informative=informative,
            details="\n".join(issue_lines[:200]),
            has_issues=bool(works_with_issues),
        )

    def _show_compatibility_report_dialog(
        self,
        *,
        title: str,
        summary: str,
        informative: str,
        details: str,
        has_issues: bool,
    ):
        dialog = QDialog(self)
        setup_editor_dialog(dialog)
        dialog.setObjectName("compatibilityReportDialog")
        dialog.setProperty("preferencesDialog", True)
        dialog.setAttribute(Qt.WA_StyledBackground, True)
        dialog.setStyleSheet(
            "QDialog#compatibilityReportDialog {"
            " background-color: #ffffff;"
            "}"
        )
        dialog.setModal(True)
        dialog.setWindowTitle(title)
        dialog.resize(700, 560)

        root = QVBoxLayout(dialog)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        summary_group = create_titled_section(self._t("preferences.database.compatibility.summary_title", "Summary"))
        summary_layout = QVBoxLayout(summary_group)
        summary_layout.setContentsMargins(12, 12, 12, 12)
        summary_layout.setSpacing(8)

        status_label = QLabel(
            self._t(
                "preferences.database.compatibility.status_warning",
                "Compatibility issues were found.",
            )
            if has_issues
            else self._t(
                "preferences.database.compatibility.status_ok",
                "All checked work references resolved successfully.",
            )
        )
        status_label.setProperty("detailHint", True)
        status_label.setWordWrap(True)
        summary_layout.addWidget(status_label)

        summary_text = QPlainTextEdit()
        summary_text.setReadOnly(True)
        summary_text.setPlainText(summary)
        summary_text.setMinimumHeight(180)
        summary_text.setStyleSheet("QPlainTextEdit { background: #ffffff; }")
        summary_layout.addWidget(summary_text)
        root.addWidget(summary_group)

        db_group = create_titled_section(self._t("preferences.database.compatibility.paths_title", "Database Paths"))
        db_layout = QVBoxLayout(db_group)
        db_layout.setContentsMargins(12, 12, 12, 12)
        db_layout.setSpacing(8)
        info_text = QPlainTextEdit()
        info_text.setReadOnly(True)
        info_text.setPlainText(informative)
        info_text.setMinimumHeight(120)
        info_text.setStyleSheet("QPlainTextEdit { background: #ffffff; }")
        db_layout.addWidget(info_text)
        root.addWidget(db_group)

        if details:
            details_group = create_titled_section(self._t("preferences.database.compatibility.details_title", "Issue Details"))
            details_layout = QVBoxLayout(details_group)
            details_layout.setContentsMargins(12, 12, 12, 12)
            details_layout.setSpacing(8)
            details_text = QPlainTextEdit()
            details_text.setReadOnly(True)
            details_text.setPlainText(details)
            details_text.setMinimumHeight(140)
            details_text.setStyleSheet("QPlainTextEdit { background: #ffffff; }")
            details_layout.addWidget(details_text)
            root.addWidget(details_group, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        ok_btn = QPushButton(self._t("common.ok", "OK"))
        ok_btn.setProperty("panelActionButton", True)
        ok_btn.setProperty("primaryAction", True)
        add_shadow(ok_btn)
        ok_btn.clicked.connect(dialog.accept)
        button_row.addWidget(ok_btn)
        root.addLayout(button_row)

        dialog.exec()

    def _refresh_localized_labels(self):
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
        self._update_navigation_labels()
        if hasattr(self, "setup_page") and hasattr(self.setup_page, "apply_localization"):
            self.setup_page.apply_localization(self._t)
        if hasattr(self, "drawing_page") and hasattr(self.drawing_page, "apply_localization"):
            self.drawing_page.apply_localization(self._t)
        if hasattr(self, "logbook_page") and hasattr(self.logbook_page, "apply_localization"):
            self.logbook_page.apply_localization(self._t)
        self._update_status_message()
        self._update_launch_actions()

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
        theme_name = self.ui_preferences.get("color_theme", "classic")
        palette = THEME_PALETTES.get(theme_name, THEME_PALETTES["classic"])
        font_family = self.ui_preferences.get("font_family", "Segoe UI").replace("'", "\\'")
        return (
            "/* Runtime UI preference overrides */\n"
            f"* {{ font-family: '{font_family}'; }}\n"
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
            "QFrame[detailField=\"true\"],\n"
            "QFrame[detailField=\"true\"][detailHeroField=\"true\"] {\n"
            f"    background-color: {palette['detail_box_bg']};\n"
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

    def closeEvent(self, event):
        """Save window geometry when closing for restoration on next launch."""
        x, y, width, height = self._current_window_rect()
        geom_file = Path(self.work_service.db.path).parent / ".window_geometry"
        try:
            geom_file.write_text(f"{x},{y},{width},{height}")
        except Exception:
            pass
        super().closeEvent(event)
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
