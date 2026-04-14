from __future__ import annotations

from pathlib import Path
from typing import Callable
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
try:
    from shared.ui.preferences_dialog_base import PreferencesDialogBase
except ModuleNotFoundError:
    workspace_root = Path(__file__).resolve().parents[2]
    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))
    from shared.ui.preferences_dialog_base import PreferencesDialogBase
from ui.widgets.common import add_shadow, apply_tool_library_combo_style


class PreferencesDialog(PreferencesDialogBase):
    def __init__(
        self,
        current_preferences: dict,
        translate: Callable[[str, str | None], str],
        parent=None,
        active_db_path: str = "",
        on_check_compatibility: Callable[[str], None] | None = None,
    ):
        super().__init__(translate, parent)
        self._current = dict(current_preferences or {})
        self._active_db_path = str(active_db_path or "").strip()
        self._on_check_compatibility = on_check_compatibility

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
        self.database_tab = self._build_database_tab()
        self.tabs.addTab(self.general_tab, self._t("preferences.tab.general", "General"))
        self.tabs.addTab(self.models_tab, self._t("preferences.tab.models_3d", "3D Models"))
        self.tabs.addTab(self.database_tab, self._t("preferences.tab.database", "Database"))

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

        self.machine_profile_combo = QComboBox()
        self.machine_profile_combo.addItem(
            self._t("preferences.machine_profile.ntx_2sp_2h", "NTX 2SP + 2H"),
            "ntx_2sp_2h",
        )
        apply_tool_library_combo_style(self.machine_profile_combo)
        card_layout.addWidget(
            self._row(
                self._t("preferences.machine_profile", "Machine Profile"),
                self.machine_profile_combo,
            )
        )

        self.assembly_transform_cb = QCheckBox(self._t("preferences.enable_assembly_transform", "Enable assembly transform editing (3D Models tab)"))
        self.assembly_transform_cb.setStyleSheet("QCheckBox { background: transparent; }")
        card_layout.addWidget(self.assembly_transform_cb)

        self.drawings_tab_cb = QCheckBox(self._t("preferences.enable_drawings_tab", "Enable Drawings tab"))
        self.drawings_tab_cb.setStyleSheet("QCheckBox { background: transparent; }")
        card_layout.addWidget(self.drawings_tab_cb)

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
            self._t("preferences.detached_preview.mode.current", "Keep Current Position"),
            "current",
        )
        apply_tool_library_combo_style(self.detached_preview_mode_combo)
        card_layout.addWidget(
            self._row(
                self._t("preferences.detached_preview.mode", "Detached 3D Preview Position"),
                self.detached_preview_mode_combo,
            )
        )

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

    def _build_database_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)
        layout.addWidget(card)

        hint = QLabel(
            self._t(
                "preferences.database.hint",
                "Choose the active Setup Manager database (.db). Changes apply after restart.",
            )
        )
        hint.setWordWrap(True)
        hint.setProperty("detailHint", True)
        card_layout.addWidget(hint)

        warning = QLabel(
            self._t(
                "preferences.database.warning",
                "Warning: Setup Manager work links depend on matching tool and jaw IDs in the currently configured Tool Library and Jaws Library databases. Changing only the Setup database may leave some work references unresolved.",
            )
        )
        warning.setWordWrap(True)
        warning.setProperty("detailHint", True)
        card_layout.addWidget(warning)

        self.setup_db_path_edit = QLineEdit()
        self.setup_db_path_edit.setMinimumWidth(260)
        self.setup_db_path_edit.setPlaceholderText(
            self._t("preferences.database.path.placeholder", "Path to setup_manager.db")
        )
        self.setup_db_browse = QPushButton(self._t("preferences.models.browse", "BROWSE"))
        self.setup_db_browse.setProperty("panelActionButton", True)
        self.setup_db_browse.clicked.connect(self._pick_setup_database)
        add_shadow(self.setup_db_browse)
        card_layout.addWidget(
            self._path_row(
                self._t("preferences.database.path", "Setup DB"),
                self.setup_db_path_edit,
                self.setup_db_browse,
            )
        )

        self.active_db_path_edit = QLineEdit()
        self.active_db_path_edit.setReadOnly(True)
        self.active_db_path_edit.setFocusPolicy(Qt.NoFocus)
        self.active_db_path_edit.setMinimumWidth(260)
        self.active_db_path_edit.setPlaceholderText(
            self._t("preferences.database.active_runtime.placeholder", "No active database path")
        )
        card_layout.addWidget(
            self._line_row(
                self._t("preferences.database.active_runtime", "Active Runtime DB"),
                self.active_db_path_edit,
            )
        )

        self.check_compatibility_btn = QPushButton(
            self._t("preferences.database.check_compatibility", "CHECK COMPATIBILITY")
        )
        self.check_compatibility_btn.setProperty("panelActionButton", True)
        self.check_compatibility_btn.clicked.connect(self._check_compatibility)
        add_shadow(self.check_compatibility_btn)
        card_layout.addWidget(self.check_compatibility_btn, 0, Qt.AlignLeft)

        layout.addStretch(1)
        return tab

    def preferences_payload(self) -> dict:
        return {
            "language": self.language_combo.currentData() or "en",
            "color_theme": self.theme_combo.currentData() or "classic",
            "machine_profile_key": self.machine_profile_combo.currentData() or "ntx_2sp_2h",
            "tools_models_root": self.tools_models_root.text().strip(),
            "jaws_models_root": self.jaws_models_root.text().strip(),
            "setup_db_path": self.setup_db_path_edit.text().strip(),
            "enable_assembly_transform": self.assembly_transform_cb.isChecked(),
            "enable_drawings_tab": self.drawings_tab_cb.isChecked(),
            "detached_preview_policy": {
                "mode": self.detached_preview_mode_combo.currentData() or "follow_last",
            },
        }

    def _load_current_values(self):
        self._set_combo_by_data(self.language_combo, self._current.get("language", "en"))
        self._set_combo_by_data(self.theme_combo, self._current.get("color_theme", "classic"))
        self._set_combo_by_data(self.machine_profile_combo, self._current.get("machine_profile_key", "ntx_2sp_2h"))
        self.tools_models_root.setText(str(self._current.get("tools_models_root", "")))
        self.jaws_models_root.setText(str(self._current.get("jaws_models_root", "")))
        self.setup_db_path_edit.setText(str(self._current.get("setup_db_path", "")))
        self.active_db_path_edit.setText(self._active_db_path)
        self.active_db_path_edit.setToolTip(self._active_db_path or "")
        self.assembly_transform_cb.setChecked(bool(self._current.get("enable_assembly_transform", False)))
        self.drawings_tab_cb.setChecked(bool(self._current.get("enable_drawings_tab", True)))
        policy = self._current.get("detached_preview_policy")
        mode = str((policy or {}).get("mode") if isinstance(policy, dict) else "follow_last").strip().lower()
        if mode not in {"follow_last", "left", "right", "current"}:
            mode = "follow_last"
        self._set_combo_by_data(self.detached_preview_mode_combo, mode)

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

    def _pick_setup_database(self):
        start_dir = self.setup_db_path_edit.text().strip()
        if not start_dir:
            start_dir = str(Path.home())
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            self._t("preferences.database.select", "Select Setup Manager database"),
            start_dir,
            self._t("preferences.database.file_filter", "SQLite Database (*.db);;All Files (*.*)"),
        )
        if chosen:
            self.setup_db_path_edit.setText(chosen)

    def _check_compatibility(self):
        if not callable(self._on_check_compatibility):
            return
        target_path = self.setup_db_path_edit.text().strip() or self._active_db_path
        self._on_check_compatibility(target_path)

    # Shared combo/path/line row, translation, and combo-data helpers are inherited.
