from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from shared.services.machine_config_service import MachineConfig, MachineConfigService, _is_machining_center_key
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from shared.services.machine_config_service import MachineConfig, MachineConfigService, _is_machining_center_key


_LIBRARY_TOOLS = "tools"
_LIBRARY_JAWS = "jaws"


def _library_items_for_config(config: MachineConfig | None) -> list[tuple[str, str]]:
    """Return (key, label) pairs for the library selector, filtered by machine profile."""
    is_mc = _is_machining_center_key(getattr(config, "machine_profile_key", None))
    items = [(_LIBRARY_TOOLS, "Tools Library")]
    if not is_mc:
        items.append((_LIBRARY_JAWS, "Jaws Library"))
    return items


def _db_path_for_library(config: MachineConfig | None, library_key: str) -> str:
    if config is None:
        return ""
    if library_key == _LIBRARY_JAWS:
        return config.jaws_db_path or ""
    return config.tools_db_path or ""


class ImportExportTab(QWidget):
    def __init__(
        self,
        machine_config_svc: MachineConfigService | None,
        on_import_clicked: Callable[[str], None],
        on_export_clicked: Callable[[str], None],
        translate: Callable,
        parent=None,
    ):
        super().__init__(parent)
        self._svc = machine_config_svc
        self._on_import = on_import_clicked
        self._on_export = on_export_clicked
        self._t = translate
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        # ── Library selector ──────────────────────────────────────────────
        lib_row = QHBoxLayout()
        lib_row.setSpacing(8)
        lib_label = QLabel(self._t("preferences.import_export.library_label", "Library"))
        lib_label.setFixedWidth(100)
        self._lib_combo = QComboBox()
        self._lib_combo.currentIndexChanged.connect(self._on_library_changed)
        lib_row.addWidget(lib_label)
        lib_row.addWidget(self._lib_combo, 1)
        root.addLayout(lib_row)

        # ── Active DB path display ────────────────────────────────────────
        db_frame = QFrame()
        db_frame.setObjectName("importExportDbFrame")
        db_layout = QVBoxLayout(db_frame)
        db_layout.setContentsMargins(10, 8, 10, 8)
        db_layout.setSpacing(2)

        db_header = QLabel(self._t("preferences.import_export.db_path_label", "Active database"))
        db_header.setProperty("sectionTitle", True)
        db_layout.addWidget(db_header)

        self._db_path_label = QLabel("")
        self._db_path_label.setWordWrap(True)
        self._db_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        db_layout.addWidget(self._db_path_label)
        root.addWidget(db_frame)

        # ── Action buttons ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._import_btn = QPushButton(self._t("preferences.import_export.import_button", "IMPORT FROM EXCEL"))
        self._import_btn.setProperty("panelActionButton", True)
        self._import_btn.clicked.connect(self._handle_import)

        self._export_btn = QPushButton(self._t("preferences.import_export.export_button", "EXPORT TO EXCEL"))
        self._export_btn.setProperty("panelActionButton", True)
        self._export_btn.setProperty("primaryAction", True)
        self._export_btn.clicked.connect(self._handle_export)

        btn_row.addWidget(self._import_btn)
        btn_row.addWidget(self._export_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        hint = QLabel(self._t(
            "preferences.import_export.hint",
            "The Tool Library app will open to perform the import or export.",
        ))
        hint.setWordWrap(True)
        hint.setProperty("navHint", True)
        root.addWidget(hint)

        root.addStretch(1)

    def refresh(self):
        """Rebuild the library combo from the active machine config."""
        config = self._svc.get_active_config() if self._svc else None
        items = _library_items_for_config(config)

        self._lib_combo.blockSignals(True)
        current_key = self._current_library_key()
        self._lib_combo.clear()
        for key, label in items:
            self._lib_combo.addItem(label, key)
        # Restore previous selection if still valid
        for i in range(self._lib_combo.count()):
            if self._lib_combo.itemData(i) == current_key:
                self._lib_combo.setCurrentIndex(i)
                break
        self._lib_combo.blockSignals(False)

        self._refresh_db_path()

    def _current_library_key(self) -> str:
        idx = self._lib_combo.currentIndex()
        if idx < 0:
            return _LIBRARY_TOOLS
        return self._lib_combo.itemData(idx) or _LIBRARY_TOOLS

    def _on_library_changed(self):
        self._refresh_db_path()

    def _refresh_db_path(self):
        config = self._svc.get_active_config() if self._svc else None
        key = self._current_library_key()
        path = _db_path_for_library(config, key)
        if path:
            self._db_path_label.setText(path)
        else:
            self._db_path_label.setText(self._t("preferences.import_export.db_default", "(app default)"))

    def _handle_import(self):
        self._on_import(self._current_library_key())

    def _handle_export(self):
        self._on_export(self._current_library_key())
