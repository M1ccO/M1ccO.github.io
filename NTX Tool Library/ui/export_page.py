from pathlib import Path
import shutil
from datetime import datetime

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import DB_PATH, EXPORT_DEFAULT_PATH
from data.database import Database
from services.tool_service import ToolService


class FieldConnectorWidget(QWidget):
    mappingChanged = Signal(str, str)

    def __init__(self, excel_headers: list[str], software_fields: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self._headers = [h for h in excel_headers if h]
        self._fields = software_fields
        self._mapping: dict[str, str] = {}

        self._left_rects: list[tuple[str, QRect]] = []
        self._right_rects: list[tuple[str, QRect]] = []
        self._dragging_header = ''
        self._drag_pos = QPoint()

        rows = max(len(self._headers), len(self._fields))
        self.setMinimumHeight(max(420, 42 + rows * 36))
        self.setMinimumWidth(940)
        self.setMouseTracking(True)

    def set_mapping(self, field_key: str, header: str):
        if header:
            self._mapping[field_key] = header
        elif field_key in self._mapping:
            del self._mapping[field_key]
        self.update()

    def remove_header_mapping(self, header: str):
        to_clear = [k for k, v in self._mapping.items() if v == header]
        for key in to_clear:
            del self._mapping[key]
        self.update()

    def mapping(self) -> dict[str, str]:
        return dict(self._mapping)

    def _layout_rects(self):
        margin = 12
        row_h = 28
        col_gap = 60
        left_w = max(260, (self.width() - (margin * 2) - col_gap) // 2)
        right_w = left_w
        left_x = margin
        right_x = left_x + left_w + col_gap
        top_y = margin + 18

        self._left_rects = []
        self._right_rects = []

        for i, text in enumerate(self._headers):
            r = QRect(left_x, top_y + i * (row_h + 4), left_w, row_h)
            self._left_rects.append((text, r))

        for i, (key, _label) in enumerate(self._fields):
            r = QRect(right_x, top_y + i * (row_h + 4), right_w, row_h)
            self._right_rects.append((key, r))

    def _header_for_field(self, field_key: str) -> str:
        return self._mapping.get(field_key, '')

    def _field_label(self, field_key: str) -> str:
        for key, label in self._fields:
            if key == field_key:
                return label
        return field_key

    def _field_key_at(self, pos: QPoint) -> str:
        for key, rect in self._right_rects:
            if rect.contains(pos):
                return key
        return ''

    def _header_at(self, pos: QPoint) -> str:
        for header, rect in self._left_rects:
            if rect.contains(pos):
                return header
        return ''

    def _center_of_header(self, header: str) -> QPoint:
        for h, rect in self._left_rects:
            if h == header:
                return rect.center()
        return QPoint()

    def _center_of_field(self, field_key: str) -> QPoint:
        for k, rect in self._right_rects:
            if k == field_key:
                return rect.center()
        return QPoint()

    def paintEvent(self, _event):
        self._layout_rects()

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        title_pen = QPen(QColor('#2b3136'))
        p.setPen(title_pen)
        p.drawText(12, 18, 'Excel headings')
        p.drawText(self.width() // 2 + 20, 18, 'Software fields')

        # Draw connection lines first so row cards render on top.
        line_pen = QPen(QColor('#2f8fdc'), 2)
        p.setPen(line_pen)
        for field_key, header in self._mapping.items():
            src = self._center_of_header(header)
            dst = self._center_of_field(field_key)
            if not src.isNull() and not dst.isNull():
                p.drawLine(src, dst)

        if self._dragging_header:
            src = self._center_of_header(self._dragging_header)
            if not src.isNull():
                drag_pen = QPen(QColor('#1f74bd'), 2, Qt.DashLine)
                p.setPen(drag_pen)
                p.drawLine(src, self._drag_pos)

        # Left side: Excel rows
        for header, rect in self._left_rects:
            is_used = header in self._mapping.values()
            fill = QColor('#dceaf9') if is_used else QColor('#ffffff')
            border = QColor('#7fa6cc') if is_used else QColor('#c7cfd6')

            p.setPen(QPen(border, 1))
            p.setBrush(fill)
            p.drawRoundedRect(rect, 5, 5)
            p.setPen(QPen(QColor('#1f2a33')))
            p.drawText(rect.adjusted(8, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, header)

        # Right side: Software rows
        for field_key, rect in self._right_rects:
            mapped = field_key in self._mapping
            fill = QColor('#e3f3e7') if mapped else QColor('#ffffff')
            border = QColor('#7db08a') if mapped else QColor('#c7cfd6')

            p.setPen(QPen(border, 1))
            p.setBrush(fill)
            p.drawRoundedRect(rect, 5, 5)
            label = self._field_label(field_key)
            p.setPen(QPen(QColor('#1f2a33')))
            p.drawText(rect.adjusted(8, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, label)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        header = self._header_at(event.position().toPoint())
        if header:
            self._dragging_header = header
            self._drag_pos = event.position().toPoint()
            self.update()
            return

        # Clicking mapped software row removes its mapping.
        field_key = self._field_key_at(event.position().toPoint())
        if field_key and field_key in self._mapping:
            self._mapping.pop(field_key, None)
            self.mappingChanged.emit(field_key, '')
            self.update()

    def mouseMoveEvent(self, event):
        if self._dragging_header:
            self._drag_pos = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if not self._dragging_header:
            return

        target_field = self._field_key_at(event.position().toPoint())
        header = self._dragging_header

        self._dragging_header = ''
        self._drag_pos = QPoint()

        if target_field:
            self._mapping[target_field] = header
            self.mappingChanged.emit(target_field, header)
        self.update()


class ImportMappingDialog(QDialog):
    GENERAL_FIELDS = [
        ('id', 'Tool ID'),
        ('tool_head', 'Tool Head'),
        ('tool_type', 'Tool type'),
        ('description', 'Description'),
        ('geom_x', 'Geom X'),
        ('geom_z', 'Geom Z'),
        ('radius', 'Radius'),
        ('nose_corner_radius', 'Nose R / Corner R'),
        ('holder_code', 'Holder code'),
        ('holder_link', 'Holder link'),
        ('holder_add_element', 'Add. Element'),
        ('holder_add_element_link', 'Add. Element link'),
        ('cutting_type', 'Cutting component type'),
        ('cutting_code', 'Cutting component code'),
        ('cutting_link', 'Cutting component link'),
        ('cutting_add_element', 'Add. Insert/Drill/Mill'),
        ('cutting_add_element_link', 'Add. Insert/Drill/Mill link'),
        ('drill_nose_angle', 'Nose angle'),
        ('mill_cutting_edges', 'Cutting edges'),
        ('notes', 'Notes'),
    ]

    ADDITIONAL_FIELDS = [
        ('support_parts', 'Support parts (JSON or text)'),
    ]

    MODEL_FIELDS = [
        ('stl_path', '3D model path / JSON'),
    ]

    def __init__(self, excel_headers: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle('Import Mapping')
        self.resize(1120, 760)
        self._headers = [h for h in excel_headers if h]
        self._connectors: list[FieldConnectorWidget] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        tabs = QTabWidget()
        tabs.addTab(self._build_connector_tab(self.GENERAL_FIELDS), 'General')
        tabs.addTab(self._build_connector_tab(self.ADDITIONAL_FIELDS), 'Additional Parts')
        tabs.addTab(self._build_connector_tab(self.MODEL_FIELDS), '3D Models')
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

    def _build_connector_tab(self, fields: list[tuple[str, str]]) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        connector = FieldConnectorWidget(self._headers, fields)
        connector.mappingChanged.connect(self._on_connector_mapping_changed)
        self._connectors.append(connector)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet('QScrollArea { background: transparent; border: none; } QScrollArea > QWidget > QWidget { background: transparent; }')
        scroll.viewport().setStyleSheet('background: transparent;')
        scroll.setWidget(connector)

        layout.addWidget(scroll, 1)
        return page

    def _on_connector_mapping_changed(self, field_key: str, header: str):
        if not header:
            return
        # Keep one-to-one mapping: one Excel heading can map to only one software field.
        for connector in self._connectors:
            current = connector.mapping()
            for k, h in list(current.items()):
                if h == header and k != field_key:
                    connector.set_mapping(k, '')

    def _browse_new_db(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Create new database', str(DB_PATH), 'Database (*.db)')
        if path:
            self.new_db_path.setText(path)

    def _update_mode_ui(self):
        enabled = self.mode_new_db.isChecked()
        self.new_db_path.setEnabled(enabled)
        self.new_db_browse.setEnabled(enabled)

    def _accept(self):
        mapped = self.mapping()
        if 'id' not in mapped:
            QMessageBox.warning(self, 'Import mapping', 'Tool ID mapping is required.')
            return
        if self.mode_new_db.isChecked() and not self.new_db_path.text().strip():
            QMessageBox.warning(self, 'Import mapping', 'Select destination path for the new database.')
            return
        self.accept()

    def mapping(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for connector in self._connectors:
            out.update(connector.mapping())
        return out

    def import_mode(self) -> str:
        return 'new-db' if self.mode_new_db.isChecked() else 'overwrite'

    def selected_new_db_path(self) -> str:
        return self.new_db_path.text().strip()


class ExportPage(QWidget):
    def __init__(self, tool_service, export_service, on_data_changed=None, on_database_switched=None, parent=None):
        super().__init__(parent)
        self.tool_service = tool_service
        self.export_service = export_service
        self.on_data_changed = on_data_changed
        self.on_database_switched = on_database_switched
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 14, 14, 10)
        root.setSpacing(10)

        title = QLabel('Export / Import')
        title.setProperty('pageTitle', True)
        root.addWidget(title)

        card = QFrame()
        card.setStyleSheet('QFrame { background: transparent; border: none; }')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(12)

        db_box = QGroupBox('Active Database')
        db_box.setStyleSheet('QGroupBox { background: transparent; }')
        db_layout = QVBoxLayout(db_box)
        db_row = QHBoxLayout()
        self.db_path_edit = QLineEdit()
        self.db_path_edit.setReadOnly(True)
        self.db_path_edit.setPlaceholderText('No database selected')
        self.db_choose_btn = QPushButton('CHOOSE DB')
        self.db_choose_btn.setProperty('panelActionButton', True)
        self.db_apply_btn = QPushButton('USE SELECTED DB')
        self.db_apply_btn.setProperty('panelActionButton', True)
        self.db_choose_btn.clicked.connect(self._choose_database_file)
        self.db_apply_btn.clicked.connect(self._apply_database_file)
        db_row.addWidget(self.db_path_edit, 1)
        db_row.addWidget(self.db_choose_btn)
        db_row.addWidget(self.db_apply_btn)
        db_layout.addLayout(db_row)
        card_layout.addWidget(db_box)

        btn_row = QHBoxLayout()
        self.import_btn = QPushButton('IMPORT FROM EXCEL')
        self.import_btn.setProperty('panelActionButton', True)
        self.import_btn.clicked.connect(self.import_excel)

        self.export_btn = QPushButton('EXPORT TO EXCEL')
        self.export_btn.setProperty('panelActionButton', True)
        self.export_btn.setProperty('primaryAction', True)
        self.export_btn.clicked.connect(self.export_excel)

        btn_row.addWidget(self.import_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addStretch(1)
        card_layout.addLayout(btn_row)

        root.addWidget(card)
        root.addStretch(1)
        self.refresh_database_path_display()

    def refresh_database_path_display(self):
        current = getattr(getattr(self.tool_service, 'db', None), 'path', None)
        if current is not None:
            self.db_path_edit.setText(str(current))

    def _choose_database_file(self):
        current = self.db_path_edit.text().strip() or str(DB_PATH)
        path, _ = QFileDialog.getOpenFileName(self, 'Choose database file', current, 'Database (*.db)')
        if path:
            self.db_path_edit.setText(path)

    def _apply_database_file(self):
        path = self.db_path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, 'Database', 'Select a database file first.')
            return
        if not callable(self.on_database_switched):
            QMessageBox.warning(self, 'Database', 'Database switch callback is not configured.')
            return

        ok, message = self.on_database_switched(path)
        if ok:
            QMessageBox.information(self, 'Database', message)
            self.refresh_database_path_display()
        else:
            QMessageBox.critical(self, 'Database switch failed', message)

    def _create_database_backup(self) -> Path:
        src = Path(getattr(self.tool_service.db, 'path', ''))
        if not src.exists():
            raise FileNotFoundError(f'Current database file not found: {src}')
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = src.with_name(f'{src.stem}_backup_{stamp}{src.suffix}')
        shutil.copy2(src, backup)
        return backup

    def export_excel(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export to Excel', str(EXPORT_DEFAULT_PATH), 'Excel (*.xlsx)')
        if not path:
            return
        try:
            self.export_service.export_tools(path, self.tool_service.list_tools())
            QMessageBox.information(self, 'Export', f'Exported to\n{path}')
        except Exception as exc:
            QMessageBox.critical(self, 'Export failed', str(exc))

    def import_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import from Excel', str(EXPORT_DEFAULT_PATH.parent), 'Excel (*.xlsx *.xlsm)')
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

        dlg = ImportMappingDialog(headers, self)
        if dlg.exec() != QDialog.Accepted:
            return

        mapping = dlg.mapping()
        try:
            tools = self.export_service.import_tools(path, mapping)
        except Exception as exc:
            QMessageBox.critical(self, 'Import failed', str(exc))
            return

        if not tools:
            QMessageBox.information(self, 'Import', 'No valid tool rows found with current mapping.')
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
                    self.tool_service.db.conn.execute('DELETE FROM tools')
                    for tool in tools:
                        self.tool_service.save_tool(tool)
                if callable(self.on_data_changed):
                    self.on_data_changed()
                QMessageBox.information(self, 'Import', f'Imported {len(tools)} tools into current database.')
                return

            db_path = Path(dlg.selected_new_db_path())
            new_db = Database(db_path)
            new_tool_service = ToolService(new_db)
            with new_db.conn:
                new_db.conn.execute('DELETE FROM tools')
            for tool in tools:
                new_tool_service.save_tool(tool)
            new_db.close()
            QMessageBox.information(self, 'Import', f'Imported {len(tools)} tools into new database:\n{db_path}')
        except Exception as exc:
            QMessageBox.critical(self, 'Import failed', str(exc))
