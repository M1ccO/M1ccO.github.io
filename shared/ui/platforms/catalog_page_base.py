"""
Abstract base class for catalog browsing pages (TOOLS, JAWS, and future domains).

This module provides the common infrastructure for paginated, searchable, filterable
item catalogs with batch operations support. Subclasses supply domain-specific
behavior via abstract methods.

Architectural Role:
  - Phase 3 platform abstraction (shared across TOOLS, JAWS, Fixtures, etc.)
  - Currently used in parallel with HomePage/JawPage for safe refactoring
  - Phase 4+: HomePage/JawPage will inherit from this base

Module Design:
  - Minimal concrete logic; maximum abstraction points for domains
  - Selection state persisted across refresh cycles
  - Batch operations abstracted into single apply_batch_action() hook
  - Search and filter panes owned by subclasses (via abstract methods)
  - Signals for external listeners (editors, preview panels, etc.)
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Final

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QLineEdit,
    QListView,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ['CatalogPageBase', 'CATALOG_ROLE_ID', 'CATALOG_ROLE_UID', 'CATALOG_ROLE_DATA', 'CATALOG_ROLE_ICON']

# ── Standard data roles for catalog items ────────────────────────────────────
CATALOG_ROLE_ID: Final[int] = Qt.UserRole
"""Primary identifier role (item_id string). Used for lookups and batch operations."""

CATALOG_ROLE_UID: Final[int] = Qt.UserRole + 1
"""Unique identifier role (uid int). Used for selection persistence across refresh."""

CATALOG_ROLE_DATA: Final[int] = Qt.UserRole + 2
"""Full item dict role. Contains all domain data; passed to batch operations."""

CATALOG_ROLE_ICON: Final[int] = Qt.UserRole + 3
"""Item icon role (QIcon). Delegate uses this for rendering."""


class CatalogPageBase(QWidget):
    """
    Abstract base for catalog pages supporting search, filter, selection, and batch operations.

    **Signals**:
      item_selected(str, int)
        Emitted when user clicks an item. Passes (item_id, uid).
      item_deleted(str)
        Emitted after successful deletion of an item. Passes item_id.

    **Key Abstractions**:
      1. Subclass provides domain-specific delegate via create_delegate()
      2. Subclass provides item service via get_item_service()
      3. Subclass provides filter UI via build_filter_pane()
      4. Subclass provides search/filter logic via apply_filters(filters_dict)
      5. Batch operations (delete, copy, export) routed through apply_batch_action()

    **Selection Persistence**:
      - Current selection (item_id, uid) stored in _current_item_id and _current_item_uid
      - On refresh_catalog(), selection restored by uid match or id match
      - Useful for keeping detail pane synchronized during searches

    **Usage Example**:

    .. code-block:: python

        class HomePage(CatalogPageBase):
            def create_delegate(self) -> QAbstractItemDelegate:
                return ToolCatalogDelegate()

            def get_item_service(self):
                return self.tool_service

            def build_filter_pane(self) -> QWidget:
                return ToolFilterPane(self._translate)

            def apply_filters(self, filters: dict) -> list[dict]:
                return self.get_item_service().list_tools(
                    search_text=filters.get('search', ''),
                    tool_head=filters.get('tool_head', 'HEAD1'),
                    tool_type=filters.get('tool_type', 'All'),
                )

        # Usage in a dialog or main window:
        page = HomePage(
            tool_service=my_service,
            parent=parent_widget,
            translate=my_translate_fn,
        )
        page.item_selected.connect(on_tool_selected)
        page.item_deleted.connect(on_tool_deleted)
    """

    # ── Signals ────────────────────────────────────────────────────────────
    item_selected = Signal(str, int)  # (item_id: str, uid: int)
    """Emitted when user selects an item from the list."""

    item_deleted = Signal(str)  # (item_id: str)
    """Emitted after an item deletion completes successfully."""

    # ── Constructor ────────────────────────────────────────────────────────
    def __init__(
        self,
        parent: QWidget | None = None,
        item_service: Any | None = None,
        translate: Callable[[str, str | None], str] | None = None,
    ) -> None:
        """
        Initialize catalog page base.

        Args:
            parent: Parent widget (optional).
            item_service: Domain-specific service (ToolService, JawService, etc.).
                          Typically passed to get_item_service().
            translate: Translation function (key, default, **kwargs) -> str.
                       Used for UI labels. Defaults to identity function.

        Note:
            Subclasses should call super().__init__() before any custom initialization.
            _build_ui() is called at end of this constructor.
        """
        super().__init__(parent)
        self.item_service = item_service
        self._translate = translate or (lambda k, d=None, **_: d or '')
        self._current_item_id: str | None = None
        self._current_item_uid: int | None = None
        self._item_model: QStandardItemModel | None = None
        self._build_ui()

    # ── Abstract Methods (Override in Subclass) ────────────────────────────
    @abstractmethod
    def create_delegate(self) -> QAbstractItemDelegate:
        """
        Create domain-specific delegate for item rendering.

        Returns:
            QAbstractItemDelegate: New delegate instance (never None).

        Example:
            def create_delegate(self) -> QAbstractItemDelegate:
                return ToolCatalogDelegate()
        """
        raise NotImplementedError

    @abstractmethod
    def get_item_service(self) -> Any:
        """
        Return the service instance for catalog queries.

        Returns:
            Service instance (ToolService, JawService, etc.).
            Must support: list_items(search, **filters) -> List[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def build_filter_pane(self) -> QWidget:
        """
        Create domain-specific filter UI (sidebar, toolbar section, etc.).

        Returns:
            QWidget: Filter pane with get_filters() method returning dict of
            current filter values.

        Required Interface on returned widget:
            def get_filters(self) -> dict:
                '''Return {filter_key: filter_value, ...} dict.'''
        """
        raise NotImplementedError

    @abstractmethod
    def apply_filters(self, filters: dict) -> list[dict]:
        """
        Query service with search text and domain filters; return item list.

        Args:
            filters: {
                'search': str (from search bar),
                'filter_key_1': value,
                'filter_key_2': value,
                ...
            }

        Returns:
            List[dict]: Queried items, each with required fields:
                - 'id': str (primary identifier for item_id)
                - 'uid': int (optional, for selection persistence)
                - ...other domain fields...
        """
        raise NotImplementedError

    # ── Concrete Methods ───────────────────────────────────────────────────
    def _build_ui(self) -> None:
        """
        Construct common catalog layout: filter pane + search bar + list view.

        Called automatically from __init__(). Override only if changing layout.
        """
        self.filter_pane = self.build_filter_pane()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            self._translate('catalog.search.placeholder', 'Search...')
        )
        self.search_input.textChanged.connect(self.refresh_catalog)

        self.list_view = QListView()
        self.list_view.setItemDelegate(self.create_delegate())
        self.list_view.clicked.connect(self._on_list_item_clicked)
        self.list_view.setUniformItemSizes(True)  # Performance optimization

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.filter_pane, 0)
        layout.addWidget(self.search_input, 0)
        layout.addWidget(self.list_view, 1)
        self.setLayout(layout)

    def refresh_catalog(self) -> None:
        """
        Reload items from service and refresh list view; restore selection.

        Selection Persistence:
        - If current item still exists after refresh, it stays selected
        - If current item was deleted/filtered out, first item becomes selected
        - Useful for UI synchronization and batch operation workflows
        """
        try:
            # Collect filter state from pane
            filter_state = self.filter_pane.get_filters() if hasattr(self.filter_pane, 'get_filters') else {}
            search_text = self.search_input.text().strip()

            # Query service with combined search + filters
            items = self.apply_filters({'search': search_text, **filter_state})

            # Block model signals during population
            self._item_model = QStandardItemModel()
            self._item_model.blockSignals(True)
            self._item_model.clear()

            # Populate model with items
            for item_dict in items:
                list_item = self._create_catalog_item(item_dict)
                self._item_model.appendRow(list_item)

            self._item_model.blockSignals(False)
            self.list_view.setModel(self._item_model)

            # Restore selection (by uid, then by id)
            self._restore_selection()

            # Trigger viewport update
            self.list_view.viewport().update()

        except Exception as exc:
            # Log or handle error; leave prior model in place
            raise

    def get_selected_items(self) -> list[dict]:
        """
        Return list of currently selected items (full dicts).

        Returns:
            list[dict]: Items with 'id', 'uid', and all domain fields.
            Empty list if nothing selected.
        """
        selected: list[dict] = []
        if not self._item_model:
            return selected

        for index in self.list_view.selectedIndexes():
            item_data = index.data(CATALOG_ROLE_DATA)
            if isinstance(item_data, dict):
                selected.append(item_data)

        return selected

    def _on_list_item_clicked(self, index: QModelIndex) -> None:
        """
        Handle list item click; update selection state and emit signal.

        Args:
            index: QModelIndex of clicked item.
        """
        if not index.isValid():
            return

        item_id = index.data(CATALOG_ROLE_ID)
        uid = index.data(CATALOG_ROLE_UID)

        self._current_item_id = item_id
        self._current_item_uid = uid

        self.item_selected.emit(str(item_id or ''), int(uid or 0))

    def apply_batch_action(self, action: str, items: list[dict]) -> None:
        """
        Execute batch operation on selected items (delete, copy, export, etc).

        Supported Actions:
        - 'delete': Remove items from service; emit item_deleted for each.
        - Custom actions: Subclass may override for domain-specific operations.

        Args:
            action: Action name ('delete', 'copy', 'export', etc.).
            items: List of item dicts to operate on.
        """
        if action == 'delete':
            if not items:
                QMessageBox.information(
                    self,
                    self._translate('catalog.action.delete', 'Delete'),
                    self._translate('catalog.message.select_first', 'Select items first.'),
                )
                return

            # Confirm deletion
            count = len(items)
            msg = self._translate(
                'catalog.message.confirm_delete',
                f'Delete {count} item(s)?',
            )
            box = QMessageBox(self)
            box.setWindowTitle(self._translate('catalog.action.delete', 'Delete'))
            box.setText(msg)
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)

            if box.exec() != QMessageBox.Yes:
                return

            # Execute deletions
            try:
                service = self.get_item_service()
                for item in items:
                    item_id = item.get('id') or item.get('item_id')
                    service.delete_item(item_id)
                    self.item_deleted.emit(str(item_id))

                # Refresh catalog
                self._current_item_id = None
                self._current_item_uid = None
                self.refresh_catalog()

            except Exception as exc:
                QMessageBox.critical(
                    self,
                    self._translate('catalog.error.delete_failed', 'Deletion failed'),
                    str(exc),
                )

    # ── Private Methods ────────────────────────────────────────────────────
    def _create_catalog_item(self, item_dict: dict) -> QStandardItem:
        """
        Create QStandardItem from domain dict; populate all data roles.

        Args:
            item_dict: {
                'id': str (required, primary key),
                'uid': int (optional, for selection persistence),
                'icon': QIcon (optional),
                ...other fields...
            }

        Returns:
            QStandardItem with roles populated.
        """
        item = QStandardItem()

        item_id = item_dict.get('id') or item_dict.get('item_id', '')
        uid = item_dict.get('uid', 0)
        icon = item_dict.get('icon')

        item.setData(str(item_id), CATALOG_ROLE_ID)
        item.setData(int(uid), CATALOG_ROLE_UID)
        item.setData(item_dict, CATALOG_ROLE_DATA)

        if icon:
            item.setData(icon, CATALOG_ROLE_ICON)

        item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)

        return item

    def _restore_selection(self) -> None:
        """
        Restore prior selection by uid or id match; select first item if missing.

        Strategy:
        1. If _current_item_uid is set, scan for matching uid
        2. If not found or uid not set, scan for matching id
        3. If found, set as current and scroll to it
        4. If not found, select first item
        """
        if not self._item_model or self._item_model.rowCount() == 0:
            return

        # Try uid match first
        if self._current_item_uid is not None:
            for row in range(self._item_model.rowCount()):
                idx = self._item_model.index(row, 0)
                if idx.data(CATALOG_ROLE_UID) == self._current_item_uid:
                    self.list_view.setCurrentIndex(idx)
                    self.list_view.scrollTo(idx)
                    return

        # Try id match
        if self._current_item_id is not None:
            for row in range(self._item_model.rowCount()):
                idx = self._item_model.index(row, 0)
                if idx.data(CATALOG_ROLE_ID) == self._current_item_id:
                    self.list_view.setCurrentIndex(idx)
                    self.list_view.scrollTo(idx)
                    return

        # Neither found; select first item
        first_idx = self._item_model.index(0, 0)
        if first_idx.isValid():
            self.list_view.setCurrentIndex(first_idx)
