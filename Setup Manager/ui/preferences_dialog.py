from __future__ import annotations

import sys
from pathlib import Path
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
    QMessageBox,
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

try:
    from shared.services.machine_config_service import MachineConfigService
except ModuleNotFoundError:
    workspace_root = Path(__file__).resolve().parents[2]
    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))
    from shared.services.machine_config_service import MachineConfigService

from ui.widgets.common import add_shadow, apply_tool_library_combo_style
from machine_profiles import load_profile
from shared.ui.helpers.editor_helpers import apply_shared_checkbox_style
from ui.import_export_tab import ImportExportTab


class PreferencesDialog(PreferencesDialogBase):
    def __init__(
        self,
        current_preferences: dict,
        translate: Callable[[str, str | None], str],
        parent=None,
        machine_config_svc: MachineConfigService | None = None,
        on_import_clicked: Callable[[str], None] | None = None,
        on_export_clicked: Callable[[str], None] | None = None,
    ):
        super().__init__(translate, parent)
        self._current = dict(current_preferences or {})
        self._machine_config_svc = machine_config_svc
        self._on_import_clicked = on_import_clicked or (lambda _lib: None)
        self._on_export_clicked = on_export_clicked or (lambda _lib: None)

        # When the user triggers a live config switch (via dropdown, Edit, or
        # New), we store the target config_id here and close the dialog via
        # reject() so the caller can emit config_switch_requested.
        self._pending_switch_config_id: str | None = None

        self.setObjectName("appRoot")
        self.setProperty("preferencesDialog", True)
        self.setModal(True)
        self.setWindowTitle(self._t("preferences.title", "Preferences"))
        self.resize(560, 400)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.general_tab = self._build_general_tab()
        self.machines_tab = self._build_machines_tab()
        self.models_tab = self._build_models_tab()
        self.import_export_tab = ImportExportTab(
            machine_config_svc=machine_config_svc,
            on_import_clicked=self._on_import_clicked,
            on_export_clicked=self._on_export_clicked,
            translate=self._t,
        )
        self.tabs.addTab(self.general_tab, self._t("preferences.tab.general", "General"))
        self.tabs.addTab(self.machines_tab, self._t("preferences.tab.machines", "Machines"))
        self.tabs.addTab(self.models_tab, self._t("preferences.tab.models_3d", "3D Models"))
        self.tabs.addTab(self.import_export_tab, self._t("preferences.tab.import_export", "Import / Export"))

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

    # ------------------------------------------------------------------ #
    # Tab builders                                                         #
    # ------------------------------------------------------------------ #

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

        self.assembly_transform_cb = QCheckBox(
            self._t(
                "preferences.enable_assembly_transform",
                "Enable assembly transform editing (3D Models tab)",
            )
        )
        apply_shared_checkbox_style(self.assembly_transform_cb, indicator_size=16)
        card_layout.addWidget(self.assembly_transform_cb)

        self.drawings_tab_cb = QCheckBox(
            self._t("preferences.enable_drawings_tab", "Enable Drawings tab")
        )
        apply_shared_checkbox_style(self.drawings_tab_cb, indicator_size=16)
        card_layout.addWidget(self.drawings_tab_cb)

        self._op20_sep = QFrame()
        self._op20_sep.setProperty("editorSeparator", True)
        self._op20_sep.setFrameShape(QFrame.HLine)
        card_layout.addWidget(self._op20_sep)

        self._op20_hint = QLabel(
            self._t(
                "preferences.work_editor.op20_hint",
                "Work Editor — OP20 defaults (applies to single-spindle machines only):",
            )
        )
        self._op20_hint.setWordWrap(True)
        self._op20_hint.setProperty("detailHint", True)
        card_layout.addWidget(self._op20_hint)

        self.op20_jaws_default_cb = QCheckBox(
            self._t(
                "preferences.work_editor.op20_jaws_default",
                "Include OP20 jaws and zero points by default",
            )
        )
        apply_shared_checkbox_style(self.op20_jaws_default_cb, indicator_size=16)
        card_layout.addWidget(self.op20_jaws_default_cb)

        self.op20_tools_default_cb = QCheckBox(
            self._t(
                "preferences.work_editor.op20_tools_default",
                "Include OP20 tools by default",
            )
        )
        apply_shared_checkbox_style(self.op20_tools_default_cb, indicator_size=16)
        card_layout.addWidget(self.op20_tools_default_cb)

        self.detached_preview_mode_combo = QComboBox()
        self.detached_preview_mode_combo.addItem(
            self._t(
                "preferences.detached_preview.mode.follow_last",
                "Follow Last Closed Position",
            ),
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
            self._t(
                "preferences.detached_preview.mode.embedded", "Embedded in Main Window"
            ),
            "embedded",
        )
        apply_tool_library_combo_style(self.detached_preview_mode_combo)
        card_layout.addWidget(
            self._row(
                self._t(
                    "preferences.detached_preview.mode", "Detached 3D Preview Position"
                ),
                self.detached_preview_mode_combo,
            )
        )

        layout.addStretch(1)
        return tab

    def _active_profile_is_single_spindle(self) -> bool:
        if self._machine_config_svc is None:
            return False
        cfg = self._machine_config_svc.get_active_config()
        if cfg is None:
            return False
        try:
            profile = load_profile(cfg.machine_profile_key)
            return int(getattr(profile, "spindle_count", 0)) == 1
        except Exception:
            return False

    def _update_op20_defaults_visibility(self) -> None:
        show = self._active_profile_is_single_spindle()
        for widget_name in (
            "_op20_sep",
            "_op20_hint",
            "op20_jaws_default_cb",
            "op20_tools_default_cb",
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setVisible(show)

    def _build_machines_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ---- Active configuration card --------------------------------
        config_card = QFrame()
        config_card.setProperty("card", True)
        config_card_layout = QVBoxLayout(config_card)
        config_card_layout.setContentsMargins(16, 14, 16, 14)
        config_card_layout.setSpacing(10)
        layout.addWidget(config_card)

        # The dropdown switches configs live on selection. Edit / New /
        # Delete operate independently — none wait for the Save button.
        self._machine_config_combo = QComboBox()
        apply_tool_library_combo_style(self._machine_config_combo)
        # Signal connected after initial population in _load_current_values
        # so the handler doesn't fire during setup.
        config_card_layout.addWidget(
            self._row(
                self._t("machine_config.active", "Active Machine"),
                self._machine_config_combo,
            )
        )

        config_btns = QHBoxLayout()
        config_btns.setContentsMargins(0, 0, 0, 0)
        config_btns.setSpacing(6)
        config_btns.addStretch(1)

        self._switch_config_btn = QPushButton(
            self._t("machine_config.switch", "Switch to Selected")
        )
        self._switch_config_btn.setProperty("panelActionButton", True)
        self._switch_config_btn.setProperty("primaryAction", True)
        self._switch_config_btn.clicked.connect(self._on_switch_config)
        add_shadow(self._switch_config_btn)
        config_btns.addWidget(self._switch_config_btn)

        self._edit_config_btn = QPushButton(
            self._t("machine_config.edit", "Edit Configuration")
        )
        self._edit_config_btn.setProperty("panelActionButton", True)
        self._edit_config_btn.clicked.connect(self._on_edit_config)
        add_shadow(self._edit_config_btn)
        config_btns.addWidget(self._edit_config_btn)

        self._new_config_btn = QPushButton(
            self._t("machine_config.new", "New Configuration")
        )
        self._new_config_btn.setProperty("panelActionButton", True)
        self._new_config_btn.clicked.connect(self._on_new_config)
        add_shadow(self._new_config_btn)
        config_btns.addWidget(self._new_config_btn)

        self._delete_config_btn = QPushButton(
            self._t("machine_config.delete", "Delete")
        )
        self._delete_config_btn.setProperty("panelActionButton", True)
        self._delete_config_btn.clicked.connect(self._on_delete_config)
        sp = self._delete_config_btn.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self._delete_config_btn.setSizePolicy(sp)
        config_btns.addWidget(self._delete_config_btn)

        config_card_layout.addLayout(config_btns)

        # ---- Notifications card ---------------------------------------
        notif_card = QFrame()
        notif_card.setProperty("card", True)
        notif_layout = QVBoxLayout(notif_card)
        notif_layout.setContentsMargins(16, 14, 16, 14)
        notif_layout.setSpacing(6)
        layout.addWidget(notif_card)

        notif_hint = QLabel(
            self._t(
                "machine_config.notifications_hint",
                "Notifications about shared databases are shown when switching machines.",
            )
        )
        notif_hint.setWordWrap(True)
        notif_hint.setProperty("detailHint", True)
        notif_layout.addWidget(notif_hint)

        self.shared_db_notice_cb = QCheckBox(
            self._t(
                "machine_config.notify_shared_db_changes",
                "Notify me when shared databases have been modified",
            )
        )
        self.shared_db_notice_cb.setStyleSheet("QCheckBox { background: transparent; }")
        notif_layout.addWidget(self.shared_db_notice_cb)

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

        hint = QLabel(
            self._t(
                "preferences.models.hint",
                "Configure root folders for portable 3D model paths.",
            )
        )
        hint.setWordWrap(True)
        hint.setProperty("detailHint", True)
        card_layout.addWidget(hint)

        self.tools_models_root = QLineEdit()
        self.tools_models_root.setMinimumWidth(260)
        self.tools_models_root.setPlaceholderText(
            self._t("preferences.models.tools.placeholder", "Folder for tool models")
        )
        self.tools_models_browse = QPushButton(
            self._t("preferences.models.browse", "BROWSE")
        )
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
        self.jaws_models_root.setPlaceholderText(
            self._t("preferences.models.jaws.placeholder", "Folder for jaw models")
        )
        self.jaws_models_browse = QPushButton(
            self._t("preferences.models.browse", "BROWSE")
        )
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

        self.fixtures_models_root = QLineEdit()
        self.fixtures_models_root.setMinimumWidth(260)
        self.fixtures_models_root.setPlaceholderText(
            self._t("preferences.models.fixtures.placeholder", "Folder for fixture models")
        )
        self.fixtures_models_browse = QPushButton(
            self._t("preferences.models.browse", "BROWSE")
        )
        self.fixtures_models_browse.setProperty("panelActionButton", True)
        self.fixtures_models_browse.clicked.connect(self._pick_fixtures_models_root)
        add_shadow(self.fixtures_models_browse)
        card_layout.addWidget(
            self._path_row(
                self._t("preferences.models.fixtures_root", "Fixtures 3D Root"),
                self.fixtures_models_root,
                self.fixtures_models_browse,
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

        layout.addStretch(1)
        return tab

    # ------------------------------------------------------------------ #
    # Payload / value management                                           #
    # ------------------------------------------------------------------ #

    def preferences_payload(self) -> dict:
        return {
            "language": self.language_combo.currentData() or "en",
            "color_theme": self.theme_combo.currentData() or "classic",
            # machine_profile_key is NOT included here — it is database-bound
            # and must only be changed via the machine configuration manager.
            "tools_models_root": self.tools_models_root.text().strip(),
            "jaws_models_root": self.jaws_models_root.text().strip(),
            "fixtures_models_root": self.fixtures_models_root.text().strip(),
            "enable_assembly_transform": self.assembly_transform_cb.isChecked(),
            "enable_preview_preload": self.preview_preload_cb.isChecked(),
            "enable_drawings_tab": self.drawings_tab_cb.isChecked(),
            "detached_preview_policy": {
                "mode": self.detached_preview_mode_combo.currentData() or "follow_last",
            },
            "show_shared_db_notice": self.shared_db_notice_cb.isChecked(),
            "op20_jaws_default": self.op20_jaws_default_cb.isChecked(),
            "op20_tools_default": self.op20_tools_default_cb.isChecked(),
        }

    def _load_current_values(self):
        self._set_combo_by_data(
            self.language_combo, self._current.get("language", "en")
        )
        self._set_combo_by_data(
            self.theme_combo, self._current.get("color_theme", "classic")
        )

        # Populate the machine configuration dropdown, then wire the signal
        # so it doesn't fire during initial population.
        self._refresh_config_combo()
        self._machine_config_combo.currentIndexChanged.connect(
            self._on_config_combo_changed
        )

        self.tools_models_root.setText(str(self._current.get("tools_models_root", "")))
        self.jaws_models_root.setText(str(self._current.get("jaws_models_root", "")))
        self.fixtures_models_root.setText(str(self._current.get("fixtures_models_root", "")))
        self.assembly_transform_cb.setChecked(
            bool(self._current.get("enable_assembly_transform", False))
        )
        self.preview_preload_cb.setChecked(
            bool(self._current.get("enable_preview_preload", True))
        )
        self.drawings_tab_cb.setChecked(
            bool(self._current.get("enable_drawings_tab", True))
        )
        self.shared_db_notice_cb.setChecked(
            bool(self._current.get("show_shared_db_notice", False))
        )
        self.op20_jaws_default_cb.setChecked(
            bool(self._current.get("op20_jaws_default", False))
        )
        self.op20_tools_default_cb.setChecked(
            bool(self._current.get("op20_tools_default", False))
        )
        self._update_op20_defaults_visibility()
        policy = self._current.get("detached_preview_policy")
        mode = str(
            (policy or {}).get("mode") if isinstance(policy, dict) else "follow_last"
        ).strip().lower()
        # Support legacy 'current' mode by converting to 'embedded'
        if mode == "current":
            mode = "embedded"
        if mode not in {"follow_last", "left", "right", "embedded"}:
            mode = "follow_last"
        self._set_combo_by_data(self.detached_preview_mode_combo, mode)

    # ------------------------------------------------------------------ #
    # Machine configuration management                                     #
    # ------------------------------------------------------------------ #

    def _refresh_config_combo(self) -> None:
        """Rebuild the config combo from current service state without firing signals."""
        if self._machine_config_svc is None:
            return
        self._machine_config_combo.blockSignals(True)
        self._machine_config_combo.clear()
        active_id = self._machine_config_svc.get_active_config_id()
        active_index = 0
        for i, cfg in enumerate(self._machine_config_svc.list_configs()):
            label = cfg.name if cfg.id != active_id else f"{cfg.name} (active)"
            self._machine_config_combo.addItem(label, cfg.id)
            if cfg.id == active_id:
                active_index = i
        self._machine_config_combo.setCurrentIndex(active_index)
        self._machine_config_combo.blockSignals(False)
        self._update_config_buttons()
        self._update_op20_defaults_visibility()

    def _update_config_buttons(self) -> None:
        """Enable/disable Switch and Delete based on whether selected == active."""
        if self._machine_config_svc is None:
            return
        selected_id = self._machine_config_combo.currentData()
        active_id = self._machine_config_svc.get_active_config_id()
        is_active = selected_id == active_id
        if hasattr(self, "_switch_config_btn"):
            self._switch_config_btn.setEnabled(not is_active)
        if hasattr(self, "_delete_config_btn"):
            self._delete_config_btn.setVisible(not is_active)

    def _on_config_combo_changed(self, _index: int) -> None:
        """Update button states when the selected config changes."""
        self._update_config_buttons()

    def _on_switch_config(self) -> None:
        """Switch to the currently selected (non-active) config after confirmation."""
        if self._machine_config_svc is None:
            return
        selected_id = self._machine_config_combo.currentData()
        if not selected_id:
            return
        cfg = self._machine_config_svc.get_config(selected_id)
        if cfg is None:
            return
        confirmed = QMessageBox.question(
            self,
            self._t("machine_config.switch_title", "Switch Configuration"),
            self._t(
                "machine_config.switch_body",
                f"Switch to '{cfg.name}'?\n\nThe application will reload immediately.",
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmed != QMessageBox.Yes:
            return
        self._pending_switch_config_id = selected_id
        self.reject()

    def _on_edit_config(self) -> None:
        if self._machine_config_svc is None:
            return
        config_id = self._machine_config_combo.currentData()
        if not config_id:
            return

        from ui.machine_config_dialog import MachineConfigDialog

        dlg = MachineConfigDialog(
            translate=self._translate,
            machine_config_svc=self._machine_config_svc,
            config_id=config_id,
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        self._refresh_config_combo()

        if dlg.requires_reload():
            self._pending_switch_config_id = config_id
            self.reject()

    def _on_new_config(self) -> None:
        if self._machine_config_svc is None:
            return

        try:
            from ui.machine_config_dialog import MachineConfigDialog

            dlg = MachineConfigDialog(
                translate=self._translate,
                machine_config_svc=self._machine_config_svc,
                config_id=None,
                parent=self,
            )
            dlg.raise_()
            dlg.activateWindow()
            if dlg.exec() != QDialog.Accepted:
                return

            result = dlg.result_config()
            if result is None:
                QMessageBox.warning(
                    self,
                    self._t("machine_config.error.title", "Validation Error"),
                    self._t(
                        "machine_config.error.create_failed",
                        "The new configuration dialog closed without creating a configuration.",
                    ),
                )
                return
        except Exception as exc:
            QMessageBox.warning(
                self,
                self._t("machine_config.error.title", "Validation Error"),
                self._t(
                    "machine_config.error.create_failed",
                    "Could not open the new configuration dialog:\n{error}",
                    error=exc,
                ),
            )
            return

        self._refresh_config_combo()

        # Select the newly created config in the combo so the user can
        # switch to it manually if desired, but don't force a reload.
        for i in range(self._machine_config_combo.count()):
            if self._machine_config_combo.itemData(i) == result.id:
                self._machine_config_combo.setCurrentIndex(i)
                break

    def _on_delete_config(self) -> None:
        if self._machine_config_svc is None:
            return
        config_id = self._machine_config_combo.currentData()
        if not config_id:
            return
        cfg = self._machine_config_svc.get_config(config_id)
        if cfg is None:
            return

        try:
            plan = self._machine_config_svc.database_cleanup_plan(config_id)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                self._t("machine_config.delete_error_title", "Cannot Delete"),
                str(exc),
            )
            return

        delete_paths = list(plan.get("delete_paths") or [])
        shared_paths = list(plan.get("shared_paths") or [])
        missing_paths = list(plan.get("missing_paths") or [])

        warn_lines = [
            self._t(
                "machine_config.delete_databases_warning",
                "This will also delete related database files that are only used by this configuration.",
            )
        ]
        if delete_paths:
            warn_lines.append(
                self._t(
                    "machine_config.delete_databases_count",
                    "Database files to delete: {count}",
                    count=len(delete_paths),
                )
            )
        if shared_paths:
            warn_lines.append(
                self._t(
                    "machine_config.delete_databases_shared",
                    "Shared database files kept: {count}",
                    count=len(shared_paths),
                )
            )
        if missing_paths:
            warn_lines.append(
                self._t(
                    "machine_config.delete_databases_missing",
                    "Already missing files: {count}",
                    count=len(missing_paths),
                )
            )

        confirmed = QMessageBox.question(
            self,
            self._t("machine_config.delete_title", "Delete Configuration"),
            self._t(
                "machine_config.delete_body_with_cleanup",
                "Delete configuration '{name}'?\n\n{warning}\n\nThis cannot be undone.",
                name=cfg.name,
                warning="\n".join(warn_lines),
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmed != QMessageBox.Yes:
            return

        try:
            delete_result = self._machine_config_svc.delete_config(
                config_id,
                delete_related_databases=True,
            )
        except ValueError as exc:
            QMessageBox.warning(
                self,
                self._t("machine_config.delete_error_title", "Cannot Delete"),
                str(exc),
            )
            return

        deleted_count = len(delete_result.get("deleted_paths") or [])
        failed_count = len(delete_result.get("failed_paths") or [])
        shared_count = len(delete_result.get("shared_paths") or [])
        if deleted_count or failed_count or shared_count:
            QMessageBox.information(
                self,
                self._t("machine_config.delete_cleanup_result_title", "Database Cleanup"),
                self._t(
                    "machine_config.delete_cleanup_result_body",
                    "Deleted DB files: {deleted}\nKept shared files: {shared}\nFailed to delete: {failed}",
                    deleted=deleted_count,
                    shared=shared_count,
                    failed=failed_count,
                ),
            )

        self._refresh_config_combo()

    # ------------------------------------------------------------------ #
    # File pickers                                                         #
    # ------------------------------------------------------------------ #

    def _pick_tools_models_root(self):
        start_dir = self.tools_models_root.text().strip()
        chosen = QFileDialog.getExistingDirectory(
            self,
            self._t(
                "preferences.models.tools.select", "Select tools model root folder"
            ),
            start_dir,
        )
        if chosen:
            self.tools_models_root.setText(chosen)

    def _pick_jaws_models_root(self):
        start_dir = self.jaws_models_root.text().strip()
        chosen = QFileDialog.getExistingDirectory(
            self,
            self._t(
                "preferences.models.jaws.select", "Select jaws model root folder"
            ),
            start_dir,
        )
        if chosen:
            self.jaws_models_root.setText(chosen)

    def _pick_fixtures_models_root(self):
        start_dir = self.fixtures_models_root.text().strip()
        chosen = QFileDialog.getExistingDirectory(
            self,
            self._t(
                "preferences.models.fixtures.select", "Select fixtures model root folder"
            ),
            start_dir,
        )
        if chosen:
            self.fixtures_models_root.setText(chosen)

    # Shared combo/path/line row, translation, and combo-data helpers are inherited.
