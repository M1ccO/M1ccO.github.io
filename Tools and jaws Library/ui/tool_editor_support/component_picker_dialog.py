"""Component picker dialog for tool component selection.

Provides an isolated, reusable dialog for browsing and selecting tool
components (holders, inserts, etc.) from existing tool library entries.
"""

from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from shared.ui.helpers.editor_helpers import apply_secondary_button_theme


class ComponentPickerDialog(QDialog):
    """Modal dialog for browsing and selecting tool components.

    Displays a searchable tree of component entries (holders, cutting inserts, etc.)
    collected from existing tools. User can search by name, code, link, or source,
    and select one to return.

    Parameters:
        title: Window title and dialog prompt.
        entries: List of component dict entries with keys: kind, name, code, link, source.
        parent: Parent widget (typically the tool editor dialog).
        translate: Translation callable(key, default, **kwargs) -> str for UI text.
    """

    def __init__(
        self,
        title: str,
        entries: list[dict],
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self._entries = entries
        self._selected_entry = None
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self._picker_syncing_widths = False
        self._picker_min_widths = [72, 110, 64]
        self._picker_name_ratio = 0.31
        self._picker_code_ratio = 0.68
        self.setWindowTitle(title)
        self.resize(560, 520)
        self.setMinimumSize(360, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            self._t('tool_editor.component.search_placeholder', 'Search by name, code, link, or source...')
        )
        self.search.textChanged.connect(self._refresh)
        root.addWidget(self.search)

        self.list_widget = QTreeWidget()
        self.list_widget.setObjectName('componentPickerTable')
        self.list_widget.setColumnCount(3)
        self.list_widget.setHeaderLabels(
            [
                self._t('tool_editor.table.part_name', 'Part name'),
                self._t('tool_editor.table.code', 'Code'),
                self._t('tool_editor.component.column_tcode', 'T-code'),
            ]
        )
        self.list_widget.setRootIsDecorated(False)
        self.list_widget.setUniformRowHeights(True)
        self.list_widget.setAlternatingRowColors(False)
        self.list_widget.setIndentation(0)
        self.list_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.list_widget.setAllColumnsShowFocus(False)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setSortingEnabled(True)
        picker_style = """
            QTreeWidget#componentPickerTable {
                background-color: #ffffff;
                border: 1px solid #d8e0e8;
                outline: none;
                selection-background-color: #cfe4f8;
                selection-color: #16334e;
                show-decoration-selected: 1;
            }
            QTreeWidget#componentPickerTable::item {
                padding: 7px 10px;
                border: none;
                border-left: none;
                border-right: none;
                border-top: none;
                border-bottom: 1px solid #d8e0e8;
                background-color: #ffffff;
                color: #25313b;
            }
            QTreeWidget#componentPickerTable::item:selected,
            QTreeWidget#componentPickerTable::item:selected:active,
            QTreeWidget#componentPickerTable::item:selected:!active {
                background-color: #cfe4f8;
                color: #16334e;
                border: none;
                border-left: none;
                border-right: none;
                border-top: none;
                border-bottom: 1px solid #d8e0e8;
            }
            QTreeWidget#componentPickerTable QHeaderView::section {
                background-color: #f3f6f8;
                border: 1px solid #d9e0e6;
                padding: 7px 8px;
                font-weight: 700;
                color: #25313b;
            }
            QTreeWidget#componentPickerTable QHeaderView::up-arrow,
            QTreeWidget#componentPickerTable QHeaderView::down-arrow {
                width: 14px;
                height: 14px;
            }
            """
        self.list_widget.setStyleSheet(picker_style)
        header = self.list_widget.header()
        header.setMinimumSectionSize(32)
        header.setStretchLastSection(False)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.sectionResized.connect(self._on_picker_header_resized)
        self.list_widget.itemDoubleClicked.connect(lambda _: self._accept_selected())
        root.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton(self._t('common.cancel', 'Cancel').upper())
        select_btn = QPushButton(self._t('tool_editor.component.select', 'SELECT'))
        cancel_btn.setProperty('panelActionButton', True)
        select_btn.setProperty('panelActionButton', True)
        select_btn.setProperty('primaryAction', True)
        cancel_btn.clicked.connect(self.reject)
        select_btn.clicked.connect(self._accept_selected)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(select_btn)
        root.addLayout(btn_row)

        # Use the same shared button theme as other editor dialogs.
        apply_secondary_button_theme(self, select_btn)

        QTimer.singleShot(0, self._set_picker_initial_widths)
        self.list_widget.sortItems(0, Qt.AscendingOrder)
        header.setSortIndicator(0, Qt.AscendingOrder)
        self._refresh()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_picker_column_widths()

    def _set_picker_initial_widths(self):
        if not hasattr(self, 'list_widget'):
            return
        self._picker_syncing_widths = True
        header = self.list_widget.header()
        header.blockSignals(True)
        try:
            self.list_widget.setColumnWidth(0, 176)
            self.list_widget.setColumnWidth(1, 230)
        finally:
            header.blockSignals(False)
            self._picker_syncing_widths = False
        self._capture_picker_column_layout()
        self._apply_picker_column_widths()

    def _capture_picker_column_layout(self):
        if not hasattr(self, 'list_widget'):
            return
        widths = [max(1, self.list_widget.columnWidth(idx)) for idx in range(self.list_widget.columnCount())]
        total = sum(widths)
        if total <= 0:
            return
        self._picker_name_ratio = widths[0] / total
        remaining = widths[1] + widths[2]
        if remaining <= 0:
            return
        self._picker_code_ratio = widths[1] / remaining

    def _apply_picker_column_widths(self):
        if not hasattr(self, 'list_widget') or self._picker_syncing_widths:
            return
        viewport_width = self.list_widget.viewport().width()
        if viewport_width <= 0:
            return

        min_name, min_code, min_tcode = self._picker_min_widths
        max_name_width = max(min_name, viewport_width - min_code - min_tcode)
        name_width = min(max_name_width, max(min_name, int(viewport_width * self._picker_name_ratio)))

        remaining = max(min_code + min_tcode, viewport_width - name_width)
        code_width = int(remaining * self._picker_code_ratio)
        code_width = max(min_code, min(code_width, remaining - min_tcode))
        tcode_width = viewport_width - name_width - code_width

        if tcode_width < min_tcode:
            tcode_width = min_tcode
            code_width = max(min_code, viewport_width - name_width - tcode_width)
            name_width = max(min_name, viewport_width - code_width - tcode_width)

        self._picker_syncing_widths = True
        header = self.list_widget.header()
        header.blockSignals(True)
        try:
            self.list_widget.setColumnWidth(0, max(min_name, name_width))
            self.list_widget.setColumnWidth(1, code_width)
            self.list_widget.setColumnWidth(2, tcode_width)
        finally:
            header.blockSignals(False)
            self._picker_syncing_widths = False

    def _on_picker_header_resized(self, _logical_index: int, _old_size: int, _new_size: int):
        if self._picker_syncing_widths:
            return
        self._capture_picker_column_layout()
        self._apply_picker_column_widths()

    def _refresh(self):
        text = self.search.text().strip().lower()
        self.list_widget.clear()
        for entry in self._entries:
            searchable = ' '.join(
                [
                    entry.get('name', ''),
                    entry.get('code', ''),
                    entry.get('link', ''),
                    entry.get('source', ''),
                ]
            ).lower()
            if text and text not in searchable:
                continue
            source = entry.get('source', '')
            item = QTreeWidgetItem(
                [
                    entry.get('name', self._t('tool_library.field.part', 'Part')),
                    entry.get('code', ''),
                    source,
                ]
            )
            item.setData(0, Qt.UserRole, entry)
            self.list_widget.addTopLevelItem(item)

        if self.list_widget.topLevelItemCount() > 0:
            self.list_widget.setCurrentItem(self.list_widget.topLevelItem(0))

    def _accept_selected(self):
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(
                self,
                self._t('tool_editor.component.select_title', 'Select component'),
                self._t('tool_editor.component.select_first', 'Select a component first.'),
            )
            return
        self._selected_entry = item.data(0, Qt.UserRole)
        self.accept()

    def selected_entry(self):
        """Return the selected component entry dict, or None if dialog was cancelled."""
        return self._selected_entry
