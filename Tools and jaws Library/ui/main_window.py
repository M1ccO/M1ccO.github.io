import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from PySide6.QtCore import (
    QEvent,
    QSize,
    Signal,
    Qt,
    QTimer,
    QPoint,
)
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QPixmap, QTransform
from PySide6.QtWidgets import (
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
    QSizePolicy,
)
from config import (
    APP_TITLE,
    APP_DIR,
    SOURCE_DIR,
    SHARED_UI_PREFERENCES_PATH,
    I18N_DIR,
    RAIL_HEAD_DROPDOWN_WIDTH,
    TOOL_ICONS_DIR,
    SETUP_MANAGER_SERVER_NAME,
    TOOL_LIBRARY_SERVER_NAME,
)
from data.database import Database
from data.fixture_database import FixtureDatabase
from data.jaw_database import JawDatabase
from services.fixture_service import FixtureService
from services.jaw_service import JawService
from shared.services.localization_service import LocalizationService
from shared.services.tool_lib_profile_view import ToolLibProfileView, profile_view_from_key
from services.tool_service import ToolService
from shared.services.ui_preferences_service import UiPreferencesService
from ui.export_page import ExportPage
from ui.fixture_page import FixturePage
from ui.home_page import HomePage
from ui.jaw_export_page import JawExportPage
from ui.jaw_page import JawPage
from ui.main_window_support import (
    clear_active_page_selection_on_background_click,
    empty_selector_session_state,
    handoff_to_setup_manager,
    selector_session_from_payload,
    send_selector_result_payload,
)
from ui.selectors.external_preview_host import close_external_selector_preview
from ui.selectors import FixtureSelectorDialog, JawSelectorDialog, ToolSelectorDialog
from ui.jaw_catalog_delegate import apply_delegate_theme as apply_jaw_delegate_theme
from ui.tool_catalog_delegate import apply_delegate_theme as apply_tool_delegate_theme
from ui.widgets.common import clear_focused_dropdown_on_outside_click
from shared.ui.main_window_helpers import THEME_PALETTES, apply_frame_geometry_string, current_window_rect, fade_in as _shared_fade_in, fade_out_and as _shared_fade_out_and, get_active_theme_palette
from shared.ui.theme import compile_app_stylesheet, current_theme_color, install_application_theme_state
from shared.ui.helpers.icon_loader import icon_from_path
from shared.ui.layout_contract import get_container_layout_contract, get_required_rail_width


class RailHeadToggleButton(QPushButton):
    currentIndexChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[tuple[str, str]] = []
        self._current_index = -1
        self._last_single_value = 'HEAD1'
        self.setContextMenuPolicy(Qt.NoContextMenu)

    def set_options(self, items: list[tuple[str, str]]):
        current_value = self.currentData() or self._last_single_value or 'HEAD1'
        self._items = [(str(text), str(data).strip().upper()) for text, data in items]
        if current_value not in {data for _, data in self._items}:
            current_value = 'HEAD1'
        self.setCurrentData(current_value, emit_signal=False)

    def count(self) -> int:
        return len(self._items)

    def currentData(self):
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index][1]
        return None

    def currentText(self) -> str:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index][0]
        return ''

    def setCurrentData(self, value: str, emit_signal: bool = True):
        normalized = str(value or 'HEAD1').strip().upper()
        if normalized not in {'HEAD1/2', 'HEAD1', 'HEAD2'}:
            normalized = 'HEAD1'
        for idx, (text, data) in enumerate(self._items):
            if data != normalized:
                continue
            changed = idx != self._current_index
            self._current_index = idx
            if normalized in {'HEAD1', 'HEAD2'}:
                self._last_single_value = normalized
            self.setText(text)
            self.update()
            if changed and emit_signal and not self.signalsBlocked():
                self.currentIndexChanged.emit(idx)
            return

    def mouseReleaseEvent(self, event):
        if not self.isEnabled() or not self.rect().contains(event.pos()):
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.RightButton:
            self.setCurrentData('HEAD1/2')
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            next_value = 'HEAD2' if (self._last_single_value or 'HEAD1') == 'HEAD1' else 'HEAD1'
            self.setCurrentData(next_value)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PlaceholderPage(QWidget):
    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        heading = QLabel(title)
        heading.setProperty('pageTitle', True)
        body = QLabel(text)
        body.setWordWrap(True)
        card = QFrame()
        card.setProperty('card', True)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.addWidget(body)
        c_layout.addStretch(1)
        layout.addWidget(heading)
        layout.addWidget(card)
        layout.addStretch(1)


_LIBRARY_DETACHED_PREVIEW_PAGE_ATTRS = (
    'home_page',
    'jaws_page',
    'fixtures_page',
    'assemblies_page',
    'holders_page',
    'inserts_page',
)


def _close_library_detached_previews(window) -> None:
    for attr_name in _LIBRARY_DETACHED_PREVIEW_PAGE_ATTRS:
        page = getattr(window, attr_name, None)
        if page is None:
            continue

        close_preview = getattr(page, '_close_detached_preview', None)
        if callable(close_preview):
            try:
                close_preview()
            except Exception:
                pass
            continue

        dialog = getattr(page, '_detached_preview_dialog', None)
        if dialog is None:
            continue
        try:
            dialog.close()
        except Exception:
            pass


def _close_selector_detached_preview(window) -> None:
    try:
        close_external_selector_preview(window)
    except Exception:
        pass


class MainWindow(QMainWindow):
    def __init__(self, tool_service, jaw_service, fixture_service, export_service, settings_service, launch_master_filter=None):
        super().__init__()
        self.tool_service = tool_service
        self.jaw_service = jaw_service
        self.fixture_service = fixture_service
        self.export_service = export_service
        self.settings_service = settings_service
        self.ui_preferences_service = UiPreferencesService(
            SHARED_UI_PREFERENCES_PATH,
            include_setup_db_path=False,
        )
        self.ui_preferences = self.ui_preferences_service.load()
        self.machine_profile: ToolLibProfileView = self._resolve_machine_profile(
            self.ui_preferences.get('machine_profile_key')
        )
        self.localization = LocalizationService(I18N_DIR)
        self.localization.set_language(self.ui_preferences.get("language", "en"))
        if hasattr(self.export_service, "set_translator"):
            self.export_service.set_translator(self._t)
        self._clamping_screen_bounds = False
        self._active_module = 'tools'
        launch_master_filter = launch_master_filter or {}
        self._master_filter_enabled = bool(launch_master_filter.get('enabled', False))
        self._master_filter_active = bool(launch_master_filter.get('active', False)) and self._master_filter_enabled
        self._master_filter_tool_ids = {str(v).strip() for v in (launch_master_filter.get('tool_ids') or []) if str(v).strip()}
        self._master_filter_jaw_ids = {str(v).strip() for v in (launch_master_filter.get('jaw_ids') or []) if str(v).strip()}
        self._selector_mode = ''
        self._selector_callback_server = ''
        self._selector_request_id = ''
        self._selector_head = ''
        self._selector_spindle = ''
        self._selector_initial_assignments: list[dict] = []
        self._selector_initial_assignment_buckets: dict[str, list[dict]] = {}
        self._selector_print_pots: bool = False
        self._tool_selector_dialog: ToolSelectorDialog | None = None
        self._jaw_selector_dialog: JawSelectorDialog | None = None
        self._fixture_selector_dialog: FixtureSelectorDialog | None = None
        self._closing_selector_dialogs = False
        # Warm-cache: pre-built dialogs that survive between selector sessions.
        # Created once at startup so the expensive widget-tree construction and
        # catalog query are already paid before the first IPC request arrives.
        # Mirrors the Work Editor shared-dialog cache pattern.
        self._tool_selector_dialog_warmcache: ToolSelectorDialog | None = None
        self._jaw_selector_dialog_warmcache: JawSelectorDialog | None = None
        self._fixture_selector_dialog_warmcache: FixtureSelectorDialog | None = None
        self._runtime_initialized = False
        self._background_catalog_preload_done = False
        self._pending_external_frame_geometry = ''
        self._applying_external_frame_geometry = False
        self._external_geometry_clamp_suspended = False
        self._external_geometry_clamp_release_timer = None
        self.setWindowTitle(self._t("tool_library.window_title", APP_TITLE))
        self.resize(1280, 780)
        self._build_ui(self.tool_service, self.jaw_service, self.fixture_service, self.export_service, self.settings_service)
        self._apply_style()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self.localization.t(key, default, **kwargs)

    @staticmethod
    def _resolve_machine_profile(profile_key: str | None) -> ToolLibProfileView:
        """Resolve a profile key into the shared lightweight Tool Library profile view."""
        return profile_view_from_key(profile_key)

    def _is_machining_center(self) -> bool:
        return self.machine_profile.is_machining_center()

    def _profile_head_keys(self) -> list[str]:
        return self.machine_profile.head_keys()

    def moveEvent(self, event):
        super().moveEvent(event)
        if self._applying_external_frame_geometry or self._external_geometry_clamp_suspended:
            return
        self._ensure_on_screen()

    def _release_external_geometry_clamp(self) -> None:
        self._external_geometry_clamp_suspended = False

    def _suspend_external_geometry_clamp(self, duration_ms: int = 0) -> None:
        self._external_geometry_clamp_suspended = bool(duration_ms > 0)
        timer = self._external_geometry_clamp_release_timer
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._release_external_geometry_clamp)
            self._external_geometry_clamp_release_timer = timer
        else:
            timer.stop()
        if duration_ms > 0:
            timer.start(max(0, int(duration_ms)))

    def showEvent(self, event):
        """Reload shared preferences when window is shown to sync with Setup Manager."""
        super().showEvent(event)
        if not self._runtime_initialized:
            self._runtime_initialized = True
            QApplication.instance().installEventFilter(self)
            QTimer.singleShot(0, self.preload_catalog_pages)
        self.ui_preferences = self.ui_preferences_service.load()
        self.localization.set_language(self.ui_preferences.get("language", "en"))
        pending_geometry = str(self._pending_external_frame_geometry or '').strip()
        if pending_geometry:
            self._pending_external_frame_geometry = ''
            self._suspend_external_geometry_clamp(520)
            self._applying_external_frame_geometry = True
            try:
                apply_frame_geometry_string(self, pending_geometry, retry_delays_ms=(0, 120, 320))
            finally:
                self._applying_external_frame_geometry = False
            return
        self._ensure_on_screen()

    def _preload_catalog_page(self, page) -> None:
        if page is None:
            return
        try:
            ensure_polished = getattr(page, "ensurePolished", None)
            if callable(ensure_polished):
                ensure_polished()
            layout = getattr(page, "layout", lambda: None)()
            if layout is not None:
                layout.activate()
        except Exception:
            pass

        try:
            setattr(page, "_initial_load_done", True)
            setattr(page, "_initial_load_scheduled", False)
            setattr(page, "_deferred_refresh_needed", False)
            refresh_catalog = getattr(page, "refresh_catalog", None)
            if callable(refresh_catalog):
                refresh_catalog()
        except Exception:
            logger.debug("Background catalog preload failed for %s", type(page).__name__, exc_info=True)

    def preload_catalog_pages(self) -> None:
        if self._background_catalog_preload_done:
            return
        self._background_catalog_preload_done = True
        try:
            self._preload_catalog_page(self.home_page)
            self._preload_catalog_page(self.jaws_page)
            self._preload_catalog_page(self.fixtures_page)
        except Exception:
            self._background_catalog_preload_done = False
            logger.debug("Background catalog preload failed", exc_info=True)

    def _position_rail_title(self):
        pass  # title is now in the layout rail

    def _ensure_on_screen(self):
        if self._clamping_screen_bounds or self._external_geometry_clamp_suspended:
            return
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or self.screen()
        if screen is None:
            return
        self._clamping_screen_bounds = True
        try:
            available = screen.availableGeometry()
            geom = self.frameGeometry()

            frame_w_extra = max(0, geom.width() - self.width())
            frame_h_extra = max(0, geom.height() - self.height())
            max_client_w = max(320, available.width() - frame_w_extra)
            max_client_h = max(260, available.height() - frame_h_extra)

            width = min(self.width(), max_client_w)
            height = min(self.height(), max_client_h)
            if width != self.width() or height != self.height():
                self.resize(width, height)
                geom = self.frameGeometry()

            x = min(max(geom.x(), available.left()), available.right() - geom.width() + 1)
            y = min(max(geom.y(), available.top()), available.bottom() - geom.height() + 1)
            if x != geom.x() or y != geom.y():
                self.move(x, y)
        finally:
            self._clamping_screen_bounds = False

    def _icon_by_name(self, icon_name: str, target_size: QSize | None = None, rotation: int = 0) -> QIcon:
        path = self._resolve_icon_path(icon_name)
        if path is None:
            return QIcon()
        if target_size is None:
            target_size = QSize(34, 34)
        if rotation:
            pm = self._pixmap_by_path(path, target_size)
            if pm.isNull():
                return QIcon()
            return QIcon(pm.transformed(QTransform().rotate(rotation), Qt.SmoothTransformation))
        # Keep icon loading aligned with shared helper so SVGs still render
        # even when the Qt SVG icon engine plugin is unavailable.
        if path.suffix.lower() == '.svg':
            return icon_from_path(path, size=target_size)
        return QIcon(self._clean_icon_pixmap(str(path), target_size))

    def _resolve_icon_path(self, icon_name: str):
        candidates = [icon_name]
        stem = Path(icon_name).stem
        suffix = Path(icon_name).suffix.lower()
        if suffix == '.png':
            candidates.append(f'{stem}.svg')
        elif suffix == '.svg':
            candidates.append(f'{stem}.png')
        else:
            candidates.extend([f'{stem}.png', f'{stem}.svg'])

        for candidate in candidates:
            tool_path = TOOL_ICONS_DIR / candidate
            if tool_path.exists():
                return tool_path
        return None

    def _pixmap_by_path(self, path: Path, target_size: QSize) -> QPixmap:
        if path.suffix.lower() == '.svg':
            icon = icon_from_path(path, size=target_size)
            return icon.pixmap(target_size) if not icon.isNull() else QPixmap()
        return self._clean_icon_pixmap(str(path), target_size)

    def _clean_icon_pixmap(self, icon_path: str, target_size: QSize) -> QPixmap:
        pm = QPixmap(icon_path)
        if pm.isNull():
            return QPixmap()

        img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
        w = img.width()
        h = img.height()

        # Remove pasted white backgrounds from PNG icons by making near-white pixels transparent.
        for y in range(h):
            for x in range(w):
                c = QColor(img.pixel(x, y))
                if c.alpha() > 0 and c.red() >= 246 and c.green() >= 246 and c.blue() >= 246:
                    c.setAlpha(0)
                    img.setPixelColor(x, y, c)

        cropped = QPixmap.fromImage(img)
        return cropped.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _build_ui(self, tool_service, jaw_service, fixture_service, export_service, settings_service):
        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)

        # ── Main layout: rail + stack, matching Setup Manager structure ──────
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 12, 0)
        root.setSpacing(0)

        # ── Left navigation rail — geometry driven by shared layout contract ──
        lc = get_container_layout_contract()
        lib_rail_title = self._t("tool_library.rail_title.tools", "Tool Library")
        self.toggle_rail = QFrame()
        self.toggle_rail.setProperty('navRail', True)
        self.toggle_rail.setFixedWidth(get_required_rail_width(lib_rail_title, lc))
        self.toggle_rail.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        toggle_layout = QVBoxLayout(self.toggle_rail)
        toggle_layout.setContentsMargins(*lc.rail_margins)
        toggle_layout.setSpacing(lc.rail_section_spacing)

        # ── Header section (matches build_rail_header_section geometry) ───────
        header_section = QFrame()
        header_section.setObjectName("libRailHeaderSection")
        header_inner = QVBoxLayout(header_section)
        header_inner.setContentsMargins(*lc.rail_header_inner_margins)
        header_inner.setSpacing(0)
        self.rail_title = QLabel(lib_rail_title)
        self.rail_title.setStyleSheet(
            f"color: #000000; font-size: {lc.rail_header_font_pt}pt; font-weight: 700;"
        )
        self.rail_title.setWordWrap(False)
        self.rail_title.setFixedHeight(lc.rail_header_height)
        self.rail_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header_inner.addWidget(self.rail_title)
        toggle_layout.addWidget(header_section)

        # ── HEAD nav buttons — top-inset matches build_primary_nav_section ───
        head_section = QFrame()
        head_section.setObjectName("libRailHeadNavSection")
        head_layout = QVBoxLayout(head_section)
        head_layout.setContentsMargins(0, lc.rail_nav_section_top_inset, 0, 0)
        head_layout.setSpacing(8)
        head_keys = self._profile_head_keys()
        self._head_nav_buttons: list[QPushButton] = []
        for head_key in head_keys:
            head_label = head_key.replace('HEAD', 'Pää ')
            btn = QPushButton(head_label)
            btn.setProperty('navButton', True)
            btn.setProperty('active', head_key == head_keys[0])
            btn.clicked.connect(lambda checked=False, k=head_key: self._on_head_nav_clicked(k))
            head_layout.addWidget(btn)
            self._head_nav_buttons.append(btn)
        toggle_layout.addWidget(head_section)

        toggle_layout.addStretch(1)

        # Hidden RailHeadToggleButton kept for API compatibility with pages
        # that call bind_external_head_filter(). Not shown in UI.
        self.tool_head_filter_combo = RailHeadToggleButton()
        self.tool_head_filter_combo.setObjectName('toolHeadRailFilter')
        self.tool_head_filter_combo.setVisible(False)
        self._rebuild_head_filter_combo_items()
        self.tool_head_filter_combo.currentIndexChanged.connect(self._on_global_tool_head_changed)

        # Launch card — mirrors Setup Manager's bottom-of-rail launch area
        self.footer_actions = QFrame()
        self.footer_actions.setObjectName('railFooterActions')
        self.footer_actions.setProperty('launchCard', True)
        self.footer_actions.setFixedWidth(lc.rail_footer_card_width)
        self.footer_actions.setMinimumHeight(lc.rail_footer_card_min_height)
        footer_layout = QVBoxLayout(self.footer_actions)
        footer_layout.setContentsMargins(12, 12, 12, 12)
        footer_layout.setSpacing(8)

        launch_title = QLabel(self._t("tool_library.launch.title", "Kirjastot"))
        launch_title.setProperty('sectionTitle', True)
        footer_layout.addWidget(launch_title)

        launch_body = QLabel(self._t("tool_library.launch.hint", "Switch between libraries"))
        launch_body.setProperty('navHint', True)
        launch_body.setWordWrap(True)
        launch_body.setMaximumHeight(48)
        footer_layout.addWidget(launch_body)

        self.module_toggle_btn = QPushButton(self._t("tool_library.launch.jaws", "LEUAT"))
        self.module_toggle_btn.setProperty('panelActionButton', True)
        self.module_toggle_btn.setProperty('sidebarLaunchButton', True)
        self.module_toggle_btn.setMinimumWidth(154)
        self.module_toggle_btn.clicked.connect(self._on_module_toggle_clicked)
        footer_layout.addWidget(self.module_toggle_btn)

        # Keep old names as aliases for API compat (pages may hold references)
        self.open_tools_btn = self.module_toggle_btn
        self.open_jaws_btn = self.module_toggle_btn

        self.master_filter_toggle = QToolButton()
        self.master_filter_toggle.setObjectName('masterFilterToggle')
        self.master_filter_toggle.setProperty('topBarIconButton', True)
        self.master_filter_toggle.setCheckable(True)
        self.master_filter_toggle.setAutoRaise(True)
        self.master_filter_toggle.setFixedSize(48, 48)
        self.master_filter_toggle.setIconSize(QSize(36, 36))
        self.master_filter_toggle.setIcon(self._icon_by_name('filter_off.svg', QSize(42, 42)))
        self.master_filter_toggle.setToolTip(self._t("tool_library.master_filter.button", "MASTER FILTER"))
        self.master_filter_toggle.setVisible(self._master_filter_enabled)
        self.master_filter_toggle.clicked.connect(self._on_master_filter_toggled)
        if self._master_filter_enabled:
            footer_layout.addWidget(self.master_filter_toggle, 0, Qt.AlignHCenter)

        self.back_to_setup_btn = QToolButton()
        self.back_to_setup_btn.setProperty('topBarIconButton', True)
        self.back_to_setup_btn.setIcon(self._icon_by_name('home_icon.svg', QSize(34, 34)))
        self.back_to_setup_btn.setIconSize(QSize(34, 34))
        self.back_to_setup_btn.setFixedSize(38, 38)
        self.back_to_setup_btn.setAutoRaise(True)
        self.back_to_setup_btn.setCursor(Qt.PointingHandCursor)
        self.back_to_setup_btn.setToolTip(self._t("tool_library.back_to_setup_tip", "Switch back to Setup Manager"))
        self.back_to_setup_btn.clicked.connect(self._back_to_setup_manager)
        footer_layout.addWidget(self.back_to_setup_btn, 0, Qt.AlignHCenter)

        toggle_layout.addWidget(self.footer_actions, 0, Qt.AlignHCenter | Qt.AlignBottom)

        root.addWidget(self.toggle_rail, 0)

        self.stack = QStackedWidget()
        self.home_page = HomePage(
            tool_service,
            export_service,
            settings_service,
            page_title=self._t("tool_library.rail_title.tools", "Tool Library"),
            view_mode='home',
            machine_profile=self.machine_profile,
            translate=self._t,
        )
        self.jaws_page = JawPage(
            jaw_service,
            show_sidebar=False,
            machine_profile=self.machine_profile,
            translate=self._t,
        )
        self.fixtures_page = FixturePage(
            fixture_service,
            show_sidebar=False,
            machine_profile=self.machine_profile,
            translate=self._t,
        )
        self.assemblies_page = HomePage(
            tool_service,
            export_service,
            settings_service,
            page_title=self._t("tool_library.nav.assemblies", "Assemblies"),
            view_mode='assemblies',
            machine_profile=self.machine_profile,
            translate=self._t,
        )
        self.holders_page = HomePage(
            tool_service,
            export_service,
            settings_service,
            page_title=self._t("tool_library.nav.holders", "Holders"),
            view_mode='holders',
            machine_profile=self.machine_profile,
            translate=self._t,
        )
        self.inserts_page = HomePage(
            tool_service,
            export_service,
            settings_service,
            page_title=self._t("tool_library.nav.inserts", "Inserts"),
            view_mode='inserts',
            machine_profile=self.machine_profile,
            translate=self._t,
        )
        self.export_page = ExportPage(
            tool_service,
            export_service,
            on_data_changed=self._refresh_catalog_pages,
            on_database_switched=self._switch_database,
            translate=self._t,
        )
        self.jaws_export_page = JawExportPage(
            jaw_service,
            on_jaw_data_changed=self._refresh_jaws_page,
            on_jaw_database_switched=self._switch_jaw_database,
            translate=self._t,
        )
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.assemblies_page)
        self.stack.addWidget(self.holders_page)
        self.stack.addWidget(self.inserts_page)
        self.stack.addWidget(self.export_page)
        self.stack.addWidget(self.jaws_page)
        self.stack.addWidget(self.jaws_export_page)
        self.stack.addWidget(self.fixtures_page)
        root.addWidget(self.stack, 1)

        _status_bar = QStatusBar()
        _status_bar.setSizeGripEnabled(False)
        self.setStatusBar(_status_bar)

        for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page]:
            page.set_module_switch_handler(self._toggle_module)
            page.bind_external_head_filter(self.tool_head_filter_combo)
        self.jaws_page.set_module_switch_handler(self._toggle_module)
        self.fixtures_page.set_module_switch_handler(self._toggle_module)

        # Apply launch-scoped master filter state only when Tool Library was opened
        # through Setup Manager viewer mode.
        self._apply_master_filter_to_pages()
        self.master_filter_toggle.setChecked(self._master_filter_active)
        self._update_master_filter_toggle_visual()

        self._apply_module_mode('tools')
        current_db_name = Path(getattr(self.tool_service.db, 'path', '')).name
        self.home_page.set_active_database_name(current_db_name)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ensure_on_screen()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            clear_focused_dropdown_on_outside_click(obj, self)
            self._clear_active_page_selection_on_background_click(obj)
        if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.RightButton:
            if isinstance(obj, QWidget) and obj.window() is self:
                self._back_to_setup_manager()
                return True
        return super().eventFilter(obj, event)

    def _clear_active_page_selection_on_background_click(self, obj):
        clear_active_page_selection_on_background_click(self, obj)

    def _refresh_catalog_pages(self):
        for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page]:
            page.current_tool_id = None
            page.refresh_list()
            page.populate_details(None)
        self.jaws_page.current_jaw_id = None
        self.jaws_page.refresh_list()
        self.jaws_page.populate_details(None)
        self.fixtures_page.current_jaw_id = None
        self.fixtures_page.refresh_list()
        self.fixtures_page.populate_details(None)

    def _switch_database(self, database_path: str):
        new_path = Path(database_path)
        if not str(database_path).strip():
            return False, 'Database path is empty.'

        current_path = getattr(self.tool_service.db, 'path', None)
        if current_path is not None and Path(current_path).resolve() == new_path.resolve():
            return True, 'Database already in use.'

        old_db = self.tool_service.db
        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            new_db = Database(new_path)
            new_tool_service = ToolService(new_db)

            self.tool_service = new_tool_service
            for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page]:
                page.tool_service = new_tool_service

            self.export_page.tool_service = new_tool_service
            self.export_page.refresh_database_path_display()
            self.home_page.set_active_database_name(new_path.name)
            self._refresh_catalog_pages()

            old_db.close()
            return True, f'Using database: {new_path}'
        except Exception as exc:
            return False, str(exc)

    def _switch_jaw_database(self, database_path: str):
        new_path = Path(database_path)
        if not str(database_path).strip():
            return False, 'Database path is empty.'
        old_db = self.jaw_service.db
        current_path = getattr(old_db, 'path', None)
        if current_path is not None and Path(current_path).resolve() == new_path.resolve():
            return True, 'Database already in use.'
        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            new_db = JawDatabase(new_path)
            new_jaw_service = JawService(new_db)
            self.jaw_service = new_jaw_service
            self.jaws_page.jaw_service = new_jaw_service
            if hasattr(self.jaws_export_page, 'set_jaw_service'):
                self.jaws_export_page.set_jaw_service(new_jaw_service)
            else:
                self.jaws_export_page.jaw_service = new_jaw_service
            self.jaws_export_page.refresh_database_path_display()
            self._refresh_jaws_page()
            old_db.close()
            return True, f'Using jaws database: {new_path.name}'
        except Exception as exc:
            return False, str(exc)

    def _refresh_jaws_page(self):
        self.jaws_page.current_jaw_id = None
        self.jaws_page.refresh_list()
        self.jaws_page.populate_details(None)

    def _switch_fixtures_database(self, database_path: str):
        new_path = Path(database_path)
        if not str(database_path).strip():
            return False, 'Database path is empty.'
        old_db = self.fixture_service.db
        current_path = getattr(old_db, 'path', None)
        if current_path is not None and Path(current_path).resolve() == new_path.resolve():
            return True, 'Database already in use.'
        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            new_db = FixtureDatabase(new_path)
            new_fixture_service = FixtureService(new_db)
            self.fixture_service = new_fixture_service
            self.fixtures_page.fixture_service = new_fixture_service
            self._refresh_fixtures_page()
            old_db.close()
            return True, f'Using fixtures database: {new_path.name}'
        except Exception as exc:
            return False, str(exc)

    def _refresh_fixtures_page(self):
        self.fixtures_page.current_jaw_id = None
        self.fixtures_page.refresh_list()
        self.fixtures_page.populate_details(None)

    def _open_tool_page(self, page_key: str):
        page_map = {
            'tools': self.home_page,
            'assemblies': self.assemblies_page,
            'holders': self.holders_page,
            'inserts': self.inserts_page,
            'export': self.export_page,
        }
        page = page_map.get(page_key, self.home_page)
        self.stack.setCurrentWidget(page)

    def _open_jaws_view(self, jaw_view_mode: str):
        if jaw_view_mode == 'export':
            self.stack.setCurrentWidget(self.jaws_export_page)
            return
        self.jaws_page.set_view_mode(jaw_view_mode)
        self.stack.setCurrentWidget(self.jaws_page)

    def _open_fixtures_view(self, fixture_view_mode: str):
        self.fixtures_page.set_view_mode(fixture_view_mode)
        self.stack.setCurrentWidget(self.fixtures_page)

    def _open_import_export_view(self, library: str, *, run_import: bool = False, run_export: bool = False) -> None:
        page = self.jaws_export_page if library == 'jaws' else self.export_page
        self.stack.setCurrentWidget(page)
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        try:
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
        except Exception:
            pass
        if run_import:
            QTimer.singleShot(150, page.import_excel)
        elif run_export:
            QTimer.singleShot(150, page.export_excel)

    def _apply_module_mode(self, module: str):
        if module == 'fixtures':
            self._active_module = 'fixtures'
        elif module == 'jaws':
            self._active_module = 'jaws'
        else:
            self._active_module = 'tools'

        if self._active_module == 'jaws':
            for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page, self.jaws_page]:
                page.set_module_switch_target('TOOLS')
            self._open_jaws_view('all')
            self._set_rail_title(self._t("tool_library.rail_title.jaws", "Jaws Library"))
            self._set_head_nav_visible(False)
        elif self._active_module == 'fixtures':
            for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page]:
                page.set_module_switch_target('TOOLS')
            self._open_fixtures_view('all')
            self._set_rail_title(self._t("tool_library.rail_title.fixtures", "Fixture Library"))
            self._set_head_nav_visible(False)
        else:
            sibling_target = 'FIXTURES' if self._is_machining_center() else 'JAWS'
            for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page, self.jaws_page]:
                page.set_module_switch_target(sibling_target)
            self._open_tool_page('tools')
            self._set_rail_title(self._t("tool_library.rail_title.tools", "Tool Library"))
            self._set_head_nav_visible(not self._is_machining_center())

        self._update_module_toggle_label()

    def _on_module_toggle_clicked(self):
        """Toggle button in rail footer — switches between tools and jaws/fixtures."""
        self._toggle_module()

    def _update_module_toggle_label(self):
        """Update the single toggle button label to show the OTHER module (where it will go)."""
        try:
            if self._active_module == 'tools':
                if self._is_machining_center():
                    label = self._t("tool_library.launch.fixtures", "KIINNITTIMET")
                else:
                    label = self._t("tool_library.launch.jaws", "LEUAT")
            else:
                label = self._t("tool_library.launch.tools", "TYÖKALUT")
            self.module_toggle_btn.setText(label)
        except Exception:
            pass

    def _toggle_module(self):
        if self._active_module == 'tools':
            self._apply_module_mode('fixtures' if self._is_machining_center() else 'jaws')
            return
        self._apply_module_mode('tools')

    def _on_head_nav_clicked(self, head_key: str):
        """Handle HEAD1/HEAD2 nav button click — drives the hidden combo for page wiring."""
        self.tool_head_filter_combo.setCurrentData(head_key)
        self._update_head_nav_active(head_key)

    def _update_head_nav_active(self, active_key: str):
        """Set active=True on the matching head nav button, False on others."""
        head_keys = self._profile_head_keys()
        for btn, key in zip(self._head_nav_buttons, head_keys):
            is_active = key == active_key
            btn.setProperty('active', is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _set_head_nav_visible(self, visible: bool):
        """Show or hide the HEAD nav buttons in the rail."""
        for btn in self._head_nav_buttons:
            btn.setVisible(visible)

    def _set_rail_title(self, text: str) -> None:
        """Set rail title and resize the rail to fit."""
        self.rail_title.setText(text)
        lc = get_container_layout_contract()
        self.toggle_rail.setFixedWidth(get_required_rail_width(text, lc))

    def _rebuild_head_filter_combo_items(self):
        head_keys = self._profile_head_keys()
        default_value = head_keys[0]
        allow_combined = len(head_keys) > 1
        current_data = str(self.tool_head_filter_combo.currentData() or default_value).strip().upper()
        valid_values = set(head_keys)
        if allow_combined:
            valid_values.add('HEAD1/2')
        if current_data not in valid_values:
            current_data = 'HEAD1/2' if allow_combined else default_value

        items = []
        if allow_combined:
            items.append((self._t('tool_library.head_filter.all', 'HEAD1/2'), 'HEAD1/2'))
        for head in self.machine_profile.heads:
            label = self._t(head.label_i18n_key, head.label_default)
            items.append((label, head.key))
        if not items:
            items = [(default_value, default_value)]

        self.tool_head_filter_combo.blockSignals(True)
        self.tool_head_filter_combo.set_options(items)
        self.tool_head_filter_combo.setCurrentData(current_data, emit_signal=False)
        self.tool_head_filter_combo.blockSignals(False)

    def _on_global_tool_head_changed(self, _index: int):
        head_keys = self._profile_head_keys()
        default_value = head_keys[0]
        allow_combined = len(head_keys) > 1
        head_value = str(self.tool_head_filter_combo.currentData() or default_value).strip().upper()
        allowed_values = set(head_keys)
        if allow_combined:
            allowed_values.add('HEAD1/2')
        if head_value not in allowed_values:
            head_value = 'HEAD1/2' if allow_combined else default_value
        for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page]:
            page.set_head_filter_value(head_value, refresh=False)
            page.refresh_list()
        # Keep selector HEAD in sync with the nav buttons
        if head_value in head_keys:
            self._update_head_nav_active(head_value)
        if self._selector_mode == 'tools' and head_value in head_keys:
            self._selector_head = head_value
            for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page]:
                if hasattr(page, 'update_selector_head'):
                    page.update_selector_head(head_value)

    def _apply_master_filter_to_pages(self):
        for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page]:
            page.set_master_filter(self._master_filter_tool_ids, self._master_filter_active and self._master_filter_enabled)
        self.jaws_page.set_master_filter(self._master_filter_jaw_ids, self._master_filter_active and self._master_filter_enabled)

    def _update_master_filter_toggle_visual(self):
        if not self._master_filter_enabled:
            return
        if self._master_filter_active:
            self.master_filter_toggle.setIcon(self._icon_by_name('filter_off.svg', QSize(42, 42)))
            self.master_filter_toggle.setToolTip(
                self._t("tool_library.master_filter.on", "MASTER FILTER: ON (Setup Manager scope)")
            )
        else:
            self.master_filter_toggle.setIcon(self._icon_by_name('filter_arrow_right.svg', QSize(42, 42)))
            self.master_filter_toggle.setToolTip(self._t("tool_library.master_filter.off", "MASTER FILTER: OFF"))

    def _on_master_filter_toggled(self, checked: bool):
        if not self._master_filter_enabled:
            return
        self._master_filter_active = bool(checked)
        self._apply_master_filter_to_pages()
        self._update_master_filter_toggle_visual()

    def _reload_shared_preferences(self):
        latest = self.ui_preferences_service.load()
        if not isinstance(latest, dict):
            return
        if latest == self.ui_preferences:
            return
        self.ui_preferences = latest
        self.machine_profile = self._resolve_machine_profile(self.ui_preferences.get('machine_profile_key'))
        for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page, self.jaws_page, self.fixtures_page]:
            page.machine_profile = self.machine_profile
        self.localization.set_language(self.ui_preferences.get("language", "en"))
        self._apply_style()
        self._refresh_localized_labels()

    def _refresh_localized_labels(self):
        self.setWindowTitle(self._t("tool_library.window_title", APP_TITLE))
        if hasattr(self, "back_to_setup_btn"):
            self.back_to_setup_btn.setToolTip(self._t("tool_library.back_to_setup_tip", "Switch back to Setup Manager"))
        if self._active_module == "jaws":
            self._set_rail_title(self._t("tool_library.rail_title.jaws", "Jaws Library"))
        elif self._active_module == "fixtures":
            self._set_rail_title(self._t("tool_library.rail_title.fixtures", "Fixture Library"))
        else:
            self._set_rail_title(self._t("tool_library.rail_title.tools", "Tool Library"))
        if hasattr(self, "master_filter_toggle"):
            self.master_filter_toggle.setToolTip(self._t("tool_library.master_filter.button", "MASTER FILTER"))
            self._update_master_filter_toggle_visual()
        if hasattr(self, "tool_head_filter_combo"):
            self._rebuild_head_filter_combo_items()
            self.tool_head_filter_combo.setToolTip(self._t('tool_library.head_filter.toggle_tip', 'Left click toggles HEAD1 and HEAD2. Right click shows both heads.'))
        if hasattr(self, "home_page"):
            self.home_page.set_page_title(self._t("tool_library.rail_title.tools", "Tool Library"))
            if hasattr(self.home_page, "apply_localization"):
                self.home_page.apply_localization(self._t)
        if hasattr(self, "assemblies_page"):
            self.assemblies_page.set_page_title(self._t("tool_library.nav.assemblies", "Assemblies"))
            if hasattr(self.assemblies_page, "apply_localization"):
                self.assemblies_page.apply_localization(self._t)
        if hasattr(self, "holders_page"):
            self.holders_page.set_page_title(self._t("tool_library.nav.holders", "Holders"))
            if hasattr(self.holders_page, "apply_localization"):
                self.holders_page.apply_localization(self._t)
        if hasattr(self, "inserts_page"):
            self.inserts_page.set_page_title(self._t("tool_library.nav.inserts", "Inserts"))
            if hasattr(self.inserts_page, "apply_localization"):
                self.inserts_page.apply_localization(self._t)
        if hasattr(self, "jaws_page") and hasattr(self.jaws_page, "apply_localization"):
            self.jaws_page.apply_localization(self._t)
        if hasattr(self, "fixtures_page") and hasattr(self.fixtures_page, "apply_localization"):
            self.fixtures_page.apply_localization(self._t)

    def _build_ui_preference_overrides(self) -> str:
        _ = get_active_theme_palette(self.ui_preferences)
        return ""

    def _set_graphics_effects_enabled(self, enabled: bool):
        if enabled:
            for effect in self._disabled_graphics_effects:
                try:
                    effect.setEnabled(True)
                except Exception:
                    pass
            self._disabled_graphics_effects = []
            return

        if self._disabled_graphics_effects:
            return

        disabled_effects = []
        for widget in self.findChildren(QWidget):
            effect = widget.graphicsEffect()
            if effect is None or not effect.isEnabled():
                continue
            try:
                effect.setEnabled(False)
                disabled_effects.append(effect)
            except Exception:
                pass
        self._disabled_graphics_effects = disabled_effects

    def _fade_out_and(self, callback):
        _shared_fade_out_and(self, callback, pre_callback=lambda: self._set_graphics_effects_enabled(True))

    def fade_in(self):
        _shared_fade_in(self, post_restore=lambda: self._set_graphics_effects_enabled(True))

    def _current_window_rect(self) -> tuple[int, int, int, int]:
        return current_window_rect(self)

    def _back_to_setup_manager(self):
        """Switch back to Setup Manager."""
        # Selector mode is session-scoped. Clear it before handoff so the
        # hidden Tool Library instance always reopens in normal library mode
        # unless a fresh selector payload explicitly enables selector mode.
        # Also close any standalone selector dialogs; leaving them open can
        # make subsequent non-selector IPC requests be ignored as if selector
        # mode were still active.
        library_was_visible = bool(getattr(self, "_selector_session_library_was_visible", False))
        logger.debug(
            "selector: _back_to_setup_manager library_was_visible=%r mode=%r request_id=%r",
            library_was_visible,
            getattr(self, "_selector_mode", ""),
            getattr(self, "_selector_request_id", ""),
        )
        self._selector_session_library_was_visible = False
        _close_selector_detached_preview(self)
        _close_library_detached_previews(self)
        self._close_selector_dialogs()
        self._set_selector_session_state(empty_selector_session_state())
        if library_was_visible:
            # Library was already open before the selector session — stay visible.
            logger.debug("selector: return path keeps library visible (skip handoff)")
            if self.windowFlags() & Qt.WindowStaysOnTopHint:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
            self.show()
            self.raise_()
            self.activateWindow()
            return
        logger.debug("selector: return path performs handoff_to_setup_manager (hide sender)")
        handoff_to_setup_manager(
            self,
            setup_manager_server_name=SETUP_MANAGER_SERVER_NAME,
            source_dir=SOURCE_DIR,
            callback_server_name=TOOL_LIBRARY_SERVER_NAME,
        )

    def _clear_selector_session(self, show: bool = True):
        _close_selector_detached_preview(self)
        self._close_selector_dialogs()
        self._set_selector_session_state(empty_selector_session_state())
        # Only remove stay-on-top when it is actually set — unconditionally
        # calling setWindowFlag on Windows can briefly recreate the native
        # window handle and cause a visible flash.
        if self.windowFlags() & Qt.WindowStaysOnTopHint:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        if show:
            self.show()

    def _set_selector_session_state(self, state: dict) -> None:
        self._selector_mode = str(state.get('mode') or '').strip().lower()
        self._selector_callback_server = str(state.get('callback_server') or '').strip()
        self._selector_request_id = str(state.get('request_id') or '').strip()
        self._selector_head = str(state.get('head') or '').strip()
        self._selector_spindle = str(state.get('spindle') or '').strip()
        self._selector_target_key = str(state.get('target_key') or '').strip()
        self._selector_initial_assignments = [dict(item) for item in (state.get('assignments') or []) if isinstance(item, dict)]
        raw_buckets = state.get('assignment_buckets') or {}
        if isinstance(raw_buckets, dict):
            self._selector_initial_assignment_buckets = {
                str(key): [dict(item) for item in value if isinstance(item, dict)]
                for key, value in raw_buckets.items()
                if isinstance(value, list)
            }
        else:
            self._selector_initial_assignment_buckets = {}
        self._selector_print_pots = bool(state.get('print_pots', False))
        self._selector_session_geometry = str(state.get('geometry') or '').strip()

    def _close_selector_dialogs(self) -> None:
        self._closing_selector_dialogs = True
        warm_cache = {
            id(self._tool_selector_dialog_warmcache),
            id(self._jaw_selector_dialog_warmcache),
            id(self._fixture_selector_dialog_warmcache),
        } - {id(None)}
        dialogs = [self._tool_selector_dialog, self._jaw_selector_dialog, self._fixture_selector_dialog]
        self._tool_selector_dialog = None
        self._jaw_selector_dialog = None
        self._fixture_selector_dialog = None
        for dialog in dialogs:
            if dialog is None:
                continue
            try:
                dialog.blockSignals(True)
                if id(dialog) in warm_cache:
                    # Warm-cached dialogs are reused across sessions — just hide
                    # them rather than destroying them so the pre-built widget tree
                    # and catalog data remain available for the next IPC request.
                    dialog.hide()
                    # Re-enable signals so the dialog is fully live for the next
                    # session (blockSignals is called above for all dialogs).
                    dialog.blockSignals(False)
                else:
                    dialog.close()
                    # Dialogs are created with parent=None so they must be
                    # explicitly scheduled for deletion.
                    dialog.deleteLater()
            except Exception:
                pass
        self._closing_selector_dialogs = False

    def _pre_warm_selector_dialogs(self) -> None:
        """Build selector dialogs once, hidden off-screen, so construction and
        catalog load are paid before the first IPC selector request arrives."""
        _lib_geo = self.geometry()
        _w = max(_lib_geo.width(), 1500)
        _h = max(_lib_geo.height(), 860)

        def _build(factory, attr):
            if getattr(self, attr) is not None:
                return
            try:
                dlg = factory()
                if hasattr(dlg, 'setAttribute'):
                    dlg.setAttribute(Qt.WA_DeleteOnClose, False)
                dlg.setGeometry(_lib_geo.x(), _lib_geo.y(), _w, _h)
                setattr(self, attr, dlg)
                logger.debug('selector: %s warm-cache ready', attr)
            except Exception:
                logger.warning('selector: pre-warm failed for %s', attr, exc_info=True)
                setattr(self, attr, None)

        _build(
            lambda: ToolSelectorDialog(
                tool_service=self.tool_service,
                machine_profile=self.machine_profile,
                translate=self._t,
                selector_head='H1',
                selector_spindle='main',
                initial_assignments=None,
                initial_assignment_buckets=None,
                initial_print_pots=False,
                on_submit=lambda _: None,
                on_cancel=lambda: None,
                parent=None,
            ),
            '_tool_selector_dialog_warmcache',
        )
        _build(
            lambda: JawSelectorDialog(
                jaw_service=self.jaw_service,
                machine_profile=self.machine_profile,
                translate=self._t,
                selector_spindle='main',
                initial_assignments=None,
                on_submit=lambda _: None,
                on_cancel=lambda: None,
                parent=None,
            ),
            '_jaw_selector_dialog_warmcache',
        )
        _build(
            lambda: FixtureSelectorDialog(
                fixture_service=self.fixture_service,
                translate=self._t,
                initial_assignments=None,
                initial_assignment_buckets=None,
                initial_target_key='',
                on_submit=lambda _: None,
                on_cancel=lambda: None,
                parent=None,
            ),
            '_fixture_selector_dialog_warmcache',
        )

    def _open_selector_dialog_for_session(self, should_show: bool) -> None:
        logger.debug("selector: opening %r dialog — head=%r spindle=%r show=%r", self._selector_mode, self._selector_head, self._selector_spindle, should_show)
        self._close_selector_dialogs()

        # _reset_kwargs is set for warm-cached dialogs.  The actual
        # reset_for_session() call is deferred to INSIDE the setUpdatesEnabled(False)
        # priming block below so widget-state changes (clear/rebuild assignment list,
        # context header update) are never visible to the compositor.
        _reset_kwargs: dict | None = None

        if self._selector_mode == 'tools':
            cached = self._tool_selector_dialog_warmcache
            if cached is not None:
                # Reuse pre-built dialog.  Capture reset kwargs; will be applied
                # inside the frozen priming block so no intermediate paint occurs.
                _reset_kwargs = dict(
                    selector_head=self._selector_head,
                    selector_spindle=self._selector_spindle,
                    initial_assignments=self._selector_initial_assignments,
                    initial_assignment_buckets=self._selector_initial_assignment_buckets,
                    initial_print_pots=bool(getattr(self, '_selector_print_pots', False)),
                    on_submit=self._on_selector_dialog_submit,
                    on_cancel=self._on_selector_dialog_cancel,
                )
                dialog = cached
            else:
                dialog = ToolSelectorDialog(
                    tool_service=self.tool_service,
                    machine_profile=self.machine_profile,
                    translate=self._t,
                    selector_head=self._selector_head,
                    selector_spindle=self._selector_spindle,
                    initial_assignments=self._selector_initial_assignments,
                    initial_assignment_buckets=self._selector_initial_assignment_buckets,
                    initial_print_pots=bool(getattr(self, '_selector_print_pots', False)),
                    on_submit=self._on_selector_dialog_submit,
                    on_cancel=self._on_selector_dialog_cancel,
                    # parent=None so hiding the main window does NOT cascade to
                    # the dialog (Windows HWND parent-child visibility propagation).
                    parent=None,
                )
                # Disable auto-delete so the dialog survives hide() and can be
                # reused across sessions. WA_DeleteOnClose is set by the dialog
                # constructor — we must clear it before caching.
                if hasattr(dialog, 'setAttribute'):
                    dialog.setAttribute(Qt.WA_DeleteOnClose, False)
                self._tool_selector_dialog_warmcache = dialog
            self._tool_selector_dialog = dialog
        elif self._selector_mode == 'jaws':
            cached = self._jaw_selector_dialog_warmcache
            if cached is not None:
                _reset_kwargs = dict(
                    selector_spindle=self._selector_spindle,
                    initial_assignments=self._selector_initial_assignments,
                    on_submit=self._on_selector_dialog_submit,
                    on_cancel=self._on_selector_dialog_cancel,
                )
                dialog = cached
            else:
                dialog = JawSelectorDialog(
                    jaw_service=self.jaw_service,
                    machine_profile=self.machine_profile,
                    translate=self._t,
                    selector_spindle=self._selector_spindle,
                    initial_assignments=self._selector_initial_assignments,
                    on_submit=self._on_selector_dialog_submit,
                    on_cancel=self._on_selector_dialog_cancel,
                    parent=None,
                )
                if hasattr(dialog, 'setAttribute'):
                    dialog.setAttribute(Qt.WA_DeleteOnClose, False)
                self._jaw_selector_dialog_warmcache = dialog
            self._jaw_selector_dialog = dialog
        elif self._selector_mode == 'fixtures':
            cached = self._fixture_selector_dialog_warmcache
            if cached is not None:
                _reset_kwargs = dict(
                    initial_assignments=self._selector_initial_assignments,
                    initial_assignment_buckets=self._selector_initial_assignment_buckets,
                    initial_target_key=getattr(self, '_selector_target_key', ''),
                    on_submit=self._on_selector_dialog_submit,
                    on_cancel=self._on_selector_dialog_cancel,
                )
                dialog = cached
            else:
                dialog = FixtureSelectorDialog(
                    fixture_service=self.fixture_service,
                    translate=self._t,
                    initial_assignments=self._selector_initial_assignments,
                    initial_assignment_buckets=self._selector_initial_assignment_buckets,
                    initial_target_key=getattr(self, '_selector_target_key', ''),
                    on_submit=self._on_selector_dialog_submit,
                    on_cancel=self._on_selector_dialog_cancel,
                    parent=None,
                )
                if hasattr(dialog, 'setAttribute'):
                    dialog.setAttribute(Qt.WA_DeleteOnClose, False)
                self._fixture_selector_dialog_warmcache = dialog
            self._fixture_selector_dialog = dialog
        else:
            return
        # Position selector dialog: use geometry sent by Work Editor if available,
        # otherwise fall back to Library's own window bounds.
        #
        # Mirror prime_work_editor_dialog exactly:
        #   1. processEvents — drain events BEFORE the frozen-update priming block
        #   2. setUpdatesEnabled(False) block: flags (no-op safety check), palette,
        #      style, geometry, ensurePolished, layout.activate, updateGeometry
        #   3. processEvents — drain events AFTER the block
        # The double drain ensures the compositor never sees a reflow-in-progress frame.
        if should_show:
            dialog.setUpdatesEnabled(False)
        try:
            # For warm-cached dialogs, reset session state INSIDE the frozen block
            # so widget-state changes (assignment list rebuild, context header update)
            # are invisible to the compositor — same as first-open where the
            # constructor runs _run_startup_initialization inside a frozen block.
            if _reset_kwargs is not None:
                try:
                    reset_fn = getattr(dialog, 'reset_for_session', None) or getattr(dialog, 'prepare_for_session', None)
                    if reset_fn is not None:
                        reset_fn(**_reset_kwargs)
                    else:
                        logger.warning('selector: no reset method on %s', type(dialog).__name__)
                except Exception:
                    logger.warning('selector: session reset failed', exc_info=True)

            if should_show:
                # Qt.Tool | Qt.WindowStaysOnTopHint are already set at construction
                # time, so the bitwise-OR is a no-op in the normal path (no HWND
                # recreation).  The explicit inequality check guarantees we never
                # call setWindowFlags when nothing changes.
                dialog.setAttribute(Qt.WA_StyledBackground, True)
                dialog.setAutoFillBackground(True)
                from PySide6.QtGui import QPalette
                _bg = current_theme_color('page_bg', '#eceff2')
                _pal = dialog.palette()
                _pal.setColor(QPalette.Window, _bg)
                _pal.setColor(QPalette.Base, _bg)
                dialog.setPalette(_pal)
                if hasattr(self, '_compiled_stylesheet') and self._compiled_stylesheet:
                    dialog.setStyleSheet(self._compiled_stylesheet)

            session_geometry = getattr(self, '_selector_session_geometry', '')
            if session_geometry:
                try:
                    parts = [int(v) for v in session_geometry.split(',')]
                    if len(parts) == 4:
                        dialog.setGeometry(*parts)
                except Exception:
                    session_geometry = ''
            if not session_geometry:
                try:
                    top_left = self.mapToGlobal(QPoint(0, 0))
                    dialog.move(top_left)
                    dialog.resize(max(self.width(), 1500), max(self.height(), 860))
                except Exception:
                    try:
                        geom = self.geometry()
                        dialog.setGeometry(geom.x(), geom.y(), max(geom.width(), 1500), max(geom.height(), 860))
                    except Exception:
                        try:
                            dialog.resize(max(self.width(), 1500), max(self.height(), 860))
                        except Exception:
                            pass

            if should_show:
                try:
                    dialog.ensurePolished()
                except Exception:
                    pass
                try:
                    layout = dialog.layout()
                    if layout is not None:
                        layout.activate()
                except Exception:
                    pass
                try:
                    dialog.updateGeometry()
                except Exception:
                    pass
        finally:
            if should_show:
                dialog.setUpdatesEnabled(True)

        # Detached 3D preview dialog is created lazily when the user clicks
        # the preview button (via ensure_detached_preview_dialog in
        # sync_detached_preview).  Pre-creating it here in a hidden state
        # causes the QWebEngineView to initialize with a 0×0 viewport,
        # which corrupts the Three.js camera/renderer on first use.

        if should_show:
            dialog.setWindowOpacity(1.0)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

    def _on_selector_dialog_cancel(self) -> None:
        if self._closing_selector_dialogs:
            return
        if self._selector_mode not in {'tools', 'jaws', 'fixtures'}:
            return
        self._clear_selector_session(show=False)
        self._back_to_setup_manager()

    def _on_selector_dialog_submit(self, result: dict) -> None:
        kind = str(result.get('kind') or '').strip().lower()
        selected_items = result.get('selected_items') or []
        selector_head = str(result.get('selector_head') or self._selector_head or '').strip().upper()
        selector_spindle = str(result.get('selector_spindle') or self._selector_spindle or '').strip().lower()
        assignment_buckets_by_target = result.get('assignment_buckets_by_target') or {}
        target_key = str(result.get('target_key') or '').strip()
        print_pots = bool(result.get('print_pots', getattr(self, '_selector_print_pots', False)))
        self._send_selector_result_payload(
            kind=kind,
            selected_items=selected_items,
            selector_head=selector_head,
            selector_spindle=selector_spindle,
            assignment_buckets_by_target=assignment_buckets_by_target,
            target_key=target_key,
            print_pots=print_pots,
        )

    def _send_selector_result_payload(
        self,
        *,
        kind: str,
        selected_items: list[dict],
        selector_head: str = '',
        selector_spindle: str = '',
        assignment_buckets_by_target: dict | None = None,
        target_key: str = '',
        print_pots: bool = False,
    ) -> None:
        sent = send_selector_result_payload(
            self,
            kind=kind,
            selected_items=selected_items,
            selector_head=selector_head,
            selector_spindle=selector_spindle,
            assignment_buckets_by_target=assignment_buckets_by_target,
            target_key=target_key,
            print_pots=print_pots,
        )
        if sent:
            self._back_to_setup_manager()

    def navigate_to(self, kind: str, item_id: str = ""):
        """Deep-link: switch to jaw or tools module and select the given item."""
        if kind == "jaw":
            self._apply_module_mode("jaws")
            if item_id:
                self.jaws_page.select_jaw_by_id(item_id)
        else:
            self._apply_module_mode("tools")
            if item_id:
                self.home_page.select_tool_by_id(item_id)

    def apply_external_request(self, payload: dict, reload_preferences: bool = True, *, caller_was_visible: bool | None = None):
        selector_state = selector_session_from_payload(payload)
        selector_mode = str(selector_state.get('mode') or '')
        should_show = bool(payload.get('show', True))
        selector_active = bool(selector_state.get('active'))
        selector_dialog_open = bool(
            (self._tool_selector_dialog is not None and self._tool_selector_dialog.isVisible())
            or (self._jaw_selector_dialog is not None and self._jaw_selector_dialog.isVisible())
            or (self._fixture_selector_dialog is not None and self._fixture_selector_dialog.isVisible())
        )

        # During an active selector dialog, ignore generic non-selector IPC
        # requests so they cannot surface the main library window behind it.
        if selector_dialog_open and not selector_active:
            return

        # Handle import/export IPC commands from Setup Manager Preferences.
        command = str((payload or {}).get('command') or '').strip().lower()
        if command in ('open_import_dialog', 'open_export_dialog'):
            library = str((payload or {}).get('library') or 'tools').strip().lower()
            self._open_import_export_view(
                library,
                run_import=(command == 'open_import_dialog'),
                run_export=(command == 'open_export_dialog'),
            )
            return

        # Selector sessions can arrive before shared preferences are refreshed.
        # Prefer explicit machine profile key from payload when provided.
        incoming_profile_key = str(payload.get('machine_profile_key') or '').strip().lower()
        if incoming_profile_key:
            resolved_profile = self._resolve_machine_profile(incoming_profile_key)
            if resolved_profile != self.machine_profile:
                self.machine_profile = resolved_profile
                for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page, self.jaws_page, self.fixtures_page]:
                    page.machine_profile = self.machine_profile
                self._rebuild_head_filter_combo_items()

        # Switch tool/jaw databases if the active machine config has config-specific paths.
        new_tools_db = str(payload.get('tools_db_path') or '').strip()
        if new_tools_db:
            self._switch_database(new_tools_db)
        new_jaws_db = str(payload.get('jaws_db_path') or '').strip()
        if new_jaws_db:
            self._switch_jaw_database(new_jaws_db)
        new_fixtures_db = str(payload.get('fixtures_db_path') or '').strip()
        if new_fixtures_db:
            self._switch_fixtures_database(new_fixtures_db)

        if selector_active:
            self._set_selector_session_state(selector_state)
            # Track whether Library was already visible before this selector
            # session. If so, _back_to_setup_manager should not hide it.
            # caller_was_visible is set by main.py before apply_external_request
            # is called, capturing the true pre-handoff visibility state.
            if caller_was_visible is not None:
                self._selector_session_library_was_visible = caller_was_visible
            else:
                self._selector_session_library_was_visible = bool(
                    self.isVisible() and not self.isMinimized()
                )
            logger.debug(
                "selector: apply_external_request active mode=%r caller_was_visible=%r stored_visible=%r should_show=%r",
                self._selector_mode,
                caller_was_visible,
                self._selector_session_library_was_visible,
                should_show,
            )
            # Open selector on top of the Library window.  The selector has
            # WindowStaysOnTopHint and is sized to cover the Library exactly,
            # so the Library stays visible underneath without any gap or flash.
            # No hide() call — hiding causes a DWM compositing gap between
            # the Library disappearing and the selector being presented.
            self._open_selector_dialog_for_session(should_show=should_show)
            return

        # Preference reload is deferred to after show/fade_in when called from the
        # IPC handoff path so it never blocks the transition animation.
        if reload_preferences:
            self._reload_shared_preferences()

        # Clear master filter when switching back normally (no filter context).
        if payload.get('clear_master_filter'):
            self._master_filter_enabled = False
            self._master_filter_active = False
            self._master_filter_tool_ids = set()
            self._master_filter_jaw_ids = set()
            self.master_filter_toggle.setVisible(False)
            self.master_filter_toggle.setChecked(False)
            self._apply_master_filter_to_pages()
        else:
            tool_ids = [str(v).strip() for v in (payload.get('master_filter_tools') or []) if str(v).strip()]
            jaw_ids = [str(v).strip() for v in (payload.get('master_filter_jaws') or []) if str(v).strip()]
            if tool_ids or jaw_ids:
                self._master_filter_enabled = True
                self._master_filter_tool_ids = set(tool_ids)
                self._master_filter_jaw_ids = set(jaw_ids)
                self._master_filter_active = bool(payload.get('master_filter_active', False))
                self.master_filter_toggle.setVisible(True)
                self.master_filter_toggle.setChecked(self._master_filter_active)
                self._apply_master_filter_to_pages()
                self._update_master_filter_toggle_visual()

        self._clear_selector_session(show=False)

        # Switch module only when NOT in selector mode.
        module = selector_mode if selector_mode in ('tools', 'jaws', 'fixtures') else str(payload.get('module', '')).strip()
        if module in ('tools', 'jaws', 'fixtures'):
            self._apply_module_mode(module)

        kind = str(payload.get('kind', '')).strip()
        item_id = str(payload.get('item_id', '')).strip()
        if kind:
            self.navigate_to(kind, item_id)

    def _apply_style(self):
        palette = install_application_theme_state(self.ui_preferences)
        apply_tool_delegate_theme(palette)
        apply_jaw_delegate_theme(palette)
        self._compiled_stylesheet = compile_app_stylesheet(APP_DIR / 'styles' / 'library_style.qss', self.ui_preferences)
        # Apply on QApplication so ALL windows (including selector dialogs) inherit it.
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(self._compiled_stylesheet)
        self.setStyleSheet(self._compiled_stylesheet)
        # Delegate-painted list views don't get repainted by setStyleSheet alone —
        # force a viewport repaint so the new CLR_CARD_SELECTED_BORDER takes effect.
        for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page, self.jaws_page, self.fixtures_page]:
            if hasattr(page, 'list_view') and page.list_view is not None:
                page.list_view.viewport().update()
