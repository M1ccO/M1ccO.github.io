"""Shared model-table helpers used by tool and jaw editor dialogs.

Provides ``ModelTableMixin`` -- a mixin class that encapsulates the
model-table row management logic (add / remove / move / reorder, color
swatch, path display, transform bookkeeping) shared between
``AddEditToolDialog`` and ``AddEditJawDialog``.

Host requirements -- the dialog mixing this in must provide:

  Attributes:
    model_table              QTableWidget  (3+ columns: name, file, color)
    models_preview           StlPreviewWidget
    _translate               Callable[[str, str | None], str]
    _part_transforms         dict[int, dict]
    _saved_part_transforms   dict[int, dict]
    _assembly_transform_enabled  bool
    _selected_part_index     int

  Methods:
    _t(key, default, **kwargs) -> str
    _models_root()           -> Path   (domain-specific model directory)
    _refresh_models_preview()          (usually delegates to preview controller)
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QTableWidgetItem,
    QWidget,
)

from config import JAW_MODELS_ROOT_DEFAULT, SHARED_UI_PREFERENCES_PATH, TOOL_MODELS_ROOT_DEFAULT
from shared.data.model_paths import format_model_path_for_display, read_model_roots
from ui.widgets.color_picker_dialog import ColorPickerDialog


class ModelTableMixin:
    """Mixin providing model-table row helpers for editor dialogs."""

    # ------------------------------------------------------------------
    # Hook -- override in the dialog for extra refresh after row changes
    # ------------------------------------------------------------------
    def _on_model_list_structure_changed(self):
        """Called after rows are added, removed, or reordered.

        Override in the dialog to perform editor-specific bookkeeping
        (e.g. refreshing measurement-part dropdowns in the tool editor).
        """

    # ------------------------------------------------------------------
    # Color helpers
    # ------------------------------------------------------------------
    def _default_color_for_part_name(self, part_name: str) -> str:
        name = (part_name or '').strip().lower()
        if 'insert' in name:
            return '#c9a227'
        if 'holder' in name:
            return '#9ea7b3'
        if 'clamp' in name:
            return '#6f7780'
        if 'screw' in name:
            return '#2f3338'
        return '#9ea7b3'

    def _set_color_button(self, row: int, color_hex: str):
        container = QWidget()
        container.setStyleSheet('background: transparent;')
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        c_layout = QHBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)

        btn = QPushButton('')
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn.setMinimumSize(0, 0)
        btn.setFlat(True)
        btn.setProperty('colorHex', color_hex)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color_hex};
                border: 1px solid #8a95a0;
                border-radius: 3px;
                padding: 0px;
                margin: 0px;
                min-width: 0px;
                min-height: 0px;
            }}
            QPushButton:hover {{
                border: 1px solid #3d7ab5;
            }}
            QPushButton:pressed {{
                border: 1px solid #1f5f92;
            }}
        """)
        c_layout.addWidget(btn, 1)
        btn.clicked.connect(lambda _checked=False, b=btn: self._choose_model_color(self._row_for_color_button(b)))
        self.model_table.setCellWidget(row, 2, container)

    def _row_for_color_button(self, button: QPushButton) -> int:
        for row in range(self.model_table.rowCount()):
            widget = self.model_table.cellWidget(row, 2)
            if widget is button:
                return row
            if isinstance(widget, QWidget) and widget.findChild(QPushButton) is button:
                return row
        return -1

    def _choose_model_color(self, row: int):
        if row < 0 or row >= self.model_table.rowCount():
            return
        current = self._get_model_row_color(row)
        chosen = ColorPickerDialog.get_color(
            initial_color=current if current else '#9ea7b3',
            parent=self,
            translate=self._translate,
        )
        if chosen is None or not chosen.isValid():
            return
        self._set_color_button(row, chosen.name())
        self._refresh_models_preview()

    def _get_model_row_color(self, row: int) -> str:
        widget = self.model_table.cellWidget(row, 2)
        if isinstance(widget, QPushButton):
            return widget.property('colorHex') or widget.toolTip() or '#9ea7b3'
        if isinstance(widget, QWidget):
            btn = widget.findChild(QPushButton)
            if btn is not None:
                return btn.property('colorHex') or btn.toolTip() or '#9ea7b3'
        item = self.model_table.item(row, 2)
        return item.text().strip() if item else '#9ea7b3'

    # ------------------------------------------------------------------
    # Row data
    # ------------------------------------------------------------------
    def _set_model_row(self, row: int, name: str = '', stl_file: str = '', color_hex: str = ''):
        self.model_table.blockSignals(True)
        name_item = QTableWidgetItem(name)
        file_item = QTableWidgetItem(self._display_model_path(stl_file))
        file_item.setData(Qt.UserRole, stl_file)
        self.model_table.setItem(row, 0, name_item)
        self.model_table.setItem(row, 1, file_item)
        self._set_color_button(row, color_hex or self._default_color_for_part_name(name))
        self.model_table.blockSignals(False)

    def _guess_part_name_from_file(self, file_path: str) -> str:
        base = os.path.splitext(os.path.basename(file_path))[0]
        pretty = base.replace('_', ' ').replace('-', ' ').strip()
        return pretty.title() if pretty else self._t('tool_editor.model.default_name', 'Model')

    def _display_model_path(self, raw_path: str) -> str:
        tools_models_root, jaws_models_root = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            JAW_MODELS_ROOT_DEFAULT,
        )
        return format_model_path_for_display(raw_path, tools_models_root, jaws_models_root)

    @staticmethod
    def _stored_model_path(item: QTableWidgetItem | None) -> str:
        if item is None:
            return ''
        raw_value = item.data(Qt.UserRole)
        if raw_value is None:
            return item.text().strip()
        return str(raw_value).strip()

    # ------------------------------------------------------------------
    # Row CRUD
    # ------------------------------------------------------------------
    def _add_model_row(self, checked=False, values=None):
        if isinstance(checked, dict) and values is None:
            values = checked

        if values is None:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                self._t('tool_editor.dialog.select_stl_model', 'Select STL model'),
                str(self._models_root()),
                self._t('jaw_editor.dialog.stl_filter', 'STL Files (*.stl)'),
            )
            if not file_path:
                return
            values = {
                'name': self._guess_part_name_from_file(file_path),
                'file': file_path,
                'color': '',
            }

        row = self.model_table.rowCount()
        self.model_table.insertRow(row)
        name = values.get('name', '')
        stl_file = values.get('file', '')
        color_hex = values.get('color', '') or self._default_color_for_part_name(name)
        self._set_model_row(row, name, stl_file, color_hex)
        self.model_table.setCurrentCell(row, 0)
        self._on_model_list_structure_changed()
        self._refresh_models_preview()

    def _remove_model_row(self):
        row = self.model_table.currentRow()
        if row < 0:
            return
        self.model_table.removeRow(row)
        self._on_model_list_structure_changed()
        self._refresh_models_preview()

    def _model_table_rows(self):
        rows = []
        for row in range(self.model_table.rowCount()):
            name_item = self.model_table.item(row, 0)
            file_item = self.model_table.item(row, 1)
            rows.append({
                'name': name_item.text().strip() if name_item else '',
                'file': self._stored_model_path(file_item),
                'color': self._get_model_row_color(row),
            })
        return rows

    def _restore_model_rows(self, rows, selected_row: int | None = None):
        self.model_table.blockSignals(True)
        self.model_table.setRowCount(0)
        for idx, row_data in enumerate(rows):
            self.model_table.insertRow(idx)
            self._set_model_row(
                idx,
                row_data.get('name', ''),
                row_data.get('file', ''),
                row_data.get('color', ''),
            )
        self.model_table.blockSignals(False)
        self._on_model_list_structure_changed()
        if selected_row is not None and 0 <= selected_row < self.model_table.rowCount():
            self.model_table.selectRow(selected_row)

    def _move_model_row(self, delta: int):
        row = self.model_table.currentRow()
        if row < 0:
            return
        target = row + int(delta)
        if target < 0 or target >= self.model_table.rowCount() or target == row:
            return

        rows_with_index = []
        for idx, row_data in enumerate(self._model_table_rows()):
            rows_with_index.append({'old_index': idx, 'data': row_data})
        moved = rows_with_index.pop(row)
        rows_with_index.insert(target, moved)

        self._restore_model_rows([entry['data'] for entry in rows_with_index], selected_row=target)

        old_transforms = dict(self._part_transforms)
        old_saved_transforms = dict(self._saved_part_transforms)
        new_transforms = {}
        new_saved_transforms = {}
        for new_idx, entry in enumerate(rows_with_index):
            old_idx = entry['old_index']
            transform = old_transforms.get(old_idx)
            if isinstance(transform, dict):
                new_transforms[new_idx] = dict(transform)
            saved_transform = old_saved_transforms.get(old_idx)
            if isinstance(saved_transform, dict):
                new_saved_transforms[new_idx] = dict(saved_transform)
        self._part_transforms = new_transforms
        self._saved_part_transforms = new_saved_transforms

        self._selected_part_index = target
        if self._assembly_transform_enabled:
            self.models_preview.select_part(target)
        self._refresh_models_preview()

    # ------------------------------------------------------------------
    # Table-change handler
    # ------------------------------------------------------------------
    def _on_model_table_changed(self, item):
        if item.column() == 1:
            item.setData(Qt.UserRole, item.text().strip())
        if item.column() == 0:
            row = item.row()
            current_color = self._get_model_row_color(row)
            if not current_color or current_color == '#9ea7b3':
                self._set_color_button(row, self._default_color_for_part_name(item.text().strip()))
            self._on_model_list_structure_changed()
        self._refresh_models_preview()

    # ------------------------------------------------------------------
    # Parts payload
    # ------------------------------------------------------------------
    def _model_table_to_parts(self):
        result = []
        for row in range(self.model_table.rowCount()):
            name_item = self.model_table.item(row, 0)
            file_item = self.model_table.item(row, 1)
            name = name_item.text().strip() if name_item else ''
            stl_file = self._stored_model_path(file_item)
            color = self._get_model_row_color(row)
            if name or stl_file:
                part = {
                    'name': name,
                    'file': stl_file,
                    'color': color or self._default_color_for_part_name(name),
                }
                t = self._part_transforms.get(row, {})
                if any(t.get(k, 0) != 0 for k in ('x', 'y', 'z', 'rx', 'ry', 'rz')):
                    part['offset_x'] = t.get('x', 0)
                    part['offset_y'] = t.get('y', 0)
                    part['offset_z'] = t.get('z', 0)
                    part['rot_x'] = t.get('rx', 0)
                    part['rot_y'] = t.get('ry', 0)
                    part['rot_z'] = t.get('rz', 0)
                result.append(part)
        return result

