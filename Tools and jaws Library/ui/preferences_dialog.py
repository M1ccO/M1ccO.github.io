from __future__ import annotations

from pathlib import Path
import sys
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)
try:
    from shared.ui.preferences_dialog_base import PreferencesDialogBase
except ModuleNotFoundError:
    workspace_root = Path(__file__).resolve().parents[2]
    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))
    from shared.ui.preferences_dialog_base import PreferencesDialogBase
from shared.ui.helpers.editor_helpers import apply_shared_checkbox_style, setup_editor_dialog
from ui.widgets.common import add_shadow, apply_shared_dropdown_style


class PreferencesDialog(PreferencesDialogBase):
    def __init__(self, current_preferences: dict, translate: Callable[[str, str | None], str], parent=None):
        super().__init__(translate, parent)
        self._current = dict(current_preferences or {})

        setup_editor_dialog(self)
        self.setObjectName("appRoot")
        self.setProperty("preferencesDialog", True)
        self.setWindowTitle(self._t("preferences.title", "Preferences"))
        self.setModal(True)
        self.resize(500, 330)

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
        apply_shared_checkbox_style(self.assembly_transform_cb, indicator_size=16)
        card_layout.addWidget(self.assembly_transform_cb)

        self.detached_preview_mode_combo = QComboBox()
        self.detached_preview_mode_combo.addItem(
            self._t("preferences.detached_preview.mode.follow_last", "Follow Last Closed Position"),
            "follow_last",
        )
        self.detached_preview_mode_combo.addItem(
            self._t("preferences.detached_preview.mode.right", "Open on Right Side"),
            "right",
        )
        self.detached_preview_mode_combo.addItem(
            self._t("preferences.detached_preview.mode.left", "Open on Left Side"),
            "left",
        )
        self.detached_preview_mode_combo.addItem(
            self._t("preferences.detached_preview.mode.embedded", "Embedded in Main Window"),
            "embedded",
        )
        apply_shared_dropdown_style(self.detached_preview_mode_combo)
        add_shadow(self.detached_preview_mode_combo)
        card_layout.addWidget(
            self._row(
                self._t("preferences.detached_preview.mode", "Detached 3D Preview Position"),
                self.detached_preview_mode_combo,
            )
        )

        self.preview_preload_cb = QCheckBox(
            self._t(
                "preferences.models.preview_preload",
                "Preload 3D preview in background for faster first open",
            )
        )
        apply_shared_checkbox_style(self.preview_preload_cb, indicator_size=16)
        card_layout.addWidget(self.preview_preload_cb)

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
            "enable_preview_preload": self.preview_preload_cb.isChecked(),
            "detached_preview_policy": {
                "mode": self.detached_preview_mode_combo.currentData() or "follow_last",
            },
        }

    def _load_current_values(self):
        self._set_combo_by_data(self.language_combo, self._current.get("language", "en"))
        self._set_combo_by_data(self.theme_combo, self._current.get("color_theme", "classic"))
        self.assembly_transform_cb.setChecked(bool(self._current.get("enable_assembly_transform", False)))
        self.preview_preload_cb.setChecked(bool(self._current.get("enable_preview_preload", True)))
        policy = self._current.get("detached_preview_policy")
        mode = str((policy or {}).get("mode") if isinstance(policy, dict) else "follow_last").strip().lower()
        # Support legacy 'current' mode by converting to 'embedded'
        if mode == "current":
            mode = "embedded"
        if mode not in {"follow_last", "left", "right", "embedded"}:
            mode = "follow_last"
        self._set_combo_by_data(self.detached_preview_mode_combo, mode)

    # Shared combo row, translation, and combo-data helpers are inherited.
