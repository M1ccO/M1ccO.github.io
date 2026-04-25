import logging
from pathlib import Path
import time

from PySide6.QtCore import QEvent, QTimer, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_TITLE,
    ENABLE_TOOL_LIBRARY_PRELOAD,
    NAV_ITEMS,
    STYLE_PATH,
    SHARED_UI_PREFERENCES_PATH,
    I18N_DIR,
    TOOL_ICONS_DIR,
    TOOL_LIBRARY_READY_PATH,
    TOOL_LIBRARY_EXE_CANDIDATES,
    TOOL_LIBRARY_MAIN_PATH,
    TOOL_LIBRARY_PROJECT_DIR,
    TOOL_LIBRARY_SERVER_NAME,
)


from ui.drawing_page import DrawingPage
from ui.logbook_page import LogbookPage
from ui.setup_catalog_delegate import apply_delegate_theme as apply_setup_delegate_theme
from ui.setup_page import SetupPage
from shared.services.ui_preferences_service import UiPreferencesService
from shared.services.localization_service import LocalizationService
from ui.widgets.common import clear_focused_dropdown_on_outside_click
from ui.main_window_support import (
    build_footer_actions_section,
    build_primary_nav_section,
    build_rail_header_section,
    clear_active_page_selection_on_background_click,
    clear_page_selection,
    complete_tool_library_handoff,
    initialize_preload_state,
    is_tool_library_ready,
    launch_tool_library,
    on_setup_launch_context_changed,
    open_tool_library_deep_link,
    open_tool_library_module,
    open_tool_library_with_master_filter,
    open_jaws_library_action,
    open_preferences_action,
    open_tool_library_action,
    preload_tool_library_background,
    retry_tool_library_preload,
    send_request_with_retry,
    send_to_tool_library,
    update_launch_actions,
    update_navigation_labels,
)
from ui.machine_family_runtime import is_machining_center_family, secondary_library_module
from shared.ui.main_window_helpers import current_window_rect, fade_in as _shared_fade_in, fade_out_and as _shared_fade_out_and
from shared.ui.layout_contract import get_container_layout_contract, get_required_rail_width
from shared.ui.theme import compile_app_stylesheet, get_active_theme_palette, install_application_theme_state
class MainWindow(QMainWindow):
    _LOGGER = logging.getLogger(__name__)

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
        initialize_preload_state(self)
        self._runtime_initialized = False
        self._is_shutting_down = False
        self._modal_trace_enabled = False
        self._modal_trace_started_at = 0.0
        self._modal_trace_event_count = 0
        self._modal_trace_log_path = Path(__file__).resolve().parents[1] / "temp" / "setup_manager_modal_trace.log"

        self._build_ui()
        self._apply_style()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self.localization.t(key, default, **kwargs)

    def _begin_modal_trace(self, label: str, **fields) -> None:
        self._modal_trace_enabled = True
        self._modal_trace_started_at = 0.0
        self._modal_trace_event_count = 0
        self._trace_modal_event("modal_trace_begin", label=label, **fields)

    def _end_modal_trace(self, reason: str, **fields) -> None:
        if not self._modal_trace_enabled:
            return
        self._trace_modal_event("modal_trace_end", reason=reason, **fields)
        self._modal_trace_enabled = False

    def _trace_modal_event(self, name: str, **fields) -> None:
        if not self._modal_trace_enabled and name not in ("modal_trace_begin", "modal_trace_end"):
            return

        now = time.monotonic()
        if self._modal_trace_started_at <= 0.0:
            self._modal_trace_started_at = now
            self._modal_trace_event_count = 0
        if self._modal_trace_event_count >= 120:
            return
        if name not in ("modal_trace_begin", "modal_trace_end") and (now - self._modal_trace_started_at) > 4.0:
            return

        self._modal_trace_event_count += 1
        payload = {
            "event": name,
            "dt_ms": int((now - self._modal_trace_started_at) * 1000),
            **{key: value for key, value in fields.items() if value not in (None, "")},
        }
        self._LOGGER.info("setup_manager.modal_trace %s", payload)
        try:
            self._modal_trace_log_path.parent.mkdir(parents=True, exist_ok=True)
            file_mode = "w" if self._modal_trace_event_count == 1 else "a"
            with self._modal_trace_log_path.open(file_mode, encoding="utf-8") as handle:
                handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {payload}\n")
        except Exception:
            pass

    def eventFilter(self, obj, event):
        if self._modal_trace_enabled:
            if obj is self and event.type() in (
                QEvent.Show,
                QEvent.Hide,
                QEvent.Move,
                QEvent.Resize,
                QEvent.Paint,
                QEvent.UpdateRequest,
                QEvent.WindowActivate,
                QEvent.WindowDeactivate,
                QEvent.WindowStateChange,
            ):
                self._trace_modal_event(
                    event.type().name,
                    visible=self.isVisible(),
                    active=self.isActiveWindow(),
                    minimized=self.isMinimized(),
                    size=f"{self.width()}x{self.height()}",
                    modal=bool(QApplication.activeModalWidget()),
                )
            elif (
                event.type() == QEvent.MouseButtonPress
                and isinstance(obj, QWidget)
                and obj.window() is self
            ):
                self._trace_modal_event(
                    "MouseButtonPress",
                    source=type(obj).__name__,
                    modal=bool(QApplication.activeModalWidget()),
                )
        if event.type() == QEvent.MouseButtonPress:
            clear_focused_dropdown_on_outside_click(obj, self)
            clear_active_page_selection_on_background_click(self, obj)
        return super().eventFilter(obj, event)

    def _clear_active_page_selection_on_background_click(self, obj):
        clear_active_page_selection_on_background_click(self, obj)

    def _clear_page_selection(self, page: QWidget):
        clear_page_selection(page)

    def _build_ui(self):
        layout_contract = get_container_layout_contract()
        setup_rail_title = self._t("setup_manager.rail_title", "Setup Manager")
        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 12, 0)
        root.setSpacing(0)

        self.nav_rail = QFrame()
        self.nav_rail.setProperty("navRail", True)
        self.nav_rail.setFixedWidth(get_required_rail_width(setup_rail_title, layout_contract))
        nav_layout = QVBoxLayout(self.nav_rail)
        nav_layout.setContentsMargins(*layout_contract.rail_margins)
        nav_layout.setSpacing(layout_contract.rail_section_spacing)

        nav_layout.addWidget(build_rail_header_section(self))
        nav_layout.addWidget(
            build_primary_nav_section(
                self,
                nav_items=list(NAV_ITEMS),
                on_nav_click=self._set_page,
            )
        )

        nav_layout.addStretch(1)
        nav_layout.addWidget(
            build_footer_actions_section(
                self,
                tool_icons_dir=TOOL_ICONS_DIR,
                on_open_tools=lambda: open_tool_library_action(self),
                on_open_jaws=lambda: open_jaws_library_action(self),
                on_open_preferences=lambda: open_preferences_action(self),
            )
        )

        root.addWidget(self.nav_rail)

        self._initialize_pages()
        root.addWidget(self.stack, 1)

        self._initialize_status_bar()

        self._set_page(0)

    def _set_rail_width_for_title(self, title_text: str) -> None:
        if not hasattr(self, "nav_rail"):
            return
        contract = get_container_layout_contract()
        self.nav_rail.setFixedWidth(get_required_rail_width(title_text, contract))

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
        fixture_state = (
            Path(source_status["fixture_db_path"]).name
            if source_status.get("fixture_db_exists")
            else self._t("setup_manager.status.missing", "missing")
        )
        self._status_data = {
            "setup_db": db_name,
            "tool_db": tool_state,
            "jaw_db": jaw_state,
            "fixture_db": fixture_state,
        }
        self._update_status_message()

    def _is_machining_center_profile(self) -> bool:
        try:
            key = str(self.work_service.get_machine_profile_key() or "").strip()
            return bool(is_machining_center_family(profile_key=key))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Tool Library launcher helpers
    # ------------------------------------------------------------------

    def _send_to_tool_library(self, payload: dict, *, retries: int = 3, timeout_ms: int = 1500) -> bool:
        """Send an IPC message to a running Tool Library instance. Returns True on success."""
        if getattr(self, "_is_shutting_down", False):
            return False
        return send_to_tool_library(
            TOOL_LIBRARY_SERVER_NAME,
            payload,
            retries=max(1, int(retries)),
            timeout_ms=max(50, int(timeout_ms)),
        )

    def _launch_tool_library(self, extra_args: list = None) -> bool:
        """Start the Tool Library process. Returns True on success."""
        if getattr(self, "_is_shutting_down", False):
            return False
        return launch_tool_library(
            TOOL_LIBRARY_MAIN_PATH,
            TOOL_LIBRARY_EXE_CANDIDATES,
            TOOL_LIBRARY_PROJECT_DIR,
            extra_args,
            ready_path=TOOL_LIBRARY_READY_PATH,
        )

    def _is_tool_library_ready(self) -> bool:
        return is_tool_library_ready(
            TOOL_LIBRARY_SERVER_NAME,
            TOOL_LIBRARY_READY_PATH,
        )

    def _preload_tool_library_background(self):
        if getattr(self, "_is_shutting_down", False):
            return
        preload_tool_library_background(self)

    def _retry_tool_library_preload(self):
        if getattr(self, "_is_shutting_down", False):
            return
        retry_tool_library_preload(self)

    def _fade_out_and(self, callback):
        # Hide immediately — the Library/selector window appearing is the visual
        # transition. A fade-out here fights fade-in on return and causes flashes.
        self.hide()
        self.setWindowOpacity(1.0)
        callback()

    def fade_in(self):
        _shared_fade_in(self)

    def _current_window_rect(self) -> tuple[int, int, int, int]:
        return current_window_rect(self)

    def _complete_tool_library_handoff(self):
        complete_tool_library_handoff(self)

    def _open_tool_library_together(self):
        # Legacy external hook retained for backward compatibility.
        """Backward-compatible helper that opens Tool Library tools module without filters."""
        self._open_tool_library_module("tools")

    def _open_tool_library_module(self, module: str):
        if getattr(self, "_is_shutting_down", False):
            return
        open_tool_library_module(self, module)

    def _open_tool_library_separate(self):
        # Legacy external hook retained for backward compatibility.
        """Backward-compatible helper that opens Jaws/Fixtures module without filters."""
        self._open_tool_library_module(
            secondary_library_module(profile_key=self.work_service.get_machine_profile_key())
        )

    def _open_tool_library_deep_link(self, kind: str, item_id: str):
        if getattr(self, "_is_shutting_down", False):
            return
        open_tool_library_deep_link(self, kind, item_id)

    def _open_tool_library_with_master_filter(self, tool_ids, jaw_ids, module: str = "tools"):
        if getattr(self, "_is_shutting_down", False):
            return
        open_tool_library_with_master_filter(self, tool_ids, jaw_ids, module=module)

    def _send_request_with_retry(
        self,
        payload: dict,
        attempts: int = 44,
        delay_ms: int = 150,
        on_success=None,
        on_failed=None,
    ):
        """Retry IPC shortly after launching Tool Library so module/filter payload is applied.

        Tool Library startup can race with the first IPC attempt; this helper smooths over
        that timing window without blocking the UI thread.
        """
        if getattr(self, "_is_shutting_down", False):
            return
        send_request_with_retry(
            self._send_to_tool_library,
            payload,
            attempts=attempts,
            delay_ms=delay_ms,
            on_success=on_success,
            on_failed=on_failed,
            ready_check=self._is_tool_library_ready,
        )

    def _refresh_localized_labels(self):
        # Keep text refresh order stable: shell labels first, then child pages, then stateful
        # launch/status text that depends on current context and translated strings.
        self.setWindowTitle(self._t("setup_manager.window_title", APP_TITLE))
        if hasattr(self, "rail_title_label"):
            rail_title = self._t("setup_manager.rail_title", "Setup Manager")
            self.rail_title_label.setText(rail_title)
            self._set_rail_width_for_title(rail_title)
        if hasattr(self, "launch_title"):
            self.launch_title.setText(self._t("setup_manager.launch.title", "Master Data"))
        if hasattr(self, "open_tools_btn"):
            self.open_tools_btn.setText(self._t("setup_manager.open_tool_library", "Open Tool Library"))
        if hasattr(self, "open_jaws_btn"):
            if secondary_library_module(profile_key=self.work_service.get_machine_profile_key()) == "fixtures":
                self.open_jaws_btn.setText(self._t("setup_manager.open_fixtures_library", "Open Fixtures Library"))
            else:
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
        if self._is_machining_center_profile():
            message = self._t(
                "setup_manager.status.message_mc",
                "Setup DB: {setup_db} | Tool DB: {tool_db} | Fixture DB: {fixture_db}",
                setup_db=self._status_data.get("setup_db", ""),
                tool_db=self._status_data.get("tool_db", ""),
                fixture_db=self._status_data.get("fixture_db", ""),
            )
        else:
            message = self._t(
                "setup_manager.status.message",
                "Setup DB: {setup_db} | Tool DB: {tool_db} | Jaw DB: {jaw_db}",
                setup_db=self._status_data.get("setup_db", ""),
                tool_db=self._status_data.get("tool_db", ""),
                jaw_db=self._status_data.get("jaw_db", ""),
            )
        self._status_bar.showMessage(message)

    def _build_ui_preference_overrides(self) -> str:
        # Shared compiler owns the final runtime overrides; keep this method as a
        # compatibility hook so older call sites still have one stable entry point.
        _ = get_active_theme_palette(self.ui_preferences)
        return ""

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
        first_show = not self._runtime_initialized
        if first_show:
            self._runtime_initialized = True
            QApplication.instance().installEventFilter(self)
            # Keep first show free of hidden dialog warmups; the old Work Editor
            # preload was the source of the launch-time hide/show flash.
            if ENABLE_TOOL_LIBRARY_PRELOAD and not getattr(self, "_tool_library_preload_completed", False):
                # The hidden Library process is already launched during startup.
                # This follow-up pass only syncs the active DB/profile payload and
                # warms the hidden instance, so it can run much sooner than the
                # original cold-start launch without causing a visible hitch.
                QTimer.singleShot(900, self._preload_tool_library_background)
        self.ui_preferences = self.ui_preferences_service.load()
        self.localization.set_language(self.ui_preferences.get("language", "en"))

        # On every re-show except the first one, assume the user may have
        # returned from the Tool Library process and invalidate resolver
        # caches so freshly edited tool/jaw metadata renders correctly on
        # the next Setup Card / Work Editor open.
        if not first_show:
            try:
                from services.preload_manager import get_preload_manager

                get_preload_manager().bump_revisions()
            except Exception:
                pass

    def closeEvent(self, event):
        """Save window geometry when closing for restoration on next launch."""
        self._is_shutting_down = True
        # Best-effort: keep Tool Library hidden if an earlier handoff/retry left
        # a pending show payload in flight.
        try:
            send_to_tool_library(TOOL_LIBRARY_SERVER_NAME, {"show": False})
        except Exception:
            pass
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
            palette = install_application_theme_state(self.ui_preferences)
            apply_setup_delegate_theme(palette)
            style_sheet = compile_app_stylesheet(STYLE_PATH, self.ui_preferences)
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(style_sheet)
            else:
                self.setStyleSheet(style_sheet)
        except Exception:
            pass

