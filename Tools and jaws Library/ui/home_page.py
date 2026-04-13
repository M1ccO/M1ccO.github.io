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

from PySide6.QtCore import Qt, QModelIndex, QTimer
from PySide6.QtGui import QIcon
# import QtSvg for SVG support
import PySide6.QtSvg  # noqa: F401
from PySide6.QtWidgets import (
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
    sync_detached_preview as _sync_detached_preview_impl,
    toggle_preview_window,
    warmup_preview_engine as _warmup_preview_engine_impl,
)
from ui.home_page_support.selection_signal_handlers import (
    connect_selection_model as _connect_selection_model_impl,
    on_current_item_changed as _on_current_item_changed_impl,
    on_item_deleted_internal as _on_item_deleted_internal_impl,
    on_item_double_clicked as _on_item_double_clicked_impl,
    on_item_selected_internal as _on_item_selected_internal_impl,
    on_multi_selection_changed as _on_multi_selection_changed_impl,
    update_selection_count_label as _update_selection_count_label_impl,
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
from ui.home_page_support.filter_coordinator import (
    apply_filters as _apply_filters_impl,
    view_match as _view_match_impl,
)
from ui.home_page_support.runtime_actions import (
    refresh_catalog as _refresh_catalog_impl,
    refresh_list as _refresh_list_impl,
    select_tool_by_id as _select_tool_by_id_impl,
    set_active_database_name as _set_active_database_name_impl,
    set_master_filter as _set_master_filter_impl,
    set_module_switch_target as _set_module_switch_target_impl,
    set_page_title as _set_page_title_impl,
)
from ui.home_page_support.link_actions import part_clicked as _part_clicked_impl

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
        self._initial_load_done = False
        self._initial_load_scheduled = False
        self._deferred_refresh_needed = False

        # Connect base class signals to tool-specific handlers
        self.item_selected.connect(self._on_item_selected_internal)
        self.item_deleted.connect(self._on_item_deleted_internal)
        self._selection_model_connected = None
        self.tool_list = self.list_view
        self._connect_selection_model()

        # Post-UI initialization is deferred until first show to avoid blocking
        # startup while four HomePage instances are being constructed.

    def _schedule_initial_load(self) -> None:
        """Schedule first visible catalog load once per page instance."""
        if self._initial_load_done or self._initial_load_scheduled:
            return
        self._initial_load_scheduled = True
        QTimer.singleShot(0, self._perform_initial_load)

    def _perform_initial_load(self) -> None:
        """Perform first catalog load after the page becomes visible."""
        self._initial_load_scheduled = False
        if self._initial_load_done or not self.isVisible():
            return
        self._initial_load_done = True
        self._deferred_refresh_needed = False
        self.refresh_catalog()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._initial_load_done:
            self._schedule_initial_load()
            return
        if self._deferred_refresh_needed:
            self._deferred_refresh_needed = False
            QTimer.singleShot(0, self.refresh_catalog)

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
        return _apply_filters_impl(self, filters)

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
        _on_item_selected_internal_impl(self, item_id, uid)

    def _on_item_deleted_internal(self, item_id: str) -> None:
        """
        Internal handler for item_deleted signal (from base class).

        Cleans up related state (preview, detail panel, etc.).

        Args:
            item_id: Tool ID that was deleted
        """
        _on_item_deleted_internal_impl(self, item_id)

    def _connect_selection_model(self) -> None:
        _connect_selection_model_impl(self)

    def _on_multi_selection_changed(self, _selected, _deselected) -> None:
        _on_multi_selection_changed_impl(self, _selected, _deselected)

    def _update_selection_count_label(self) -> None:
        _update_selection_count_label_impl(self)

    def on_current_item_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        _on_current_item_changed_impl(self, current, previous)

    def on_item_double_clicked(self, index: QModelIndex) -> None:
        _on_item_double_clicked_impl(self, index)

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
        return _view_match_impl(self, tool)

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
        _set_page_title_impl(self, title)

    def set_active_database_name(self, db_name: str) -> None:
        """Store active database display name for status/tooltips."""
        _set_active_database_name_impl(self, db_name)

    def set_module_switch_target(self, target: str) -> None:
        """Update module switch button target."""
        _set_module_switch_target_impl(self, target)

    def set_master_filter(self, tool_ids, active: bool) -> None:
        """Set external master filter (Setup Manager context)."""
        _set_master_filter_impl(self, tool_ids, active)

    def refresh_list(self) -> None:
        """Refresh catalog list (synonym for refresh_catalog)."""
        if not self._initial_load_done and not self.isVisible():
            self._deferred_refresh_needed = True
            return
        _refresh_list_impl(self)

    def refresh_catalog(self) -> None:
        if not self._initial_load_done and not self.isVisible():
            self._deferred_refresh_needed = True
            return
        self._initial_load_done = True
        self._deferred_refresh_needed = False
        _refresh_catalog_impl(self)

    def select_tool_by_id(self, tool_id: str) -> None:
        _select_tool_by_id_impl(self, tool_id)

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
        _part_clicked_impl(self, part)

    def apply_localization(self, translate=None) -> None:
        apply_home_page_localization(self, translate)

    def _build_tool_type_filter_items(self) -> None:
        """Build tool type filter dropdown items."""
        _build_tool_type_filter_items_impl(self)
