import json
import sys
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QSize,
    Signal,
    Qt,
    QTimer,
    QProcess,
)
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon, QImage, QPixmap, QTransform
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)
from config import (
    APP_TITLE,
    STYLE_PATH,
    APP_DIR,
    SOURCE_DIR,
    SHARED_UI_PREFERENCES_PATH,
    I18N_DIR,
    RAIL_HEAD_DROPDOWN_WIDTH,
    TOOL_ICONS_DIR,
    NAV_ITEM_TO_ICON,
    NAV_ICON_DEFAULT_SIZE,
    NAV_ICON_RENDER_OVERRIDES,
    SETUP_MANAGER_SERVER_NAME,
)
from data.database import Database
from data.jaw_database import JawDatabase
from services.jaw_service import JawService
from services.localization_service import LocalizationService
from services.tool_service import ToolService
from services.ui_preferences_service import UiPreferencesService
from shared.editor_helpers import style_panel_action_button
from ui.export_page import ExportPage
from ui.home_page import HomePage
from ui.jaw_export_page import JawExportPage
from ui.jaw_page import JawPage
from ui.widgets.common import clear_focused_dropdown_on_outside_click


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


class MainWindow(QMainWindow):
    def __init__(self, tool_service, jaw_service, export_service, settings_service, launch_master_filter=None):
        super().__init__()
        self.tool_service = tool_service
        self.jaw_service = jaw_service
        self.export_service = export_service
        self.settings_service = settings_service
        self.ui_preferences_service = UiPreferencesService(SHARED_UI_PREFERENCES_PATH)
        self.ui_preferences = self.ui_preferences_service.load()
        self.localization = LocalizationService(I18N_DIR)
        self.localization.set_language(self.ui_preferences.get("language", "en"))
        if hasattr(self.export_service, "set_translator"):
            self.export_service.set_translator(self._t)
        self._clamping_screen_bounds = False
        self._nav_width = 48
        self._nav_revealed = False
        self._nav_anim_group = None
        self._nav_button_effects = []
        self._disabled_graphics_effects = []
        self._nav_hide_timer = QTimer(self)
        self._nav_hide_timer.setSingleShot(True)
        self._nav_hide_timer.setInterval(160)
        self._nav_hide_timer.timeout.connect(self._hide_nav_if_needed)
        self._active_module = 'tools'
        self._active_nav_items = []
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
        self.setWindowTitle(self._t("tool_library.window_title", APP_TITLE))
        self.resize(1280, 780)
        self._build_ui(self.tool_service, self.jaw_service, self.export_service, self.settings_service)
        self._apply_style()
        QApplication.instance().installEventFilter(self)

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self.localization.t(key, default, **kwargs)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ensure_on_screen()
        self._position_rail_title()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._ensure_on_screen()

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_on_screen()
        self._position_rail_title()

    def _position_rail_title(self):
        """Place the header label at the top-left of the central widget."""
        if not hasattr(self, 'rail_title'):
            return
        self.rail_title.move(10, 13)
        # Let it be as wide as its text needs — it's outside the layout.
        self.rail_title.setFixedWidth(self.rail_title.fontMetrics().horizontalAdvance(self.rail_title.text()) + 16)
        self.rail_title.raise_()

    def _ensure_on_screen(self):
        if self._clamping_screen_bounds:
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
        # Render raster icons through cleanup/scaling; let Qt render SVG directly.
        if path.suffix.lower() == '.svg':
            return QIcon(str(path))
        return QIcon(self._clean_icon_pixmap(str(path), target_size))

    def _mirrored_icon_by_name(self, icon_name: str, target_size: QSize | None = None, rotation: int = 0) -> QIcon:
        path = self._resolve_icon_path(icon_name)
        if path is None:
            return QIcon()
        if target_size is None:
            target_size = QSize(34, 34)
        pm = self._pixmap_by_path(path, target_size)
        if pm.isNull():
            return QIcon()
        transform = QTransform().scale(-1, 1)
        if rotation:
            transform = transform.rotate(rotation)
        return QIcon(pm.transformed(transform, Qt.SmoothTransformation))

    def _nav_icon_render_options(self, icon_name: str) -> tuple[QSize, int]:
        size = QSize(*NAV_ICON_DEFAULT_SIZE)
        rotation = 0

        override = NAV_ICON_RENDER_OVERRIDES.get(icon_name)
        if override:
            size_override = override.get('size')
            if size_override:
                size = QSize(*size_override)
            rotation = int(override.get('rotation', 0))

        return size, rotation

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
            return QIcon(str(path)).pixmap(target_size)
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

    def _nav_icon_for_state(
        self,
        icon_name: str,
        target_size: QSize,
        mirrored: bool,
        rotation: int,
        selected: bool,
    ) -> QIcon:
        path = self._resolve_icon_path(icon_name)
        if path is None:
            return QIcon()

        pm = self._pixmap_by_path(path, target_size)
        if pm.isNull():
            return QIcon()

        transform = QTransform()
        if mirrored:
            transform = transform.scale(-1, 1)
        if rotation:
            transform = transform.rotate(rotation)
        if not transform.isIdentity():
            pm = pm.transformed(transform, Qt.SmoothTransformation)

        return QIcon(pm)

    def _refresh_nav_button_icons(self):
        for idx, btn in enumerate(self.nav_buttons):
            if idx >= len(self._active_nav_items):
                continue
            _title, icon_name, mirror, _callback = self._active_nav_items[idx]
            icon_size, rotation = self._nav_icon_render_options(icon_name)
            selected = btn.isChecked()
            btn.setIcon(self._nav_icon_for_state(icon_name, icon_size, mirror, rotation, selected))
            btn.setIconSize(icon_size)

    def _build_ui(self, tool_service, jaw_service, export_service, settings_service):
        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)

        # ── Header: absolutely positioned, NOT in any layout ─────────────────
        # This is the only way to guarantee the title width has zero effect on
        # the rail width.  It's a direct child of central, raised above the
        # layout, and repositioned via _position_rail_title().
        self._header_height = 38
        self.rail_title = QLabel(self._t("tool_library.rail_title.tools", "Tool Library"), central)
        self.rail_title.setStyleSheet('color: #000000; font-size: 14pt; font-weight: 700;')
        self.rail_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.rail_title.setFixedHeight(self._header_height)
        self.rail_title.adjustSize()
        self.rail_title.raise_()

        # ── Main layout: rail + stack, with a compact shared top gutter ──────
        root = QHBoxLayout(central)
        root.setContentsMargins(4, 10, 12, 12)
        root.setSpacing(0)

        self.toggle_rail = QWidget()
        self.toggle_rail.setFixedWidth(110)
        self.toggle_rail.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        toggle_layout = QVBoxLayout(self.toggle_rail)
        toggle_layout.setContentsMargins(6, 60, 6, 10)
        toggle_layout.setSpacing(0)

        self.nav_frame = QFrame()
        self.nav_frame.setObjectName('navFrame')
        self.nav_frame.setFixedWidth(self._nav_width)
        nav_layout = QVBoxLayout(self.nav_frame)
        nav_layout.setContentsMargins(0, 10, 0, 8)
        nav_layout.setSpacing(10)
        self.nav_buttons = []
        self.nav_button_group = QButtonGroup(self)
        self.nav_button_group.setExclusive(True)
        self._nav_button_count = 5
        for index in range(self._nav_button_count):
            btn = QToolButton()
            btn.setObjectName('sideNavButton')
            btn.setIconSize(QSize(30, 30))
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setFixedSize(42, 46)
            btn.clicked.connect(lambda checked=False, idx=index: self._on_nav_button_clicked(idx))
            self.nav_button_group.addButton(btn, index)
            self.nav_buttons.append(btn)
            nav_layout.addWidget(btn, 0, Qt.AlignHCenter | Qt.AlignTop)
        nav_layout.addStretch(1)
        nav_h = (len(self.nav_buttons) * 50) + ((len(self.nav_buttons) - 1) * nav_layout.spacing()) + 18
        self.nav_frame.setFixedHeight(nav_h)

        # Host the animated nav frame in a fixed slot so layout won't fight the slide animation.
        self.nav_slot = QWidget()
        self.nav_slot.setFixedSize(self._nav_width, nav_h)
        self.nav_frame.setParent(self.nav_slot)
        self.nav_frame.move(0, 0)

        self.tool_head_filter_combo = RailHeadToggleButton()
        self.tool_head_filter_combo.setObjectName('toolHeadRailFilter')
        self.tool_head_filter_combo.setFixedWidth(RAIL_HEAD_DROPDOWN_WIDTH)
        self.tool_head_filter_combo.setCursor(Qt.PointingHandCursor)
        combo_policy = self.tool_head_filter_combo.sizePolicy()
        combo_policy.setRetainSizeWhenHidden(True)
        self.tool_head_filter_combo.setSizePolicy(combo_policy)
        self.tool_head_filter_combo.setToolTip(self._t('tool_library.head_filter.toggle_tip', 'Left click toggles HEAD1 and HEAD2. Right click shows both heads.'))
        style_panel_action_button(self.tool_head_filter_combo)
        self._rebuild_head_filter_combo_items()
        self.tool_head_filter_combo.currentIndexChanged.connect(self._on_global_tool_head_changed)
        toggle_layout.addSpacing(10)
        toggle_layout.addWidget(self.tool_head_filter_combo, 0, Qt.AlignHCenter)
        toggle_layout.addSpacing(10)
        toggle_layout.addWidget(self.nav_slot, 0, Qt.AlignHCenter)

        toggle_layout.addStretch(1)

        # Keep footer actions grouped so their placement matches Setup Manager's left-rail launcher area.
        self.footer_actions = QFrame()
        self.footer_actions.setObjectName('railFooterActions')
        self.footer_actions.setProperty('launchCard', True)
        footer_layout = QVBoxLayout(self.footer_actions)
        footer_layout.setContentsMargins(16, 0, 16, 20)
        footer_layout.setSpacing(6)

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
        footer_layout.addWidget(self.master_filter_toggle, 0, Qt.AlignHCenter)

        self.selector_send_btn = QPushButton(self._t('tool_library.selector.done', 'DONE'))
        self.selector_send_btn.setProperty('selectorPrimaryActionButton', True)
        self.selector_send_btn.setVisible(False)
        self.selector_send_btn.clicked.connect(self._send_selector_selection)

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

        toggle_layout.addWidget(self.footer_actions, 0)

        root.addWidget(self.toggle_rail, 0)

        self.stack = QStackedWidget()
        self.home_page = HomePage(
            tool_service,
            export_service,
            settings_service,
            page_title=self._t("tool_library.rail_title.tools", "Tool Library"),
            view_mode='home',
            translate=self._t,
        )
        self.jaws_page = JawPage(jaw_service, show_sidebar=False, translate=self._t)
        self.assemblies_page = HomePage(
            tool_service,
            export_service,
            settings_service,
            page_title=self._t("tool_library.nav.assemblies", "Assemblies"),
            view_mode='assemblies',
            translate=self._t,
        )
        self.holders_page = HomePage(
            tool_service,
            export_service,
            settings_service,
            page_title=self._t("tool_library.nav.holders", "Holders"),
            view_mode='holders',
            translate=self._t,
        )
        self.inserts_page = HomePage(
            tool_service,
            export_service,
            settings_service,
            page_title=self._t("tool_library.nav.inserts", "Inserts"),
            view_mode='inserts',
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
        root.addWidget(self.stack, 1)

        for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page]:
            page.set_module_switch_handler(self._toggle_module)
            page.bind_external_head_filter(self.tool_head_filter_combo)
        self.jaws_page.set_module_switch_handler(self._toggle_module)

        # Apply launch-scoped master filter state only when Tool Library was opened
        # through Setup Manager viewer mode.
        self._apply_master_filter_to_pages()
        self.master_filter_toggle.setChecked(self._master_filter_active)
        self._update_master_filter_toggle_visual()

        # Nav stays always visible; hover logic remains for compatibility.
        self._setup_nav_hover_animation()
        self._apply_module_mode('tools')
        current_db_name = Path(getattr(self.tool_service.db, 'path', '')).name
        self.home_page.set_active_database_name(current_db_name)

    def _setup_nav_hover_animation(self):
        self._nav_button_effects.clear()
        self._nav_hover_widgets = []
        self._nav_revealed = True
        self.nav_frame.move(0, 0)
        self._set_nav_button_opacity(1.0)

    def _set_nav_button_opacity(self, opacity: float):
        _ = opacity

    def _animate_nav(self, show: bool):
        self._nav_revealed = show
        self.nav_frame.move(0, 0)
        self._set_nav_button_opacity(1.0)

    def _show_nav(self):
        self._nav_hide_timer.stop()
        self._nav_revealed = True
        self.nav_frame.move(0, 0)
        self._set_nav_button_opacity(1.0)

    def _hide_nav_if_needed(self):
        self._nav_revealed = True
        self.nav_frame.move(0, 0)
        self._set_nav_button_opacity(1.0)

    def _cursor_inside_nav_zone(self) -> bool:
        if not self.toggle_rail.isVisible():
            return False
        local_pos = self.toggle_rail.mapFromGlobal(QCursor.pos())
        return self.toggle_rail.rect().adjusted(-2, -2, 2, 2).contains(local_pos)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            clear_focused_dropdown_on_outside_click(obj, self)
            self._clear_active_page_selection_on_background_click(obj)
        if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.RightButton:
            if isinstance(obj, QWidget) and obj.window() is self:
                self._back_to_setup_manager()
                return True
        if hasattr(self, '_nav_hover_widgets') and obj in self._nav_hover_widgets:
            if event.type() == QEvent.Enter:
                self._show_nav()
            elif event.type() == QEvent.Leave:
                self._nav_hide_timer.start()
        return super().eventFilter(obj, event)

    def _clear_active_page_selection_on_background_click(self, obj):
        if not isinstance(obj, QWidget):
            return
        # Skip events that belong to a different top-level window (e.g. a
        # combo-box dropdown popup which is its own Qt.Popup window).
        if obj.window() is not self:
            return
        # Skip directly interactive widgets — their own handlers manage state.
        widget = obj
        while widget is not None:
            if isinstance(widget, (QAbstractButton, QLineEdit, QComboBox, QAbstractItemView, QSplitter)):
                return
            widget = widget.parentWidget()

        page = self.stack.currentWidget() if hasattr(self, 'stack') else None
        if page is None:
            return

        # Identify the catalog list for the active page.
        catalog_view = getattr(page, 'tool_list', None) or getattr(page, 'jaw_list', None)

        # If the click is anywhere inside the catalog list widget tree, let
        # the list handle its own selection — do NOT clear here.
        if catalog_view is not None:
            w = obj
            while w is not None:
                if w is catalog_view:
                    return
                w = w.parentWidget()

        # All other clicks: clear the active catalog selection.
        if hasattr(page, '_clear_selection'):
            page._clear_selection()

    def _refresh_catalog_pages(self):
        for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page]:
            page.current_tool_id = None
            page.refresh_list()
            page.populate_details(None)
        self.jaws_page.current_jaw_id = None
        self.jaws_page.refresh_list()
        self.jaws_page.populate_details(None)

    def _switch_database(self, database_path: str):
        new_path = Path(database_path)
        if not str(database_path).strip():
            return False, 'Database path is empty.'

        current_path = getattr(self.tool_service.db, 'path', None)
        if current_path is not None and Path(current_path).resolve() == new_path.resolve():
            return True, 'Database already in use.'

        old_db = self.tool_service.db
        try:
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
        old_db = self.jaw_service.db
        try:
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

    def _module_nav_items(self, module: str):
        if module == 'jaws':
            return [
                (self._t("tool_library.nav.all_jaws", "All Jaws"), 'library.svg', False, lambda: self._open_jaws_view('all')),
                (self._t("tool_library.nav.main_spindle", "Main Spindle"), 'arrow_circle_left.svg', False, lambda: self._open_jaws_view('main')),
                (self._t("tool_library.nav.sub_spindle", "Sub Spindle"), 'arrow_circle_right.svg', False, lambda: self._open_jaws_view('sub')),
                (self._t("tool_library.nav.export", "Export"), 'import_export.svg', False, lambda: self._open_jaws_view('export')),
            ]

        return [
            (self._t("tool_library.nav.tools", "Tools"), NAV_ITEM_TO_ICON['TOOLS'], False, lambda: self._open_tool_page('tools')),
            (self._t("tool_library.nav.assemblies", "Assemblies"), NAV_ITEM_TO_ICON['ASSEMBLIES'], False, lambda: self._open_tool_page('assemblies')),
            (self._t("tool_library.nav.holders", "Holders"), NAV_ITEM_TO_ICON['HOLDERS'], False, lambda: self._open_tool_page('holders')),
            (self._t("tool_library.nav.inserts", "Inserts"), NAV_ITEM_TO_ICON['INSERTS'], False, lambda: self._open_tool_page('inserts')),
            (self._t("tool_library.nav.export", "Export"), NAV_ITEM_TO_ICON['EXPORT'], False, lambda: self._open_tool_page('export')),
        ]

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

    def _apply_module_mode(self, module: str):
        self._active_module = 'jaws' if module == 'jaws' else 'tools'
        self._active_nav_items = self._module_nav_items(self._active_module)

        for idx, btn in enumerate(self.nav_buttons):
            if idx < len(self._active_nav_items):
                title, icon_name, mirror, _callback = self._active_nav_items[idx]
                icon_size, rotation = self._nav_icon_render_options(icon_name)
                btn.setIconSize(icon_size)
                btn.setToolTip(title)
                btn.setVisible(True)
            else:
                btn.setVisible(False)

        if self._active_module == 'jaws':
            self.tool_head_filter_combo.hide()
            for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page, self.jaws_page]:
                page.set_module_switch_target('TOOLS')
            self._open_jaws_view('all')
            # Update left rail title for JAWS module
            try:
                self.rail_title.setText(self._t("tool_library.rail_title.jaws", "Jaws Library"))
                self._position_rail_title()
            except Exception:
                pass
        else:
            self.tool_head_filter_combo.show()
            for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page, self.jaws_page]:
                page.set_module_switch_target('JAWS')
            self._open_tool_page('tools')
            # Update left rail title for Tools module
            try:
                self.rail_title.setText(self._t("tool_library.rail_title.tools", "Tool Library"))
                self._position_rail_title()
            except Exception:
                pass

        if self.nav_buttons:
            self.nav_buttons[0].setChecked(True)
        self._refresh_nav_button_icons()

    def _toggle_module(self):
        if self._active_module == 'tools':
            self._apply_module_mode('jaws')
            return
        self._apply_module_mode('tools')

    def _rebuild_head_filter_combo_items(self):
        current_data = str(self.tool_head_filter_combo.currentData() or 'HEAD1').strip().upper()
        if current_data not in {'HEAD1/2', 'HEAD1', 'HEAD2'}:
            current_data = 'HEAD1'

        self.tool_head_filter_combo.blockSignals(True)
        self.tool_head_filter_combo.set_options([
            (self._t('tool_library.head_filter.all', 'HEAD1/2'), 'HEAD1/2'),
            (self._t('tool_library.head_filter.head1', 'HEAD1'), 'HEAD1'),
            (self._t('tool_library.head_filter.head2', 'HEAD2'), 'HEAD2'),
        ])
        self.tool_head_filter_combo.setCurrentData(current_data, emit_signal=False)
        self.tool_head_filter_combo.blockSignals(False)

    def _on_nav_button_clicked(self, index: int):
        if index < 0 or index >= len(self._active_nav_items):
            return
        _title, _icon, _mirror, callback = self._active_nav_items[index]
        callback()
        if 0 <= index < len(self.nav_buttons):
            self.nav_buttons[index].setChecked(True)
        self._refresh_nav_button_icons()

    def _on_global_tool_head_changed(self, _index: int):
        head_value = str(self.tool_head_filter_combo.currentData() or 'HEAD1').strip().upper()
        for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page]:
            page.set_head_filter_value(head_value, refresh=False)
            page.refresh_list()
        # Keep selector HEAD in sync with the dropdown
        if self._selector_mode == 'tools' and head_value in ('HEAD1', 'HEAD2'):
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
        self.localization.set_language(self.ui_preferences.get("language", "en"))
        self._apply_style()
        self._refresh_localized_labels()

    def _refresh_localized_labels(self):
        self.setWindowTitle(self._t("tool_library.window_title", APP_TITLE))
        if hasattr(self, "back_to_setup_btn"):
            self.back_to_setup_btn.setToolTip(self._t("tool_library.back_to_setup_tip", "Switch back to Setup Manager"))
        self._active_nav_items = self._module_nav_items(self._active_module)
        if hasattr(self, "nav_buttons"):
            for idx, btn in enumerate(self.nav_buttons):
                if idx < len(self._active_nav_items):
                    btn.setToolTip(self._active_nav_items[idx][0])
        if self._active_module == "jaws":
            self.rail_title.setText(self._t("tool_library.rail_title.jaws", "Jaws Library"))
        else:
            self.rail_title.setText(self._t("tool_library.rail_title.tools", "Tool Library"))
        if hasattr(self, "master_filter_toggle"):
            self.master_filter_toggle.setToolTip(self._t("tool_library.master_filter.button", "MASTER FILTER"))
            self._update_master_filter_toggle_visual()
        self._update_selector_action_button()
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

    def _build_ui_preference_overrides(self) -> str:
        theme_name = self.ui_preferences.get("color_theme", "classic")
        palette = THEME_PALETTES.get(theme_name, THEME_PALETTES["classic"])
        return (
            "/* Runtime UI preference overrides */\n"
            "QFrame[catalogShell=\"true\"],\n"
            "QListView#toolCatalog,\n"
            "QListView#toolCatalog::viewport,\n"
            "QListWidget#toolCatalog,\n"
            "QListWidget#toolCatalog::viewport {\n"
            f"    background-color: {palette['surface_bg']};\n"
            "}\n"
            "QFrame[detailField=\"true\"] {\n"
            f"    background-color: {palette['detail_box_bg']};\n"
            "}\n"
        )

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
        """Immediately run *callback* without animation."""
        if getattr(self, '_fade_anim', None) is not None:
            self._fade_anim.stop()
        self._fade_anim = None
        self.setWindowOpacity(1.0)
        self._set_graphics_effects_enabled(True)
        callback()

    def fade_in(self):
        """Show fully visible without animation."""
        if getattr(self, '_fade_anim', None) is not None:
            self._fade_anim.stop()
        self._fade_anim = None
        self.setWindowOpacity(1.0)
        self._set_graphics_effects_enabled(True)

    def _current_window_rect(self) -> tuple[int, int, int, int]:
        """Return the actual on-screen window rectangle, including snap placement."""
        try:
            import ctypes

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = RECT()
            hwnd = int(self.winId())
            if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        except Exception:
            pass
        geom = self.frameGeometry()
        return geom.x(), geom.y(), geom.width(), geom.height()

    def _back_to_setup_manager(self):
        """Switch back to Setup Manager."""
        import ctypes
        import ctypes.wintypes
        x, y, width, height = self._current_window_rect()

        # Grant Setup Manager permission to take foreground focus (Windows).
        try:
            ctypes.windll.user32.AllowSetForegroundWindow(ctypes.wintypes.DWORD(-1))
        except Exception:
            pass

        # Preferred path: IPC to the already-running Setup Manager process.
        socket = QLocalSocket()
        socket.connectToServer(SETUP_MANAGER_SERVER_NAME)
        if socket.waitForConnected(300):
            try:
                socket.write(json.dumps({
                    "command": "show",
                    "geometry": f"{x},{y},{width},{height}",
                }).encode("utf-8"))
                socket.flush()
                socket.waitForBytesWritten(300)
            except Exception:
                pass
            finally:
                socket.disconnectFromServer()
            def _finish_handoff():
                self.hide()
                self.setWindowOpacity(1.0)
            self._fade_out_and(_finish_handoff)
            return

        # Fallback: launch Setup Manager from disk.
        launched = False
        setup_roots = [
            SOURCE_DIR.parent / 'Setup Manager',
            Path(sys.executable).resolve().parent.parent / 'Setup Manager',
        ]
        for setup_root in setup_roots:
            setup_manager_main = setup_root / 'main.py'
            if setup_manager_main.exists():
                try:
                    launched = QProcess.startDetached(
                        str(Path(sys.executable)),
                        [str(setup_manager_main), "--geometry", f"{x},{y},{width},{height}"],
                        str(setup_root),
                    )
                except Exception:
                    launched = False
                if launched:
                    break
            for exe_name in ['Setup Manager.exe']:
                setup_manager_exe = setup_root / exe_name
                if not setup_manager_exe.exists():
                    continue
                try:
                    launched = QProcess.startDetached(
                        str(setup_manager_exe),
                        ["--geometry", f"{x},{y},{width},{height}"],
                        str(setup_root),
                    )
                except Exception:
                    launched = False
                if launched:
                    break
            if launched:
                break

        if launched:
            def _finish_launch():
                self.hide()
                self.setWindowOpacity(1.0)
            self._fade_out_and(_finish_launch)
        else:
            QMessageBox.warning(
                self,
                'Setup Manager unavailable',
                'Could not locate a launchable Setup Manager instance.',
            )

    def _clear_selector_session(self):
        self._selector_mode = ''
        self._selector_callback_server = ''
        self._selector_request_id = ''
        self._selector_head = ''
        self._selector_spindle = ''
        self._selector_initial_assignments = []
        self._selector_initial_assignment_buckets = {}
        self._update_selector_action_button()
        self._apply_selector_context_to_pages()
        # Remove stay-on-top hint so the window behaves normally
        self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        self.show()

    def _selector_context_suffix(self) -> str:
        parts = [part for part in [self._selector_head, self._selector_spindle] if part]
        return ' / '.join(parts)

    def _update_selector_action_button(self):
        if not hasattr(self, 'selector_send_btn'):
            return
        self.selector_send_btn.setVisible(False)
        self.selector_send_btn.setToolTip('')

    def _apply_selector_context_to_pages(self):
        tools_selector_active = self._selector_mode == 'tools'
        jaws_selector_active = self._selector_mode == 'jaws'
        selector_head = self._selector_head
        selector_spindle = self._selector_spindle
        selector_assignments = self._selector_initial_assignments if (tools_selector_active or jaws_selector_active) else []
        selector_assignment_buckets = self._selector_initial_assignment_buckets if tools_selector_active else {}

        for page in [self.home_page, self.assemblies_page, self.holders_page, self.inserts_page]:
            if hasattr(page, 'set_selector_context'):
                page.set_selector_context(
                    tools_selector_active,
                    selector_head,
                    selector_spindle,
                    selector_assignments,
                    selector_assignment_buckets,
                )
        if hasattr(self.jaws_page, 'set_selector_context'):
            self.jaws_page.set_selector_context(jaws_selector_active, selector_spindle, selector_assignments)

    def _send_selector_selection(self):
        if self._selector_mode not in ('tools', 'jaws'):
            return

        if self._selector_mode == 'jaws':
            selected_items = []
            if hasattr(self.jaws_page, 'selector_assigned_jaws_for_setup_assignment'):
                selected_items = self.jaws_page.selector_assigned_jaws_for_setup_assignment()
            if not selected_items:
                selected_items = self.jaws_page.selected_jaws_for_setup_assignment()
            kind = 'jaws'
        else:
            active_page = self.stack.currentWidget() if hasattr(self, 'stack') else None
            selected_items = []
            selector_head = self._selector_head
            selector_spindle = self._selector_spindle
            if hasattr(active_page, 'selector_assigned_tools_for_setup_assignment'):
                selected_items = active_page.selector_assigned_tools_for_setup_assignment()
            if hasattr(active_page, 'selector_current_target_for_setup_assignment'):
                target = active_page.selector_current_target_for_setup_assignment()
                if isinstance(target, dict):
                    target_head = str(target.get('head') or '').strip().upper()
                    target_spindle = str(target.get('spindle') or '').strip().lower()
                    if target_head in {'HEAD1', 'HEAD2'}:
                        selector_head = target_head
                    if target_spindle in {'main', 'sub'}:
                        selector_spindle = target_spindle
            if not selected_items and hasattr(active_page, 'selected_tools_for_setup_assignment'):
                selected_items = active_page.selected_tools_for_setup_assignment()
            if not selected_items:
                selected_items = self.home_page.selected_tools_for_setup_assignment()
            kind = 'tools'

        if kind == 'tools' and not selected_items:
            QMessageBox.information(
                self,
                self._t('tool_library.selector.no_selection.title', 'Nothing selected'),
                self._t(
                    'tool_library.selector.no_selection.body',
                    'Select at least one {kind} before sending the selection back.',
                    kind=self._t('tool_library.selector.tools', 'tools') if kind == 'tools' else self._t('tool_library.selector.jaws', 'jaws'),
                ),
            )
            return

        if not self._selector_callback_server:
            QMessageBox.warning(
                self,
                self._t('tool_library.selector.callback_missing.title', 'Selection callback unavailable'),
                self._t(
                    'tool_library.selector.callback_missing.body',
                    'The selection callback server name is missing.',
                ),
            )
            return

        payload = {
            'command': 'selector_result',
            'request_id': self._selector_request_id,
            'kind': kind,
            'items': selected_items,
            'selected_items': selected_items,
        }
        if kind == 'tools':
            payload['selector_head'] = selector_head
            payload['selector_spindle'] = selector_spindle

        socket = QLocalSocket()
        socket.connectToServer(self._selector_callback_server)
        if not socket.waitForConnected(300):
            QMessageBox.warning(
                self,
                self._t('tool_library.selector.callback_failed.title', 'Selection callback unavailable'),
                self._t(
                    'tool_library.selector.callback_failed.body',
                    'Could not connect to the selection callback server.',
                ),
            )
            return

        try:
            socket.write(json.dumps(payload).encode('utf-8'))
            socket.flush()
            if not socket.waitForBytesWritten(300):
                raise RuntimeError('Selection payload was not written to the callback socket.')
        except Exception:
            QMessageBox.warning(
                self,
                self._t('tool_library.selector.callback_failed.title', 'Selection callback unavailable'),
                self._t(
                    'tool_library.selector.callback_failed.body',
                    'Could not send the selected items back to Setup Manager.',
                ),
            )
            return
        finally:
            socket.disconnectFromServer()

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

    def apply_external_request(self, payload: dict, reload_preferences: bool = True):
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

        selector_mode = str(payload.get('selector_mode', '') or '').strip().lower()
        if selector_mode in ('tools', 'jaws'):
            self._selector_mode = selector_mode
            self._selector_callback_server = str(payload.get('selector_callback_server', '') or '').strip()
            self._selector_request_id = str(payload.get('selector_request_id', '') or '').strip()
            self._selector_head = str(payload.get('selector_head', '') or '').strip()
            self._selector_spindle = str(payload.get('selector_spindle', '') or '').strip()
            raw_assignments = payload.get('current_assignments') if selector_mode in ('tools', 'jaws') else []
            self._selector_initial_assignments = [
                dict(item) for item in (raw_assignments or []) if isinstance(item, dict)
            ]
            raw_assignment_buckets = payload.get('current_assignments_by_target') if selector_mode == 'tools' else {}
            if isinstance(raw_assignment_buckets, dict):
                self._selector_initial_assignment_buckets = {
                    str(key): [
                        dict(item)
                        for item in value
                        if isinstance(item, dict)
                    ]
                    for key, value in raw_assignment_buckets.items()
                    if isinstance(value, list)
                }
            else:
                self._selector_initial_assignment_buckets = {}
            self._update_selector_action_button()
            self._apply_selector_context_to_pages()
            # Bring window on top of Work Editor
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            self.show()
            self.raise_()
            self.activateWindow()
        else:
            self._clear_selector_session()
            # Remove stay-on-top when exiting selector mode
            self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
            self.show()

        # Switch module if requested.
        module = selector_mode if selector_mode in ('tools', 'jaws') else str(payload.get('module', '')).strip()
        if module in ('tools', 'jaws'):
            self._apply_module_mode(module)

        kind = str(payload.get('kind', '')).strip()
        item_id = str(payload.get('item_id', '')).strip()
        if kind:
            self.navigate_to(kind, item_id)

    def _apply_style(self):
        def _resolve_asset_urls(qss: str) -> str:
            assets_dir = (APP_DIR / 'assets').resolve().as_posix()
            return qss.replace('url("assets/', f'url("{assets_dir}/').replace("url('assets/", f"url('{assets_dir}/")

        base_style = ""
        # Modules directory is the single source of truth for styles.
        modules_dir = APP_DIR / 'styles' / 'modules'
        if modules_dir.exists():
            parts = [_resolve_asset_urls(p.read_text(encoding='utf-8')) for p in sorted(modules_dir.glob('*.qss'))]
            if parts:
                base_style = '\n\n'.join(parts)

        # Fallback for legacy deployments where the modules directory is absent.
        if not base_style and STYLE_PATH.exists():
            base_style = _resolve_asset_urls(STYLE_PATH.read_text(encoding='utf-8'))

        self.setStyleSheet(base_style + "\n\n" + self._build_ui_preference_overrides())
