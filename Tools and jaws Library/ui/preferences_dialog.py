from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)
from ui.widgets.common import add_shadow, apply_shared_dropdown_style


class PreferencesDialog(QDialog):
    def __init__(self, current_preferences: dict, translate: Callable[[str, str | None], str], parent=None):
        super().__init__(parent)
        self._translate = translate
        self._current = dict(current_preferences or {})

        self.setObjectName("appRoot")
        self.setWindowTitle(self._t("preferences.title", "Preferences"))
        self.setModal(True)
        self.resize(500, 280)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)
        root.addWidget(card)

        hint = QLabel(self._t("preferences.hint", "Language changes are applied after restart."))
        hint.setObjectName("preferencesHintLabel")
        hint.setWordWrap(True)
        hint.setProperty("detailHint", True)
        card_layout.addWidget(hint)

        self.language_combo = QComboBox()
        self.language_combo.addItem(self._t("language.english", "English"), "en")
        self.language_combo.addItem(self._t("language.finnish", "Finnish"), "fi")
        apply_shared_dropdown_style(self.language_combo)
        add_shadow(self.language_combo)
        card_layout.addWidget(self._row(self._t("preferences.language", "Language"), self.language_combo))

        self.theme_combo = QComboBox()
        self.theme_combo.addItem(self._t("theme.classic", "Classic"), "classic")
        self.theme_combo.addItem(self._t("theme.graphite", "Graphite"), "graphite")
        apply_shared_dropdown_style(self.theme_combo)
        add_shadow(self.theme_combo)
        card_layout.addWidget(self._row(self._t("preferences.color_theme", "Color Theme"), self.theme_combo))

        self.assembly_transform_cb = QCheckBox(self._t("preferences.enable_assembly_transform", "Enable assembly transform editing (3D Models tab)"))
        self.assembly_transform_cb.setStyleSheet("QCheckBox { background: transparent; }")
        card_layout.addWidget(self.assembly_transform_cb)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 6, 0, 0)
        buttons.setSpacing(8)
        buttons.addStretch(1)

        self.save_btn = QPushButton(self._t("common.save", "Save"))
        self.save_btn.setProperty("panelActionButton", True)
        self.save_btn.setProperty("primaryAction", True)
        self.save_btn.clicked.connect(self.accept)
        buttons.addWidget(self.save_btn)

        self.cancel_btn = QPushButton(self._t("common.cancel", "Cancel"))
        self.cancel_btn.setProperty("panelActionButton", True)
        self.cancel_btn.setProperty("secondaryAction", True)
        self.cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_btn)
        card_layout.addLayout(buttons)

        self._load_current_values()

    def preferences_payload(self) -> dict:
        return {
            "language": self.language_combo.currentData() or "en",
            "color_theme": self.theme_combo.currentData() or "classic",
            "enable_assembly_transform": self.assembly_transform_cb.isChecked(),
        }

    def _load_current_values(self):
        self._set_combo_by_data(self.language_combo, self._current.get("language", "en"))
        self._set_combo_by_data(self.theme_combo, self._current.get("color_theme", "classic"))
        self.assembly_transform_cb.setChecked(bool(self._current.get("enable_assembly_transform", False)))

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: str):
        target = str(value or "").strip()
        for idx in range(combo.count()):
            if str(combo.itemData(idx) or "").strip() == target:
                combo.setCurrentIndex(idx)
                return

    def _row(self, label_text: str, combo: QComboBox) -> QFrame:
        row = QFrame()
        row.setProperty("editorFieldCard", True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        label = QLabel(label_text)
        label.setProperty("detailFieldKey", True)
        label.setMinimumWidth(130)
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        combo.setMinimumWidth(220)
        combo.setFixedHeight(36)
        layout.addWidget(label)
        layout.addWidget(combo, 1)
        return row

    def _t(self, key: str, default: str | None = None) -> str:
        return self._translate(key, default)
