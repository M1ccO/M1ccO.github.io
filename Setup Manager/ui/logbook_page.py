from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QDate, QEvent, Qt, QSize, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QFileDialog,
    QFrame,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSizePolicy,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import ICONS_DIR, TOOL_LIBRARY_TOOL_ICONS_DIR


def _toolbar_icon(name: str) -> QIcon:
    png = ICONS_DIR / 'tools' / f'{name}.png'
    if png.exists():
        return QIcon(str(png))
    shared_png = TOOL_LIBRARY_TOOL_ICONS_DIR / f'{name}.png'
    if shared_png.exists():
        return QIcon(str(shared_png))
    svg = ICONS_DIR / 'tools' / f'{name}.svg'
    if svg.exists():
        return QIcon(str(svg))
    shared_svg = TOOL_LIBRARY_TOOL_ICONS_DIR / f'{name}.svg'
    if shared_svg.exists():
        return QIcon(str(shared_svg))
    return QIcon()


_SORT_VALUE_ROLE = Qt.UserRole + 1


class _SortableTableWidgetItem(QTableWidgetItem):
    def __init__(self, text: str, sort_value=None):
        super().__init__(text)
        self.setData(_SORT_VALUE_ROLE, text if sort_value is None else sort_value)

    def __lt__(self, other):
        if other is None:
            return False
        left_value = self.data(_SORT_VALUE_ROLE)
        right_value = other.data(_SORT_VALUE_ROLE)
        if left_value is None or right_value is None:
            return super().__lt__(other)
        try:
            return left_value < right_value
        except TypeError:
            return str(left_value) < str(right_value)


class LogbookPage(QWidget):
    logbookChanged = Signal()

    def __init__(
        self,
        logbook_service,
        work_service,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self.logbook_service = logbook_service
        self.work_service = work_service
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or "")
        self._detail_hint_text = self._t("logbook_page.detail_hint", "Select a logbook row to view details.")
        self.entries = []
        self._row_highlights = []
        self._header_highlight = None
        self._active_search_column = None
        self._column_keys = ["date", "batch_serial", "work_id", "order_number", "quantity", "notes"]

        root = QVBoxLayout(self)

        self.title = QLabel(self._t("setup_manager.nav.logbook", "Logbook"))
        self.title.setProperty("pageTitle", True)
        root.addWidget(self.title)

        self.search_icon = _toolbar_icon('search_icon')
        self.close_icon = _toolbar_icon('close_icon')
        self.search_toggle_btn = QToolButton()
        self.search_toggle_btn.setProperty('topBarIconButton', True)
        self.search_toggle_btn.setCheckable(True)
        self.search_toggle_btn.setToolTip(self._t('logbook_page.search_toggle_tip', 'Show/hide filters'))
        self.search_toggle_btn.setIcon(self.search_icon)
        self.search_toggle_btn.setIconSize(QSize(28, 28))
        self.search_toggle_btn.setFixedSize(36, 36)
        self.search_toggle_btn.setAutoRaise(True)
        self.search_toggle_btn.clicked.connect(self._toggle_filters)

        self.filters_host = QWidget()
        filters = QFormLayout()
        self.filters_host.setLayout(filters)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            self._t("logbook_page.search.placeholder", "Search work ID, order, serial, notes...")
        )
        self.search_input.textChanged.connect(self.refresh_entries)
        self.search_input.setFixedWidth(260)
        self.search_input.setVisible(False)
        filters.addRow(self._t("logbook_page.search.label", "Search"), self.search_input)
        self.filters_host.setVisible(False)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        actions.addWidget(self.search_toggle_btn)
        actions.addWidget(self.search_input)
        self.refresh_btn = QPushButton(self._t("drawing_page.action.refresh", "Refresh"))
        self.refresh_btn.setProperty("panelActionButton", True)
        self.refresh_btn.clicked.connect(self.refresh_entries)
        self.delete_btn = QPushButton(self._t("logbook_page.action.delete", "Delete"))
        self.delete_btn.setProperty("panelActionButton", True)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.export_btn = QPushButton(self._t("logbook_page.action.export_excel", "Export Excel"))
        self.export_btn.setProperty("panelActionButton", True)
        self.export_btn.clicked.connect(self.export_excel)
        self.result_count = QLabel("")
        actions.addWidget(self.refresh_btn)
        actions.addWidget(self.delete_btn)
        actions.addWidget(self.export_btn)
        actions.addStretch(1)
        actions.addWidget(self.result_count)
        root.addLayout(actions)

        splitter = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                self._t("logbook_page.col.date", "Date"),
                self._t("logbook_page.col.serial", "Serial"),
                self._t("setup_page.field.work_id", "Work ID"),
                self._t("logbook_page.col.order", "Order"),
                self._t("logbook_page.col.qty", "Qty"),
                self._t("setup_page.field.notes", "Notes"),
            ]
        )
        self.table_font = QFont(self.table.font())
        self.table_font.setPointSizeF(11.5)
        self.table.setFont(self.table_font)
        # Hide the vertical header (row numbers)
        self.table.verticalHeader().hide()
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setStyleSheet(
            "QTableWidget { selection-background-color: transparent; selection-color: black; }"
            "QTableWidget::item:selected { background-color: transparent; color: black; }"
            "QTableWidget::item:selected:active { background-color: transparent; color: black; }"
            "QTableWidget::item:selected:!active { background-color: transparent; color: black; }"
            "QHeaderView::section { padding: 6px 22px 6px 8px; }"
            "QHeaderView::up-arrow, QHeaderView::down-arrow { width: 20px; height: 20px; }"
        )
        palette = self.table.palette()
        palette.setColor(QPalette.Highlight, QColor(0, 0, 0, 0))
        palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
        self.table.setPalette(palette)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setFixedHeight(38)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.viewport().installEventFilter(self)
        self.table.horizontalHeader().viewport().installEventFilter(self)
        self.table.horizontalScrollBar().valueChanged.connect(self._update_row_highlight)
        self.table.verticalScrollBar().valueChanged.connect(self._update_row_highlight)
        self.table.horizontalScrollBar().valueChanged.connect(self._update_header_highlight)
        splitter.addWidget(self.table)

        self._header_highlight = QFrame(self.table.horizontalHeader().viewport())
        self._header_highlight.setStyleSheet("background: transparent; border: 2px solid #2fa1ee; border-radius: 6px;")
        self._header_highlight.hide()
        self._header_highlight.raise_()

        detail_host = QFrame()
        detail_host.setProperty("catalogShell", True)
        detail_layout = QVBoxLayout(detail_host)
        detail_layout.setContentsMargins(12, 12, 12, 8)
        detail_layout.setSpacing(6)

        detail_title = QLabel(self._t("logbook_page.detail.title", "Entry Details"))
        detail_title.setProperty("sectionTitle", True)
        detail_title_font = QFont(detail_title.font())
        detail_title_font.setPointSizeF(14.0)
        detail_title_font.setWeight(QFont.DemiBold)
        detail_title.setFont(detail_title_font)
        detail_layout.addWidget(detail_title)

        self.detail_card = QFrame()
        self.detail_card.setProperty("subCard", True)
        card_layout = QVBoxLayout(self.detail_card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)

        self.detail_list = QListWidget()
        self.detail_list.setObjectName("logbookDetailList")
        self.detail_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.detail_list.setFocusPolicy(Qt.NoFocus)
        self.detail_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card_layout.addWidget(self.detail_list)
        detail_layout.addWidget(self.detail_card, 1)

        splitter.addWidget(detail_host)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, 1)

        self.refresh_entries()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _toggle_filters(self):
        show = self.search_toggle_btn.isChecked()
        self.search_input.setVisible(show)
        self.search_toggle_btn.setIcon(self.close_icon if show else self.search_icon)
        if show:
            self.search_input.setFocus()
        else:
            self._active_search_column = None
            self.search_input.clear()
            self._update_header_highlight()
            self._update_search_placeholder()
            self.refresh_entries()

    def eventFilter(self, obj, event):
        if obj is self.table.viewport():
            event_type = event.type()
            if event_type == QEvent.MouseButtonPress and self.table.itemAt(event.pos()) is None:
                self.table.clearSelection()
                self.table.setCurrentCell(-1, -1)
                self._show_detail_hint()
                self._hide_row_highlights()
                return False
            # Avoid recursive highlight updates: child-frame events from highlight
            # overlays can re-enter this filter and crash native Qt.
            if event_type in (QEvent.Resize, QEvent.Show, QEvent.Hide):
                self._update_row_highlight()
        elif obj is self.table.horizontalHeader().viewport():
            if event.type() in (QEvent.Resize, QEvent.Show, QEvent.Hide):
                self._update_header_highlight()
        return super().eventFilter(obj, event)

    def _format_date(self, date_str: str) -> str:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
        except Exception:
            return date_str or ''

    def _set_detail_card_selected(self, selected: bool) -> None:
        """Apply selected-state styling to the right-side detail card."""
        self.detail_card.setProperty("selected", bool(selected))
        style = self.detail_card.style()
        style.unpolish(self.detail_card)
        style.polish(self.detail_card)

    def _show_detail_hint(self) -> None:
        """Reset the detail panel to its neutral hint state."""
        self._set_detail_message(self._detail_hint_text)
        self._set_detail_card_selected(False)

    def _update_search_placeholder(self):
        if self._active_search_column is None:
            self.search_input.setPlaceholderText(
                self._t("logbook_page.search.placeholder_full", "Search work ID, order, serial, notes, date...")
            )
            return
        header_text = self.table.horizontalHeaderItem(self._active_search_column).text()
        self.search_input.setPlaceholderText(
            self._t("logbook_page.search.placeholder_column", "Search {column}...", column=header_text.lower())
        )

    def _on_header_clicked(self, section: int):
        if not self.search_input.isVisible():
            return
        self._active_search_column = section
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self._hide_row_highlights()
        self._show_detail_hint()
        self._update_header_highlight()
        self._update_search_placeholder()
        self.refresh_entries()

    def _update_header_highlight(self):
        if self._header_highlight is None or self._active_search_column is None or not self.search_input.isVisible():
            if self._header_highlight is not None:
                self._header_highlight.hide()
            return
        header = self.table.horizontalHeader()
        left = header.sectionViewportPosition(self._active_search_column) + 1
        width = max(0, header.sectionSize(self._active_search_column) - 2)
        height = max(0, header.height() - 2)
        self._header_highlight.setGeometry(left, 1, width, height)
        self._header_highlight.show()
        self._header_highlight.raise_()

    def _entry_matches_search(self, entry: dict, search_text: str) -> bool:
        search = (search_text or '').strip().lower()
        if not search:
            return True
        formatted_values = {
            "date": self._format_date(str(entry.get("date", ""))),
            "batch_serial": str(entry.get("batch_serial", "") or ""),
            "work_id": str(entry.get("work_id", "") or ""),
            "order_number": str(entry.get("order_number", "") or ""),
            "quantity": str(entry.get("quantity", "") or ""),
            "notes": str(entry.get("notes", "") or ""),
        }
        if self._active_search_column is not None:
            key = self._column_keys[self._active_search_column]
            return search in formatted_values.get(key, '').lower()
        return any(search in value.lower() for value in formatted_values.values())

    def _hide_row_highlights(self):
        for frame in self._row_highlights:
            frame.hide()

    def _ensure_row_highlight_count(self, count: int):
        while len(self._row_highlights) < count:
            frame = QFrame(self.table.viewport())
            frame.setStyleSheet("background: transparent; border: 2px solid #2fa1ee; border-radius: 6px;")
            frame.hide()
            frame.raise_()
            self._row_highlights.append(frame)

    def _update_row_highlight(self):
        if self.table.columnCount() == 0:
            self._hide_row_highlights()
            return
        selection_model = self.table.selectionModel()
        selected_rows = selection_model.selectedRows() if selection_model is not None else []
        if not selected_rows:
            self._hide_row_highlights()
            return

        self._ensure_row_highlight_count(len(selected_rows))
        visible_count = 0
        for model_index in selected_rows:
            row = model_index.row()
            left_item = self.table.item(row, 0)
            right_item = self.table.item(row, self.table.columnCount() - 1)
            if left_item is None or right_item is None:
                continue
            left_rect = self.table.visualItemRect(left_item)
            right_rect = self.table.visualItemRect(right_item)
            if not left_rect.isValid() or not right_rect.isValid():
                continue
            left = left_rect.left() + 1
            top = left_rect.top() + 1
            width = max(0, right_rect.right() - left_rect.left() - 1)
            height = max(0, left_rect.height() - 2)
            frame = self._row_highlights[visible_count]
            frame.setGeometry(left, top, width, height)
            frame.show()
            frame.raise_()
            visible_count += 1

        for frame in self._row_highlights[visible_count:]:
            frame.hide()

    def refresh_entries(self):
        filters = {}
        all_entries = self.logbook_service.list_entries("", filters=filters)
        self.entries = [entry for entry in all_entries if self._entry_matches_search(entry, self.search_input.text())]
        self.result_count.setText(
            self._t(
                "logbook_page.result_count",
                "{count} entr{suffix}",
                count=len(self.entries),
                suffix="y" if len(self.entries) == 1 else "ies",
            )
        )

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.entries))
        for row_index, entry in enumerate(self.entries):
            date_value = entry.get("date", "")
            formatted_date = self._format_date(str(date_value or ""))
            quantity_value = entry.get("quantity", "")
            quantity_text = "" if quantity_value is None else str(quantity_value)
            try:
                quantity_sort_value = int(quantity_text)
            except Exception:
                quantity_sort_value = 0
            values = [
                formatted_date,
                "" if entry.get("batch_serial") is None else str(entry.get("batch_serial")),
                "" if entry.get("work_id") is None else str(entry.get("work_id")),
                "" if entry.get("order_number") is None else str(entry.get("order_number")),
                quantity_text,
                "" if entry.get("notes") is None else str(entry.get("notes")),
            ]
            for col_index, value in enumerate(values):
                if col_index == 0:
                    item = _SortableTableWidgetItem(value, sort_value=str(date_value or ""))
                elif col_index == 4:
                    item = _SortableTableWidgetItem(value, sort_value=quantity_sort_value)
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    item = QTableWidgetItem(value)
                item.setFont(self.table_font)
                item.setData(Qt.UserRole, entry.get("id"))
                self.table.setItem(row_index, col_index, item)

        self.table.resizeColumnsToContents()
        # Ensure minimum readable column widths
        min_widths = {0: 116, 1: 82, 2: 126, 3: 118, 4: 62, 5: 90}
        for col, mw in min_widths.items():
            if self.table.columnWidth(col) < mw:
                self.table.setColumnWidth(col, mw)
        self.table.setSortingEnabled(True)
        for row_index in range(self.table.rowCount()):
            self.table.setRowHeight(row_index, 40)
        if self.table.rowCount() > 0:
            # In column-search mode, keep rows deselected to reduce visual noise.
            if self.search_input.isVisible() and self._active_search_column is not None:
                self.table.clearSelection()
                self.table.setCurrentCell(-1, -1)
                self._hide_row_highlights()
            else:
                self.table.selectRow(0)
                self._update_row_highlight()
            self._update_header_highlight()
        else:
            self._show_detail_hint()
            self._hide_row_highlights()
            self._update_header_highlight()

    def _selected_entry(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        id_item = self.table.item(row, 0)
        if id_item is None:
            return None
        entry_id = id_item.data(Qt.UserRole)
        for entry in self.entries:
            if entry.get("id") == entry_id:
                return entry
        return None

    def _selected_entries(self):
        selection_model = self.table.selectionModel()
        if selection_model is None:
            return []
        selected_rows = selection_model.selectedRows()
        if not selected_rows:
            return []

        selected_ids = []
        for index in selected_rows:
            item = self.table.item(index.row(), 0)
            if item is None:
                continue
            entry_id = item.data(Qt.UserRole)
            if entry_id not in selected_ids:
                selected_ids.append(entry_id)

        return [entry for entry in self.entries if entry.get("id") in selected_ids]

    def _on_selection(self):
        selected_entries = self._selected_entries()
        if not selected_entries:
            self._show_detail_hint()
            self._hide_row_highlights()
            return
        if len(selected_entries) > 1:
            self._set_detail_message(
                self._t("logbook_page.message.entries_selected", "{count} entries selected", count=len(selected_entries))
            )
            self._update_row_highlight()
            self._set_detail_card_selected(True)
            return

        entry = selected_entries[0]
        # Format date as DD/MM/YYYY
        date_str = entry.get('date', '')
        formatted_date = self._format_date(date_str)
        self._set_detail_rows(
            [
                f"{self._t('setup_page.field.work_id', 'Work ID')}: {entry.get('work_id', '')}",
                f"{self._t('logbook_page.col.order', 'Order')}: {entry.get('order_number', '')}",
                f"{self._t('logbook_page.col.date', 'Date')}: {formatted_date}",
                f"{self._t('logbook_page.col.serial', 'Serial')}: {entry.get('batch_serial', '')}",
                f"{self._t('setup_page.log_entry.quantity', 'Quantity')}: {entry.get('quantity', '')}",
                f"{self._t('setup_page.field.notes', 'Notes')}: {entry.get('notes', '')}",
            ]
        )
        self._update_row_highlight()
        self._set_detail_card_selected(True)

    def _clear_detail_rows(self):
        self.detail_list.clear()

    def _set_detail_message(self, text: str):
        self._clear_detail_rows()
        self._add_detail_row(text)

    def _set_detail_rows(self, lines: list[str]):
        self._clear_detail_rows()
        cleaned = [str(line or "").strip() for line in lines]
        for line in cleaned:
            self._add_detail_row(line)

    def _add_detail_row(self, line: str):
        item = QListWidgetItem()
        item.setFlags(Qt.ItemIsEnabled)
        row = QFrame()
        row.setStyleSheet(
            "QFrame {"
            "  background: transparent;"
            "  border: none;"
            "}"
        )
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 10, 10, 12)
        row_layout.setSpacing(6)

        font = QFont(row.font())
        font.setPointSizeF(15.8)
        font.setWeight(QFont.Medium)
        value_font = QFont(font)
        value_font.setWeight(QFont.Bold)

        parts = str(line or "").split(":", 1)
        label_text = str(line or "")
        value_text = ""
        if len(parts) == 2:
            label_text = parts[0].strip() + ":"
            value_text = parts[1].strip()

        label = QLabel(label_text)
        label.setProperty("logbookDetailLabel", True)
        label.setFont(font)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        row_layout.addWidget(label)

        if value_text:
            value = QLabel(value_text)
            value.setProperty("logbookDetailValue", True)
            value.setFont(value_font)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            row_layout.addWidget(value)

        row_layout.addStretch(1)
        row.adjustSize()
        row_height = max(row.sizeHint().height(), 50)
        row.setMinimumHeight(row_height)
        item.setSizeHint(QSize(0, row_height))
        self.detail_list.addItem(item)
        self.detail_list.setItemWidget(item, row)

    def delete_selected(self):
        selected_entries = self._selected_entries()
        if not selected_entries:
            return

        if len(selected_entries) == 1:
            entry = selected_entries[0]
            prompt = self._t(
                "logbook_page.delete.single_prompt",
                "Delete logbook entry #{entry_id}?",
                entry_id=entry.get("id"),
            )
        else:
            prompt = self._t(
                "logbook_page.delete.multi_prompt",
                "Delete {count} selected logbook entries?",
                count=len(selected_entries),
            )

        answer = QMessageBox.question(
            self,
            self._t("logbook_page.delete.single_title", "Delete entry")
            if len(selected_entries) == 1
            else self._t("logbook_page.delete.multi_title", "Delete entries"),
            prompt,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        for entry in selected_entries:
            self.logbook_service.delete_entry(entry["id"])
        self.refresh_entries()
        self.logbookChanged.emit()

    def export_excel(self):
        if not self.entries:
            QMessageBox.information(
                self,
                self._t("logbook_page.export.no_data_title", "No data"),
                self._t("logbook_page.export.no_data_body", "There are no entries to export."),
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._t("logbook_page.export.dialog_title", "Export logbook"),
            str(Path.home() / "setup_logbook.xlsx"),
            self._t("logbook_page.export.filter", "Excel Files (*.xlsx)"),
        )
        if not path:
            return
        try:
            self.logbook_service.export_entries_to_excel(self.entries, path)
            QMessageBox.information(
                self,
                self._t("logbook_page.export.done_title", "Exported"),
                self._t("logbook_page.export.done_body", "Saved:\n{path}", path=path),
            )
        except Exception as exc:
            QMessageBox.critical(self, self._t("logbook_page.export.failed_title", "Export failed"), str(exc))


