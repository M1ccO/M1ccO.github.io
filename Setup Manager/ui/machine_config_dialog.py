"""Edit / New Machine Configuration dialog.

Each database row (Setup Manager, Tools Library, Jaws Library) has a
"Use shared database" checkbox.  When unchecked the user specifies a file
path directly.  When checked, a dropdown lists every other saved machine
configuration and the stored path is automatically copied from that config's
corresponding database.
"""
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
    QVBoxLayout,
    QWidget,
)

try:
    from shared.services.machine_config_service import MachineConfig, MachineConfigService
except ModuleNotFoundError:
    _workspace = Path(__file__).resolve().parents[2]
    if str(_workspace) not in sys.path:
        sys.path.insert(0, str(_workspace))
    from shared.services.machine_config_service import MachineConfig, MachineConfigService

from machine_profiles import load_profile
from ui.widgets.common import add_shadow, apply_tool_library_combo_style


# --------------------------------------------------------------------------- #
# _DbRow — one database row with shared / custom toggle                       #
# --------------------------------------------------------------------------- #

class _DbRow(QFrame):
    """A single database configuration row.

    Shows a label, a "Use shared database" checkbox, and either:
    - a path QLineEdit + BROWSE + CLEAR buttons  (custom mode)
    - a QComboBox listing other machine configs   (shared mode)
    """

    def __init__(
        self,
        label_text: str,
        db_attr: str,           # "setup_db_path" | "tools_db_path" | "jaws_db_path"
        svc: MachineConfigService,
        own_config_id: str,     # "" for new-config mode
        translate: Callable,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("editorFieldCard", True)
        self._db_attr = db_attr
        self._svc = svc
        self._own_id = own_config_id
        self._t = translate

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # ---- Top row: label + checkbox -----------------------------------
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)

        lbl = QLabel(label_text)
        lbl.setProperty("detailFieldKey", True)
        lbl.setMinimumWidth(120)
        lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        top.addWidget(lbl)

        self._shared_cb = QCheckBox(
            translate("machine_config.use_shared_db", "Use shared database")
        )
        self._shared_cb.toggled.connect(self._on_toggle)
        top.addWidget(self._shared_cb)
        top.addStretch(1)
        outer.addLayout(top)

        # ---- Bottom row: path widgets OR shared combo --------------------
        bottom = QHBoxLayout()
        bottom.setContentsMargins(120 + 10, 0, 0, 0)   # indent under label
        bottom.setSpacing(6)

        # Custom-path widgets
        self._path_edit = QLineEdit()
        self._path_edit.setFixedHeight(32)
        self._path_edit.setPlaceholderText(
            translate("machine_config.db_default_placeholder", "(use default)")
        )
        self._browse_btn = QPushButton(translate("preferences.models.browse", "BROWSE"))
        self._browse_btn.setProperty("panelActionButton", True)
        self._browse_btn.clicked.connect(self._pick_path)
        add_shadow(self._browse_btn)
        self._clear_btn = QPushButton(translate("common.clear", "Clear"))
        self._clear_btn.setProperty("panelActionButton", True)
        self._clear_btn.clicked.connect(lambda: self._path_edit.clear())

        bottom.addWidget(self._path_edit, 1)
        bottom.addWidget(self._browse_btn)
        bottom.addWidget(self._clear_btn)

        # Shared-config dropdown (hidden initially)
        shared_lbl = QLabel(
            translate("machine_config.shared_with_label", "Shared with:")
        )
        shared_lbl.setProperty("detailFieldKey", True)
        self._shared_label = shared_lbl

        self._shared_combo = QComboBox()
        apply_tool_library_combo_style(self._shared_combo)
        self._shared_combo.setFixedHeight(32)
        self._rebuild_shared_combo()

        bottom.addWidget(shared_lbl)
        bottom.addWidget(self._shared_combo, 1)

        outer.addLayout(bottom)

        # Start in custom mode
        self._on_toggle(False)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _rebuild_shared_combo(self) -> None:
        self._shared_combo.clear()
        if self._svc is None:
            return
        for cfg in self._svc.list_configs():
            if cfg.id == self._own_id:
                continue
            other_path = getattr(cfg, self._db_attr, "") or ""
            label = cfg.name if other_path else f"{cfg.name} (default path)"
            self._shared_combo.addItem(label, cfg.id)

    def _on_toggle(self, checked: bool) -> None:
        # Custom-path widgets
        self._path_edit.setVisible(not checked)
        self._browse_btn.setVisible(not checked)
        self._clear_btn.setVisible(not checked)
        # Shared widgets
        self._shared_label.setVisible(checked)
        self._shared_combo.setVisible(checked)

    def _pick_path(self) -> None:
        start = self._path_edit.text().strip() or str(Path.home())
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            self._t("preferences.database.select", "Select database"),
            start,
            self._t(
                "preferences.database.file_filter",
                "SQLite Database (*.db);;All Files (*.*)",
            ),
        )
        if chosen:
            self._path_edit.setText(chosen)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def set_value(self, path: str) -> None:
        """Populate the row from an existing stored path.

        Detects whether *path* is shared (matches another config's same-field
        path) and pre-selects the shared combo accordingly.
        """
        if path and self._svc:
            # Check if any other config shares exactly this path for this field.
            for cfg in self._svc.list_configs():
                if cfg.id == self._own_id:
                    continue
                if getattr(cfg, self._db_attr, "") == path:
                    # Shared — pre-select that config.
                    self._rebuild_shared_combo()
                    self._shared_cb.setChecked(True)
                    for i in range(self._shared_combo.count()):
                        if self._shared_combo.itemData(i) == cfg.id:
                            self._shared_combo.setCurrentIndex(i)
                            return
                    # If the combo got rebuilt but the match is gone, fall through.
                    self._shared_cb.setChecked(False)
                    break

        # Custom (or empty) path.
        self._shared_cb.setChecked(False)
        self._path_edit.setText(path)

    def get_value(self) -> str:
        """Return the path to store.

        Shared mode: returns the selected config's path for this DB field
        (may be "" if that config uses the app default).
        Custom mode: returns the text in the path edit.
        """
        if not self._shared_cb.isChecked():
            return self._path_edit.text().strip()
        selected_id = self._shared_combo.currentData()
        if not selected_id or self._svc is None:
            return ""
        other = self._svc.get_config(selected_id)
        if other is None:
            return ""
        return getattr(other, self._db_attr, "") or ""

    def is_shared(self) -> bool:
        return self._shared_cb.isChecked()

    def shared_with_name(self) -> str:
        """Human-readable name of the config being shared with, or ''."""
        if not self._shared_cb.isChecked():
            return ""
        selected_id = self._shared_combo.currentData()
        if not selected_id or self._svc is None:
            return ""
        cfg = self._svc.get_config(selected_id)
        return cfg.name if cfg else ""


# --------------------------------------------------------------------------- #
# MachineConfigDialog                                                          #
# --------------------------------------------------------------------------- #

class MachineConfigDialog(QDialog):
    """Create a new machine configuration or edit an existing one."""

    def __init__(
        self,
        translate: Callable,
        machine_config_svc: MachineConfigService,
        config_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._translate = translate
        self._svc = machine_config_svc
        self._config_id = config_id
        self._is_create = config_id is None

        # Snapshot for reload-detection (edit mode only).
        self._original_profile_key: str = "ntx_2sp_2h"
        self._original_setup_db: str = ""
        self._original_tools_db: str = ""
        self._original_jaws_db: str = ""

        self._profile_key: str = "ntx_2sp_2h"
        self._result_config: MachineConfig | None = None

        existing: MachineConfig | None = None
        if not self._is_create:
            existing = machine_config_svc.get_config(config_id)
            if existing:
                self._original_profile_key = existing.machine_profile_key
                self._original_setup_db = existing.setup_db_path
                self._original_tools_db = existing.tools_db_path
                self._original_jaws_db = existing.jaws_db_path
                self._profile_key = existing.machine_profile_key

        self.setObjectName("appRoot")
        self.setProperty("preferencesDialog", True)
        self.setModal(True)
        self.resize(620, 520)

        title_text = self._t(
            "machine_config.new_title" if self._is_create else "machine_config.edit_title",
            "New Configuration" if self._is_create else "Edit Configuration",
        )
        self.setWindowTitle(title_text)

        self._build_ui()

        if existing is not None:
            self._populate(existing)

    # ------------------------------------------------------------------ #
    # Translation                                                          #
    # ------------------------------------------------------------------ #

    def _t(self, key: str, default: str | None = None) -> str:
        return self._translate(key, default)

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(12)

        # ---- Name -------------------------------------------------------
        self.name_edit = QLineEdit()
        self.name_edit.setFixedHeight(36)
        self.name_edit.setPlaceholderText(
            self._t("machine_config.name.placeholder", "e.g. NTX2500")
        )
        card_layout.addWidget(
            self._field_row(self._t("machine_config.name", "Name"), self.name_edit)
        )

        # ---- Machine Profile --------------------------------------------
        self.profile_label = QLabel()
        self.profile_label.setProperty("detailFieldValue", True)

        self._change_profile_btn = QPushButton(
            self._t("machine_config.change_profile", "Change...")
        )
        self._change_profile_btn.setProperty("panelActionButton", True)
        self._change_profile_btn.clicked.connect(self._on_change_profile)
        add_shadow(self._change_profile_btn)

        profile_widget = QWidget()
        profile_layout = QHBoxLayout(profile_widget)
        profile_layout.setContentsMargins(0, 0, 0, 0)
        profile_layout.setSpacing(8)
        profile_layout.addWidget(self.profile_label, 1)
        profile_layout.addWidget(self._change_profile_btn, 0)

        card_layout.addWidget(
            self._field_row(
                self._t("machine_config.machine_profile", "Machine Profile"),
                profile_widget,
            )
        )

        self.profile_warning = QLabel(
            self._t(
                "machine_config.profile_change_warning",
                "⚠  Changing the machine profile will reload the application.",
            )
        )
        self.profile_warning.setProperty("warningHint", True)
        self.profile_warning.setWordWrap(True)
        self.profile_warning.setVisible(False)
        card_layout.addWidget(self.profile_warning)

        # ---- DB rows ----------------------------------------------------
        own_id = self._config_id or ""

        self._setup_db_row = _DbRow(
            self._t("machine_config.setup_db", "Setup DB"),
            "setup_db_path",
            self._svc,
            own_id,
            self._translate,
        )
        card_layout.addWidget(self._setup_db_row)

        self._tools_db_row = _DbRow(
            self._t("machine_config.tools_db", "Tools Library"),
            "tools_db_path",
            self._svc,
            own_id,
            self._translate,
        )
        card_layout.addWidget(self._tools_db_row)

        self._jaws_db_row = _DbRow(
            self._t("machine_config.jaws_db", "Jaws Library"),
            "jaws_db_path",
            self._svc,
            own_id,
            self._translate,
        )
        card_layout.addWidget(self._jaws_db_row)

        if self._is_create:
            note = QLabel(
                self._t(
                    "machine_config.auto_db_hint",
                    "ℹ  Leave all fields empty and dedicated databases will be "
                    "created automatically for this configuration.",
                )
            )
            note.setProperty("detailHint", True)
            note.setWordWrap(True)
            card_layout.addWidget(note)

        root.addWidget(card)

        # ---- Dialog buttons --------------------------------------------
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        buttons.addStretch(1)

        self.save_btn = QPushButton(self._t("common.save", "Save"))
        self.save_btn.setProperty("panelActionButton", True)
        self.save_btn.setProperty("primaryAction", True)
        self.save_btn.clicked.connect(self._on_save)
        add_shadow(self.save_btn)
        buttons.addWidget(self.save_btn)

        self.cancel_btn = QPushButton(self._t("common.cancel", "Cancel"))
        self.cancel_btn.setProperty("panelActionButton", True)
        self.cancel_btn.setProperty("secondaryAction", True)
        self.cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_btn)

        root.addLayout(buttons)

        self._refresh_profile_label()

    def _populate(self, config: MachineConfig) -> None:
        self.name_edit.setText(config.name)
        self._setup_db_row.set_value(config.setup_db_path)
        self._tools_db_row.set_value(config.tools_db_path)
        self._jaws_db_row.set_value(config.jaws_db_path)

    # ------------------------------------------------------------------ #
    # Layout helpers                                                       #
    # ------------------------------------------------------------------ #

    def _field_row(self, label_text: str, widget: QWidget) -> QFrame:
        row = QFrame()
        row.setProperty("editorFieldCard", True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        lbl = QLabel(label_text)
        lbl.setProperty("detailFieldKey", True)
        lbl.setMinimumWidth(120)
        lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        layout.addWidget(lbl)
        layout.addWidget(widget, 1)
        return row

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _refresh_profile_label(self) -> None:
        try:
            profile = load_profile(self._profile_key)
            self.profile_label.setText(profile.name)
        except Exception:
            self.profile_label.setText(self._profile_key)

    def _update_profile_warning(self) -> None:
        changed = (
            not self._is_create
            and self._profile_key != self._original_profile_key
        )
        self.profile_warning.setVisible(changed)

    # ------------------------------------------------------------------ #
    # Slots                                                                #
    # ------------------------------------------------------------------ #

    def _on_change_profile(self) -> None:
        from ui.machine_setup_wizard import MachineSetupWizard

        wizard = MachineSetupWizard(translate=self._translate, parent=self)
        if wizard.exec() == QDialog.Accepted:
            self._profile_key = wizard.selected_profile_key()
            self._refresh_profile_label()
            self._update_profile_warning()

    def _on_save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(
                self,
                self._t("machine_config.error.title", "Validation Error"),
                self._t(
                    "machine_config.error.name_empty",
                    "Configuration name cannot be empty.",
                ),
            )
            return

        setup_db = self._setup_db_row.get_value()
        tools_db = self._tools_db_row.get_value()
        jaws_db = self._jaws_db_row.get_value()

        if self._is_create:
            config = self._svc.create_config(
                name=name,
                machine_profile_key=self._profile_key,
                setup_db_path=setup_db,
                tools_db_path=tools_db,
                jaws_db_path=jaws_db,
            )
            self._bootstrap_new_db(config)
        else:
            config = self._svc.update_config(
                self._config_id,
                name=name,
                machine_profile_key=self._profile_key,
                setup_db_path=setup_db,
                tools_db_path=tools_db,
                jaws_db_path=jaws_db,
            )

        self._result_config = config
        self.accept()

    def _bootstrap_new_db(self, config: MachineConfig) -> None:
        """Create and migrate the database for a brand-new configuration."""
        try:
            from data.database import Database
            from services.work_service import WorkService

            Path(config.setup_db_path).parent.mkdir(parents=True, exist_ok=True)
            db = Database(config.setup_db_path)
            ws = WorkService(db)
            ws.set_machine_profile_key(config.machine_profile_key)
            db.conn.close()
        except Exception as exc:
            QMessageBox.warning(
                self,
                self._t("machine_config.db_init_warning_title", "Database Warning"),
                self._t(
                    "machine_config.db_init_warning_body",
                    "The database could not be initialised automatically:\n"
                    f"{exc}\n\nIt will be created when you switch to this "
                    "configuration.",
                ),
            )

        # Pre-create empty tool/jaw library SQLite files so they exist on disk
        # as soon as the config is saved.  The Tool Library will apply its full
        # schema when it first connects to the file.
        import sqlite3 as _sqlite3
        for lib_path_str in (config.tools_db_path, config.jaws_db_path):
            if not lib_path_str:
                continue
            lib_path = Path(lib_path_str)
            try:
                lib_path.parent.mkdir(parents=True, exist_ok=True)
                if not lib_path.exists():
                    _conn = _sqlite3.connect(str(lib_path))
                    _conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Public result accessors                                              #
    # ------------------------------------------------------------------ #

    def result_config(self) -> MachineConfig | None:
        """The config that was created or updated; None if dialog was cancelled."""
        return self._result_config

    def requires_reload(self) -> bool:
        """True when the *active* config was changed in a reload-requiring way."""
        if self._result_config is None or self._is_create:
            return False
        if self._config_id != self._svc.get_active_config_id():
            return False
        return (
            self._result_config.machine_profile_key != self._original_profile_key
            or self._result_config.setup_db_path != self._original_setup_db
            or self._result_config.tools_db_path != self._original_tools_db
            or self._result_config.jaws_db_path != self._original_jaws_db
        )
