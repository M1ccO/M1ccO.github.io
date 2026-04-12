"""Spare parts table row management and component linking coordinator.

Isolates the responsibilities of managing spare parts rows, debounced dropdown
refresh, and component key linkage. Decouples table DOM manipulation from
dialog state management.
"""

from typing import Callable

from PySide6.QtCore import Qt, QTimer

from ui.widgets.parts_table import PartsTable


class SparePartsTableCoordinator:
    """Coordinates spare parts table row operations and dropdown refresh.

    Handles:
    - Adding/removing spare part rows with initial state
    - Getting/setting component key linkages
    - Debounced refresh of dropdown displays (via timer)

    Parameters:
        table: The spare parts PartsTable widget to manage.
        component_dropdown_values: Callable returning [(display, key), ...].
        component_display_for_key: Callable(key) -> str for fallback display.
        refresh_on_structure_change: Callable() invoked when table structure changes.
    """

    def __init__(
        self,
        *,
        table: PartsTable,
        component_dropdown_values: Callable[[], list[tuple[str, str]]],
        component_display_for_key: Callable[[str], str],
        refresh_on_structure_change: Callable[[], None] | None = None,
    ):
        self._table = table
        self._get_component_dropdown_values = component_dropdown_values
        self._get_component_display_for_key = component_display_for_key
        self._on_structure_changed = refresh_on_structure_change or (lambda: None)

        # Debounce timer for dropdown refresh (avoids rapid re-renders)
        self._refresh_timer = QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(75)
        self._refresh_timer.timeout.connect(self._refresh_spare_component_dropdowns)

    def schedule_refresh(self, *_args):
        """Request a debounced refresh of dropdown displays.

        Called whenever the component list changes or rows are added/removed.
        Multiple calls within 75ms are coalesced into one refresh.
        """
        if self._refresh_timer:
            self._refresh_timer.start()

    def _refresh_spare_component_dropdowns(self):
        """Refresh dropdown text for all spare parts rows.

        Updates the display value of each row's linked component to match
        the current options and selected component key.
        """
        options = self._get_component_dropdown_values()
        option_map = {key: display for display, key in options}

        for row in range(self._table.rowCount()):
            current_key = self.get_component_key(row)
            display = option_map.get(current_key, self._get_component_display_for_key(current_key))
            self._table.set_cell_text(row, 'linked_component', display)
            self._table.set_cell_user_data(row, 'linked_component', Qt.UserRole, current_key)

    def add_spare_part_row(self, part: dict | None = None):
        """Add a new spare parts row.

        Parameters:
            part: Dict with keys: name, code, link, component_key, group.
                  Missing keys are filled with empty strings.

        Automatically schedules dropdown refresh.
        """
        part = part or {}
        self._table.add_row_dict(
            {
                'name': (part.get('name') or '').strip(),
                'code': (part.get('code') or '').strip(),
                'link': (part.get('link') or '').strip(),
                'linked_component': '',
                'group': (part.get('group') or '').strip(),
            }
        )
        row = self._table.rowCount() - 1
        self.set_component_key(row, (part.get('component_key') or '').strip())
        self._on_structure_changed()

    def get_component_key(self, row: int) -> str:
        """Get the component reference key for a row.

        Returns empty string if row is invalid or no key is set.
        """
        if row < 0 or row >= self._table.rowCount():
            return ''
        return str(self._table.cell_user_data(row, 'linked_component', Qt.UserRole, '') or '').strip()

    def set_component_key(self, row: int, current_key: str = ''):
        """Set the component reference key for a row.

        Updates the displayed text and underlying data to the new key.
        Does not trigger refresh (caller must call `schedule_refresh()` if needed).
        """
        if row < 0 or row >= self._table.rowCount():
            return

        current_key = (current_key or '').strip()
        # Keep linked-component column as plain item data to avoid item/widget desync.
        existing_widget = self._table.cellWidget(row, 3)
        if existing_widget is not None:
            self._table.removeCellWidget(row, 3)

        display = self._get_component_display_for_key(current_key)
        self._table.set_cell_text(row, 'linked_component', display)
        self._table.set_cell_user_data(row, 'linked_component', Qt.UserRole, current_key)

    def set_component_keys_for_rows(self, rows: list[int], component_ref: str):
        """Set the same component key for multiple rows.

        Useful for bulk linking of selected rows to a single component.
        """
        for row in rows:
            self.set_component_key(row, component_ref)
        self.schedule_refresh()

    def shutdown(self):
        """Stop the refresh timer.

        Call during dialog cleanup to prevent timer callbacks after shutdown.
        """
        if self._refresh_timer:
            self._refresh_timer.stop()
