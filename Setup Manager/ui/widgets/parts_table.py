from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem


class PartsTable(QTableWidget):
    def __init__(self, headers, min_rows=0, parent=None):
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
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
            self.setItem(row, col, QTableWidgetItem(str(value)))

    def remove_selected_row(self):
        row = self.currentRow()
        if row >= 0:
            self.removeRow(row)

    def _row_values(self, row):
        vals = []
        for col in range(self.columnCount()):
            item = self.item(row, col)
            vals.append(item.text() if item else '')
        return vals

    def _snapshot_rows(self):
        return [self._row_values(r) for r in range(self.rowCount())]

    def _restore_rows(self, rows):
        self.setRowCount(0)
        for values in rows:
            self.add_empty_row(values)

    def move_selected_row(self, delta: int):
        row = self.currentRow()
        if row < 0:
            return

        new_row = row + delta
        if new_row < 0 or new_row >= self.rowCount() or new_row == row:
            return

        rows = self._snapshot_rows()
        moved = rows.pop(row)
        rows.insert(new_row, moved)
        self._restore_rows(rows)
        self.selectRow(new_row)
