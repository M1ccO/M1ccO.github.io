
import json
import shutil
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QUrl, QTimer, QModelIndex, QItemSelectionModel
from PySide6.QtGui import QIcon, QDesktopServices, QFontMetrics, QKeySequence, QShortcut, QStandardItemModel, QStandardItem, QColor, QPainter, QPixmap, QTransform
# import QtSvg so that SVG image support is initialized early
import PySide6.QtSvg  # noqa: F401
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QDialogButtonBox, QLabel, QLineEdit, QListView, QMessageBox, QPushButton,
    QScrollArea, QSplitter, QVBoxLayout, QWidget, QSizePolicy, QToolButton
)
from config import (
    EXPORT_DEFAULT_PATH,
    ALL_TOOL_TYPES,
    MILLING_TOOL_TYPES,
    TURNING_TOOL_TYPES,
    TOOL_TYPE_TO_ICON,
    TOOL_ICONS_DIR,
    DEFAULT_TOOL_ICON,
)
from ui.tool_editor_dialog import AddEditToolDialog
from ui.tool_catalog_delegate import (
    ToolCatalogDelegate, tool_icon_for_type,
    ROLE_TOOL_ID, ROLE_TOOL_DATA, ROLE_TOOL_ICON, ROLE_TOOL_UID,
)
from ui.widgets.common import add_shadow, apply_shared_dropdown_style, repolish_widget
from shared.editor_helpers import (
    apply_secondary_button_theme,
    ask_multi_edit_mode,
    create_titled_section,
    create_dialog_buttons,
    setup_editor_dialog,
)

from ui.stl_preview import StlPreviewWidget


# ==============================
# Home Page Shell
# ==============================
class HomePage(QWidget):
    def __init__(
        self,
        tool_service,
        export_service,
        settings_service,
        parent=None,
        page_title: str = 'Tool Library',
        view_mode: str = 'home',
        translate=None,
    ):
        super().__init__(parent)
        self.tool_service = tool_service
        self.export_service = export_service
        self.settings_service = settings_service
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self.page_title = page_title
        self.view_mode = (view_mode or 'home').lower()
        self.current_tool_id = None
        self.current_tool_uid = None
        self._details_hidden = True
        self._last_splitter_sizes = None
        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._close_preview_shortcut = None
        self._measurement_toggle_btn = None
        self._measurement_filter_combo = None
        self._detached_measurements_enabled = True
        self._detached_measurement_filter = None
        self._detached_preview_last_model_key = None
        self._inline_preview_warmup = None
        self._active_db_name = ''
        self._module_switch_callback = None
        self._external_head_filter = None
        self._head_filter_value = 'HEAD1/2'
        self._master_filter_ids: set[str] = set()
        self._master_filter_active = False
        self._build_ui()
        self._warmup_preview_engine()
        self.refresh_list()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    @staticmethod
    def _strip_tool_id_prefix(value: str) -> str:
        raw = str(value or '').strip()
        if raw.lower().startswith('t'):
            raw = raw[1:].strip()
        return ''.join(ch for ch in raw if ch.isdigit())

    @classmethod
    def _tool_id_storage_value(cls, value: str) -> str:
        stripped = cls._strip_tool_id_prefix(value)
        return f'T{stripped}' if stripped else ''

    @classmethod
    def _tool_id_display_value(cls, value: str) -> str:
        return cls._tool_id_storage_value(value)

    def _warmup_preview_engine(self):
        """Pre-create a hidden preview widget so first detail-open doesn't flash."""
        if StlPreviewWidget is None:
            return
        self._inline_preview_warmup = StlPreviewWidget(parent=self)
        self._inline_preview_warmup.set_control_hint_text(
            self._t(
                'tool_editor.hint.rotate_pan_zoom',
                'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
            )
        )
        self._inline_preview_warmup.hide()

        def _drop_warmup():
            if self._inline_preview_warmup is not None:
                self._inline_preview_warmup.deleteLater()
                self._inline_preview_warmup = None

        # Keep warmup alive long enough for first user interactions.
        QTimer.singleShot(10000, _drop_warmup)

    def _update_row_type_visibility(self, show: bool):
        """Called when the detail panel opens/closes.
        With the delegate-based list, we just need to trigger a repaint.
        """
        self.tool_list.viewport().update()

    def _refresh_row_style(self, widget):
        """No-op — delegate rows don't have child widgets to repolish."""
        pass

    # ==============================
    # Home Page Layout
    # ==============================
    def _build_ui(self):
        root = QVBoxLayout(self)
        # Set all margins to 0 for flush alignment
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        filter_frame = QFrame()
        filter_frame.setObjectName('filterFrame')
        filter_frame.setProperty('card', True)
        self.filter_layout = QHBoxLayout(filter_frame)
        # Left margin must clear the absolutely-positioned rail_title label in
        # main_window, which starts at x=10 on the central widget and can extend
        # ~200px for long Finnish titles, bleeding ~90px into the stack area.
        # 108px ensures the first toolbar button is always visible.
        self.filter_layout.setContentsMargins(108, 6, 0, 6)
        self.filter_layout.setSpacing(4)

        self.toolbar_title_label = QLabel(self.page_title)
        self.toolbar_title_label.setProperty('pageTitle', True)
        self.toolbar_title_label.setStyleSheet('padding-left: 0px; padding-right: 20px;')

        self.search_toggle = QToolButton()
        self.search_icon = QIcon(str(TOOL_ICONS_DIR / 'search_icon.svg'))
        self.close_icon = QIcon(str(TOOL_ICONS_DIR / 'close_icon.svg'))
        self.search_toggle.setIcon(self.search_icon)
        self.search_toggle.setIconSize(QSize(28, 28))
        self.search_toggle.setCheckable(True)
        self.search_toggle.setAutoRaise(True)
        self.search_toggle.setProperty('topBarIconButton', True)
        self.search_toggle.setFixedSize(36, 36)
        self.search_toggle.clicked.connect(self._toggle_search)

        # details toggle as icon-only toolbutton (tooltip SVG) - moved next to search
        self.toggle_details_btn = QToolButton()
        self.toggle_details_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / 'tooltip.svg')))
        self.toggle_details_btn.setIconSize(QSize(28, 28))
        self.toggle_details_btn.setAutoRaise(True)
        self.toggle_details_btn.setProperty('topBarIconButton', True)
        self.toggle_details_btn.setProperty('secondaryAction', True)
        self.toggle_details_btn.setFixedSize(36, 36)
        self.toggle_details_btn.clicked.connect(self.toggle_details)

        # actual search entry, hidden initially
        self.search = QLineEdit()
        self.search.setPlaceholderText(self._t('tool_library.search.placeholder', 'Tool ID, description, holder or cutting code'))
        self.search.textChanged.connect(self.refresh_list)
        self.search.setVisible(False)
        # restrict search width so it doesn't force layout centering
        from PySide6.QtWidgets import QSizePolicy
        self.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search.setMaximumWidth(300)

        # type filter icon (initially no active filter)
        self.filter_icon = QToolButton()
        self.filter_icon.setIcon(QIcon(str(TOOL_ICONS_DIR / 'filter_arrow_right.svg')))
        # match search button size
        self.filter_icon.setIconSize(QSize(28, 28))
        self.filter_icon.setAutoRaise(True)
        self.filter_icon.setProperty('topBarIconButton', True)
        self.filter_icon.setFixedSize(36, 36)
        self.filter_icon.clicked.connect(self._clear_filter)

        self.type_filter = QComboBox()
        self.type_filter.setObjectName('topTypeFilter')
        self._build_tool_type_filter_items()
        self.type_filter.setMaxVisibleItems(8)
        type_popup_view = self.type_filter.view()
        type_popup_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        type_popup_view.setMinimumHeight(0)
        type_popup_view.setMaximumHeight(8 * 40)
        type_popup_view.window().setMinimumHeight(0)
        type_popup_view.window().setMaximumHeight(8 * 40 + 8)
        # make the combo just wide enough for its content, don't stretch
        from PySide6.QtWidgets import QSizePolicy
        self.type_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.type_filter.setMinimumWidth(60)  # kept narrow from stylesheet
        self.type_filter.currentIndexChanged.connect(self._on_type_changed)
        add_shadow(self.type_filter)
        # give property hover tracking and monitor the popup view
        self.type_filter.installEventFilter(self)
        self.type_filter.view().installEventFilter(self)
        apply_shared_dropdown_style(self.type_filter)

        self.preview_window_btn = QToolButton()
        self.preview_window_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / '3d_icon.svg')))
        self.preview_window_btn.setIconSize(QSize(28, 28))
        self.preview_window_btn.setAutoRaise(True)
        self.preview_window_btn.setProperty('topBarIconButton', True)
        self.preview_window_btn.setCheckable(True)
        self.preview_window_btn.setToolTip(self._t('tool_library.preview.toggle', 'Toggle detached 3D preview'))
        self.preview_window_btn.setFixedSize(36, 36)
        self.preview_window_btn.clicked.connect(self.toggle_preview_window)

        # right-side details header that stays aligned with top-bar icons
        self.detail_header_container = QWidget()
        detail_top = QHBoxLayout(self.detail_header_container)
        detail_top.setContentsMargins(0, 0, 0, 0)
        detail_top.setSpacing(6)
        self.detail_section_label = QLabel(self._t('tool_library.section.tool_details', 'Tool details'))
        self.detail_section_label.setProperty('detailSectionTitle', True)
        self.detail_section_label.setStyleSheet('padding: 0 2px 0 0; font-size: 18px;')
        detail_top.addWidget(self.detail_section_label)

        self.detail_close_btn = QToolButton()
        self.detail_close_btn.setIcon(self.close_icon)
        self.detail_close_btn.setIconSize(QSize(20, 20))
        self.detail_close_btn.setAutoRaise(True)
        self.detail_close_btn.setProperty('topBarIconButton', True)
        self.detail_close_btn.setFixedSize(32, 32)
        self.detail_close_btn.clicked.connect(self.hide_details)
        detail_top.addWidget(self.detail_close_btn)

        self._rebuild_filter_row()
        root.addWidget(filter_frame)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)

        # catalogue and detail panes
        left_card = QFrame()
        left_card.setProperty('catalogShell', True)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        self.tool_list = QListView()
        self.tool_list.setObjectName('toolCatalog')
        self.tool_list.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.tool_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tool_list.setSelectionMode(QListView.ExtendedSelection)
        self.tool_list.setMouseTracking(True)   # needed for hover in delegate
        self.tool_list.setStyleSheet(
            "QListView#toolCatalog { border: none; outline: none; padding: 8px; }"
            " QListView#toolCatalog::item { background: transparent; border: none; }"
        )
        self.tool_list.setSpacing(4)
        self._tool_model = QStandardItemModel(self)
        self.tool_list.setModel(self._tool_model)
        self._tool_delegate = ToolCatalogDelegate(
            parent=self.tool_list,
            view_mode=self.view_mode,
            translate=self._t,
        )
        self.tool_list.setItemDelegate(self._tool_delegate)
        self.tool_list.selectionModel().currentChanged.connect(self._on_current_changed)
        self.tool_list.selectionModel().selectionChanged.connect(self._on_multi_selection_changed)
        self.tool_list.doubleClicked.connect(self._on_double_clicked)
        self.tool_list.installEventFilter(self)
        self.tool_list.viewport().installEventFilter(self)
        left_layout.addWidget(self.tool_list, 1)
        self.splitter.addWidget(left_card)

        self.detail_container = QWidget()
        self.detail_container.setContentsMargins(0, 0, 0, 0)
        self.detail_container.setMinimumWidth(220)
        self.detail_container.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        dc_layout = QVBoxLayout(self.detail_container)
        dc_layout.setContentsMargins(0, 0, 0, 0)
        dc_layout.setSpacing(2)

        self.detail_card = QFrame()
        self.detail_card.setProperty('card', True)
        detail_card_layout = QVBoxLayout(self.detail_card)
        detail_card_layout.setContentsMargins(0, 0, 0, 0)
        detail_card_layout.setSpacing(0)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName('detailScrollArea')
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail_panel = QWidget()
        self.detail_panel.setObjectName('detailPanel')
        self.detail_panel.setMinimumWidth(0)
        self.detail_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.detail_layout = QVBoxLayout(self.detail_panel)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(10)
        self.detail_scroll.setWidget(self.detail_panel)
        self.detail_layout.addWidget(self._build_placeholder_details())
        detail_card_layout.addWidget(self.detail_scroll, 1)
        dc_layout.addWidget(self.detail_card, 1)
        self.splitter.addWidget(self.detail_container)
        root.addWidget(self.splitter, 1)

        self.detail_container.hide()
        self.detail_header_container.hide()
        self.splitter.setSizes([1, 0])

        button_bar = QFrame()
        button_bar.setProperty('bottomBar', True)
        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(10, 8, 10, 8)
        button_layout.setSpacing(8)

        self.copy_btn = QPushButton(self._t('tool_library.action.copy_tool', 'COPY TOOL'))
        self.copy_btn.setProperty('panelActionButton', True)
        self.copy_btn.clicked.connect(self.copy_tool)
        self.edit_btn = QPushButton(self._t('tool_library.action.edit_tool', 'EDIT TOOL'))
        self.edit_btn.setProperty('panelActionButton', True)
        self.edit_btn.clicked.connect(self.edit_tool)
        self.delete_btn = QPushButton(self._t('tool_library.action.delete_tool', 'DELETE TOOL'))
        self.delete_btn.setProperty('panelActionButton', True)
        self.delete_btn.setProperty('dangerAction', True)
        self.delete_btn.clicked.connect(self.delete_tool)
        self.add_btn = QPushButton(self._t('tool_library.action.add_tool', 'ADD TOOL'))
        self.add_btn.setProperty('panelActionButton', True)
        self.add_btn.setProperty('primaryAction', True)
        self.add_btn.clicked.connect(self.add_tool)

        self.module_switch_label = QLabel(self._t('tool_library.module.switch_to', 'Switch to'))
        self.module_switch_label.setProperty('pageSubtitle', True)
        self.module_toggle_btn = QPushButton(self._t('tool_library.module.jaws', 'JAWS'))
        self.module_toggle_btn.setProperty('panelActionButton', True)
        self.module_toggle_btn.setFixedHeight(28)
        self.module_toggle_btn.clicked.connect(self._on_module_switch_clicked)

        button_layout.addWidget(self.module_switch_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        button_layout.addWidget(self.module_toggle_btn, 0, Qt.AlignLeft | Qt.AlignVCenter)
        button_layout.addStretch(1)
        self.selection_count_label = QLabel('')
        self.selection_count_label.setProperty('detailHint', True)
        self.selection_count_label.setStyleSheet('background: transparent; border: none;')
        self.selection_count_label.hide()
        button_layout.addWidget(self.selection_count_label, 0, Qt.AlignBottom)
        button_layout.addWidget(self.add_btn)
        button_layout.addWidget(self.edit_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.copy_btn)
        root.addWidget(button_bar)

    def _on_module_switch_clicked(self):
        if callable(self._module_switch_callback):
            self._module_switch_callback()

    def set_module_switch_handler(self, callback):
        self._module_switch_callback = callback

    def set_page_title(self, title: str):
        self.page_title = str(title or '')
        if hasattr(self, 'toolbar_title_label'):
            self.toolbar_title_label.setText(self.page_title)

    def set_module_switch_target(self, target: str):
        target_text = (target or '').strip().upper() or 'JAWS'
        display = self._t('tool_library.module.tools', 'TOOLS') if target_text == 'TOOLS' else self._t('tool_library.module.jaws', 'JAWS')
        self.module_toggle_btn.setText(display)
        self.module_toggle_btn.setToolTip(self._t('tool_library.module.switch_to_target', 'Switch to {target} module', target=display))

    def set_master_filter(self, tool_ids, active: bool):
        self._master_filter_ids = {str(t).strip() for t in (tool_ids or []) if str(t).strip()}
        self._master_filter_active = bool(active) and bool(self._master_filter_ids)
        self.refresh_list()

    def _rebuild_filter_row(self):
        while self.filter_layout.count():
            item = self.filter_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        self.filter_layout.addWidget(self.search_toggle)
        self.filter_layout.addWidget(self.toggle_details_btn)
        if self.search.isVisible():
            self.filter_layout.addWidget(self.search, 1)
        self.filter_layout.addWidget(self.filter_icon)
        self.filter_layout.addWidget(self.type_filter)
        self.filter_layout.addWidget(self.preview_window_btn)
        self.filter_layout.addStretch(1)
        self.filter_layout.addWidget(self.detail_header_container)

    def set_active_database_name(self, db_name: str):
        self._active_db_name = (db_name or '').strip()

    # ==============================
    # Home Page Filters + List State
    # ==============================
    def _toggle_search(self):
        """Show or hide the search field and update widget order."""
        show = self.search_toggle.isChecked()
        # hide the combo entirely while we rearrange; this prevents it from briefly
        # popping up in its own window when its geometry shifts under the cursor.
        self.type_filter.hide()
        self.search.setVisible(show)
        self.search_toggle.setIcon(self.search_icon if not show else self.close_icon)
        if not show:
            # clear search when closed
            self.search.clear()
            self.refresh_list()
        self._rebuild_filter_row()
        # hide any open popup that might have been triggered by the mouse
        self.type_filter.hidePopup()
        # set a flag so eventFilter can swallow any upcoming show events
        self._suppress_combo = True
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: setattr(self, '_suppress_combo', False))
        # briefly disable the combo so stray press/release events can't open it
        self.type_filter.setEnabled(False)
        QTimer.singleShot(0, lambda: self.type_filter.setEnabled(True))
        # show combo once layout has been rebuilt
        self.type_filter.show()
        if show:
            # delay focusing the search field until after the layout settles
            QTimer.singleShot(0, self.search.setFocus)

    def _tool_icon(self, tool_type: str) -> QIcon:
        filename = TOOL_TYPE_TO_ICON.get(tool_type, DEFAULT_TOOL_ICON)
        path = TOOL_ICONS_DIR / filename
        if not path.exists():
            path = TOOL_ICONS_DIR / DEFAULT_TOOL_ICON
        return QIcon(str(path)) if path.exists() else QIcon()

    def _load_preview_content(self, viewer, stl_path: str | None, label: str | None = None) -> bool:
        if StlPreviewWidget is None or viewer is None or not stl_path:
            return False

        try:
            parsed = json.loads(stl_path)

            if isinstance(parsed, list):
                viewer.load_parts(parsed)
                return True

            if isinstance(parsed, str) and parsed.strip():
                viewer.load_stl(parsed, label=label)
                return True
        except Exception:
            viewer.load_stl(stl_path, label=label)
            return True

        return False

    def _set_preview_button_checked(self, checked: bool):
        self.preview_window_btn.blockSignals(True)
        self.preview_window_btn.setChecked(checked)
        self.preview_window_btn.blockSignals(False)

    def _ensure_detached_preview_dialog(self):
        if self._detached_preview_dialog is not None:
            return

        dialog = QDialog(self)
        dialog.setProperty('detachedPreviewDialog', True)
        dialog.setWindowTitle(self._t('tool_library.preview.window_title', '3D Preview'))
        dialog.resize(620, 820)
        dialog.finished.connect(self._on_detached_preview_closed)
        self._close_preview_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), dialog)
        self._close_preview_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._close_preview_shortcut.activated.connect(dialog.close)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        controls_host = QWidget(dialog)
        controls_host.setProperty('detachedPreviewToolbar', True)
        controls_host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        controls_layout = QHBoxLayout(controls_host)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        controls_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self._measurement_toggle_btn = QToolButton(controls_host)
        self._measurement_toggle_btn.setCheckable(True)
        self._measurement_toggle_btn.setChecked(self._detached_measurements_enabled)
        self._measurement_toggle_btn.setIconSize(QSize(28, 28))
        self._measurement_toggle_btn.setAutoRaise(True)
        self._measurement_toggle_btn.setProperty('topBarIconButton', True)
        self._measurement_toggle_btn.setFixedSize(36, 36)
        self._update_detached_measurement_toggle_icon(self._measurement_toggle_btn.isChecked())
        self._measurement_toggle_btn.clicked.connect(self._on_detached_measurements_toggled)
        controls_layout.addWidget(self._measurement_toggle_btn)

        measurements_label = QLabel(self._t('tool_library.preview.measurements_label', 'Mittaukset'))
        measurements_label.setProperty('detailHint', True)
        measurements_label.setProperty('detachedPreviewToolbarLabel', True)
        measurements_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        controls_layout.addWidget(measurements_label)

        self._measurement_filter_combo = None
        controls_layout.addStretch(1)
        layout.addWidget(controls_host)

        if StlPreviewWidget is not None:
            self._detached_preview_widget = StlPreviewWidget()
            self._detached_preview_widget.set_control_hint_text(
                self._t(
                    'tool_editor.hint.rotate_pan_zoom',
                    'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
                )
            )
            self._detached_preview_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self._detached_preview_widget, 1)
        else:
            fallback = QLabel(self._t('tool_library.preview.unavailable', 'Preview component not available.'))
            fallback.setWordWrap(True)
            fallback.setAlignment(Qt.AlignCenter)
            self._detached_preview_widget = None
            fallback.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(fallback, 1)

        self._detached_preview_dialog = dialog
        self._refresh_detached_measurement_controls([])

    def _apply_detached_preview_default_bounds(self):
        if self._detached_preview_dialog is None:
            return
        host_window = self.window()
        if host_window is None:
            return

        host_frame = host_window.frameGeometry()
        if host_frame.width() <= 0 or host_frame.height() <= 0:
            return

        width = max(520, int(host_frame.width() * 0.37))
        width = min(width, 700)
        max_height = max(420, host_frame.height() - 30)
        height = max(600, int(host_frame.height() * 0.86))
        height = min(height, max_height)

        x = host_frame.right() - width + 1
        y = host_frame.bottom() - height + 1
        min_y = host_frame.top() + 30
        if y < min_y:
            y = min_y

        self._detached_preview_dialog.setGeometry(x, y, width, height)

    def _update_detached_measurement_toggle_icon(self, enabled: bool):
        if self._measurement_toggle_btn is None:
            return
        is_enabled = bool(enabled)
        icon_name = 'comment_disable.svg' if is_enabled else 'comment.svg'
        self._measurement_toggle_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
        tooltip = self._t(
            'tool_library.preview.measurements_hide' if is_enabled else 'tool_library.preview.measurements_show',
            'Piilota mittaukset' if is_enabled else 'Näytä mittaukset',
        )
        self._measurement_toggle_btn.setToolTip(tooltip)

    def _on_detached_preview_closed(self, _result):
        if self._detached_preview_widget is not None:
            self._detached_preview_widget.set_measurement_focus_index(-1)
        self._detached_preview_last_model_key = None
        self._set_preview_button_checked(False)

    def _refresh_detached_measurement_controls(self, overlays):
        if self._measurement_toggle_btn is None:
            return

        names = []
        seen = set()
        for overlay in overlays or []:
            if not isinstance(overlay, dict):
                continue
            name = str(overlay.get('name') or '').strip()
            if not name or name in seen:
                continue
            names.append(name)
            seen.add(name)

        has_measurements = bool(names)
        self._measurement_toggle_btn.setEnabled(has_measurements)

        self._measurement_toggle_btn.blockSignals(True)
        self._measurement_toggle_btn.setChecked(self._detached_measurements_enabled and has_measurements)
        self._measurement_toggle_btn.blockSignals(False)
        self._update_detached_measurement_toggle_icon(self._measurement_toggle_btn.isChecked())
        self._detached_measurement_filter = None

    def _apply_detached_measurement_state(self, overlays):
        if self._detached_preview_widget is None:
            return
        self._detached_preview_widget.set_measurement_overlays(overlays or [])
        self._detached_preview_widget.set_measurements_visible(
            bool(overlays) and self._detached_measurements_enabled
        )
        self._detached_preview_widget.set_measurement_filter(self._detached_measurement_filter)

    def _on_detached_measurements_toggled(self, checked: bool):
        self._detached_measurements_enabled = bool(checked)
        self._update_detached_measurement_toggle_icon(self._detached_measurements_enabled)
        if self._detached_preview_widget is not None:
            self._detached_preview_widget.set_measurements_visible(self._detached_measurements_enabled)

    def _on_detached_measurement_filter_changed(self, _index: int):
        if self._measurement_filter_combo is None:
            return
        current_data = self._measurement_filter_combo.currentData()
        self._detached_measurement_filter = None if current_data in (None, '__all__') else str(current_data)
        if self._detached_preview_widget is not None:
            self._detached_preview_widget.set_measurement_filter(self._detached_measurement_filter)

    def _close_detached_preview(self):
        if self._detached_preview_dialog is not None:
            self._detached_preview_dialog.close()
        else:
            self._set_preview_button_checked(False)

    def _sync_detached_preview(self, show_errors: bool = False) -> bool:
        if not self.preview_window_btn.isChecked():
            return False

        if not self.current_tool_id:
            self._close_detached_preview()
            return False

        tool = self._get_selected_tool()
        if not tool:
            self._close_detached_preview()
            return False

        stl_path = tool.get('stl_path')
        if not stl_path:
            if show_errors:
                QMessageBox.information(
                    self,
                    self._t('tool_library.preview.window_title', '3D Preview'),
                    self._t('tool_library.preview.none_assigned_selected', 'The selected tool has no 3D model assigned.'),
                )
            self._close_detached_preview()
            return False

        self._ensure_detached_preview_dialog()
        was_visible = bool(self._detached_preview_dialog and self._detached_preview_dialog.isVisible())
        label = tool.get('description', '').strip() or tool.get('id', '3D Preview')
        raw_model_key = stl_path if isinstance(stl_path, str) else json.dumps(stl_path, ensure_ascii=False, sort_keys=True)
        model_key = (
            int(tool.get('uid')) if str(tool.get('uid', '')).strip().isdigit() else str(tool.get('id') or '').strip(),
            str(raw_model_key or ''),
        )
        loaded = True
        if self._detached_preview_last_model_key != model_key:
            loaded = self._load_preview_content(self._detached_preview_widget, stl_path, label=label)
            if loaded:
                self._detached_preview_last_model_key = model_key
            else:
                self._detached_preview_last_model_key = None
        if not loaded:
            if show_errors:
                QMessageBox.information(
                    self,
                    self._t('tool_library.preview.window_title', '3D Preview'),
                    self._t('tool_library.preview.no_valid_selected', 'No valid 3D model data found for the selected tool.'),
                )
            self._close_detached_preview()
            return False

        overlays = tool.get('measurement_overlays', []) if isinstance(tool, dict) else []
        self._refresh_detached_measurement_controls(overlays)
        self._apply_detached_measurement_state(overlays)

        tool_id = self._tool_id_display_value(tool.get('id', ''))
        self._detached_preview_dialog.setWindowTitle(
            self._t('tool_library.preview.window_title_tool', '3D Preview - {tool_id}', tool_id=tool_id).rstrip(' -')
        )
        if not was_visible:
            self._apply_detached_preview_default_bounds()
            self._detached_preview_dialog.show()
            self._detached_preview_dialog.raise_()
            self._detached_preview_dialog.activateWindow()
        self._set_preview_button_checked(True)
        return True

    def toggle_preview_window(self):
        if self.preview_window_btn.isChecked():
            if not self._sync_detached_preview(show_errors=True):
                self._set_preview_button_checked(False)
            return

        self._close_detached_preview()

    def select_tool_by_id(self, tool_id: str):
        """Navigate the list to the tool with the given id."""
        self.current_tool_id = tool_id.strip()
        self.current_tool_uid = None
        self.refresh_list()
        for row in range(self._tool_model.rowCount()):
            idx = self._tool_model.index(row, 0)
            if idx.data(ROLE_TOOL_ID) == self.current_tool_id:
                self.tool_list.setCurrentIndex(idx)
                self.tool_list.scrollTo(idx)
                break

    def _get_selected_tool(self):
        if self.current_tool_uid is not None:
            tool = self.tool_service.get_tool_by_uid(self.current_tool_uid)
            if tool:
                return tool
        if self.current_tool_id:
            return self.tool_service.get_tool(self.current_tool_id)
        return None

    def refresh_list(self):
        # bail if UI hasn't been built yet
        if not hasattr(self, 'tool_list'):
            return
        tools = self.tool_service.list_tools(
            self.search.text(),
            self.type_filter.currentData() or 'All',
            self._selected_head_filter(),
        )
        if self._master_filter_active:
            tools = [tool for tool in tools if str(tool.get('id', '')).strip() in self._master_filter_ids]
        tools = [tool for tool in tools if self._view_match(tool)]
        self._tool_model.blockSignals(True)
        self._tool_model.clear()
        for tool in tools:
            item = QStandardItem()
            tool_id = tool.get('id', '')
            tool_uid = tool.get('uid')
            item.setData(tool_id, ROLE_TOOL_ID)
            item.setData(tool_uid, ROLE_TOOL_UID)
            item.setData(tool, ROLE_TOOL_DATA)
            item.setData(tool_icon_for_type(tool.get('tool_type', '')), ROLE_TOOL_ICON)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self._tool_model.appendRow(item)
        self._tool_model.blockSignals(False)
        # restore selection
        if self.current_tool_uid is not None:
            for row in range(self._tool_model.rowCount()):
                idx = self._tool_model.index(row, 0)
                if idx.data(ROLE_TOOL_UID) == self.current_tool_uid:
                    self.tool_list.setCurrentIndex(idx)
                    self.tool_list.scrollTo(idx)
                    break
        elif self.current_tool_id:
            for row in range(self._tool_model.rowCount()):
                idx = self._tool_model.index(row, 0)
                if idx.data(ROLE_TOOL_ID) == self.current_tool_id:
                    self.tool_list.setCurrentIndex(idx)
                    self.tool_list.scrollTo(idx)
                    break

        # Force immediate relayout/repaint so head-filter changes are visible
        # without requiring a hover/mouse-move over the list viewport.
        self.tool_list.doItemsLayout()
        self.tool_list.viewport().update()
        self.tool_list.viewport().repaint()

    def _view_match(self, tool: dict) -> bool:
        if self.view_mode == 'holders':
            return bool((tool.get('holder_code', '') or '').strip())

        if self.view_mode == 'inserts':
            return bool((tool.get('cutting_code', '') or '').strip())

        if self.view_mode == 'assemblies':
            support_parts = tool.get('support_parts', [])
            if isinstance(support_parts, str):
                try:
                    support_parts = json.loads(support_parts or '[]')
                except Exception:
                    support_parts = []

            stl_parts = []
            stl_data = tool.get('stl_path', '')
            if isinstance(stl_data, str) and stl_data.strip():
                try:
                    parsed = json.loads(stl_data)
                    stl_parts = parsed if isinstance(parsed, list) else []
                except Exception:
                    stl_parts = []

            return len(support_parts) > 0 or len(stl_parts) > 1

        # home/tools/export pages use full list
        return True

    def toggle_details(self):
        if self._details_hidden:
            if not self.current_tool_id:
                QMessageBox.information(self, self._t('tool_library.message.show_details', 'Show details'), self._t('tool_library.message.select_tool_first', 'Select a tool first.'))
                return
            tool = self._get_selected_tool()
            self.populate_details(tool)
            self.show_details()
        else:
            self.hide_details()

    def show_details(self):
        self._details_hidden = False
        self.detail_container.show()
        self.detail_header_container.show()
        self.toggle_details_btn.setText(self._t('tool_library.details.hide', 'HIDE DETAILS'))
        if not self._last_splitter_sizes:
            total = max(600, self.splitter.width())
            self._last_splitter_sizes = [int(total * 0.62), int(total * 0.38)]
        self.splitter.setSizes(self._last_splitter_sizes)
        self._update_row_type_visibility(False)

    def hide_details(self):
        self._details_hidden = True
        if self.detail_container.isVisible():
            self._last_splitter_sizes = self.splitter.sizes()
        self.detail_container.hide()
        self.detail_header_container.hide()
        self.toggle_details_btn.setText(self._t('tool_library.details.show', 'SHOW DETAILS'))
        self.splitter.setSizes([1, 0])
        self._update_row_type_visibility(True)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if getattr(obj, 'property', None) and obj.property('elideGroupTitle'):
            if event.type() in (QEvent.Resize, QEvent.Show, QEvent.FontChange):
                self._refresh_elided_group_title(obj)
        if obj is getattr(self, 'type_filter', None) or (
                getattr(self, 'type_filter', None) and obj is self.type_filter.view()):
            # if we are currently suppressing, swallow any show events
            if getattr(self, '_suppress_combo', False) and event.type() in (QEvent.Show, QEvent.ShowToParent):
                return True
        # clear selection when clicking on empty area of the tool list or its viewport
        if obj in (getattr(self, 'tool_list', None),
                   getattr(self, 'tool_list', None) and self.tool_list.viewport()):
            if event.type() == QEvent.MouseButtonPress:
                # coordinate is in viewport space either way
                if not self.tool_list.indexAt(event.pos()).isValid():
                    self._clear_selection()
        return super().eventFilter(obj, event)

    def _refresh_elided_group_title(self, group):
        if group is None or not hasattr(group, 'setTitle'):
            return
        full_title = str(group.property('fullGroupTitle') or group.title() or '').strip()
        if not full_title:
            return
        available = max(12, group.width() - 30)
        elided = QFontMetrics(group.font()).elidedText(full_title, Qt.ElideRight, available)
        group.setTitle(elided)
        group.setToolTip(full_title)

    def _clear_selection(self):
        """Internal helper to clear row selection and reset details."""
        details_were_open = not self._details_hidden
        if hasattr(self, 'tool_list'):
            self.tool_list.selectionModel().clearSelection()
            self.tool_list.setCurrentIndex(QModelIndex())
        self.current_tool_id = None
        self.current_tool_uid = None
        self._update_selection_count_label()
        self.populate_details(None)
        if details_were_open:
            self.hide_details()
        if hasattr(self, 'preview_window_btn') and self.preview_window_btn.isChecked():
            self._close_detached_preview()

    def _selected_tool_uids(self) -> list[int]:
        model = self.tool_list.selectionModel()
        if model is None:
            return []
        indexes = sorted(model.selectedIndexes(), key=lambda idx: idx.row())
        uids: list[int] = []
        for index in indexes:
            uid = index.data(ROLE_TOOL_UID)
            if uid is None:
                continue
            try:
                parsed = int(uid)
            except Exception:
                continue
            if parsed not in uids:
                uids.append(parsed)
        return uids

    def _on_multi_selection_changed(self, _selected, _deselected):
        self._update_selection_count_label()

    def _update_selection_count_label(self):
        count = len(self._selected_tool_uids())
        if count > 1:
            self.selection_count_label.setText(
                self._t('tool_library.selection.count', '{count} selected', count=count)
            )
            self.selection_count_label.show()
            return
        self.selection_count_label.hide()

    @staticmethod
    def _prune_backups(db_path: Path, tag: str, keep: int = 5):
        prefix = f"{db_path.stem}_{tag}_"
        backups = sorted(
            db_path.parent.glob(f"{prefix}*.bak"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for stale in backups[keep:]:
            try:
                stale.unlink()
            except Exception:
                pass

    def _create_db_backup(self, tag: str) -> Path:
        db_path = Path(self.tool_service.db.path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = db_path.parent / f"{db_path.stem}_{tag}_{timestamp}.bak"
        shutil.copy2(db_path, backup_path)
        self._prune_backups(db_path, tag)
        return backup_path

    def _prompt_batch_cancel_behavior(self) -> str:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(self._t('tool_library.batch.cancel.title', 'Batch edit cancelled'))
        box.setText(
            self._t(
                'tool_library.batch.cancel.body',
                'You stopped editing partway through the batch. Do you want to keep the changes you\'ve already saved, or undo all of them?',
            )
        )
        keep_btn = box.addButton(
            self._t('tool_library.batch.cancel.keep', 'Keep'),
            QMessageBox.AcceptRole,
        )
        undo_btn = box.addButton(
            self._t('tool_library.batch.cancel.undo', 'Undo'),
            QMessageBox.DestructiveRole,
        )
        box.addButton(self._t('common.cancel', 'Cancel'), QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is undo_btn:
            return 'undo'
        if clicked is keep_btn:
            return 'keep'
        return 'keep'

    def _batch_edit_tools(self, uids: list[int]):
        saved_before: list[dict] = []
        total = len(uids)
        for idx, uid in enumerate(uids, 1):
            tool = self.tool_service.get_tool_by_uid(uid)
            if not tool:
                continue
            draft_tool = dict(tool)
            while True:
                dlg = AddEditToolDialog(
                    self,
                    tool=draft_tool,
                    tool_service=self.tool_service,
                    translate=self._t,
                    batch_label=f"{idx}/{total}",
                )
                if dlg.exec() != QDialog.Accepted:
                    if saved_before:
                        action = self._prompt_batch_cancel_behavior()
                        if action == 'undo':
                            for previous in reversed(saved_before):
                                self.tool_service.save_tool(previous, allow_duplicate=True)
                    self.refresh_list()
                    return
                result = self._save_from_dialog(dlg)
                if result == 'saved':
                    saved_before.append(tool)
                    break
                if result == 'retry':
                    draft_tool = dlg.get_tool_data()
                    draft_tool['uid'] = uid
                    continue
                self.refresh_list()
                return
        self.refresh_list()

    def _group_edit_tools(self, uids: list[int]):
        dlg = AddEditToolDialog(
            self,
            tool_service=self.tool_service,
            translate=self._t,
            group_edit_mode=True,
            group_count=len(uids),
        )
        baseline = dlg.get_tool_data()
        if dlg.exec() != QDialog.Accepted:
            return
        edited_data = dlg.get_tool_data()
        changed_fields = {
            key: value
            for key, value in edited_data.items()
            if value != baseline.get(key)
        }
        if not changed_fields:
            QMessageBox.information(
                self,
                self._t('tool_library.group_edit.no_changes_title', 'No changes'),
                self._t('tool_library.group_edit.no_changes_body', 'No fields were changed.'),
            )
            return

        self._create_db_backup('group_edit')
        for uid in uids:
            existing = self.tool_service.get_tool_by_uid(uid)
            if not existing:
                continue
            merged = dict(existing)
            merged.update(changed_fields)
            merged['uid'] = uid
            self.tool_service.save_tool(merged, allow_duplicate=True)
        self.refresh_list()

    def keyPressEvent(self, event):
        """Handle escape key to deselect any selected tool row."""
        from PySide6.QtCore import Qt as _Qt
        if event.key() == _Qt.Key_Escape:
            self._clear_selection()
            return
        super().keyPressEvent(event)

    def _on_type_changed(self, _index):
        # update filter icon based on whether a real filter is active
        active = (self.type_filter.currentData() or 'All') != 'All'
        icon_name = 'filter_off.svg' if active else 'filter_arrow_right.svg'
        self.filter_icon.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
        if active:
            # apply filter immediately
            self.refresh_list()
        else:
            # if filter cleared programmatically, restore list
            self.refresh_list()

    def _on_head_filter_changed(self, _text):
        self.refresh_list()

    def _selected_head_filter(self) -> str:
        if self._external_head_filter is not None:
            raw = self._external_head_filter.currentData()
            if raw is not None:
                return str(raw)
            return self._external_head_filter.currentText()
        return self._head_filter_value

    def _localized_tool_type(self, raw_tool_type: str) -> str:
        key = f"tool_library.tool_type.{(raw_tool_type or '').strip().lower().replace('.', '_').replace('/', '_').replace(' ', '_')}"
        return self._t(key, raw_tool_type)

    def _localized_cutting_type(self, raw_cutting_type: str) -> str:
        key = f"tool_library.cutting_type.{(raw_cutting_type or '').strip().lower().replace(' ', '_')}"
        return self._t(key, raw_cutting_type)

    @staticmethod
    def _is_turning_drill_tool_type(raw_tool_type: str) -> bool:
        normalized = (raw_tool_type or '').strip().lower()
        return normalized in {'turn drill', 'turn spot drill', 'turn center drill'}

    @staticmethod
    def _is_mill_tool_type(raw_tool_type: str) -> bool:
        return (raw_tool_type or '').strip() in MILLING_TOOL_TYPES

    def _build_tool_type_filter_items(self):
        current_raw = self.type_filter.currentData() if hasattr(self, 'type_filter') and self.type_filter.count() else 'All'
        if not hasattr(self, 'type_filter'):
            return
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem(self._t('tool_library.filter.all', 'All'), 'All')
        for raw_type in ALL_TOOL_TYPES:
            self.type_filter.addItem(self._localized_tool_type(raw_type), raw_type)
        for idx in range(self.type_filter.count()):
            if self.type_filter.itemData(idx) == current_raw:
                self.type_filter.setCurrentIndex(idx)
                break
        if self.type_filter.count() and self.type_filter.currentIndex() < 0:
            self.type_filter.setCurrentIndex(0)
        self.type_filter.blockSignals(False)

    def bind_external_head_filter(self, combo: QComboBox | None):
        self._external_head_filter = combo
        self.refresh_list()

    def set_head_filter_value(self, value: str, refresh: bool = True):
        normalized = (value or 'HEAD1/2').strip().upper()
        if normalized not in {'HEAD1/2', 'HEAD1', 'HEAD2'}:
            normalized = 'HEAD1/2'
        self._head_filter_value = normalized
        if refresh:
            self.refresh_list()

    def _clear_filter(self):
        # clicked the icon when filter active -> set back to All
        for idx in range(self.type_filter.count()):
            if self.type_filter.itemData(idx) == 'All':
                self.type_filter.setCurrentIndex(idx)
                break

    def _on_current_changed(self, current: QModelIndex, previous: QModelIndex):
        if not current.isValid():
            self.current_tool_id = None
            self.current_tool_uid = None
            self._update_selection_count_label()
            self.populate_details(None)
            if self.preview_window_btn.isChecked():
                self._close_detached_preview()
            return
        self.current_tool_id = current.data(ROLE_TOOL_ID)
        self.current_tool_uid = current.data(ROLE_TOOL_UID)
        self._update_selection_count_label()
        # if details pane is already visible, refresh its contents
        if not self._details_hidden:
            tool = self._get_selected_tool()
            self.populate_details(tool)
        if self.preview_window_btn.isChecked():
            self._sync_detached_preview(show_errors=False)

    def _on_double_clicked(self, index: QModelIndex):
        self.current_tool_id = index.data(ROLE_TOOL_ID)
        self.current_tool_uid = index.data(ROLE_TOOL_UID)
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.edit_tool()
            return
        # if detail window already open, close it; otherwise open/update
        if not self._details_hidden:
            self.hide_details()
        else:
            self.populate_details(self._get_selected_tool())
            self.show_details()

    # ==============================
    # Detail Panel Construction
    # ==============================
    def _clear_details(self):
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _build_placeholder_details(self):
        card = QFrame()
        card.setProperty('subCard', True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        title = QLabel(self._t('tool_library.section.tool_details', 'Tool details'))
        title.setProperty('detailSectionTitle', True)
        layout.addWidget(title)
        info = QLabel(self._t('tool_library.message.select_tool_for_details', 'Select a tool to view details.'))
        info.setProperty('detailHint', True)
        info.setWordWrap(True)
        layout.addWidget(info)
        preview = QFrame()
        preview.setProperty('diagramPanel', True)
        p = QVBoxLayout(preview)
        p.setContentsMargins(12, 12, 12, 12)
        p.addStretch(1)
        p.addStretch(1)
        layout.addWidget(preview)
        return card

    def populate_details(self, tool):
        self._clear_details()
        if not tool:
            self.detail_layout.addWidget(self._build_placeholder_details())
            return

        support_parts = tool.get('support_parts', []) if isinstance(tool.get('support_parts'), list) else json.loads(tool.get('support_parts', '[]') or '[]')

        card = QFrame()
        card.setProperty('subCard', True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QFrame()
        header.setProperty('detailHeader', True)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 14, 14, 12)
        header_layout.setSpacing(4)

        name_label = QLabel(tool.get('description', '').strip() or self._t('tool_library.common.no_description', 'No description'))
        name_label.setProperty('detailHeroTitle', True)
        name_label.setWordWrap(True)
        name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        tool_id_text = self._tool_id_display_value(tool.get('id', '')) or '-'
        id_label = QLabel(tool_id_text)
        id_label.setProperty('detailHeroTitle', True)
        id_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        title_row.addWidget(name_label, 1)
        title_row.addWidget(id_label, 0, Qt.AlignRight)

        meta_row = QHBoxLayout()
        badge = QLabel(self._localized_tool_type(tool.get('tool_type', '')))
        badge.setProperty('toolBadge', True)
        meta_row.addWidget(badge, 0, Qt.AlignLeft)
        tool_head = (tool.get('tool_head', 'HEAD1') or 'HEAD1').strip().upper()
        head_badge = QLabel(tool_head)
        head_badge.setProperty('toolBadge', True)
        meta_row.addStretch(1)
        meta_row.addWidget(head_badge, 0, Qt.AlignRight)
        header_layout.addLayout(title_row)
        header_layout.addLayout(meta_row)
        layout.addWidget(header)

        # helper to create a field widget with key and value
        def build_field(label_text: str, value_text: str, multiline: bool = False) -> QWidget:
            field_group = create_titled_section(label_text)
            field_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            field_group.setMinimumWidth(0)
            field_group.setProperty('elideGroupTitle', True)
            field_group.setProperty('fullGroupTitle', label_text)
            field_group.installEventFilter(self)
            QTimer.singleShot(0, lambda g=field_group: self._refresh_elided_group_title(g))

            flayout = QVBoxLayout(field_group)
            flayout.setContentsMargins(6, 4, 6, 4)
            flayout.setSpacing(4)

            raw_value = '' if value_text is None else str(value_text)
            if multiline:
                normalized_value = (
                    raw_value
                    .replace('\r\n', '\n')
                    .replace('\r', '\n')
                    .replace('\u2028', '\n')
                    .replace('\u2029', '\n')
                    .replace('\\n', '\n')
                )
                value_edit = QLabel(normalized_value if normalized_value.strip() else '-')
                value_edit.setWordWrap(True)
                value_edit.setTextInteractionFlags(Qt.TextSelectableByMouse)
                value_edit.setFocusPolicy(Qt.NoFocus)
                value_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                value_edit.setMinimumHeight(32)
                value_edit.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                value_edit.setStyleSheet(
                    'QLabel {'
                    '  background-color: #ffffff;'
                    '  border: 1px solid #c8d4e0;'
                    '  border-radius: 6px;'
                    '  padding: 6px;'
                    '  font-size: 10.5pt;'
                    '}'
                )
                # Avoid tooltip popups over notes; the wrapped text is fully visible in-place.
                value_edit.setToolTip('')
            else:
                value_edit = QLineEdit(raw_value if raw_value.strip() else '-')
                value_edit.setReadOnly(True)
                value_edit.setFocusPolicy(Qt.NoFocus)
                value_edit.setCursorPosition(0)
                value_edit.setToolTip(raw_value.strip() or '-')
                value_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            flayout.addWidget(value_edit)
            return field_group

        raw_cutting_type = tool.get('cutting_type', 'Insert')
        raw_tool_type = tool.get('tool_type', '')
        turning_drill_type = self._is_turning_drill_tool_type(raw_tool_type)
        mill_tool_type = self._is_mill_tool_type(raw_tool_type)

        # Build the information grid using 6 equal columns.
        # Two-box rows use 3+3 spans; three-box rows use 2+2+2 spans.
        info = QGridLayout()
        info.setHorizontalSpacing(6)
        info.setVerticalSpacing(8)
        info.setColumnStretch(0, 1)
        info.setColumnStretch(1, 1)
        info.setColumnStretch(2, 1)
        info.setColumnStretch(3, 1)

        info.setColumnStretch(4, 1)
        info.setColumnStretch(5, 1)

        def add_two_box_row(row, left_label, left_value, right_label, right_value):
            info.addWidget(build_field(left_label, left_value), row, 0, 1, 3, Qt.AlignTop)
            info.addWidget(build_field(right_label, right_value), row, 3, 1, 3, Qt.AlignTop)

        def add_three_box_row(row, first_label, first_value, second_label, second_value, third_label, third_value):
            info.addWidget(build_field(first_label, first_value), row, 0, 1, 2, Qt.AlignTop)
            info.addWidget(build_field(second_label, second_value), row, 2, 1, 2, Qt.AlignTop)
            info.addWidget(build_field(third_label, third_value), row, 4, 1, 2, Qt.AlignTop)

        is_milling = raw_tool_type in MILLING_TOOL_TYPES
        is_drill_cutting = raw_cutting_type in {'Drill', 'Center drill'}
        is_drill_tool = (raw_tool_type or '').strip() == 'Drill'
        is_chamfer = (raw_tool_type or '').strip() == 'Chamfer'
        is_center_drill_tool = (raw_tool_type or '').strip() == 'Spot Drill'
        uses_pitch_label = (raw_tool_type or '').strip() == 'Tapping'
        is_turning_tool = raw_tool_type in TURNING_TOOL_TYPES
        show_b_axis = is_turning_tool and not turning_drill_type and tool_head == 'HEAD1'
        is_head2_turning_non_drill = tool_head == 'HEAD2' and is_turning_tool and not turning_drill_type

        if is_head2_turning_non_drill:
            # HEAD2 turning tools: one row with Geom X, Geom Z, and Nirkonsade.
            add_three_box_row(
                0,
                self._t('tool_library.field.geom_x', 'Geom X'),
                str(tool.get('geom_x', '')),
                self._t('tool_library.field.geom_z', 'Geom Z'),
                str(tool.get('geom_z', '')),
                self._t('tool_library.field.nose_radius', 'Nose radius'),
                str(tool.get('nose_corner_radius', '')),
            )
        else:
            add_two_box_row(
                0,
                self._t('tool_library.field.geom_x', 'Geom X'),
                str(tool.get('geom_x', '')),
                self._t('tool_library.field.geom_z', 'Geom Z'),
                str(tool.get('geom_z', '')),
            )

        angle_value = str(tool.get('drill_nose_angle', ''))
        if not angle_value.strip():
            # Backward compatibility: older records may store point angle in nose_corner_radius.
            angle_value = str(tool.get('nose_corner_radius', ''))

        if turning_drill_type:
            # Turn drills / turn center drills:
            # row 1 = Geom X + Geom Z, row 2 = Radius + Nose angle.
            add_two_box_row(
                1,
                self._t('tool_library.field.radius', 'Radius'),
                str(tool.get('radius', '')),
                self._t('tool_library.field.nose_angle', 'Nose angle'),
                angle_value,
            )
            full_row = 2
        elif is_turning_tool:
            if show_b_axis:
                add_two_box_row(
                    1,
                    self._t('tool_library.field.b_axis_angle', 'B-axis angle'),
                    str(tool.get('b_axis_angle', '0')),
                    self._t('tool_library.field.nose_radius', 'Nose radius'),
                    str(tool.get('nose_corner_radius', '')),
                )
                full_row = 2
            elif is_head2_turning_non_drill:
                full_row = 1
            else:
                full_row = 1
        elif is_chamfer:
            add_three_box_row(
                1,
                self._t('tool_library.field.radius', 'Radius'),
                str(tool.get('radius', '')),
                self._t('tool_library.field.nose_angle', 'Nose angle'),
                angle_value,
                self._t('tool_library.field.number_of_flutes', 'Number of flutes'),
                str(tool.get('mill_cutting_edges', '')),
            )
            full_row = 2
        elif is_center_drill_tool:
            add_two_box_row(
                1,
                self._t('tool_library.field.radius', 'Radius'),
                str(tool.get('radius', '')),
                self._t('tool_library.field.nose_angle', 'Nose angle'),
                angle_value,
            )
            full_row = 2
        elif is_drill_tool:
            add_two_box_row(
                1,
                self._t('tool_library.field.radius', 'Radius'),
                str(tool.get('radius', '')),
                self._t('tool_library.field.nose_angle', 'Nose angle'),
                angle_value,
            )
            full_row = 2
        elif is_milling and not is_drill_cutting:
            add_three_box_row(
                1,
                self._t('tool_library.field.radius', 'Radius'),
                str(tool.get('radius', '')),
                self._t('tool_library.field.number_of_flutes', 'Number of flutes'),
                str(tool.get('mill_cutting_edges', '')),
                self._t('tool_library.field.pitch', 'Pitch') if uses_pitch_label else self._t('tool_library.field.corner_radius', 'Corner radius'),
                str(tool.get('nose_corner_radius', '')),
            )
            full_row = 2
        else:
            if is_drill_cutting:
                info.addWidget(build_field(self._t('tool_library.field.radius', 'Radius'), str(tool.get('radius', ''))), 1, 0, 1, 3, Qt.AlignTop)
                info.addWidget(build_field(self._t('tool_library.field.nose_angle', 'Nose angle'), angle_value), 1, 3, 1, 3, Qt.AlignTop)
            elif not is_drill_cutting:
                info.addWidget(build_field(self._t('tool_library.field.radius', 'Radius'), str(tool.get('radius', ''))), 1, 0, 1, 3, Qt.AlignTop)
                info.addWidget(build_field(self._t('tool_library.field.nose_corner_radius', 'Nose R / Corner R'), str(tool.get('nose_corner_radius', ''))), 1, 3, 1, 3, Qt.AlignTop)
            full_row = 2

        # notes field - spans full width
        notes_text = tool.get('notes', tool.get('spare_parts', ''))
        if notes_text:
            notes_field = build_field(self._t('tool_library.field.notes', 'Notes'), notes_text, multiline=True)
            info.addWidget(notes_field, full_row, 0, 1, 6)
        layout.addLayout(info)
        layout.addWidget(self._build_components_panel(tool, support_parts))
        layout.addWidget(self._build_preview_panel(tool.get('stl_path')))
        layout.addStretch(1)
        self.detail_layout.addWidget(card)

    def _value_label(self, text):
        lbl = QLabel(text or '-')
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setProperty('detailValue', True)
        lbl.setMinimumWidth(0)
        lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        return lbl
    
    def _detail_key_label(self, text):
        lbl = QLabel(text)
        lbl.setProperty('detailFieldKey', True)
        lbl.setWordWrap(True)
        lbl.setMinimumWidth(0)
        lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        return lbl

    def _component_toggle_arrow_pixmaps(self):
        cached = getattr(self, '_component_toggle_arrows', None)
        if cached is not None:
            return cached

        canvas_size = 20
        font = self.font()
        font.setPixelSize(16)
        font.setBold(True)

        up_arrow = QPixmap(canvas_size, canvas_size)
        up_arrow.fill(Qt.transparent)

        painter = QPainter(up_arrow)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setFont(font)
        painter.setPen(QColor('#2b3640'))
        painter.drawText(up_arrow.rect(), Qt.AlignCenter, '\u25b2')
        painter.end()

        left_arrow = up_arrow.transformed(QTransform().rotate(-90), Qt.SmoothTransformation)
        self._component_toggle_arrows = (left_arrow, up_arrow)
        return self._component_toggle_arrows

    # ==============================
    # Detail Panel Sections
    # ==============================
    def _build_components_panel(self, tool, support_parts):
        frame = create_titled_section(self._t('tool_library.section.tool_components', 'Tool components'))
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(6)

        body_host = QFrame()
        body_host.setObjectName('toolComponentsBodyHost')
        body_host.setStyleSheet(
            'QFrame#toolComponentsBodyHost {'
            '  background-color: #ffffff;'
            '  border: none;'
            '  border-radius: 4px;'
            '}'
        )
        body_layout = QVBoxLayout(body_host)
        body_layout.setContentsMargins(8, 8, 8, 8)
        body_layout.setSpacing(6)

        list_layout = QVBoxLayout()
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(4)

        def _component_key(item: dict, fallback_idx: int) -> str:
            explicit = (item.get('component_key') or '').strip()
            if explicit:
                return explicit
            role = (item.get('role') or 'component').strip().lower()
            code = (item.get('code') or '').strip()
            if code:
                return f"{role}:{code}"
            return f"{role}:idx:{fallback_idx}"

        component_items = tool.get('component_items', [])
        if isinstance(component_items, str):
            try:
                component_items = json.loads(component_items or '[]')
            except Exception:
                component_items = []

        normalized = []
        if isinstance(component_items, list):
            for idx, item in enumerate(component_items):
                if not isinstance(item, dict):
                    continue
                role = (item.get('role') or '').strip().lower()
                if role not in {'holder', 'cutting', 'support'}:
                    continue
                code = (item.get('code') or '').strip()
                if not code:
                    continue
                try:
                    order = int(item.get('order', idx))
                except Exception:
                    order = idx
                normalized.append(
                    {
                        'role': role,
                        'label': (item.get('label') or '').strip(),
                        'code': code,
                        'link': (item.get('link') or '').strip(),
                        'group': (item.get('group') or '').strip(),
                        'component_key': (item.get('component_key') or '').strip(),
                        'order': order,
                    }
                )

        if not normalized:
            # Legacy fallback for rows without component_items.
            raw_cutting_name = tool.get('cutting_type', '')
            cutting_name = self._localized_cutting_type(raw_cutting_name) if raw_cutting_name else self._t('tool_library.field.cutting_part', 'Cutting part')
            legacy_candidates = [
                {
                    'role': 'holder',
                    'label': self._t('tool_library.field.holder', 'Holder'),
                    'code': tool.get('holder_code', ''),
                    'link': (tool.get('holder_link', '') or '').strip(),
                    'group': '',
                    'component_key': 'holder:' + (tool.get('holder_code', '') or '').strip(),
                    'order': 0,
                },
                {
                    'role': 'holder',
                    'label': self._t('tool_library.field.add_element', 'Add. Element'),
                    'code': tool.get('holder_add_element', ''),
                    'link': (tool.get('holder_add_element_link', '') or '').strip(),
                    'group': '',
                    'component_key': 'holder:' + (tool.get('holder_add_element', '') or '').strip(),
                    'order': 1,
                },
                {
                    'role': 'cutting',
                    'label': cutting_name,
                    'code': tool.get('cutting_code', ''),
                    'link': (tool.get('cutting_link', '') or '').strip(),
                    'group': '',
                    'component_key': 'cutting:' + (tool.get('cutting_code', '') or '').strip(),
                    'order': 2,
                },
                {
                    'role': 'cutting',
                    'label': self._t('tool_library.field.add_cutting', 'Add. {cutting_type}', cutting_type=cutting_name),
                    'code': tool.get('cutting_add_element', ''),
                    'link': (tool.get('cutting_add_element_link', '') or '').strip(),
                    'group': '',
                    'component_key': 'cutting:' + (tool.get('cutting_add_element', '') or '').strip(),
                    'order': 3,
                },
            ]
            normalized.extend([item for item in legacy_candidates if (item.get('code') or '').strip()])

        normalized.sort(key=lambda entry: int(entry.get('order', 0)))

        spare_index = {}
        for part in support_parts or []:
            if isinstance(part, str):
                try:
                    part = json.loads(part)
                except Exception:
                    part = {'name': part, 'code': '', 'link': '', 'component_key': ''}
            if not isinstance(part, dict):
                continue
            part_key = (
                (part.get('component_key') or '').strip()
                or (part.get('component') or '').strip()
                or (part.get('component_code') or '').strip()
            )
            if not part_key:
                continue
            spare_index.setdefault(part_key, []).append(part)

        last_group = None
        for idx, item in enumerate(normalized):
            group = (item.get('group') or '').strip()
            if group != last_group:
                last_group = group
                if group:
                    group_label = QLabel(group)
                    group_label.setProperty('detailFieldKey', True)
                    group_label.setStyleSheet(
                        'background: transparent;'
                        'font-weight: 600; font-size: 9pt; color: #5a6a7a;'
                        'border-bottom: 1px solid #d0d8e0; padding: 4px 0 2px 0;'
                    )
                    list_layout.addWidget(group_label)

            display_name = item.get('label', self._t('tool_library.field.part', 'Part'))
            button_text = (display_name or '').strip()

            component_key = _component_key(item, idx)
            linked_spares = spare_index.get(component_key, [])

            row_card = QFrame()
            row_card.setProperty('editorFieldCard', True)
            row_layout = QHBoxLayout(row_card)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            btn = QPushButton(button_text)
            btn.setProperty('panelActionButton', True)
            btn.setProperty('componentCompact', True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip((item.get('link') or '').strip() or self._t('tool_library.part.no_link', 'No link set for: {name}', name=display_name))
            btn.setMinimumWidth(100)
            fm = QFontMetrics(btn.font())
            required_width = fm.horizontalAdvance(button_text) + 34
            btn_width = max(88, min(360, required_width))
            btn.setFixedWidth(btn_width)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
            btn.clicked.connect(lambda _=False, p=item: self.part_clicked(p))
            row_layout.addWidget(btn, 0)

            raw_code = (item.get('code', '') or '').strip()
            code_lbl = QLabel(raw_code if raw_code else '-')
            code_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            code_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            code_style_default = (
                'background: transparent;'
                'border: none;'
                'padding: 0 2px;'
                'font-size: 11pt;'
                'color: #22303c;'
                'font-weight: 400;'
                'border-bottom: 1px solid transparent;'
            )
            code_style_hover = (
                'background: transparent;'
                'border: none;'
                'padding: 0 2px;'
                'font-size: 11pt;'
                'color: #1f5f9a;'
                'font-weight: 400;'
                'border-bottom: 1px solid #1f5f9a;'
            )
            code_lbl.setStyleSheet(code_style_default)
            row_layout.addWidget(code_lbl, 1)

            if linked_spares:
                arrow_style_default = 'background: transparent; border: none; padding: 0 4px;'
                arrow_left, arrow_up = self._component_toggle_arrow_pixmaps()
                arrow_lbl = QLabel()
                arrow_lbl.setPixmap(arrow_left)
                arrow_lbl.setStyleSheet(arrow_style_default)
                arrow_lbl.setAlignment(Qt.AlignCenter)
                arrow_lbl.setFixedWidth(24)
                arrow_lbl.setCursor(Qt.PointingHandCursor)
                arrow_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
                row_layout.addWidget(arrow_lbl, 0)
                # Make the whole code area clickable to toggle spares
                code_lbl.setCursor(Qt.PointingHandCursor)

                def _set_code_hover(
                    hovered: bool,
                    label=code_lbl,
                    default_style=code_style_default,
                    hover_style=code_style_hover,
                ):
                    label.setStyleSheet(hover_style if hovered else default_style)

            list_layout.addWidget(row_card)

            if linked_spares:
                spare_host = QFrame()
                spare_host.setProperty('editorFieldGroup', True)
                spare_host_layout = QVBoxLayout(spare_host)
                spare_host_layout.setContentsMargins(12, 4, 0, 2)
                spare_host_layout.setSpacing(4)
                spare_host.setVisible(False)

                SPARE_BTN_WIDTH = 150

                for spare in linked_spares:
                    spare_row = QFrame()
                    spare_row.setProperty('editorFieldCard', True)
                    spare_row_layout = QHBoxLayout(spare_row)
                    spare_row_layout.setContentsMargins(0, 0, 0, 0)
                    spare_row_layout.setSpacing(8)

                    spare_name = (spare.get('name') or self._t('tool_library.field.part', 'Part')).strip()
                    spare_btn = QPushButton(spare_name)
                    spare_btn.setProperty('panelActionButton', True)
                    spare_btn.setProperty('componentCompact', True)
                    spare_btn.setCursor(Qt.PointingHandCursor)
                    spare_btn.setToolTip((spare.get('link') or '').strip() or self._t('tool_library.part.no_link', 'No link set for: {name}', name=spare_name))
                    spare_btn_fm = QFontMetrics(spare_btn.font())
                    spare_required_width = spare_btn_fm.horizontalAdvance(spare_name) + 48
                    spare_btn.setFixedWidth(max(110, min(360, spare_required_width)))
                    spare_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
                    spare_btn.clicked.connect(lambda _=False, p=spare: self.part_clicked(p))

                    spare_code = (spare.get('code') or '').strip()
                    spare_code_lbl = QLabel(spare_code if spare_code else '-')
                    spare_code_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    spare_code_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                    spare_code_lbl.setStyleSheet(
                        'background: transparent;'
                        'border: none;'
                        'padding: 0 2px;'
                        'font-size: 10.5pt;'
                        'color: #22303c;'
                    )

                    spare_row_layout.addWidget(spare_btn, 0)
                    spare_row_layout.addWidget(spare_code_lbl, 1)
                    spare_host_layout.addWidget(spare_row)

                def _toggle_spares(
                    _e,
                    host=spare_host,
                    arrow=arrow_lbl,
                    up=arrow_up,
                    left=arrow_left,
                    panel=frame,
                    set_hover=_set_code_hover,
                ):
                    visible = not host.isVisible()
                    host.setVisible(visible)
                    arrow.setPixmap(up if visible else left)
                    set_hover(False)
                    panel.updateGeometry()
                    panel.update()

                def _hover_enter(_e, set_hover=_set_code_hover):
                    set_hover(True)

                def _hover_leave(_e, set_hover=_set_code_hover):
                    set_hover(False)

                code_lbl.mousePressEvent = _toggle_spares
                arrow_lbl.mousePressEvent = _toggle_spares
                code_lbl.enterEvent = _hover_enter
                code_lbl.leaveEvent = _hover_leave
                arrow_lbl.enterEvent = _hover_enter
                arrow_lbl.leaveEvent = _hover_leave

                list_layout.addWidget(spare_host)

        if not normalized:
            empty_row = QFrame()
            empty_row.setProperty('editorFieldCard', True)
            empty_row_layout = QVBoxLayout(empty_row)
            empty_row_layout.setContentsMargins(0, 0, 0, 0)
            empty_row_layout.setSpacing(0)

            empty_edit = QLineEdit('-')
            empty_edit.setReadOnly(True)
            empty_edit.setFocusPolicy(Qt.NoFocus)
            empty_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            empty_row_layout.addWidget(empty_edit)
            list_layout.addWidget(empty_row)

        body_layout.addLayout(list_layout)
        layout.addWidget(body_host)
        return frame

    def _build_preview_panel(self, stl_path: str | None = None):
        frame = create_titled_section(self._t('tool_library.section.preview', 'Preview'))
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(frame)
        layout.setSpacing(10)
        layout.setContentsMargins(6, 4, 6, 6)

        diagram = QWidget()
        diagram.setObjectName('detailPreviewGradientHost')
        diagram.setAttribute(Qt.WA_StyledBackground, True)
        diagram.setStyleSheet(
            'QWidget#detailPreviewGradientHost {'
            '  background-color: #d6d9de;'
            '  border: none;'
            '  border-radius: 6px;'
            '}'
        )
        diagram.setMinimumHeight(300)
        diagram.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        dlay = QVBoxLayout(diagram)
        dlay.setContentsMargins(6, 6, 6, 6)
        dlay.setSpacing(0)

        viewer = StlPreviewWidget() if StlPreviewWidget is not None else None
        if viewer is not None:
            viewer.setStyleSheet('background: transparent; border: none;')
            viewer.set_control_hint_text(
                self._t(
                    'tool_editor.hint.rotate_pan_zoom',
                    'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
                )
            )
        loaded = self._load_preview_content(viewer, stl_path, label='Detail Preview') if viewer is not None else False
        if viewer is not None:
            viewer.setMinimumHeight(260)
            viewer.set_measurement_overlays([])
            viewer.set_measurements_visible(False)

        if loaded:
            dlay.addWidget(viewer, 1)
            viewer.show()
        else:
            txt = QLabel(
                self._t('tool_library.preview.invalid_data', 'No valid 3D model data found.')
                if stl_path else
                self._t('tool_library.preview.none_assigned', 'No 3D model assigned.')
            )
            txt.setWordWrap(True)
            txt.setAlignment(Qt.AlignCenter)
            dlay.addStretch(1)
            dlay.addWidget(txt)
            dlay.addStretch(1)

        layout.addWidget(diagram, 1)
        return frame

    # ==============================
    # Dialogs + CRUD Actions
    # ==============================
    def _show_stl_dialog(self, path: str):
        dlg = QDialog(self)
        dlg.setWindowTitle(self._t('tool_library.preview.window_title', '3D Preview'))
        layout = QVBoxLayout(dlg)
        if StlPreviewWidget is not None:
            viewer = StlPreviewWidget()
            viewer.set_control_hint_text(
                self._t(
                    'tool_editor.hint.rotate_pan_zoom',
                    'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
                )
            )
            if self._load_preview_content(viewer, path, label='3D Preview'):
                layout.addWidget(viewer)
            else:
                fallback = QLabel(
                    self._t('tool_library.preview.no_valid_for_path', 'No valid preview data found for:\n{path}', path=path)
                )
                fallback.setWordWrap(True)
                layout.addWidget(fallback)
        else:
            layout.addWidget(
                QLabel(
                    self._t(
                        'tool_library.preview.unavailable_for_path',
                        'Preview component not available for:\n{path}',
                        path=path,
                    )
                )
            )
        dlg.resize(800, 600)
        dlg.exec()

    def part_clicked(self, part):
        link = (part.get('link', '') or '').strip()
        if not link:
            QMessageBox.information(
                self,
                self._t('tool_library.part.title', 'Tool component'),
                self._t('tool_library.part.no_link', 'No link set for: {name}', name=part.get('name', self._t('tool_library.field.part', 'Part'))),
            )
            return

        url = QUrl.fromUserInput(link)
        if not url.isValid() or not url.scheme():
            QMessageBox.warning(
                self,
                self._t('tool_library.part.title', 'Tool component'),
                self._t('tool_library.part.invalid_link', 'Invalid link: {link}', link=link),
            )
            return
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(
                self,
                self._t('tool_library.part.title', 'Tool component'),
                self._t('tool_library.part.open_failed', 'Unable to open link: {link}', link=link),
            )

    def _save_from_dialog(self, dlg):
        try:
            data = dlg.get_tool_data()
            source_uid = data.get('uid')
            is_new_tool = source_uid is None

            if is_new_tool and self.tool_service.tcode_exists(data['id'], exclude_uid=data.get('uid')):
                confirm_text = (
                    self._t(
                        'tool_library.warning.duplicate_tcode',
                        'This T-code already exists, want to save the tool anyway?\n\n'
                        'This does not overwrite or replace the existing tool.',
                    )
                )
                if not self._confirm_yes_no(
                    self._t('tool_library.warning.duplicate_tcode_title', 'Duplicate T-code'),
                    confirm_text,
                    danger=False,
                ):
                    return 'retry'

            saved_uid = self.tool_service.save_tool(data, allow_duplicate=True)
            saved_tool = self.tool_service.get_tool_by_uid(saved_uid)
            self.current_tool_uid = saved_uid
            self.current_tool_id = (saved_tool or {}).get('id', data['id'])
            self.refresh_list()
            self.populate_details(saved_tool)
            if self.preview_window_btn.isChecked():
                self._sync_detached_preview(show_errors=False)
            return 'saved'
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))
            return 'error'

    def _open_tool_editor(self, tool=None):
        draft_tool = tool
        while True:
            dlg = AddEditToolDialog(self, tool=draft_tool, tool_service=self.tool_service, translate=self._t)
            if dlg.exec() != QDialog.Accepted:
                return
            result = self._save_from_dialog(dlg)
            if result == 'saved':
                return
            if result == 'retry':
                draft_tool = dlg.get_tool_data()
                draft_tool.pop('uid', None)
                continue
            return

    def add_tool(self):
        self._open_tool_editor()

    def edit_tool(self):
        selected_uids = self._selected_tool_uids()
        if not selected_uids:
            QMessageBox.information(
                self,
                self._t('tool_library.action.edit_tool_title', 'Edit tool'),
                self._t('tool_library.message.select_tool_first', 'Select a tool first.'),
            )
            return
        if len(selected_uids) > 1:
            mode = ask_multi_edit_mode(self, len(selected_uids), self._t)
            if mode == 'batch':
                self._batch_edit_tools(selected_uids)
            elif mode == 'group':
                self._group_edit_tools(selected_uids)
            return
        tool = self.tool_service.get_tool_by_uid(selected_uids[0])
        self._open_tool_editor(tool=tool)

    def apply_localization(self, translate=None):
        if translate is not None:
            self._translate = translate
        if hasattr(self, 'toolbar_title_label'):
            self.toolbar_title_label.setText(self.page_title)
        if hasattr(self, 'search'):
            self.search.setPlaceholderText(self._t('tool_library.search.placeholder', 'Tool ID, description, holder or cutting code'))
        if hasattr(self, 'detail_section_label'):
            self.detail_section_label.setText(self._t('tool_library.section.tool_details', 'Tool details'))
        if hasattr(self, 'module_switch_label'):
            self.module_switch_label.setText(self._t('tool_library.module.switch_to', 'Switch to'))
        if hasattr(self, 'copy_btn'):
            self.copy_btn.setText(self._t('tool_library.action.copy_tool', 'COPY TOOL'))
        if hasattr(self, 'edit_btn'):
            self.edit_btn.setText(self._t('tool_library.action.edit_tool', 'EDIT TOOL'))
        if hasattr(self, 'delete_btn'):
            self.delete_btn.setText(self._t('tool_library.action.delete_tool', 'DELETE TOOL'))
        if hasattr(self, 'add_btn'):
            self.add_btn.setText(self._t('tool_library.action.add_tool', 'ADD TOOL'))
        if hasattr(self, 'preview_window_btn'):
            self.preview_window_btn.setToolTip(self._t('tool_library.preview.toggle', 'Toggle detached 3D preview'))
        if hasattr(self, 'type_filter'):
            self._build_tool_type_filter_items()
        self._update_selection_count_label()
        self.refresh_list()
        if self.current_tool_id or self.current_tool_uid is not None:
            self.populate_details(self._get_selected_tool())
        else:
            self.populate_details(None)

    def copy_tool(self):
        if not self.current_tool_id:
            QMessageBox.information(
                self,
                self._t('tool_library.action.copy_tool_title', 'Copy tool'),
                self._t('tool_library.message.select_tool_first', 'Select a tool first.'),
            )
            return
        new_id, ok = self._prompt_text(
            self._t('tool_library.action.copy_tool_title', 'Copy tool'),
            self._t('tool_library.prompt.new_tool_id', 'New Tool ID:'),
        )
        if not ok or not new_id.strip():
            return
        new_id_storage = self._tool_id_storage_value(new_id)
        if not new_id_storage:
            QMessageBox.warning(
                self,
                self._t('tool_library.action.copy_tool_title', 'Copy tool'),
                self._t('tool_editor.error.tool_id_required', 'Tool ID is required.'),
            )
            return
        new_desc, _ = self._prompt_text(
            self._t('tool_library.action.copy_tool_title', 'Copy tool'),
            self._t('tool_library.prompt.new_description_optional', 'New description (optional):'),
        )
        allow_duplicate = False
        if self.tool_service.tcode_exists(new_id_storage):
            confirm_text = self._t(
                'tool_library.warning.duplicate_tcode',
                'This T-code already exists, want to save the tool anyway?\n\n'
                'This does not overwrite or replace the existing tool.',
            )
            if not self._confirm_yes_no(
                self._t('tool_library.warning.duplicate_tcode_title', 'Duplicate T-code'),
                confirm_text,
                danger=False,
            ):
                return
            allow_duplicate = True
        try:
            if self.current_tool_uid is not None:
                copied = self.tool_service.copy_tool_by_uid(
                    self.current_tool_uid,
                    new_id_storage,
                    new_desc,
                    allow_duplicate=allow_duplicate,
                )
            else:
                copied = self.tool_service.copy_tool(
                    self.current_tool_id,
                    new_id_storage,
                    new_desc,
                    allow_duplicate=allow_duplicate,
                )
            self.current_tool_uid = copied.get('uid') if isinstance(copied, dict) else None
            self.current_tool_id = (copied.get('id') if isinstance(copied, dict) else '') or new_id_storage
            self.refresh_list()
            self.populate_details(self._get_selected_tool())
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.action.copy_tool_title', 'Copy tool'), str(exc))

    def _prompt_text(self, title: str, label: str, initial: str = '') -> tuple[str, bool]:
        dlg = QDialog(self)
        setup_editor_dialog(dlg)
        dlg.setWindowTitle(title)
        dlg.setModal(True)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        prompt = QLabel(label)
        prompt.setProperty('detailFieldKey', True)
        prompt.setWordWrap(True)
        root.addWidget(prompt)

        editor = QLineEdit()
        editor.setText(initial)
        root.addWidget(editor)

        buttons = create_dialog_buttons(
            dlg,
            save_text=self._t('common.ok', 'OK'),
            cancel_text=self._t('common.cancel', 'Cancel'),
            on_save=dlg.accept,
            on_cancel=dlg.reject,
        )
        root.addWidget(buttons)

        apply_secondary_button_theme(dlg, buttons.button(QDialogButtonBox.Save))
        editor.setFocus()
        editor.selectAll()

        accepted = dlg.exec() == QDialog.Accepted
        return editor.text(), accepted

    def _confirm_yes_no(self, title: str, text: str, *, danger: bool) -> bool:
        box = QMessageBox(self)
        setup_editor_dialog(box)
        box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
        box.setWindowTitle(title)
        main_text = text
        info_text = ''
        if '\n\n' in text:
            main_text, info_text = text.split('\n\n', 1)
        box.setText(main_text)
        if info_text:
            box.setInformativeText(info_text)
            # Style only the secondary line to be subtler.
            box.setStyleSheet(
                '#qt_msgbox_informativelabel { font-style: italic; font-weight: 400; color: #5f6a74; }'
            )
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        yes_btn = box.button(QMessageBox.Yes)
        no_btn = box.button(QMessageBox.No)
        if yes_btn is not None:
            yes_btn.setText(self._t('common.yes', 'Yes'))
            yes_btn.setProperty('panelActionButton', True)
            yes_btn.setProperty('dangerAction', bool(danger))
            yes_btn.setProperty('primaryAction', not danger)
        if no_btn is not None:
            no_btn.setText(self._t('common.no', 'No'))
            no_btn.setProperty('panelActionButton', True)
            no_btn.setProperty('secondaryAction', True)

        return box.exec() == QMessageBox.Yes

    def delete_tool(self):
        if not self.current_tool_id:
            QMessageBox.information(
                self,
                self._t('tool_library.action.delete_tool_title', 'Delete tool'),
                self._t('tool_library.message.select_tool_first', 'Select a tool first.'),
            )
            return
        if self._confirm_yes_no(
            self._t('tool_library.action.delete_tool_title', 'Delete tool'),
            self._t('tool_library.prompt.delete_tool', 'Delete tool {tool_id}?', tool_id=self.current_tool_id),
            danger=True,
        ):
            if self.current_tool_uid is not None:
                self.tool_service.delete_tool_by_uid(self.current_tool_uid)
            else:
                self.tool_service.delete_tool(self.current_tool_id)
            self.current_tool_id = None
            self.current_tool_uid = None
            self.refresh_list()
            self.populate_details(None)
            if self.preview_window_btn.isChecked():
                self._close_detached_preview()

    def export_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._t('tool_library.export.title', 'Export to Excel'),
            str(EXPORT_DEFAULT_PATH),
            self._t('tool_library.export.filter_excel', 'Excel (*.xlsx)'),
        )
        if not path:
            return
        try:
            self.export_service.export_tools(path, self.tool_service.list_tools())
            QMessageBox.information(
                self,
                self._t('tool_library.export.done_title', 'Export'),
                self._t('tool_library.export.done_body', 'Exported to\n{path}', path=path),
            )
        except Exception as exc:
            QMessageBox.critical(self, self._t('tool_library.export.failed_title', 'Export failed'), str(exc))

