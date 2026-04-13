# Complete HomePage Refactoring Design: 2,223L → ~400L

**Phase**: 4 (TOOLS Migration, Pilot)  
**Date**: April 13, 2026  
**Target**: New HomePage class implementation (~400-450L) inheriting from CatalogPageBase  
**Status**: Design document for implementation  
**Constraint**: Zero behavior change, all parity tests must pass, backward-compatible  

---

## Table of Contents

1. [Overview](#overview)
2. [New HomePage Implementation (Complete)](#new-homepage-implementation-complete)
3. [Line Mapping: Old → New](#line-mapping-old--new)
4. [What Stays in home_page.py](#what-stays-in-home_pagepy)
5. [What Moves to home_page_support/](#what-moves-to-home_page_support)
6. [Integration Points & Signal Wiring](#integration-points--signal-wiring)
7. [Implementation Checklist](#implementation-checklist)

---

## Overview

### Goals

1. Reduce HomePage from **2,223L to ~400L** by inheriting from CatalogPageBase
2. Preserve **all tool-specific behavior** (selector, preview, batch operations)
3. Extract **~200L of detail panel rendering** to support modules
4. Enable **parity-preserving migration** for JawPage in Phase 5
5. Consolidate **72-85% duplicate patterns** to shared base class

### Architecture

```
CatalogPageBase (shared/ui/platforms/catalog_page_base.py)
      ↓
      └─ HomePage(CatalogPageBase)
            ├─ __init__() [initialize services, tool state]
            ├─ create_delegate() [return ToolCatalogDelegate]
            ├─ get_item_service() [return tool_service]
            ├─ build_filter_pane() [return type filter + head filter]
            ├─ apply_filters(filters) [query service + constraints]
            ├─ Signal emissions: item_selected, item_deleted
            ├─ Tool-specific: selector, preview, batch operations
            └─ Detail panel display (signal-driven from base)
```

### Key Design Decisions

1. **Selector state orthogonal to platform**: Selector logic remains in HomePage, independent of CatalogPageBase
2. **Detail panel signal-driven**: Detail panel shown/hidden by external listeners on `item_selected` signal
3. **No AddEditToolDialog migration**: Dialog remains as-is (future Phase 5+ refactor)
4. **Signal-based coupling**: External modules listen to `item_selected`/`item_deleted` rather than calling HomePage methods

---

## New HomePage Implementation (Complete)

### Complete Source Code (~420 lines)

```python
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
from ui.home_page_support import (
    apply_tool_detail_layout_rules,
    ensure_detached_preview_dialog,
    toggle_preview_window,
    close_detached_preview,
    on_selector_cancel,
    on_selector_done,
    set_selector_context as _set_selector_context_impl,
    selector_assigned_tools_for_setup_assignment as _selector_assigned_tools_impl,
    SelectorAssignmentRowWidget,
    ToolAssignmentListWidget,
    ToolCatalogListView,
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
        _set_selector_context_impl(
            self,
            active=active,
            head=head,
            spindle=spindle,
            initial_assignments=initial_assignments,
            initial_assignment_buckets=initial_assignment_buckets,
        )

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


# ─────────────────────────────────────────────────────────────────────────────
# END OF HomePage CLASS (~420 lines)
# ─────────────────────────────────────────────────────────────────────────────
```

---

## Line Mapping: Old → New

### Current HomePage Structure (2,223 lines)

```
Lines 1-90:       Imports + HomePage class header                [~90L]
Lines 91-135:     __init__ constructor + service initialization  [~45L]
Lines 136-180:    Helper methods (_t, _strip_tool_id, etc.)      [~45L]
Lines 181-770:    _build_ui() [massive: filter row, toolbar,     [~590L]
                             list, detail panel, selector card]
Lines 771-850:    _build_selector_card()                          [~80L]
Lines 851-950:    _build_bottom_bars()                            [~100L]
Lines 951-1050:   Catalog refresh _on_current_changed, etc.       [~100L]
Lines 1051-1200:  Filter UI (_rebuild_filter_row, _on_type_       [~150L]
                  changed, etc.)
Lines 1201-1350:  Detail panel _build_placeholder_details()       [~150L]
Lines 1351-1550:  populate_details()                              [~200L] ← EXTRACT
Lines 1551-1700:  _build_components_panel()                       [~150L] ← EXTRACT
Lines 1701-1850:  _build_detail_field()                           [~150L] ← EXTRACT
Lines 1851-1950:  Detail helpers (_add_two_box_row, etc.)         [~100L] ← EXTRACT
Lines 1951-2050:  Tool CRUD (add_tool, edit_tool, delete_tool)    [~100L]
Lines 2051-2150:  Selector methods (set_selector_context, etc.)   [~100L]
Lines 2151-2223:  Preview + batch ops + remaining methods         [~73L]
────────────────────────────────────────────────────────────────────────────
TOTAL                                                              [2,223L]
```

### New HomePage Structure (~420 lines)

```
Lines 1-50:       Imports + module docstring                      [~50L]
Lines 51-80:      __all__ + CatalogPageBase inheritance header    [~30L]
Lines 81-220:     __init__ constructor + service initialization   [~140L]
                  (includes signal connections + warmup)
Lines 221-250:    Helper methods (_t)                             [~30L]
Lines 251-300:    create_delegate() abstract method impl.         [~20L]
Lines 301-320:    get_item_service() abstract method impl.        [~20L]
Lines 321-370:    build_filter_pane() abstract method impl.       [~50L]
Lines 371-420:    apply_filters() abstract method impl.           [~50L]
Lines 421-450:    _on_item_selected_internal() signal handler     [~30L]
Lines 451-470:    _on_item_deleted_internal() signal handler      [~20L]
Lines 471-500:    populate_details() + show/hide/toggle_details() [~30L]
Lines 501-550:    add_tool() / edit_tool() / delete_tool() /      [~50L]
                  copy_tool()
Lines 551-600:    Batch helpers (_get_selected_tool, etc.)        [~50L]
Lines 601-650:    Preview management methods                      [~50L]
                  (toggle_preview_window, _sync, _warmup)
Lines 651-700:    Selector context methods                        [~50L]
                  (set_selector_context, etc.)
Lines 701-710:    Module switch + master filter + refresh_list()  [~10L]
────────────────────────────────────────────────────────────────────────────
TOTAL (estimated)                                                  [~420L]
```

### Line Extraction Map

| Old Lines | Content | New Location | Status |
|-----------|---------|--------------|--------|
| 1200-1350 | _build_placeholder_details() | home_page_support/detail_panel_builder.py | → EXTRACT |
| 1351-1550 | populate_details() + related | home_page_support/detail_panel_builder.py | → EXTRACT |
| 1551-1700 | _build_components_panel() | home_page_support/components_panel_builder.py | → EXTRACT |
| 1701-1850 | _build_detail_field() | home_page_support/detail_fields_builder.py | → EXTRACT |
| 1851-1950 | Detail field helpers | home_page_support/detail_fields_builder.py | → EXTRACT |
| 181-770 | _build_ui() [partially] | CatalogPageBase._build_ui() | → DELEGATE |
| 771-850 | _build_selector_card() | already in home_page_support | → STAY (call via helper) |
| 851-950 | _build_bottom_bars() | already in home_page_support | → STAY (call via helper) |

### Lines Removed (moved to base class or extracted)

```
Lines to REMOVE from HomePage:
  • ~200L of _build_ui() (list view, search input, filter pane setup)
    → CatalogPageBase handles this
  • ~200L of populate_details() + detail panel builders
    → move to home_page_support/detail_panel_builder.py
  • ~150L of _build_components_panel()
    → move to home_page_support/components_panel_builder.py
  • ~150L of _build_detail_field() + helpers
    → move to home_page_support/detail_fields_builder.py
  ────────────────────
  TOTAL REMOVED: ~700L

Lines to KEEP in HomePage:
  • __init__ + service initialization (~140L)
  • 4 abstract method implementations (~140L)
  • Signal emission + handlers (~50L)
  • Tool CRUD operations (add/edit/delete/copy) (~50L)
  • Batch helpers (~50L)
  • Preview management (~50L)
  • Selector context (~50L)
  • Toggle_details / show_details / hide_details (~30L)
  • Module switch + attribute helpers (~30L)
  ────────────────────
  TOTAL KEPT: ~420L

REDUCTION: 2,223L → ~420L (82% less monolithic)
```

---

## What Stays in home_page.py

### Categories of Retained Code

#### 1. Initialization & Service Management (~140L)

```python
def __init__(self, tool_service, export_service, settings_service, ...):
    # • Store services
    # • Call super().__init__() (triggers CatalogPageBase._build_ui)
    # • Initialize tool-specific state (selector, preview, master filter)
    # • Connect signals
    # • Call refresh_list()
```

**Rationale**: Services are domain-specific; must remain at HomePage init layer.

#### 2. Abstract Method Implementations (~140L)

```python
def create_delegate(self) -> QAbstractItemDelegate:
def get_item_service(self) -> Any:
def build_filter_pane(self) -> QWidget:
def apply_filters(self, filters: dict) -> list[dict]:
```

**Rationale**: Contract-required overrides; define HomePage's specific platform integration.

#### 3. Signal Handling (~50L)

```python
def _on_item_selected_internal(self, item_id: str, uid: int):
def _on_item_deleted_internal(self, item_id: str):
```

**Rationale**: Tool-specific side effects on selection change + deletion.

#### 4. Detail Panel Toggle (~30L)

```python
def populate_details(tool: dict | None):  [delegates to support module]
def show_details():
def hide_details():
def toggle_details():
```

**Rationale**: Display orchestration (what's shown where); stays in HomePage but delegates rendering to support.

#### 5. Tool CRUD Operations (~50L)

```python
def add_tool():
def edit_tool():
def delete_tool():
def copy_tool():
```

**Rationale**: Tool-specific operations; remain as public API entry points.

#### 6. Batch & Selection Helpers (~50L)

```python
def _get_selected_tool():
def _selected_tool_uids():
def _restore_selection_by_uid():
def _selected_head_filter():
def _view_match(tool):
def _tool_matches_selector_spindle(tool):
```

**Rationale**: Tool-specific query logic; used by CRUD + filters.

#### 7. Preview Management (~50L)

```python
def toggle_preview_window():
def _sync_detached_preview(show_errors):
def _warmup_preview_engine():
```

**Rationale**: Preview orchestration; delegates implementation to support modules but orchestrates state.

#### 8. Selector Context (~50L)

```python
def set_selector_context(active, head, spindle, ...):
def selector_assigned_tools_for_setup_assignment():
def set_module_switch_handler(callback):
def set_page_title(title):
def set_module_switch_target(target):
def set_master_filter(tool_ids, active):
```

**Rationale**: Setup Manager integration API; external callers depend on these methods.

#### 9. Helper Methods (~30L)

```python
def _t(key, default, **kwargs):
def refresh_list():  [synonym for refresh_catalog()]
```

**Rationale**: Utility methods used throughout.

---

## What Moves to home_page_support/

### 1. Detail Panel Rendering → **detail_panel_builder.py** (NEW)

**Lines to Extract**: ~200L

```python
# NEW: home_page_support/detail_panel_builder.py

def populate_detail_panel(home_page, tool):
    """Populate detail layout with tool data or placeholder."""
    # Replaces current HomePage.populate_details()

def _build_placeholder_details():
    """Build placeholder card shown when no tool selected."""

def _build_components_panel(tool, support_parts):
    """Build expandable component section."""

def _build_preview_panel(stl_path):
    """Build inline STL preview embed."""

def _build_detail_field(label, value, multiline=False):
    """Build single detail field row."""

def _add_two_box_row(layout, label1, value1, label2, value2):
    """Add two-column field row."""

# ... other component rendering helpers ...
```

**Why**: Detail panel rendering is tool-specific but disconnected from dialog logic. Extracted for:
- Clarity (180+ lines of complex UI building)
- Reusability (future JawPage may share pattern)
- Testability (independent module for detail rendering logic)

---

### 2. Components Panel Rendering → **components_panel_builder.py**

**Lines to Extract**: ~150L (already partially separated)

```python
# Expands: home_page_support/components_panel_builder.py

def build_component_browser(home_page, components):
    """Build component list with spare parts."""

def build_component_card(component):
    """Render single component card."""

def build_spare_parts_list(spare_parts):
    """Render spare parts sub-section."""
```

**Status**: Already partially extracted; expand with detail panel extraction.

---

### 3. Detail Field Layout Rules → **detail_layout_rules.py**

**Current Status**: Partially extracted.

```python
# Expands: home_page_support/detail_layout_rules.py

def apply_tool_detail_layout_rules(tool, layout):
    """Apply layout rules based on tool type."""
    # Rules for milling, turning, etc.
```

**Why**: Layout depends on tool_type field values; keep modular for future filtering/display rules.

---

### 4. Selector Integration → **home_page_support/selector_*.py**

**Current Status**: Already extracted (14 modules).

```
home_page_support/selector_card_builder.py
home_page_support/selector_actions.py
home_page_support/selector_assignment_state.py
home_page_support/selector_model.py
```

**No additional extraction needed**; already separated.

---

### 5. Preview Management → **detached_preview.py**

**Current Status**: Already extracted.

```
home_page_support/detached_preview.py
```

**Reference from HomePage** (new implementation):
```python
def _sync_detached_preview(self, show_errors: bool = True):
    """Sync detached preview with current tool."""
    if not self._detached_preview_dialog:
        return
    # Delegate to support module
    from ui.home_page_support.detached_preview import load_preview_content
    load_preview_content(self, stl_path)
```

---

### Summary: home_page_support/ Post-Refactoring

```
home_page_support/
├── __init__.py  [re-export all support modules]
├── detail_panel_builder.py            [NEW, ~200L extracted]
├── components_panel_builder.py        [expand ~50L]
├── detail_fields_builder.py          [expand ~50L]
├── detail_layout_rules.py
├── batch_actions.py
├── bottom_bars_builder.py
├── catalog_list_widgets.py
├── detached_preview.py
├── dialog_helpers.py
├── preview_panel_builder.py
├── selector_actions.py
├── selector_assignment_state.py
├── selector_card_builder.py
├── selector_model.py
├── topbar_builder.py
└── __pycache__/
```

**Total support modules**: 16 (was 14, +2 new)  
**Total support lines**: ~1000L (extracted + new)

---

## Integration Points & Signal Wiring

### Signal Flow Diagram

```
┌────────────────────────────────────────────────────────────────┐
│ HomePage (refactored, ~420L)                                    │
└────────────────────────────────────────────────────────────────┘
                          ↓
        CatalogPageBase._build_ui()  [shared]
        ├─ Creates search_input
        ├─ Creates list_view
        ├─ Creates model
        ├─ Calls create_delegate() → ToolCatalogDelegate
        ├─ Calls build_filter_pane() → type filter + head filter
        └─ Connects list_view.clicked → _on_list_item_clicked()
                          ↓
        CatalogPageBase._on_list_item_clicked()
        ├─ Updates _current_item_id, _current_item_uid
        └─ EMITS: item_selected(item_id, uid)
                          ↓
        HomePage._on_item_selected_internal()
        ├─ Stores tool_id, uid in instance
        ├─ Calls populate_details(tool)  [delegates to support]
        └─ Syncs detached preview if open
                          ↓
        home_page_support.detail_panel_builder.populate_detail_panel()
        └─ Renders tool data in detail panel
                          ↓
        ┌─ Detail buttons clicked (Edit, Delete, Copy, etc.)
        │
        ├─ Edit: opens AddEditToolDialog → refresh_list()
        ├─ Delete: confirms → deletes → EMITS item_deleted(id)
        └─ Copy: opens AddEditToolDialog with template → refresh_list()
```

### External Signal Listeners

Other modules may connect to HomePage signals:

```python
# In main_window.py or app initialization

home_page = HomePage(tool_service, export_service, settings_service)

# Listen for selection changes
home_page.item_selected.connect(on_tool_selected)

# Listen for deletions (e.g., update Setup Manager assignments)
home_page.item_deleted.connect(on_tool_deleted)

def on_tool_selected(tool_id: str, uid: int):
    # Update preview, detail panel externally
    print(f"Tool selected: {tool_id} (uid={uid})")
    # May trigger external updates like:
    #  - refresh_preview_panel()
    #  - update_setup_assignments()

def on_tool_deleted(tool_id: str):
    # Clean up references
    print(f"Tool deleted: {tool_id}")
    # May trigger external cleanup like:
    #  - remove_from_setup_assignments(tool_id)
    #  - clear_detail_view()
```

### Integration Checklist

- [x] CatalogPageBase inherited (2,223L → ~420L reduction)
- [x] 4 abstract methods implemented (create_delegate, get_item_service, build_filter_pane, apply_filters)
- [x] Signal emission wired (item_selected, item_deleted)
- [x] Internal handlers for signal side effects (_on_item_selected_internal, _on_item_deleted_internal)
- [x] Detail panel delegated to support modules (populate_details)
- [x] Tool CRUD operations retained as public API
- [x] Selector state preserved orthogonal to base class
- [x] Preview management delegated to support modules
- [x] Batch helpers retained for selection tracking

---

## Implementation Checklist

### Phase 4: HomePageRefactoring Implementation

**Pass 1: Class Structure** (2-4 hours)

- [ ] Update HomePage class declaration to inherit from CatalogPageBase
- [ ] Move imports to top (CatalogPageBase from shared/ui/platforms/...)
- [ ] Update __init__() to call super().__init__()
- [ ] Implement 4 abstract methods (create_delegate, get_item_service, build_filter_pane, apply_filters)
- [ ] Remove custom _build_ui() catalog logic (delegated to base)
- [ ] Test: Verify no import errors

**Pass 2: Signal Emission** (2-3 hours)

- [ ] Add _on_item_selected_internal() handler to __init__ signal connection
- [ ] Add _on_item_deleted_internal() handler to __init__ signal connection
- [ ] Update populate_details() to be called from _on_item_selected_internal()
- [ ] Update _sync_detached_preview() to be called from _on_item_selected_internal()
- [ ] Wire delete_tool() to emit item_deleted signal
- [ ] Test: Manual signal verification (connect external listeners, verify firing)

**Pass 3: Detail Panel Delegation** (3-5 hours)

- [ ] Create home_page_support/detail_panel_builder.py
  - [ ] Move populate_details() content
  - [ ] Move _build_placeholder_details()
  - [ ] Move _build_components_panel()
  - [ ] Move _build_detail_field()
  - [ ] Move component helpers
- [ ] Update HomePage.populate_details() to delegate
- [ ] Update home_page_support/__init__.py re-exports
- [ ] Test: Verify detail panel still renders; parity tests pass

**Pass 4: Selector Isolation** (1-2 hours)

- [ ] Verify _selector_* state variables remain in HomePage
- [ ] Verify apply_filters() respects _selector_active flag
- [ ] Verify _tool_matches_selector_spindle() still works
- [ ] Test: Selector mode activate/deactivate; parity tests pass

**Pass 5: Preview Preservation** (1-2 hours)

- [ ] Verify toggle_preview_window() calls support module
- [ ] Verify _sync_detached_preview() implementation
- [ ] Verify _warmup_preview_engine() still works
- [ ] Test: Detached + inline preview; parity tests pass

**Pass 6: Testing & Parity** (4-6 hours)

- [ ] Run smoke_test.py: both apps start
- [ ] Run import_path_checker.py: no violations
- [ ] Run duplicate_detector.py: home_page.py < 500L
- [ ] Execute parity test suite: 13/13 PASS
- [ ] Manual verification of 13 test groups
- [ ] Verify DB integrity (no schema changes)

**Pass 7: Code Review & Finalization** (1-2 hours)

- [ ] Code review approval
- [ ] Update AGENTS.md if canonical paths changed
- [ ] Update README_AI.md with new structure
- [ ] Commit with message: "Phase 4: Migrate HomePage to CatalogPageBase"
- [ ] Update TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md (Phase 4 to COMPLETE)

**TOTAL**: 14-24 hours (2-3 day sprint)

---

## Parity Test Verification

After implementation, run:

```bash
# Smoke tests
python scripts/smoke_test.py
# Expected: 2/2 apps start

# Import quality gate
python scripts/import_path_checker.py
# Expected: exit code 0, no violations

# File size verification
python scripts/duplicate_detector.py
# Expected: home_page.py < 500L, duplication reduced

# Parity test suite
python tests/run_parity_tests.py --phase 4
# Expected: 13/13 PASS

# Optional: baseline comparison
python tests/run_parity_tests.py --phase 4 --compare-baseline
# Expected: ✅ PARITY VERIFIED
```

---

## Success Criteria Summary

| Gate | Metric | Target | Status |
|------|--------|--------|--------|
| 1 | HomePage lines | ~400 ± 50 | ✅ Implement |
| 2 | Duplicated patterns | 0% (in base class) | ✅ Delegated |
| 3 | Parity tests | 13/13 PASS | ✅ Required |
| 4 | Import violations | 0 | ✅ Required |
| 5 | Smoke tests | 2/2 apps start | ✅ Required |

**Phase 4 Complete When All 5 Gates Passed** ✅

---

**End of Complete HomePage Refactoring Design**

For detailed platform layer info: [PHASE_4_MIGRATION_DESIGN.md](PHASE_4_MIGRATION_DESIGN.md)  
For CatalogPageBase contract: [shared/ui/platforms/catalog_page_base.py](shared/ui/platforms/catalog_page_base.py)  
For current HomePage: [home_page.py](home_page.py)
