from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox


class PreferencesDialogBase(QDialog):
    def __init__(self, translate: Callable[[str, str | None], str], parent=None):
        super().__init__(parent)
        self._translate = translate

    def _t(self, key: str, default: str | None = None) -> str:
        return self._translate(key, default)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: str):
        target = str(value or '').strip()
        for idx in range(combo.count()):
            if str(combo.itemData(idx) or '').strip() == target:
                combo.setCurrentIndex(idx)
                return

    def _row(self, label_text: str, combo: QComboBox) -> QFrame:
        row = QFrame()
        row.setProperty('editorFieldCard', True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        label = QLabel(label_text)
        label.setProperty('detailFieldKey', True)
        label.setMinimumWidth(130)
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        combo.setMinimumWidth(220)
        combo.setFixedHeight(36)
        layout.addWidget(label)
        layout.addWidget(combo, 1)
        return row

    def _line_row(self, label_text: str, line_edit: QLineEdit) -> QFrame:
        row = QFrame()
        row.setProperty('editorFieldCard', True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        label = QLabel(label_text)
        label.setProperty('detailFieldKey', True)
        label.setMinimumWidth(130)
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        line_edit.setMinimumWidth(220)
        line_edit.setFixedHeight(36)
        layout.addWidget(label)
        layout.addWidget(line_edit, 1)
        return row

    def _path_row(self, label_text: str, line_edit: QLineEdit, browse_btn: QPushButton) -> QFrame:
        row = QFrame()
        row.setProperty('editorFieldCard', True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        label = QLabel(label_text)
        label.setProperty('detailFieldKey', True)
        label.setMinimumWidth(130)
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        line_edit.setMinimumWidth(220)
        line_edit.setFixedHeight(36)
        browse_btn.setMinimumWidth(96)
        layout.addWidget(label)
        layout.addWidget(line_edit, 1)
        layout.addWidget(browse_btn)
        return row
