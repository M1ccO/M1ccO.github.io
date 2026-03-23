from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
)

from data.jaw_database import JawDatabase
from services.jaw_service import JawService
from services.export_service import ExportService
from ui.export_page import ExportPage, ImportMappingDialog


class JawImportMappingDialog(ImportMappingDialog):
    """ImportMappingDialog variant pre-configured for Jaw fields."""

    GENERAL_FIELDS = [
        ('jaw_id', 'Jaw ID'),
        ('jaw_type', 'Jaw type'),
        ('spindle_side', 'Spindle side'),
        ('clamping_diameter_text', 'Clamping diameter'),
        ('clamping_length', 'Clamping length'),
        ('used_in_work', 'Used in works:'),
        ('turning_washer', 'Turning ring'),
        ('last_modified', 'Last modified'),
        ('notes', 'Notes'),
        ('stl_path', '3D model path / JSON'),
    ]
    ADDITIONAL_FIELDS: list = []
    MODEL_FIELDS: list = []

    def __init__(self, excel_headers: list[str], parent=None):
        super().__init__(excel_headers, parent)
        self.setWindowTitle('Import Jaw Mapping')

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        tabs = QTabWidget()
        tabs.addTab(self._build_connector_tab(self.GENERAL_FIELDS), 'General')
        root.addWidget(tabs, 1)

        mode_box = QGroupBox('Import Mode')
        mode_box.setStyleSheet('QGroupBox { background: transparent; }')
        mode_layout = QVBoxLayout(mode_box)
        self.mode_group = QButtonGroup(self)
        self.mode_overwrite = QRadioButton('Overwrite current database')
        self.mode_overwrite.setChecked(True)
        self.mode_new_db = QRadioButton('Create new database file')
        self.mode_group.addButton(self.mode_overwrite)
        self.mode_group.addButton(self.mode_new_db)
        self.mode_overwrite.setStyleSheet('QRadioButton { background-color: transparent; }')
        self.mode_new_db.setStyleSheet('QRadioButton { background-color: transparent; }')

        newdb_row = QHBoxLayout()
        self.new_db_path = QLineEdit()
        self.new_db_path.setPlaceholderText('Choose destination .db file...')
        self.new_db_browse = QPushButton('BROWSE')
        self.new_db_browse.setProperty('panelActionButton', True)
        self.new_db_browse.clicked.connect(self._browse_new_db)
        newdb_row.addWidget(self.new_db_path, 1)
        newdb_row.addWidget(self.new_db_browse)

        mode_layout.addWidget(self.mode_overwrite)
        mode_layout.addWidget(self.mode_new_db)
        mode_layout.addLayout(newdb_row)
        root.addWidget(mode_box)

        self.mode_overwrite.toggled.connect(self._update_mode_ui)
        self._update_mode_ui()

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton('CANCEL')
        cancel.setProperty('panelActionButton', True)
        ok = QPushButton('IMPORT')
        ok.setProperty('panelActionButton', True)
        ok.setProperty('primaryAction', True)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        root.addLayout(btns)

    def _accept(self):
        if 'jaw_id' not in self.mapping():
            QMessageBox.warning(self, 'Import mapping', 'Jaw ID mapping is required.')
            return
        if self.mode_new_db.isChecked() and not self.new_db_path.text().strip():
            QMessageBox.warning(self, 'Import mapping', 'Select destination path for the new database.')
            return
        self.accept()


class _JawToolServiceAdapter:
    def __init__(self, jaw_service: JawService):
        self.jaw_service = jaw_service

    @property
    def db(self):
        return self.jaw_service.db

    def list_tools(self):
        # ExportPage expects list_tools(); map to jaws list API.
        rows = self.jaw_service.list_jaws('', 'all', 'All')
        # Keep row coloring support from ExportService by mirroring jaw_type into tool_type.
        for row in rows:
            row['tool_type'] = row.get('jaw_type', '')
        return rows

    def save_tool(self, jaw: dict):
        self.jaw_service.save_jaw(jaw)


class _JawExportServiceAdapter(ExportService):
    GENERAL_FIELDS = [
        ('jaw_id', 'Jaw ID'),
        ('jaw_type', 'Jaw type'),
        ('spindle_side', 'Spindle side'),
        ('clamping_diameter_text', 'Clamping diameter'),
        ('clamping_length', 'Clamping length'),
        ('used_in_work', 'Used in works:'),
        ('turning_washer', 'Turning ring'),
        ('last_modified', 'Last modified'),
        ('notes', 'Notes'),
        ('stl_path', '3D model path / JSON'),
    ]

    IMPORT_DEFAULTS = {
        'jaw_id': '',
        'jaw_type': 'Soft jaws',
        'spindle_side': 'Main spindle',
        'clamping_diameter_text': '',
        'clamping_length': '',
        'used_in_work': '',
        'turning_washer': '',
        'last_modified': '',
        'notes': '',
        'stl_path': '',
    }

    def export_tools(self, filename: str, tools: list[dict]):
        rows = []
        for row in tools or []:
            converted = dict(row)
            converted['tool_type'] = row.get('jaw_type', '')
            rows.append(converted)
        super().export_tools(filename, rows)


class JawExportPage(ExportPage):
    def __init__(self, jaw_service, on_jaw_data_changed=None, on_jaw_database_switched=None, parent=None):
        self.jaw_service = jaw_service
        self._jaw_tool_adapter = _JawToolServiceAdapter(jaw_service)
        self._jaw_export_adapter = _JawExportServiceAdapter()
        super().__init__(
            tool_service=self._jaw_tool_adapter,
            export_service=self._jaw_export_adapter,
            on_data_changed=on_jaw_data_changed,
            on_database_switched=on_jaw_database_switched,
            parent=parent,
        )

    def set_jaw_service(self, jaw_service: JawService):
        self.jaw_service = jaw_service
        self._jaw_tool_adapter.jaw_service = jaw_service

    def import_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import from Excel', '', 'Excel (*.xlsx *.xlsm)')
        if not path:
            return

        try:
            headers = self.export_service.read_excel_headers(path)
        except Exception as exc:
            QMessageBox.critical(self, 'Import failed', f'Could not read Excel headers:\n{exc}')
            return

        if not headers:
            QMessageBox.warning(self, 'Import', 'No header row found in selected Excel file.')
            return

        dlg = JawImportMappingDialog(headers, self)
        if dlg.exec() != QDialog.Accepted:
            return

        mapping = dlg.mapping()
        if 'jaw_id' not in mapping:
            QMessageBox.warning(self, 'Import mapping', 'Jaw ID mapping is required.')
            return

        try:
            jaws = self.export_service.import_tools(path, mapping)
        except Exception as exc:
            QMessageBox.critical(self, 'Import failed', str(exc))
            return

        if not jaws:
            QMessageBox.information(self, 'Import', 'No valid jaw rows found with current mapping.')
            return

        try:
            if dlg.import_mode() == 'overwrite':
                confirm = QMessageBox.question(
                    self,
                    'Confirm overwrite',
                    'Are you sure you want to overwrite current database contents?',
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if confirm != QMessageBox.Yes:
                    return

                backup_answer = QMessageBox.question(
                    self,
                    'Backup before overwrite',
                    'Create a backup of the current database before overwrite?',
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes,
                )
                if backup_answer == QMessageBox.Cancel:
                    return
                if backup_answer == QMessageBox.Yes:
                    backup_path = self._create_database_backup()
                    QMessageBox.information(self, 'Backup created', f'Backup saved to:\n{backup_path}')

                with self.tool_service.db.conn:
                    self.tool_service.db.conn.execute('DELETE FROM jaws')
                    for jaw in jaws:
                        self.tool_service.save_tool(jaw)
                if callable(self.on_data_changed):
                    self.on_data_changed()
                QMessageBox.information(self, 'Import', f'Imported {len(jaws)} jaws into current database.')
                return

            db_path = Path(dlg.selected_new_db_path())
            if db_path.suffix.lower() != '.db':
                db_path = db_path.with_suffix('.db')
            new_db = JawDatabase(db_path)
            new_jaw_service = JawService(new_db)
            with new_db.conn:
                new_db.conn.execute('DELETE FROM jaws')
            for jaw in jaws:
                new_jaw_service.save_jaw(jaw)
            new_db.close()
            QMessageBox.information(self, 'Import', f'Imported {len(jaws)} jaws into new database:\n{db_path}')
        except Exception as exc:
            QMessageBox.critical(self, 'Import failed', str(exc))
