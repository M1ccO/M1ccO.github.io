from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from ui.widgets.common import add_shadow, apply_tool_library_combo_style


class PreferencesDialog(QDialog):
    def __init__(self, current_preferences: dict, translate: Callable[[str, str | None], str], parent=None):
        super().__init__(parent)
        self._translate = translate
        self._current = dict(current_preferences or {})

        self.setObjectName("appRoot")
        self.setProperty("preferencesDialog", True)
        self.setWindowTitle(self._t("preferences.title", "Preferences"))
        self.setModal(True)
        self.resize(500, 280)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.general_tab = self._build_general_tab()
        self.models_tab = self._build_models_tab()
        self.tabs.addTab(self.general_tab, self._t("preferences.tab.general", "General"))
        self.tabs.addTab(self.models_tab, self._t("preferences.tab.models_3d", "3D Models"))

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
        root.addLayout(buttons)

        self._load_current_values()

    def _build_general_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)
        layout.addWidget(card)

        hint = QLabel(self._t("preferences.hint", "Language changes are applied after restart."))
        hint.setObjectName("preferencesHintLabel")
        hint.setWordWrap(True)
        hint.setProperty("detailHint", True)
        card_layout.addWidget(hint)

        self.language_combo = QComboBox()
        self.language_combo.addItem(self._t("language.english", "English"), "en")
        self.language_combo.addItem(self._t("language.finnish", "Finnish"), "fi")
        apply_tool_library_combo_style(self.language_combo)
        card_layout.addWidget(self._row(self._t("preferences.language", "Language"), self.language_combo))

        self.theme_combo = QComboBox()
        self.theme_combo.addItem(self._t("theme.classic", "Classic"), "classic")
        self.theme_combo.addItem(self._t("theme.graphite", "Graphite"), "graphite")
        apply_tool_library_combo_style(self.theme_combo)
        card_layout.addWidget(self._row(self._t("preferences.color_theme", "Color Theme"), self.theme_combo))

        self.assembly_transform_cb = QCheckBox(self._t("preferences.enable_assembly_transform", "Enable assembly transform editing (3D Models tab)"))
        self.assembly_transform_cb.setStyleSheet("QCheckBox { background: transparent; }")
        card_layout.addWidget(self.assembly_transform_cb)

        self.drawings_tab_cb = QCheckBox(self._t("preferences.enable_drawings_tab", "Enable Drawings tab"))
        self.drawings_tab_cb.setStyleSheet("QCheckBox { background: transparent; }")
        card_layout.addWidget(self.drawings_tab_cb)

        layout.addStretch(1)
        return tab

    def _build_models_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)
        layout.addWidget(card)

        hint = QLabel(self._t("preferences.models.hint", "Configure root folders for portable 3D model paths."))
        hint.setWordWrap(True)
        hint.setProperty("detailHint", True)
        card_layout.addWidget(hint)

        self.tools_models_root = QLineEdit()
        self.tools_models_root.setMinimumWidth(260)
        self.tools_models_root.setPlaceholderText(self._t("preferences.models.tools.placeholder", "Folder for tool models"))
        self.tools_models_browse = QPushButton(self._t("preferences.models.browse", "BROWSE"))
        self.tools_models_browse.setProperty("panelActionButton", True)
        self.tools_models_browse.clicked.connect(self._pick_tools_models_root)
        add_shadow(self.tools_models_browse)
        card_layout.addWidget(
            self._path_row(
                self._t("preferences.models.tools_root", "Tools 3D Root"),
                self.tools_models_root,
                self.tools_models_browse,
            )
        )

        self.jaws_models_root = QLineEdit()
        self.jaws_models_root.setMinimumWidth(260)
        self.jaws_models_root.setPlaceholderText(self._t("preferences.models.jaws.placeholder", "Folder for jaw models"))
        self.jaws_models_browse = QPushButton(self._t("preferences.models.browse", "BROWSE"))
        self.jaws_models_browse.setProperty("panelActionButton", True)
        self.jaws_models_browse.clicked.connect(self._pick_jaws_models_root)
        add_shadow(self.jaws_models_browse)
        card_layout.addWidget(
            self._path_row(
                self._t("preferences.models.jaws_root", "Jaws 3D Root"),
                self.jaws_models_root,
                self.jaws_models_browse,
            )
        )

        layout.addStretch(1)
        return tab

    def preferences_payload(self) -> dict:
        return {
            "language": self.language_combo.currentData() or "en",
            "color_theme": self.theme_combo.currentData() or "classic",
            "tools_models_root": self.tools_models_root.text().strip(),
            "jaws_models_root": self.jaws_models_root.text().strip(),
            "enable_assembly_transform": self.assembly_transform_cb.isChecked(),
            "enable_drawings_tab": self.drawings_tab_cb.isChecked(),
        }

    def _load_current_values(self):
        self._set_combo_by_data(self.language_combo, self._current.get("language", "en"))
        self._set_combo_by_data(self.theme_combo, self._current.get("color_theme", "classic"))
        self.tools_models_root.setText(str(self._current.get("tools_models_root", "")))
        self.jaws_models_root.setText(str(self._current.get("jaws_models_root", "")))
        self.assembly_transform_cb.setChecked(bool(self._current.get("enable_assembly_transform", False)))
        self.drawings_tab_cb.setChecked(bool(self._current.get("enable_drawings_tab", True)))

    def _pick_tools_models_root(self):
        start_dir = self.tools_models_root.text().strip()
        chosen = QFileDialog.getExistingDirectory(
            self,
            self._t("preferences.models.tools.select", "Select tools model root folder"),
            start_dir,
        )
        if chosen:
            self.tools_models_root.setText(chosen)

    def _pick_jaws_models_root(self):
        start_dir = self.jaws_models_root.text().strip()
        chosen = QFileDialog.getExistingDirectory(
            self,
            self._t("preferences.models.jaws.select", "Select jaws model root folder"),
            start_dir,
        )
        if chosen:
            self.jaws_models_root.setText(chosen)

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

    def _path_row(self, label_text: str, line_edit: QLineEdit, browse_btn: QPushButton) -> QFrame:
        row = QFrame()
        row.setProperty("editorFieldCard", True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        label = QLabel(label_text)
        label.setProperty("detailFieldKey", True)
        label.setMinimumWidth(130)
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        line_edit.setMinimumWidth(220)
        line_edit.setFixedHeight(36)
        browse_btn.setMinimumWidth(96)
        layout.addWidget(label)
        layout.addWidget(line_edit, 1)
        layout.addWidget(browse_btn)
        return row

    def _t(self, key: str, default: str | None = None) -> str:
        return self._translate(key, default)
