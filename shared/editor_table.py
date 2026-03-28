from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QLineEdit, QStyledItemDelegate, QTableWidget, QTableWidgetItem


class _EditorTableItemDelegate(QStyledItemDelegate):
    """Make in-cell editors feel like full-height spreadsheet cells."""

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setObjectName('editorTableCellEditor')
        editor.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return editor

    def updateEditorGeometry(self, editor, option, index):
        # Keep a tiny inset while filling most of the cell area.
        editor.setGeometry(option.rect.adjusted(1, 1, -1, -1))


class EditorTable(QTableWidget):
    """Shared editable table used by Tool Library and Setup Manager dialogs."""

    def __init__(self, headers, min_rows=0, parent=None):
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self._column_keys = [str(h) for h in headers]
        self._read_only_columns = set()
        self.setItemDelegate(_EditorTableItemDelegate(self))
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setAlternatingRowColors(False)
        self.setShowGrid(True)

        # Drag/drop is intentionally disabled; row ordering is button-driven.
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.viewport().setAcceptDrops(False)
        self.setDropIndicatorShown(False)
        self.setDragDropOverwriteMode(False)
        self.setDragDropMode(QAbstractItemView.NoDragDrop)

        self.setSizeAdjustPolicy(QTableWidget.AdjustToContentsOnFirstShow)

        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsMovable(False)
        for idx in range(len(headers)):
            header.setSectionResizeMode(idx, QHeaderView.Interactive)

        self._apply_default_widths(headers)
        for _ in range(min_rows):
            self.add_empty_row()

    def set_column_keys(self, keys):
        if not isinstance(keys, (list, tuple)) or len(keys) != self.columnCount():
            raise ValueError('Column keys must match table column count.')
        self._column_keys = [str(k) for k in keys]

    def column_key(self, column: int) -> str:
        if 0 <= column < len(self._column_keys):
            return self._column_keys[column]
        return str(column)

    def column_index(self, key_or_index):
        if isinstance(key_or_index, int):
            return key_or_index
        key = str(key_or_index)
        try:
            return self._column_keys.index(key)
        except ValueError:
            return -1

    def set_read_only_columns(self, columns):
        normalized = set()
        for col in columns:
            idx = self.column_index(col)
            if 0 <= idx < self.columnCount():
                normalized.add(idx)
        self._read_only_columns = normalized

        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item is not None:
                    self._apply_item_flags(item, col)

    def _apply_default_widths(self, headers):
        for idx, header in enumerate(headers):
            header_l = header.lower()
            if 'description' in header_l:
                self.setColumnWidth(idx, 420)
            elif 'code' in header_l:
                self.setColumnWidth(idx, 260)
            elif 'name' in header_l:
                self.setColumnWidth(idx, 180)
            elif 'spindle' in header_l:
                self.setColumnWidth(idx, 110)
            elif 'b-axis' in header_l or 'variant' in header_l or 'h-code' in header_l:
                self.setColumnWidth(idx, 90)
            else:
                self.setColumnWidth(idx, 140)

    def add_empty_row(self, values=None):
        values = values or [''] * self.columnCount()
        row = self.rowCount()
        self.insertRow(row)
        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            self._apply_item_flags(item, col)
            self.setItem(row, col, item)

    def add_row_dict(self, row_data: dict):
        values = []
        for key in self._column_keys:
            values.append(str(row_data.get(key, '')))
        self.add_empty_row(values)

    def row_dict(self, row: int) -> dict:
        data = {}
        if row < 0 or row >= self.rowCount():
            return data
        for col in range(self.columnCount()):
            item = self.item(row, col)
            data[self.column_key(col)] = item.text().strip() if item else ''
        return data

    def row_dicts(self) -> list[dict]:
        return [self.row_dict(row) for row in range(self.rowCount())]

    def set_cell_text(self, row: int, column_or_key, text: str):
        col = self.column_index(column_or_key)
        if row < 0 or col < 0:
            return
        item = self.item(row, col)
        if item is None:
            item = QTableWidgetItem('')
            self._apply_item_flags(item, col)
            self.setItem(row, col, item)
        item.setText(str(text or ''))

    def cell_text(self, row: int, column_or_key) -> str:
        col = self.column_index(column_or_key)
        if row < 0 or col < 0:
            return ''
        item = self.item(row, col)
        return item.text().strip() if item else ''

    def set_cell_user_data(self, row: int, column_or_key, role: int, value):
        col = self.column_index(column_or_key)
        if row < 0 or col < 0:
            return
        item = self.item(row, col)
        if item is None:
            item = QTableWidgetItem('')
            self._apply_item_flags(item, col)
            self.setItem(row, col, item)
        item.setData(role, value)

    def cell_user_data(self, row: int, column_or_key, role: int, default=None):
        col = self.column_index(column_or_key)
        if row < 0 or col < 0:
            return default
        item = self.item(row, col)
        if item is None:
            return default
        value = item.data(role)
        return default if value is None else value

    def remove_selected_row(self):
        row = self.currentRow()
        if row >= 0:
            self.removeRow(row)

    def _apply_item_flags(self, item: QTableWidgetItem, col: int):
        flags = item.flags() | Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if col in self._read_only_columns:
            flags &= ~Qt.ItemIsEditable
        else:
            flags |= Qt.ItemIsEditable
        item.setFlags(flags)

    def _swap_rows(self, row_a: int, row_b: int):
        if row_a == row_b:
            return

        col_count = self.columnCount()
        items_a = []
        items_b = []
        widgets_a = []
        widgets_b = []

        for col in range(col_count):
            items_a.append(self.takeItem(row_a, col))
            items_b.append(self.takeItem(row_b, col))

            wa = self.cellWidget(row_a, col)
            wb = self.cellWidget(row_b, col)
            widgets_a.append(wa)
            widgets_b.append(wb)
            if wa is not None:
                self.removeCellWidget(row_a, col)
            if wb is not None:
                self.removeCellWidget(row_b, col)

        for col in range(col_count):
            if items_a[col] is not None:
                self.setItem(row_b, col, items_a[col])
            if items_b[col] is not None:
                self.setItem(row_a, col, items_b[col])

            if widgets_a[col] is not None:
                self.setCellWidget(row_b, col, widgets_a[col])
            if widgets_b[col] is not None:
                self.setCellWidget(row_a, col, widgets_b[col])

    def move_selected_row(self, delta: int):
        row = self.currentRow()
        if row < 0:
            return

        new_row = row + delta
        if new_row < 0 or new_row >= self.rowCount() or new_row == row:
            return

        focus_widget = self.focusWidget()
        if focus_widget is not None and focus_widget is not self:
            focus_widget.clearFocus()

        step = 1 if new_row > row else -1
        current = row
        while current != new_row:
            next_row = current + step
            self._swap_rows(current, next_row)
            current = next_row

        self.selectRow(new_row)
