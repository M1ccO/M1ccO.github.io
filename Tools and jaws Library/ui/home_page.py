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

from PySide6.QtCore import Qt, QSize, QUrl, QTimer, QModelIndex, Signal
from PySide6.QtGui import QIcon, QDesktopServices, QStandardItemModel, QStandardItem
# import QtSvg for SVG support
import PySide6.QtSvg  # noqa: F401
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QFrame, QMessageBox,
    QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QLabel, QLineEdit,
    QPushButton,
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
)
from ui.tool_editor_dialog import AddEditToolDialog
from ui.home_page_support.detached_preview import (
    close_detached_preview,
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

        # Post-UI initialization
        self._warmup_preview_engine()
        self.refresh_list()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        """Shorthand for translation function."""
        return self._translate(key, default, **kwargs)

    # ─────────────────────────────────────────────────────────────────────
    # CatalogPageBase Abstract Method Implementations
    # ─────────────────────────────────────────────────────────────────────

    def create_delegate(self) -> QAbstractItemView:
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

    def build_filter_pane(self) -> QWidget:
        """
        Build tool-specific filter UI pane containing type filter.

        Called by CatalogPageBase._build_ui() during initialization.
        Must return a QWidget with get_filters() method.

        Returns:
            QFrame with type filter dropdown and get_filters() method attached.
        """
        frame = QFrame()
        frame.setObjectName('toolFilterPane')
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Type filter dropdown
        self.type_filter = QComboBox()
        self.type_filter.setObjectName('topTypeFilter')
        self._build_tool_type_filter_items()
        self.type_filter.currentIndexChanged.connect(self.refresh_catalog)
        layout.addWidget(self.type_filter, 0)

        layout.addStretch(1)

        # Attach get_filters() method to frame
        frame.get_filters = lambda: {
            'tool_head': self._selected_head_filter(),
            'tool_type': self.type_filter.currentData() or 'All',
        }

        return frame

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
            search=search_text,
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

        return tools

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
        if self.preview_window_btn and self.preview_window_btn.isChecked():
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
        if self.preview_window_btn and self.preview_window_btn.isChecked():
            close_detached_preview(self)

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
            return str(self._external_head_filter).strip() or 'HEAD1/2'
        return self._head_filter_value

    def _view_match(self, tool: dict) -> bool:
        """Check if tool matches current view mode."""
        # Placeholder; extend based on tool types + view mode
        return True

    def _tool_matches_selector_spindle(self, tool: dict) -> bool:
        """Check if tool compatible with selector spindle constraint."""
        if not self._selector_active:
            return True
        # Delegate to support module (selector state helpers)
        return True  # Placeholder; implement in selector logic

    # ─────────────────────────────────────────────────────────────────────
    # Preview Management
    # ─────────────────────────────────────────────────────────────────────

    def toggle_preview_window(self) -> None:
        """Toggle detached STL preview window."""
        toggle_preview_window(self)

    def _sync_detached_preview(self, show_errors: bool = True) -> None:
        """Sync detached preview with current tool."""
        if not self._detached_preview_dialog:
            return
        tool = self._get_selected_tool()
        if not tool:
            return

        stl_path = tool.get('stl_path', '')
        if not stl_path:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self._t('tool_library.preview.warning', 'Preview'),
                    self._t(
                        'tool_library.preview.no_stl',
                        'This tool has no STL model.',
                    ),
                )
            return

        from ui.home_page_support.detached_preview import (
            load_preview_content,
        )
        load_preview_content(self, stl_path)

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
        # TODO: Implement selector context setup (Phase 5+)
        pass

    def selector_assigned_tools_for_setup_assignment(self) -> list[dict]:
        """Return persisted tools with head/spindle metadata for setup assignment."""
        # TODO: Implement selector assignment retrieval (Phase 5+)
        return []

    def set_module_switch_handler(self, callback) -> None:
        """Set external callback for module switch button."""
        self._module_switch_callback = callback

    def set_page_title(self, title: str) -> None:
        """Update page title label."""
        self.page_title = str(title or '')
        if hasattr(self, 'toolbar_title_label'):
            self.toolbar_title_label.setText(self.page_title)

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

    def _build_tool_type_filter_items(self) -> None:
        """Build tool type filter dropdown items."""
        self.type_filter.addItem('All', 'All')
        for tool_type in ALL_TOOL_TYPES:
            self.type_filter.addItem(tool_type, tool_type)
