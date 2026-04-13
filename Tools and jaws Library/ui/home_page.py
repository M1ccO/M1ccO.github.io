"""
HomePage — Tool catalog browsing page (Phase 4 refactored).

Inherits from CatalogPageBase (Phase 3 platform abstraction) for shared
catalog patterns. Implements tool-specific behavior via abstract method
overrides and signal emission.

Signals:
  item_selected(str, uid: int)  — (tool_id, uid) when user selects tool
  item_deleted(str)              — (tool_id) after deletion
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QSize, QUrl, QTimer, QModelIndex, QEvent, Signal
from PySide6.QtGui import QIcon, QDesktopServices, QFontMetrics, QStandardItemModel, QStandardItem
# import QtSvg for SVG support
import PySide6.QtSvg  # noqa: F401
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemDelegate,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import (
    ALL_TOOL_TYPES,
    TOOL_TYPE_TO_ICON,
    TOOL_ICONS_DIR,
)
from shared.ui.platforms.catalog_page_base import CatalogPageBase
from ui.tool_catalog_delegate import (
    ToolCatalogDelegate,
    ROLE_TOOL_ID,
    ROLE_TOOL_DATA,
    ROLE_TOOL_ICON,
    ROLE_TOOL_UID,
    tool_icon_for_type,
)
from ui.tool_editor_dialog import AddEditToolDialog
from ui.home_page_support.detached_preview import (
    close_detached_preview,
    sync_detached_preview as _sync_detached_preview_impl,
    toggle_preview_window,
)
from ui.selector_state_helpers import (
    default_selector_splitter_sizes,
    normalize_selector_bucket,
    normalize_selector_mode,
    selector_assignments_for_target,
    selector_bucket_map,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ['HomePage']


class HomePage(CatalogPageBase):
    """
    Tool catalog browsing page with detail panel, selector context, and batch operations.

    Inherits platform catalog logic from CatalogPageBase; provides tool-specific
    implementations of abstract methods + additional tool-specific features
    (selector, preview, detail panel, batch operations).

    **Signals** (inherited from CatalogPageBase):
      item_selected(str, int)  — (tool_id, uid) on user selection
      item_deleted(str)        — (tool_id) after deletion

    **External Listeners**:
      Other modules (Preview, Detail Panel, Selector UI) connect to signals:
      ```python
      page.item_selected.connect(on_tool_selected)
      page.item_deleted.connect(on_tool_deleted)
      ```

    **Tool-Specific Features**:
      • Detail panel toggle + population
      • Selector context for Setup Manager integration
      • Preview management (detached + inline STL)
      • Batch operations (edit, delete, copy)
      • Excel export/import
    """

    def __init__(
        self,
        tool_service,
        export_service,
        settings_service,
        parent: QWidget | None = None,
        page_title: str = 'Tool Library',
        view_mode: str = 'home',
        translate=None,
    ) -> None:
        """
        Initialize HomePage with services, tool-specific state, and UI.

        Args:
            tool_service: ToolService instance for tool queries + CRUD
            export_service: ExportService instance for Excel import/export
            settings_service: SettingsService instance for preferences
            parent: Parent widget (optional)
            page_title: Display title for the page (e.g., 'Tool Library')
            view_mode: View mode string ('home', 'inline_preview', etc.)
            translate: Translation function (key, default, **kwargs) → str

        Architecture Note:
            1. Stores services as instance attributes (used in abstract methods)
            2. Calls super().__init__() which calls _build_ui() → calls our
               create_delegate(), get_item_service(), build_filter_pane()
            3. After base init, initializes tool-specific state (selector, preview, etc.)
            4. Calls refresh_list() to load initial catalog
        """
        # Store services (used by abstract methods + tool-specific logic)
        self.tool_service = tool_service
        self.export_service = export_service
        self.settings_service = settings_service

        # Store tool-specific UI parameters
        self.page_title = str(page_title or 'Tool Library')
        self.view_mode = (view_mode or 'home').lower()

        # Initialize parent with translation function
        translate_fn = translate or (lambda k, d=None, **_: d or '')
        super().__init__(parent=parent, item_service=tool_service, translate=translate_fn)

        # Tool-specific state (selection tracking)
        self.current_tool_id: str | None = None
        self.current_tool_uid: int | None = None

        # Detail panel state
        self._details_hidden = True
        self._last_splitter_sizes = None

        # Preview state (detached window + inline warmup)
        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._close_preview_shortcut = None
        self._measurement_toggle_btn = None
        self._measurement_filter_combo = None
        self._detached_measurements_enabled = True
        self._detached_measurement_filter = None
        self._detached_preview_last_model_key = None
        self._inline_preview_warmup = None

        # Database + external state
        self._active_db_name = ''
        self._module_switch_callback = None

        # Filter state (head filter external binding)
        self._external_head_filter = None
        self._head_filter_value = 'HEAD1/2'

        # Master filter (Setup Manager context)
        self._master_filter_ids: set[str] = set()
        self._master_filter_active = False

        # Selector context state (for Setup Manager integration)
        self._selector_active = False
        self._selector_head = ''
        self._selector_spindle = ''
        self._selector_panel_mode = 'details'
        self._selector_assigned_tools: list[dict] = []
        self._selector_assignments_by_target: dict[str, list[dict]] = {}
        self._selector_saved_details_hidden = True

        # Connect base class signals to tool-specific handlers
        self.item_selected.connect(self._on_item_selected_internal)
        self.item_deleted.connect(self._on_item_deleted_internal)
        self._selection_model_connected = None
        self.tool_list = self.list_view
        self._connect_selection_model()

        # Post-UI initialization
        self._warmup_preview_engine()
        self.refresh_list()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        """Shorthand for translation function."""
        return self._translate(key, default, **kwargs)

    # ─────────────────────────────────────────────────────────────────────
    # CatalogPageBase Abstract Method Implementations
    # ─────────────────────────────────────────────────────────────────────

    def create_delegate(self) -> QAbstractItemDelegate:
        """
        Create domain-specific delegate for tool catalog item rendering.

        Inherited from CatalogPageBase contract; called during base UI setup.

        Returns:
            ToolCatalogDelegate configured for this HomePage instance.
        """
        return ToolCatalogDelegate(
            parent=self.list_view,
            view_mode=self.view_mode,
            translate=self._t,
        )

    def get_item_service(self) -> Any:
        """
        Return the item service for catalog queries.

        Inherited from CatalogPageBase contract.

        Returns:
            tool_service (ToolService instance with list_tools, get_tool, etc.)
        """
        return self.tool_service

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.textChanged.connect(self.refresh_list)

        self.filter_pane = self.build_filter_pane()
        root.addWidget(self.filter_pane)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._build_catalog_list_card())
        self.splitter.addWidget(self._build_detail_container())
        root.addWidget(self.splitter, 1)

        self._build_bottom_bars(root)

        self.detail_container.hide()
        self.detail_header_container.hide()
        self.splitter.setSizes([1, 0])

    def _build_catalog_list_card(self) -> QFrame:
        list_card = QFrame()
        list_card.setProperty('catalogShell', True)
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(10)

        self.list_view = QListView()
        self.tool_list = self.list_view
        self.list_view.setObjectName('toolCatalog')
        self.list_view.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_view.setSelectionMode(QListView.ExtendedSelection)
        self.list_view.setDragEnabled(True)
        self.list_view.setMouseTracking(True)
        self.list_view.setStyleSheet(
            'QListView#toolCatalog { border: none; outline: none; padding: 8px; }'
            ' QListView#toolCatalog::item { background: transparent; border: none; }'
        )
        self.list_view.setSpacing(4)
        self.list_view.setUniformItemSizes(True)

        self.list_view.setItemDelegate(self.create_delegate())
        self.list_view.clicked.connect(self._on_list_item_clicked)
        self.list_view.doubleClicked.connect(self.on_item_double_clicked)
        self.list_view.installEventFilter(self)
        self.list_view.viewport().installEventFilter(self)

        list_layout.addWidget(self.list_view, 1)
        return list_card

    def _build_detail_container(self) -> QWidget:
        self.detail_container = QWidget()
        self.detail_container.setMinimumWidth(280)
        detail_layout = QVBoxLayout(self.detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(0)

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
        self.detail_layout = QVBoxLayout(self.detail_panel)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(10)
        self.detail_scroll.setWidget(self.detail_panel)

        detail_card_layout.addWidget(self.detail_scroll, 1)
        detail_layout.addWidget(self.detail_card, 1)

        self.populate_details(None)
        return self.detail_container

    def _build_bottom_bars(self, root: QVBoxLayout) -> None:
        self.button_bar = QFrame()
        self.button_bar.setProperty('bottomBar', True)
        actions = QHBoxLayout(self.button_bar)
        actions.setContentsMargins(10, 8, 10, 8)
        actions.setSpacing(8)

        self.edit_btn = QPushButton(self._t('tool_library.action.edit_tool', 'EDIT TOOL'))
        self.delete_btn = QPushButton(self._t('tool_library.action.delete_tool', 'DELETE TOOL'))
        self.add_btn = QPushButton(self._t('tool_library.action.add_tool', 'ADD TOOL'))
        self.copy_btn = QPushButton(self._t('tool_library.action.copy_tool', 'COPY TOOL'))
        for btn in (self.edit_btn, self.delete_btn, self.add_btn, self.copy_btn):
            btn.setProperty('panelActionButton', True)
        self.delete_btn.setProperty('dangerAction', True)
        self.add_btn.setProperty('primaryAction', True)

        self.edit_btn.clicked.connect(self.edit_tool)
        self.delete_btn.clicked.connect(self.delete_tool)
        self.add_btn.clicked.connect(self.add_tool)
        self.copy_btn.clicked.connect(self.copy_tool)

        self.module_switch_label = QLabel(self._t('tool_library.module.switch_to', 'Switch to'))
        self.module_switch_label.setProperty('pageSubtitle', True)
        self.module_toggle_btn = QPushButton(self._t('tool_library.module.jaws', 'JAWS'))
        self.module_toggle_btn.setProperty('panelActionButton', True)
        self.module_toggle_btn.setFixedHeight(28)
        self.module_toggle_btn.clicked.connect(
            lambda: self._module_switch_callback() if callable(self._module_switch_callback) else None
        )

        actions.addWidget(self.module_switch_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        actions.addWidget(self.module_toggle_btn, 0, Qt.AlignLeft | Qt.AlignVCenter)
        actions.addStretch(1)

        self.selection_count_label = QLabel('')
        self.selection_count_label.setProperty('detailHint', True)
        self.selection_count_label.setStyleSheet('background: transparent; border: none;')
        self.selection_count_label.hide()

        actions.addWidget(self.selection_count_label, 0, Qt.AlignBottom)
        actions.addWidget(self.add_btn)
        actions.addWidget(self.edit_btn)
        actions.addWidget(self.delete_btn)
        actions.addWidget(self.copy_btn)
        root.addWidget(self.button_bar)

        self.selector_bottom_bar = QFrame()
        self.selector_bottom_bar.setProperty('bottomBar', True)
        self.selector_bottom_bar.setVisible(False)
        root.addWidget(self.selector_bottom_bar)

    def build_filter_pane(self) -> QWidget:
        """
        Build tool-specific filter UI pane containing type filter.

        Called by CatalogPageBase._build_ui() during initialization.
        Must return a QWidget with get_filters() method.

        Returns:
            QFrame with type filter dropdown and get_filters() method attached.
        """
        frame = QFrame()
        frame.setObjectName('filterFrame')
        frame.setProperty('card', True)

        self.filter_layout = QHBoxLayout(frame)
        self.filter_layout.setContentsMargins(56, 6, 0, 6)
        self.filter_layout.setSpacing(4)

        self.toolbar_title_label = QLabel(self.page_title)
        self.toolbar_title_label.setProperty('pageTitle', True)
        self.toolbar_title_label.setStyleSheet('padding-left: 0px; padding-right: 20px;')

        self.search_icon = QIcon(str(TOOL_ICONS_DIR / 'search_icon.svg'))
        self.close_icon = QIcon(str(TOOL_ICONS_DIR / 'close_icon.svg'))

        self.search_toggle = QToolButton()
        self.search_toggle.setIcon(self.search_icon)
        self.search_toggle.setIconSize(QSize(28, 28))
        self.search_toggle.setCheckable(True)
        self.search_toggle.setAutoRaise(True)
        self.search_toggle.setProperty('topBarIconButton', True)
        self.search_toggle.setFixedSize(36, 36)
        self.search_toggle.clicked.connect(self._toggle_search)

        self.search_input.setPlaceholderText(
            self._t(
                'tool_library.search.placeholder',
                'Search tool ID, name, dimensions, holder, insert, notes...',
            )
        )
        self.search_input.setVisible(False)

        self.toggle_details_btn = QToolButton()
        self.toggle_details_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / 'tooltip.svg')))
        self.toggle_details_btn.setIconSize(QSize(28, 28))
        self.toggle_details_btn.setAutoRaise(True)
        self.toggle_details_btn.setProperty('topBarIconButton', True)
        self.toggle_details_btn.setProperty('secondaryAction', True)
        self.toggle_details_btn.setFixedSize(36, 36)
        self.toggle_details_btn.clicked.connect(self.toggle_details)

        self.detail_header_container = QWidget()
        detail_top = QHBoxLayout(self.detail_header_container)
        detail_top.setContentsMargins(0, 0, 0, 0)
        detail_top.setSpacing(6)

        self.detail_section_label = QLabel(self._t('tool_library.section.tool_details', 'Tool details'))
        self.detail_section_label.setProperty('detailSectionTitle', True)
        self.detail_section_label.setStyleSheet('padding: 0 2px 0 0; font-size: 18px;')
        detail_top.addWidget(self.detail_section_label)
        detail_top.addStretch(1)

        self.detail_close_btn = QToolButton()
        self.detail_close_btn.setIcon(self.close_icon)
        self.detail_close_btn.setIconSize(QSize(20, 20))
        self.detail_close_btn.setAutoRaise(True)
        self.detail_close_btn.setProperty('topBarIconButton', True)
        self.detail_close_btn.setFixedSize(32, 32)
        self.detail_close_btn.clicked.connect(self.hide_details)
        detail_top.addWidget(self.detail_close_btn)

        self.filter_icon = QToolButton()
        self.filter_icon.setIcon(QIcon(str(TOOL_ICONS_DIR / 'filter_arrow_right.svg')))
        self.filter_icon.setIconSize(QSize(28, 28))
        self.filter_icon.setAutoRaise(True)
        self.filter_icon.setProperty('topBarIconButton', True)
        self.filter_icon.setFixedSize(36, 36)
        self.filter_icon.clicked.connect(self._clear_filters)

        self.type_filter = QComboBox()
        self.type_filter.setObjectName('topTypeFilter')
        self.type_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.type_filter.setMinimumWidth(140)
        self._build_tool_type_filter_items()
        self.type_filter.currentIndexChanged.connect(self._on_filter_changed)

        self.preview_window_btn = QToolButton()
        self.preview_window_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / '3d_icon.svg')))
        self.preview_window_btn.setIconSize(QSize(28, 28))
        self.preview_window_btn.setCheckable(True)
        self.preview_window_btn.setAutoRaise(True)
        self.preview_window_btn.setProperty('topBarIconButton', True)
        self.preview_window_btn.setToolTip(self._t('tool_library.preview.toggle', 'Toggle detached 3D preview'))
        self.preview_window_btn.setFixedSize(36, 36)
        self.preview_window_btn.clicked.connect(self.toggle_preview_window)

        self._rebuild_filter_row()

        # Attach get_filters() method to frame
        frame.get_filters = lambda: {
            'tool_head': self._selected_head_filter(),
            'tool_type': self.type_filter.currentData() or 'All',
        }

        return frame

    def _rebuild_filter_row(self) -> None:
        while self.filter_layout.count():
            item = self.filter_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        self.filter_layout.addWidget(self.search_toggle)
        self.filter_layout.addWidget(self.toggle_details_btn)
        if self.search_input.isVisible():
            self.filter_layout.addWidget(self.search_input, 1)
        self.filter_layout.addWidget(self.filter_icon)
        self.filter_layout.addWidget(self.type_filter)
        self.filter_layout.addWidget(self.preview_window_btn)
        self.filter_layout.addStretch(1)
        self.filter_layout.addWidget(self.detail_header_container)

    def _toggle_search(self) -> None:
        show = self.search_toggle.isChecked()
        self.search_input.setVisible(show)
        self.search_toggle.setIcon(self.close_icon if show else self.search_icon)
        if not show:
            self.search_input.clear()
            self.refresh_list()
        self._rebuild_filter_row()
        if show:
            QTimer.singleShot(0, self.search_input.setFocus)

    def _clear_filters(self) -> None:
        if hasattr(self, 'type_filter') and self.type_filter.count():
            self.type_filter.setCurrentIndex(0)

    def _on_filter_changed(self, _index: int) -> None:
        self.refresh_list()

    def apply_filters(self, filters: dict) -> list[dict]:
        """
        Query tool service with filters + apply domain-specific constraints.

        Inherited from CatalogPageBase contract; called by refresh_catalog().

        Args:
            filters: {
                'search': str (from search bar),
                'tool_head': str (HEAD1, HEAD2, or HEAD1/2),
                'tool_type': str (tool type name or 'All'),
            }

        Returns:
            list[dict] of tools matching all filters.
        """
        search_text = filters.get('search', '').strip()
        tool_type = filters.get('tool_type', 'All')
        tool_head = filters.get('tool_head', self._selected_head_filter())

        # Query service
        tools = self.tool_service.list_tools(
            search_text=search_text,
            tool_type=tool_type,
            tool_head=tool_head,
        )

        # Apply selector spindle constraint (if selector active)
        if self._selector_active:
            tools = [
                tool for tool in tools
                if self._tool_matches_selector_spindle(tool)
            ]

        # Apply master filter (Setup Manager context)
        if self._master_filter_active:
            tools = [
                tool for tool in tools
                if str(tool.get('id', '')).strip() in self._master_filter_ids
            ]

        # Apply view mode filter
        tools = [tool for tool in tools if self._view_match(tool)]

        # Build catalog payload expected by CatalogPageBase + delegate roles.
        catalog_items: list[dict] = []
        for tool in tools:
            item = dict(tool)
            item['id'] = str(item.get('id', '')).strip()
            try:
                item['uid'] = int(item.get('uid', 0) or 0)
            except Exception:
                item['uid'] = 0
            item['icon'] = tool_icon_for_type(str(item.get('tool_type', '') or ''))
            catalog_items.append(item)

        return catalog_items

    # ─────────────────────────────────────────────────────────────────────
    # Signal & Selection Handling (Tool-Specific)
    # ─────────────────────────────────────────────────────────────────────

    def _on_item_selected_internal(self, item_id: str, uid: int) -> None:
        """
        Internal handler for item_selected signal (from base class).

        Updates tool-specific selection state + detail panel display.

        Args:
            item_id: Tool ID
            uid: Tool UID for persistence
        """
        self.current_tool_id = item_id
        self.current_tool_uid = uid

        # Update detail panel if visible
        if not self._details_hidden:
            tool = self.tool_service.get_tool_by_uid(uid) if uid else None
            if tool is None and item_id:
                tool = self.tool_service.get_tool(item_id)
            self.populate_details(tool)

        # Update detached preview if open
        preview_btn = getattr(self, 'preview_window_btn', None)
        if preview_btn and preview_btn.isChecked():
            self._sync_detached_preview(show_errors=False)

    def _on_item_deleted_internal(self, item_id: str) -> None:
        """
        Internal handler for item_deleted signal (from base class).

        Cleans up related state (preview, detail panel, etc.).

        Args:
            item_id: Tool ID that was deleted
        """
        # Clear selection if deleted tool was current
        if self.current_tool_id == item_id:
            self.current_tool_id = None
            self.current_tool_uid = None
            self.populate_details(None)

        # Close detached preview if open
        preview_btn = getattr(self, 'preview_window_btn', None)
        if preview_btn and preview_btn.isChecked():
            close_detached_preview(self)

    def _connect_selection_model(self) -> None:
        selection_model = self.list_view.selectionModel()
        if (
            selection_model is None
            or getattr(self, '_selection_model_connected', None) is selection_model
        ):
            return
        selection_model.currentChanged.connect(self.on_current_item_changed)
        selection_model.selectionChanged.connect(self._on_multi_selection_changed)
        self._selection_model_connected = selection_model

    def _on_multi_selection_changed(self, _selected, _deselected) -> None:
        self._update_selection_count_label()

    def _update_selection_count_label(self) -> None:
        count = len(self._selected_tool_uids())
        if count > 1 and hasattr(self, 'selection_count_label'):
            self.selection_count_label.setText(
                self._t('tool_library.selection.count', '{count} selected', count=count)
            )
            self.selection_count_label.show()
            return
        if hasattr(self, 'selection_count_label'):
            self.selection_count_label.hide()

    def on_current_item_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        _ = previous
        if not current.isValid():
            self.current_tool_id = None
            self.current_tool_uid = None
            return

        tool_id = str(current.data(ROLE_TOOL_ID) or '').strip()
        uid = current.data(ROLE_TOOL_UID)
        self.current_tool_id = tool_id or None
        self.current_tool_uid = int(uid or 0) or None

        if not self._details_hidden:
            self.populate_details(self._get_selected_tool())

    def on_item_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return

        self.current_tool_id = str(index.data(ROLE_TOOL_ID) or '').strip() or None
        uid = index.data(ROLE_TOOL_UID)
        self.current_tool_uid = int(uid or 0) or None

        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.edit_tool()
            return

        if self._details_hidden:
            self.populate_details(self._get_selected_tool())
            self.show_details()
            return

        self.hide_details()

    # ─────────────────────────────────────────────────────────────────────
    # Detail Panel Display
    # ─────────────────────────────────────────────────────────────────────

    def populate_details(self, tool: dict | None) -> None:
        """
        Populate detail panel with tool data or show placeholder.

        Delegated to home_page_support.detail_panel_builder module
        (to be extracted in refactoring pass 4).

        Args:
            tool: Tool dict or None (for empty state).
        """
        from ui.home_page_support.detail_panel_builder import (
            populate_detail_panel,
        )
        populate_detail_panel(self, tool)

    def show_details(self) -> None:
        """Show detail panel."""
        if not hasattr(self, 'splitter'):
            return
        if not self._details_hidden:
            return
        self._details_hidden = False
        if not self._last_splitter_sizes:
            self._last_splitter_sizes = default_selector_splitter_sizes(
                self.splitter.width()
            )
        self.splitter.setSizes(self._last_splitter_sizes)
        self.detail_container.show()
        self.detail_header_container.show()
        self._update_row_type_visibility(False)

    def hide_details(self) -> None:
        """Hide detail panel."""
        if not hasattr(self, 'splitter'):
            return
        if self._details_hidden:
            return
        self._details_hidden = True
        self._last_splitter_sizes = self.splitter.sizes()
        self.splitter.setSizes([1, 0])
        self.detail_container.hide()
        self.detail_header_container.hide()
        self._update_row_type_visibility(True)

    def toggle_details(self) -> None:
        """Toggle detail panel visibility."""
        if self._details_hidden:
            if not self.current_tool_id:
                QMessageBox.information(
                    self,
                    self._t('tool_library.message.show_details', 'Show details'),
                    self._t(
                        'tool_library.message.select_tool_first',
                        'Select a tool first.',
                    ),
                )
                return
            tool = self._get_selected_tool()
            self.populate_details(tool)
            self.show_details()
        else:
            self.hide_details()

    def _update_row_type_visibility(self, show: bool) -> None:
        """Update list row type visibility when detail panel opens/closes."""
        if hasattr(self, 'tool_list'):
            self.tool_list.viewport().update()

    # ─────────────────────────────────────────────────────────────────────
    # Tool CRUD Operations
    # ─────────────────────────────────────────────────────────────────────

    def add_tool(self) -> None:
        """Open AddEditToolDialog in 'add' mode."""
        dlg = AddEditToolDialog(
            parent=self,
            tool=None,
            tool_service=self.tool_service,
            translate=self._t,
        )
        if dlg.exec() == QDialog.Accepted:
            self.refresh_list()

    def edit_tool(self) -> None:
        """Open AddEditToolDialog in 'edit' mode for selected tool."""
        tool = self._get_selected_tool()
        if not tool:
            QMessageBox.information(
                self,
                self._t('tool_library.message.edit_tool', 'Edit tool'),
                self._t(
                    'tool_library.message.select_tool_first',
                    'Select a tool first.',
                ),
            )
            return

        uid = tool.get('uid')
        dlg = AddEditToolDialog(
            parent=self,
            tool=tool,
            tool_service=self.tool_service,
            translate=self._t,
        )
        if dlg.exec() == QDialog.Accepted:
            self.refresh_list()
            # Re-select by UID if available
            if uid:
                self._restore_selection_by_uid(uid)

    def delete_tool(self) -> None:
        """Delete selected tool(s) with confirmation."""
        uids = self._selected_tool_uids()
        if not uids:
            QMessageBox.information(
                self,
                self._t('tool_library.message.delete_tool', 'Delete tool'),
                self._t(
                    'tool_library.message.select_tool_first',
                    'Select a tool first.',
                ),
            )
            return

        count = len(uids)
        reply = QMessageBox.question(
            self,
            self._t('tool_library.message.confirm_delete', 'Confirm Delete'),
            self._t(
                'tool_library.message.delete_count',
                'Delete {count} tool(s)?',
                count=count,
            ),
        )

        if reply != QMessageBox.Yes:
            return

        # Delete each tool (triggers item_deleted signal via apply_batch_action)
        for uid in uids:
            tool = self.tool_service.get_tool_by_uid(uid)
            if tool:
                tool_id = tool.get('id', '')
                self.tool_service.delete_tool(tool_id)
                self.item_deleted.emit(tool_id)

        self.refresh_list()

    def copy_tool(self) -> None:
        """Copy selected tool as new tool."""
        tool = self._get_selected_tool()
        if not tool:
            QMessageBox.information(
                self,
                self._t('tool_library.message.copy_tool', 'Copy tool'),
                self._t(
                    'tool_library.message.select_tool_first',
                    'Select a tool first.',
                ),
            )
            return

        tool_copy = dict(tool)
        tool_copy['id'] = ''  # Clear ID for new tool
        dlg = AddEditToolDialog(
            parent=self,
            tool=tool_copy,
            tool_service=self.tool_service,
            translate=self._t,
        )
        if dlg.exec() == QDialog.Accepted:
            self.refresh_list()

    # ─────────────────────────────────────────────────────────────────────
    # Batch Operations & Helpers
    # ─────────────────────────────────────────────────────────────────────

    def _get_selected_tool(self) -> dict | None:
        """Return currently selected tool dict or None."""
        if not self.current_tool_id:
            return None
        return self.tool_service.get_tool(self.current_tool_id)

    def _selected_tool_uids(self) -> list[int]:
        """Return list of UIDs for currently selected tools."""
        if not self.list_view.selectionModel():
            return []
        uids = []
        for idx in self.list_view.selectionModel().selectedIndexes():
            uid = idx.data(ROLE_TOOL_UID)
            if uid:
                uids.append(uid)
        return uids

    def _restore_selection_by_uid(self, uid: int) -> None:
        """Find and select tool by UID."""
        if not self._item_model:
            return
        for row in range(self._item_model.rowCount()):
            idx = self._item_model.index(row, 0)
            if idx.data(ROLE_TOOL_UID) == uid:
                self.list_view.setCurrentIndex(idx)
                self.list_view.scrollTo(idx)
                break

    def _selected_head_filter(self) -> str:
        """Return active head filter value."""
        if self._external_head_filter:
            try:
                external_value = self._external_head_filter.currentData()
            except Exception:
                external_value = None
            if external_value is not None:
                return str(external_value).strip() or 'HEAD1/2'
        return self._head_filter_value

    def _normalize_selector_tool(self, item: dict | None) -> dict | None:
        if not isinstance(item, dict):
            return None

        tool_id = str(item.get('tool_id') or item.get('id') or '').strip()
        uid_value = item.get('uid')
        try:
            uid = int(uid_value)
        except Exception:
            uid = 0

        if not tool_id and uid <= 0:
            return None

        head = str(item.get('tool_head') or item.get('head') or self._selector_head or 'HEAD1').strip().upper()
        if head not in {'HEAD1', 'HEAD2'}:
            head = 'HEAD1'

        spindle = str(item.get('spindle') or item.get('spindle_orientation') or self._selector_spindle or 'main').strip().lower()
        if spindle not in {'main', 'sub'}:
            spindle = 'main'

        normalized = dict(item)
        normalized['tool_id'] = tool_id
        normalized['id'] = tool_id
        normalized['uid'] = uid
        normalized['tool_head'] = head
        normalized['spindle'] = spindle
        normalized['spindle_orientation'] = spindle
        return normalized

    @staticmethod
    def _selector_tool_key(item: dict | None) -> str:
        if not isinstance(item, dict):
            return ''
        tool_id = str(item.get('tool_id') or item.get('id') or '').strip()
        uid = str(item.get('uid') or '').strip()
        head = str(item.get('tool_head') or item.get('head') or '').strip().upper()
        spindle = str(item.get('spindle') or item.get('spindle_orientation') or '').strip().lower()
        if tool_id:
            return f'{head}:{spindle}:{tool_id}'
        if uid:
            return f'{head}:{spindle}:uid:{uid}'
        return ''

    @staticmethod
    def _selector_target_key(head: str, spindle: str) -> str:
        normalized_head = str(head or 'HEAD1').strip().upper()
        if normalized_head not in {'HEAD1', 'HEAD2'}:
            normalized_head = 'HEAD1'
        normalized_spindle = str(spindle or 'main').strip().lower()
        if normalized_spindle not in {'main', 'sub'}:
            normalized_spindle = 'main'
        return f'{normalized_head}:{normalized_spindle}'

    def _selector_current_target_key(self) -> str:
        return self._selector_target_key(self._selector_head, self._selector_spindle)

    def bind_external_head_filter(self, head_filter_widget) -> None:
        """Bind shared rail head-filter control from MainWindow."""
        self._external_head_filter = head_filter_widget

    def set_head_filter_value(self, value: str, refresh: bool = True) -> None:
        """Set active head filter value and optionally refresh list."""
        normalized = str(value or 'HEAD1/2').strip().upper()
        if normalized not in {'HEAD1/2', 'HEAD1', 'HEAD2'}:
            normalized = 'HEAD1/2'

        self._head_filter_value = normalized

        if self._external_head_filter is not None:
            setter = getattr(self._external_head_filter, 'setCurrentData', None)
            if callable(setter):
                try:
                    setter(normalized, emit_signal=False)
                except TypeError:
                    setter(normalized)
                except Exception:
                    pass

        if refresh:
            self.refresh_list()

    def _view_match(self, tool: dict) -> bool:
        """Check if tool matches current view mode."""
        mode = (self.view_mode or 'home').strip().lower()
        if mode in {'home', 'tools'}:
            return True
        if mode == 'holders':
            return bool(str(tool.get('holder_code', '')).strip())
        if mode == 'inserts':
            return bool(str(tool.get('cutting_code', '')).strip())
        if mode == 'assemblies':
            return bool(tool.get('component_items') or tool.get('support_parts') or tool.get('stl_path'))
        return True

    def _tool_matches_selector_spindle(self, tool: dict) -> bool:
        """Check if tool compatible with selector spindle constraint."""
        if not self._selector_active:
            return True

        spindle = str(
            tool.get('spindle_orientation')
            or tool.get('spindle')
            or tool.get('spindle_side')
            or ''
        ).strip().lower()
        if not spindle:
            return True
        if self._selector_spindle == 'main':
            return spindle in {'main', 'both', 'all'}
        if self._selector_spindle == 'sub':
            return spindle in {'sub', 'both', 'all'}
        return True

    def selected_tools_for_setup_assignment(self) -> list[dict]:
        selected_items = self.get_selected_items()
        payload: list[dict] = []
        for item in selected_items:
            normalized = self._normalize_selector_tool(item)
            if normalized is None:
                continue
            payload.append(normalized)
        return payload

    def selector_assignment_buckets_for_setup_assignment(self) -> dict[str, list[dict]]:
        return {
            key: [dict(item) for item in items if isinstance(item, dict)]
            for key, items in self._selector_assignments_by_target.items()
        }

    def selector_current_target_for_setup_assignment(self) -> dict:
        return {
            'head': self._selector_head,
            'spindle': self._selector_spindle,
        }

    # ─────────────────────────────────────────────────────────────────────
    # Preview Management
    # ─────────────────────────────────────────────────────────────────────

    def toggle_preview_window(self) -> None:
        """Toggle detached STL preview window."""
        toggle_preview_window(self)

    def _sync_detached_preview(self, show_errors: bool = True) -> None:
        """Sync detached preview with current tool."""
        _sync_detached_preview_impl(self, show_errors=show_errors)

    def _warmup_preview_engine(self) -> None:
        """Pre-create a hidden preview widget for first detail-open."""
        from shared.ui.stl_preview import StlPreviewWidget

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

        QTimer.singleShot(10000, _drop_warmup)

    # ─────────────────────────────────────────────────────────────────────
    # Selector Context (Setup Manager Integration)
    # ─────────────────────────────────────────────────────────────────────

    def set_selector_context(
        self,
        active: bool,
        head: str = '',
        spindle: str = '',
        initial_assignments: list[dict] | None = None,
        initial_assignment_buckets: dict[str, list[dict]] | None = None,
    ) -> None:
        """
        Activate or deactivate selector mode.

        Called by Setup Manager when opening tool selector context.

        Args:
            active: Selector active flag
            head: Target HEAD ('HEAD1', 'HEAD2')
            spindle: Target spindle ('main', 'sub')
            initial_assignments: Initial tool list
            initial_assignment_buckets: Persisted tool buckets by head/spindle
        """
        self._selector_active = bool(active)
        self._selector_head = str(head or 'HEAD1').strip().upper()
        if self._selector_head not in {'HEAD1', 'HEAD2'}:
            self._selector_head = 'HEAD1'

        self._selector_spindle = str(spindle or 'main').strip().lower()
        if self._selector_spindle not in {'main', 'sub'}:
            self._selector_spindle = 'main'

        self._selector_assigned_tools = normalize_selector_bucket(
            initial_assignments,
            self._normalize_selector_tool,
            self._selector_tool_key,
        )

        self._selector_assignments_by_target = selector_bucket_map(
            initial_assignment_buckets,
            self._normalize_selector_tool,
            self._selector_tool_key,
            self._selector_target_key,
        )

        target_key = self._selector_current_target_key()
        existing = selector_assignments_for_target(
            self._selector_assignments_by_target,
            target_key,
        )
        if existing:
            self._selector_assigned_tools = existing

        self._selector_assignments_by_target[target_key] = [
            dict(item)
            for item in self._selector_assigned_tools
            if isinstance(item, dict)
        ]

        if hasattr(self, 'selector_bottom_bar') and hasattr(self, 'button_bar'):
            self.selector_bottom_bar.setVisible(self._selector_active)
            self.button_bar.setVisible(not self._selector_active)

        self.refresh_list()

    def selector_assigned_tools_for_setup_assignment(self) -> list[dict]:
        """Return persisted tools with head/spindle metadata for setup assignment."""
        target_key = self._selector_current_target_key()
        if self._selector_active:
            self._selector_assignments_by_target[target_key] = [
                dict(item)
                for item in self._selector_assigned_tools
                if isinstance(item, dict)
            ]

        persisted = selector_assignments_for_target(
            self._selector_assignments_by_target,
            target_key,
        )
        return persisted if persisted else self.selected_tools_for_setup_assignment()

    def set_module_switch_handler(self, callback) -> None:
        """Set external callback for module switch button."""
        self._module_switch_callback = callback

    def set_page_title(self, title: str) -> None:
        """Update page title label."""
        self.page_title = str(title or '')
        if hasattr(self, 'toolbar_title_label'):
            self.toolbar_title_label.setText(self.page_title)

    def set_active_database_name(self, db_name: str) -> None:
        """Store active database display name for status/tooltips."""
        self._active_db_name = str(db_name or '').strip()

    def set_module_switch_target(self, target: str) -> None:
        """Update module switch button target."""
        target_text = (target or '').strip().upper() or 'JAWS'
        display = (
            self._t('tool_library.module.tools', 'TOOLS')
            if target_text == 'TOOLS'
            else self._t('tool_library.module.jaws', 'JAWS')
        )
        if hasattr(self, 'module_toggle_btn'):
            self.module_toggle_btn.setText(display)
            self.module_toggle_btn.setToolTip(
                self._t(
                    'tool_library.module.switch_to_target',
                    'Switch to {target} module',
                    target=display,
                )
            )

    def set_master_filter(self, tool_ids, active: bool) -> None:
        """Set external master filter (Setup Manager context)."""
        self._master_filter_ids = {
            str(t).strip() for t in (tool_ids or []) if str(t).strip()
        }
        self._master_filter_active = bool(active) and bool(self._master_filter_ids)
        self.refresh_list()

    def refresh_list(self) -> None:
        """Refresh catalog list (synonym for refresh_catalog)."""
        self.refresh_catalog()

    def refresh_catalog(self) -> None:
        super().refresh_catalog()
        self._connect_selection_model()

    def select_tool_by_id(self, tool_id: str) -> None:
        self.current_tool_id = str(tool_id or '').strip() or None
        self.current_tool_uid = None
        self._current_item_id = self.current_tool_id
        self._current_item_uid = None
        self.refresh_list()

    def eventFilter(self, obj, event):
        event_type = event.type() if event is not None else None
        if event_type == QEvent.MouseButtonDblClick and hasattr(self, 'list_view'):
            if obj in {self.list_view, self.list_view.viewport()}:
                pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                index = self.list_view.indexAt(pos)
                if index.isValid():
                    self.on_item_double_clicked(index)
                    return True
        if event_type in {QEvent.Resize, QEvent.Show, QEvent.LayoutRequest}:
            if hasattr(obj, 'property') and bool(obj.property('elideGroupTitle')):
                self._refresh_elided_group_title(obj)
        return super().eventFilter(obj, event)

    def _refresh_elided_group_title(self, group_widget) -> None:
        if group_widget is None or not hasattr(group_widget, 'property'):
            return
        full_title = str(group_widget.property('fullGroupTitle') or group_widget.title() or '').strip()
        if not full_title:
            return
        width = max(36, int(group_widget.width()) - 18)
        metrics = QFontMetrics(group_widget.font())
        group_widget.setTitle(metrics.elidedText(full_title, Qt.ElideRight, width))

    @staticmethod
    def _tool_id_display_value(value: str) -> str:
        raw = str(value or '').strip()
        if not raw:
            return ''
        body = raw[1:] if raw.lower().startswith('t') else raw
        digits = ''.join(ch for ch in body if ch.isdigit())
        if digits:
            return f'T{digits}'
        return raw

    def _localized_tool_type(self, tool_type: str) -> str:
        key = str(tool_type or '').strip()
        if not key:
            return '-'
        return self._t(f'tool_library.type.{key.lower().replace(" ", "_")}', key)

    @staticmethod
    def _is_turning_drill_tool_type(tool_type: str) -> bool:
        normalized = str(tool_type or '').strip()
        return normalized in {'Turn Drill', 'Turn Spot Drill', 'Turn Center Drill'}

    def _load_preview_content(self, viewer, stl_path: str | None, *, label: str | None = None) -> bool:
        from ui.home_page_support.detached_preview import load_preview_content

        return load_preview_content(viewer, stl_path, label=label)

    def part_clicked(self, part: dict) -> None:
        if not isinstance(part, dict):
            return
        link = str(part.get('link') or '').strip()
        name = str(part.get('name') or part.get('label') or self._t('tool_library.field.part', 'Part')).strip()
        if not link:
            QMessageBox.information(
                self,
                self._t('tool_library.part.missing_link_title', 'Link missing'),
                self._t('tool_library.part.no_link', 'No link set for: {name}', name=name),
            )
            return
        if not QDesktopServices.openUrl(QUrl(link)):
            QMessageBox.warning(
                self,
                self._t('tool_library.part.open_failed_title', 'Open failed'),
                self._t('tool_library.part.open_failed', 'Could not open link: {link}', link=link),
            )

    def apply_localization(self, translate=None) -> None:
        if translate is not None:
            self._translate = translate

        current_tool_type = self.type_filter.currentData() if hasattr(self, 'type_filter') else 'All'
        if hasattr(self, 'type_filter'):
            self.type_filter.blockSignals(True)
            self.type_filter.clear()
            self._build_tool_type_filter_items()
            for idx in range(self.type_filter.count()):
                if self.type_filter.itemData(idx) == current_tool_type:
                    self.type_filter.setCurrentIndex(idx)
                    break
            self.type_filter.blockSignals(False)

        if hasattr(self, 'search_input'):
            self.search_input.setPlaceholderText(
                self._t(
                    'tool_library.search.placeholder',
                    'Search tool ID, name, dimensions, holder, insert, notes...',
                )
            )

        if hasattr(self, 'toolbar_title_label'):
            self.toolbar_title_label.setText(self.page_title)
        if hasattr(self, 'detail_section_label'):
            self.detail_section_label.setText(
                self._t('tool_library.section.tool_details', 'Tool details')
            )
        if hasattr(self, 'preview_window_btn'):
            self.preview_window_btn.setToolTip(
                self._t('tool_library.preview.toggle', 'Toggle detached 3D preview')
            )
        if hasattr(self, 'edit_btn'):
            self.edit_btn.setText(self._t('tool_library.action.edit_tool', 'EDIT TOOL'))
        if hasattr(self, 'delete_btn'):
            self.delete_btn.setText(self._t('tool_library.action.delete_tool', 'DELETE TOOL'))
        if hasattr(self, 'add_btn'):
            self.add_btn.setText(self._t('tool_library.action.add_tool', 'ADD TOOL'))
        if hasattr(self, 'copy_btn'):
            self.copy_btn.setText(self._t('tool_library.action.copy_tool', 'COPY TOOL'))
        if hasattr(self, 'module_switch_label'):
            self.module_switch_label.setText(self._t('tool_library.module.switch_to', 'Switch to'))
        self._rebuild_filter_row()

        self.refresh_list()

    def _build_tool_type_filter_items(self) -> None:
        """Build tool type filter dropdown items."""
        self.type_filter.addItem(
            self._t('tool_library.filter.all', 'All'),
            'All',
        )
        for tool_type in ALL_TOOL_TYPES:
            self.type_filter.addItem(
                self._localized_tool_type(tool_type),
                tool_type,
            )
