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

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QUrl, QModelIndex
from PySide6.QtGui import QIcon, QDesktopServices
# import QtSvg for SVG support
import PySide6.QtSvg  # noqa: F401
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemDelegate,
    QFrame,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from shared.ui.platforms.catalog_page_base import CatalogPageBase
from ui.tool_catalog_delegate import (
    ToolCatalogDelegate,
    ROLE_TOOL_ID,
    ROLE_TOOL_UID,
    tool_icon_for_type,
)
from ui.home_page_support.page_builders import (
    build_tool_page_layout,
    build_catalog_list_card as _build_catalog_list_card_impl,
    build_detail_container as _build_detail_container_impl,
    build_bottom_bars as _build_bottom_bars_impl,
)
from ui.home_page_support.topbar_builder import (
    build_tool_filter_toolbar,
    clear_filters as _clear_filters_impl,
    rebuild_filter_row as _rebuild_filter_row_impl,
    toggle_search as _toggle_search_impl,
)
from ui.home_page_support.crud_actions import (
    add_tool as _add_tool_impl,
    copy_tool as _copy_tool_impl,
    delete_tool as _delete_tool_impl,
    edit_tool as _edit_tool_impl,
)
from ui.home_page_support.topbar_filter_state import (
    bind_external_head_filter as _bind_external_head_filter_impl,
    selected_head_filter as _selected_head_filter_impl,
    set_head_filter_value as _set_head_filter_value_impl,
)
from ui.home_page_support.detail_visibility import (
    hide_tool_details,
    show_tool_details,
    toggle_tool_details,
)
from ui.home_page_support.selection_helpers import (
    get_selected_tool as _get_selected_tool_impl,
    restore_selection_by_uid as _restore_selection_by_uid_impl,
    selected_tool_uids as _selected_tool_uids_impl,
)
from ui.home_page_support.event_filter import handle_home_page_event
from ui.home_page_support.retranslate_page import (
    apply_home_page_localization,
    build_tool_type_filter_items as _build_tool_type_filter_items_impl,
    localized_tool_type as _localized_tool_type_impl,
    tool_id_display_value as _tool_id_display_value_impl,
)
from ui.home_page_support.detached_preview import (
    close_detached_preview,
    sync_detached_preview as _sync_detached_preview_impl,
    toggle_preview_window,
    warmup_preview_engine as _warmup_preview_engine_impl,
)
from ui.home_page_support.selector_context import (
    normalize_selector_tool as _normalize_selector_tool_impl,
    selector_tool_key as _selector_tool_key_impl,
    selector_target_key as _selector_target_key_impl,
    selector_current_target_key as _selector_current_target_key_impl,
    tool_matches_selector_spindle as _tool_matches_selector_spindle_impl,
    selected_tools_for_setup_assignment as _selected_tools_for_setup_assignment_impl,
    selector_assignment_buckets_for_setup_assignment as _selector_assignment_buckets_impl,
    selector_current_target_for_setup_assignment as _selector_current_target_impl,
    set_selector_context as _set_selector_context_impl,
    selector_assigned_tools_for_setup_assignment as _selector_assigned_tools_impl,
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
        machine_profile=None,
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
        self.machine_profile = machine_profile

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
        build_tool_page_layout(self)

    def _build_catalog_list_card(self) -> QFrame:
        return _build_catalog_list_card_impl(self)

    def _build_detail_container(self) -> QWidget:
        return _build_detail_container_impl(self)

    def _build_bottom_bars(self, root: QVBoxLayout) -> None:
        _build_bottom_bars_impl(self, root)

    def build_filter_pane(self) -> QWidget:
        """Build tool-specific filter toolbar. Delegated to topbar_builder module."""
        return build_tool_filter_toolbar(self)

    def _rebuild_filter_row(self) -> None:
        _rebuild_filter_row_impl(self)

    def _toggle_search(self) -> None:
        _toggle_search_impl(self)

    def _clear_filters(self) -> None:
        _clear_filters_impl(self)

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
        show_tool_details(self)

    def hide_details(self) -> None:
        """Hide detail panel."""
        hide_tool_details(self)

    def toggle_details(self) -> None:
        """Toggle detail panel visibility."""
        toggle_tool_details(self)

    # ─────────────────────────────────────────────────────────────────────
    # Tool CRUD Operations
    # ─────────────────────────────────────────────────────────────────────

    def add_tool(self) -> None:
        """Open AddEditToolDialog in 'add' mode."""
        _add_tool_impl(self)

    def edit_tool(self) -> None:
        """Open AddEditToolDialog in 'edit' mode for selected tool."""
        _edit_tool_impl(self)

    def delete_tool(self) -> None:
        """Delete selected tool(s) with confirmation."""
        _delete_tool_impl(self)

    def copy_tool(self) -> None:
        """Copy selected tool as a new tool."""
        _copy_tool_impl(self)

    # ─────────────────────────────────────────────────────────────────────
    # Batch Operations & Helpers
    # ─────────────────────────────────────────────────────────────────────

    def _get_selected_tool(self) -> dict | None:
        """Return currently selected tool dict or None."""
        return _get_selected_tool_impl(self)

    def _selected_tool_uids(self) -> list[int]:
        """Return list of UIDs for all currently selected tools."""
        return _selected_tool_uids_impl(self)

    def _restore_selection_by_uid(self, uid: int) -> None:
        """Find and re-select tool by UID after list refresh."""
        _restore_selection_by_uid_impl(self, uid)

    def _selected_head_filter(self) -> str:
        """Return active head filter value."""
        return _selected_head_filter_impl(self)

    def _normalize_selector_tool(self, item: dict | None) -> dict | None:
        return _normalize_selector_tool_impl(self, item)

    @staticmethod
    def _selector_tool_key(item: dict | None) -> str:
        return _selector_tool_key_impl(item)

    @staticmethod
    def _selector_target_key(head: str, spindle: str) -> str:
        return _selector_target_key_impl(head, spindle)

    def _selector_current_target_key(self) -> str:
        return _selector_current_target_key_impl(self)

    def bind_external_head_filter(self, head_filter_widget) -> None:
        """Bind shared rail head-filter control from MainWindow."""
        _bind_external_head_filter_impl(self, head_filter_widget)

    def set_head_filter_value(self, value: str, refresh: bool = True) -> None:
        """Set active head filter value and optionally refresh list."""
        _set_head_filter_value_impl(self, value, refresh=refresh)

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
        return _tool_matches_selector_spindle_impl(self, tool)

    def selected_tools_for_setup_assignment(self) -> list[dict]:
        return _selected_tools_for_setup_assignment_impl(self)

    def selector_assignment_buckets_for_setup_assignment(self) -> dict[str, list[dict]]:
        return _selector_assignment_buckets_impl(self)

    def selector_current_target_for_setup_assignment(self) -> dict:
        return _selector_current_target_impl(self)

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
        _warmup_preview_engine_impl(self)

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
        _set_selector_context_impl(self, active, head, spindle, initial_assignments, initial_assignment_buckets)

    def selector_assigned_tools_for_setup_assignment(self) -> list[dict]:
        """Return persisted tools with head/spindle metadata for setup assignment."""
        return _selector_assigned_tools_impl(self)

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
        if handle_home_page_event(self, obj, event):
            return True
        return super().eventFilter(obj, event)

    @staticmethod
    def _tool_id_display_value(value: str) -> str:
        return _tool_id_display_value_impl(value)

    def _localized_tool_type(self, tool_type: str) -> str:
        return _localized_tool_type_impl(self, tool_type)

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
        apply_home_page_localization(self, translate)

    def _build_tool_type_filter_items(self) -> None:
        """Build tool type filter dropdown items."""
        _build_tool_type_filter_items_impl(self)
