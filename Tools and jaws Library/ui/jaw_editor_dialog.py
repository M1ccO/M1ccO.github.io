import json
import os
from typing import Callable

from PySide6.QtCore import QEvent, Qt, QTimer, QSize, QEventLoop
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QTableWidgetItem,
)

from config import JAW_MODELS_ROOT_DEFAULT, SHARED_UI_PREFERENCES_PATH, TOOL_ICONS_DIR, TOOL_MODELS_ROOT_DEFAULT
from shared.editor_helpers import (
    apply_secondary_button_theme,
    build_editor_field_card,
    build_editor_field_group,
    create_dialog_buttons,
    focus_editor_widget,
    setup_editor_dialog,
)
from shared.model_paths import format_model_path_for_display, read_model_roots
from ui.jaw_editor_support import build_models_tab
from ui.measurement_editor_dialog import MeasurementEditorDialog
from ui.shared.preview_controller import EditorPreviewController
from ui.tool_editor_support.measurement_rules import (
    empty_measurement_editor_state,
    measurement_overlays_from_state,
    normalize_measurement_editor_state,
    parse_measurement_overlays,
)
from ui.tool_editor_support.transform_rules import (
    all_part_transforms_payload,
    compact_transform_dict,
    normalize_transform_dict,
)
from ui.widgets.color_picker_dialog import ColorPickerDialog
from ui.widgets.common import apply_shared_dropdown_style, clear_focused_dropdown_on_outside_click


class AddEditJawDialog(QDialog):
    JAW_TYPES = ['Soft jaws', 'Hard jaws', 'Spiked jaws', 'Special jaws']
    SPINDLE_SIDES = ['Main spindle', 'Sub spindle', 'Both']

    def __init__(
        self,
        parent=None,
        jaw=None,
        translate: Callable[[str, str | None], str] | None = None,
        batch_label: str | None = None,
        group_edit_mode: bool = False,
        group_count: int | None = None,
    ):
        super().__init__(parent)
        self.jaw = jaw or {}
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self._batch_label = (batch_label or '').strip()
        self._group_edit_mode = bool(group_edit_mode)
        self._group_count = int(group_count or 0)
        self._general_field_columns = None

        self._assembly_transform_enabled = self._is_assembly_transform_enabled()
        self._part_transforms: dict[int, dict] = {}
        self._saved_part_transforms: dict[int, dict] = {}
        self._measurement_editor_state = self._empty_measurement_editor_state()
        self._current_transform_mode = 'translate'
        self._fine_transform_enabled = False
        self._selected_part_index = -1
        self._selected_part_indices: list[int] = []
        self._suspend_preview_refresh = False
        self._preview_controller = EditorPreviewController(self)
        self._clamping_screen_bounds = False

        self.setWindowTitle(self._dialog_title())
        self.resize(1120, 760)
        self.setMinimumSize(900, 660)
        self.setModal(True)
        setup_editor_dialog(self)
        self._build_ui()
        self._load_jaw()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _dialog_title(self) -> str:
        if self._group_edit_mode:
            if self._group_count > 1:
                return self._t(
                    'jaw_editor.window_title.group',
                    'Group Edit ({count} items)',
                    count=self._group_count,
                )
            return self._t('jaw_editor.window_title.group', 'Group Edit')
        jaw_id = self.jaw.get('jaw_id', '').strip()
        if jaw_id:
            base = self._t('jaw_editor.window_title.edit', 'Edit Jaw - {jaw_id}', jaw_id=jaw_id)
        else:
            base = self._t('jaw_editor.window_title.add', 'Add Jaw')
        if self._batch_label:
            return f"{base} ({self._batch_label})"
        return base

    def _localized_jaw_type(self, raw: str) -> str:
        normalized = (raw or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.jaw_type.{normalized}', raw)

    def _localized_spindle_side(self, raw: str) -> str:
        normalized = (raw or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.spindle_side.{normalized}', raw)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: str):
        target = (value or '').strip()
        for idx in range(combo.count()):
            if (combo.itemData(idx) or '').strip() == target:
                combo.setCurrentIndex(idx)
                return

    def _build_ui(self):
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_general_tab(), self._t('jaw_editor.tab.general', 'General'))
        build_models_tab(self, self.tabs)

        self._dialog_buttons = create_dialog_buttons(
            self,
            save_text=self._t('jaw_editor.action.save_jaw', 'SAVE JAW'),
            cancel_text=self._t('common.cancel', 'Cancel').upper(),
            on_save=self.accept,
            on_cancel=self.reject,
        )
        self._save_btn = self._dialog_buttons.button(QDialogButtonBox.Save)
        root.addWidget(self._dialog_buttons)
        apply_secondary_button_theme(self, self._save_btn)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            clear_focused_dropdown_on_outside_click(obj, self)
        if obj is getattr(self, '_reset_transform_btn', None):
            if event.type() == QEvent.MouseButtonPress and hasattr(event, 'button') and event.button() == Qt.RightButton:
                self._reset_current_part_transform(target='saved')
                return True
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)

    def _build_general_tab(self):
        tab = QWidget()
        tab.setProperty('editorPageSurface', True)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        self.general_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(scroll, 1)

        general_content = QWidget()
        general_content.setProperty('editorFieldsViewport', True)
        general_content.setProperty('editorPageSurface', True)
        general_content_layout = QVBoxLayout(general_content)
        general_content_layout.setContentsMargins(0, 0, 0, 0)
        general_content_layout.setSpacing(0)
        scroll.setWidget(general_content)

        form_frame = QFrame()
        form_frame.setProperty('subCard', True)
        form_layout = QVBoxLayout(form_frame)
        form_layout.setContentsMargins(14, 14, 14, 14)
        form_layout.setSpacing(10)

        header = QFrame()
        header.setProperty('detailHeader', True)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        self.header_title = QLabel(self._t('jaw_editor.header.new_jaw', 'New jaw'))
        self.header_title.setProperty('detailHeroTitle', True)
        self.header_title.setWordWrap(True)
        self.header_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.header_id = QLabel('')
        self.header_id.setProperty('detailHeroTitle', True)
        self.header_id.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title_row.addWidget(self.header_title, 1)
        title_row.addWidget(self.header_id, 0, Qt.AlignRight)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        self.type_badge = QLabel('')
        self.type_badge.setProperty('toolBadge', True)
        meta_row.addWidget(self.type_badge, 0, Qt.AlignLeft)
        meta_row.addStretch(1)

        header_layout.addLayout(title_row)
        header_layout.addLayout(meta_row)
        form_layout.addWidget(header)

        self.jaw_id = QLineEdit()
        self.jaw_type = QComboBox()
        for raw_type in self.JAW_TYPES:
            self.jaw_type.addItem(self._localized_jaw_type(raw_type), raw_type)
        self.spindle_side = QComboBox()
        for raw_side in self.SPINDLE_SIDES:
            self.spindle_side.addItem(self._localized_spindle_side(raw_side), raw_side)
        self.clamping_diameter_text = QLineEdit()
        self.clamping_length = QLineEdit()
        self.turning_washer = QLineEdit()
        self.last_modified = QLineEdit()
        self.notes = QLineEdit()

        self.clamping_diameter_text.setPlaceholderText(self._t('jaw_editor.placeholder.clamping_diameter', '52.40 mm or 50-58 mm'))
        self.clamping_length.setPlaceholderText(self._t('jaw_editor.placeholder.clamping_length', 'e.g. 24.0 mm'))

        self._style_combo(self.jaw_type)
        self._style_combo(self.spindle_side)
        self.jaw_type.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.jaw_type.setMinimumWidth(180)
        self.spindle_side.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.spindle_side.setMinimumWidth(180)

        group1 = self._build_field_group([
            self._build_edit_field(self._t('jaw_library.field.jaw_id', 'Jaw ID'), self.jaw_id),
            self._build_edit_field(self._t('jaw_library.field.jaw_type', 'Jaw type'), self.jaw_type),
            self._build_edit_field(self._t('jaw_library.field.spindle_side', 'Spindle side'), self.spindle_side),
        ])
        group2 = self._build_field_group([
            self._build_edit_field(self._t('jaw_library.field.clamping_diameter', 'Clamping diameter'), self.clamping_diameter_text),
            self._build_edit_field(self._t('jaw_library.field.clamping_length', 'Clamping length'), self.clamping_length),
            self._build_edit_field(self._t('jaw_library.field.turning_ring', 'Turning ring'), self.turning_washer),
        ])
        self._last_modified_field = self._build_edit_field(self._t('jaw_library.field.last_modified', 'Last modified'), self.last_modified)
        group3 = self._build_field_group([
            self._last_modified_field,
            self._build_edit_field(self._t('jaw_library.field.notes', 'Notes'), self.notes),
        ])

        form_layout.addWidget(group1)
        form_layout.addWidget(group2)
        form_layout.addWidget(group3)
        general_content_layout.addWidget(form_frame)
        general_content_layout.addStretch(1)

        self.jaw_id.textChanged.connect(self._update_header)
        self.jaw_type.currentTextChanged.connect(self._update_header)
        self.jaw_type.currentTextChanged.connect(self._update_spiked_fields)
        self._update_header()
        self._update_spiked_fields()
        return tab

    def _update_spiked_fields(self):
        is_spiked = (self.jaw_type.currentData() or '') == 'Spiked jaws'
        self._last_modified_field.setVisible(not is_spiked)

    def _build_edit_field(self, title: str, editor: QWidget) -> QFrame:
        return build_editor_field_card(
            title,
            editor,
            label_min_width=200,
            label_max_width=200,
            label_word_wrap=True,
            label_top_align=True,
            focus_handler=self._focus_editor,
        )

    def _build_field_group(self, fields: list) -> QFrame:
        return build_editor_field_group(fields)

    def _focus_editor(self, widget: QWidget):
        focus_editor_widget(widget)

    def _style_combo(self, combo: QComboBox):
        apply_shared_dropdown_style(combo)

    def _is_assembly_transform_enabled(self) -> bool:
        try:
            with open(SHARED_UI_PREFERENCES_PATH, 'r', encoding='utf-8') as f:
                prefs = json.load(f)
            return bool(prefs.get('enable_assembly_transform', False))
        except Exception:
            return False

    def _empty_measurement_editor_state(self):
        return empty_measurement_editor_state()

    def _normalize_measurement_editor_state(self, data):
        return normalize_measurement_editor_state(data)

    def _load_measurement_overlays(self, overlays):
        self._measurement_editor_state = parse_measurement_overlays(overlays)
        self._update_measurement_summary_label()

    def _measurement_overlays_from_tables(self):
        return measurement_overlays_from_state(
            self._measurement_editor_state,
            translate=lambda key, default: self._t(key, default),
        )

    def _update_measurement_summary_label(self):
        if not hasattr(self, 'measurement_summary_label'):
            return
        total = sum(len(items) for items in self._measurement_editor_state.values())
        if total <= 0:
            self.measurement_summary_label.setText(
                self._t('tool_editor.measurements.none', 'No measurements configured')
            )
            return
        self.measurement_summary_label.setText(
            self._t('tool_editor.measurements.count', '{count} measurements configured', count=total)
        )

    def _open_measurement_editor(self):
        dialog = MeasurementEditorDialog(
            tool_data=self._normalize_measurement_editor_state(self._measurement_editor_state),
            parts=self._model_table_to_parts(),
            parent=self,
            translate=self._translate,
        )
        dialog.resize(max(dialog.width(), 1180), max(dialog.height(), 780))
        dialog.setMinimumSize(980, 700)
        if dialog.exec() != QDialog.Accepted:
            return
        self._measurement_editor_state = self._normalize_measurement_editor_state(dialog.get_measurements())
        self._update_measurement_summary_label()
        self._refresh_models_preview()

    def _update_header(self):
        jaw_id = self.jaw_id.text().strip()
        self.header_title.setText(
            self._t('jaw_editor.header.new_jaw', 'New jaw')
            if not jaw_id
            else self._t('jaw_editor.header.jaw_with_id', 'Jaw {jaw_id}', jaw_id=jaw_id)
        )
        self.header_id.setText(jaw_id)
        self.type_badge.setText(self.jaw_type.currentText())

    def _load_jaw(self):
        if not self.jaw:
            self._update_measurement_summary_label()
            return
        self.jaw_id.setText(self.jaw.get('jaw_id', ''))
        self._set_combo_by_data(self.jaw_type, self.jaw.get('jaw_type', 'Soft jaws'))
        self._set_combo_by_data(self.spindle_side, self.jaw.get('spindle_side', 'Main spindle'))
        self.clamping_diameter_text.setText(self.jaw.get('clamping_diameter_text', ''))
        self.clamping_length.setText(self.jaw.get('clamping_length', ''))
        self.turning_washer.setText(self.jaw.get('turning_washer', ''))
        self.last_modified.setText(self.jaw.get('last_modified', ''))
        self.notes.setText(self.jaw.get('notes', ''))

        raw_models = self.jaw.get('stl_path', '')
        model_parts = []
        if isinstance(raw_models, list):
            model_parts = raw_models
        elif isinstance(raw_models, str) and raw_models.strip():
            try:
                parsed = json.loads(raw_models)
                if isinstance(parsed, list):
                    model_parts = parsed
                elif isinstance(parsed, str):
                    model_parts = [{'name': self._t('tool_editor.model.default_name', 'Model'), 'file': parsed, 'color': '#9ea7b3'}]
            except Exception:
                model_parts = [{'name': self._t('tool_editor.model.default_name', 'Model'), 'file': raw_models, 'color': '#9ea7b3'}]

        self._suspend_preview_refresh = True
        try:
            for part in model_parts:
                if not isinstance(part, dict):
                    continue
                self._add_model_row(
                    {
                        'name': str(part.get('name', '') or ''),
                        'file': str(part.get('file', '') or ''),
                        'color': str(part.get('color', '') or ''),
                    }
                )
        finally:
            self._suspend_preview_refresh = False

        self._part_transforms = {}
        self._saved_part_transforms = {}
        for index, part in enumerate(model_parts):
            if not isinstance(part, dict):
                continue
            transform = {
                'x': part.get('offset_x', 0),
                'y': part.get('offset_y', 0),
                'z': part.get('offset_z', 0),
                'rx': part.get('rot_x', 0),
                'ry': part.get('rot_y', 0),
                'rz': part.get('rot_z', 0),
            }
            compact = compact_transform_dict(normalize_transform_dict(transform))
            if compact:
                self._part_transforms[index] = dict(compact)
                self._saved_part_transforms[index] = dict(compact)

        self._load_measurement_overlays(self.jaw.get('measurement_overlays', []))

        selected_parts = []
        raw_selected_parts = self.jaw.get('preview_selected_parts', [])
        if isinstance(raw_selected_parts, str):
            try:
                raw_selected_parts = json.loads(raw_selected_parts)
            except Exception:
                raw_selected_parts = []
        if isinstance(raw_selected_parts, list):
            for value in raw_selected_parts:
                try:
                    idx = int(value)
                except Exception:
                    continue
                if idx >= 0:
                    selected_parts.append(idx)
        if not selected_parts:
            try:
                one = int(self.jaw.get('preview_selected_part', -1) or -1)
            except Exception:
                one = -1
            if one >= 0:
                selected_parts = [one]
        self._selected_part_indices = selected_parts
        self._selected_part_index = selected_parts[-1] if selected_parts else -1

        mode = str(self.jaw.get('preview_transform_mode', 'translate') or 'translate').strip().lower()
        self._current_transform_mode = mode if mode in {'translate', 'rotate'} else 'translate'
        self._fine_transform_enabled = bool(self.jaw.get('preview_fine_transform', False))

        self._refresh_models_preview()
        self._update_mode_toggle_button_appearance()
        self._update_fine_transform_button_appearance()
        self._refresh_transform_selection_state()
        if self._assembly_transform_enabled and self._selected_part_indices:
            self.models_preview.select_parts(self._selected_part_indices)
        self._update_header()

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
        btn.setStyleSheet(
            f"""
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
            """
        )
        c_layout.addWidget(btn, 1)
        btn.clicked.connect(lambda _, r=row: self._choose_model_color(r))
        self.model_table.setCellWidget(row, 2, container)

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

    def _jaws_models_root(self):
        _, jaws_models_root = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            JAW_MODELS_ROOT_DEFAULT,
        )
        jaws_models_root.mkdir(parents=True, exist_ok=True)
        return jaws_models_root

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

    def _add_model_row(self, checked=False, values=None):
        if isinstance(checked, dict) and values is None:
            values = checked
        if values is None:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                self._t('tool_editor.dialog.select_stl_model', 'Select STL model'),
                str(self._jaws_models_root()),
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
        self._refresh_models_preview()

    def _remove_model_row(self):
        row = self.model_table.currentRow()
        if row < 0:
            return
        self.model_table.removeRow(row)
        self._refresh_models_preview()

    def _model_table_rows(self):
        rows = []
        for row in range(self.model_table.rowCount()):
            name_item = self.model_table.item(row, 0)
            file_item = self.model_table.item(row, 1)
            rows.append(
                {
                    'name': name_item.text().strip() if name_item else '',
                    'file': self._stored_model_path(file_item),
                    'color': self._get_model_row_color(row),
                }
            )
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

    def _on_model_table_changed(self, item):
        if item.column() == 1:
            item.setData(Qt.UserRole, item.text().strip())
        if item.column() == 0:
            row = item.row()
            current_color = self._get_model_row_color(row)
            if not current_color or current_color == '#9ea7b3':
                self._set_color_button(row, self._default_color_for_part_name(item.text().strip()))
        self._refresh_models_preview()

    def _model_table_to_parts(self):
        result = []
        for row in range(self.model_table.rowCount()):
            name_item = self.model_table.item(row, 0)
            file_item = self.model_table.item(row, 1)
            name = name_item.text().strip() if name_item else ''
            stl_file = self._stored_model_path(file_item)
            color = self._get_model_row_color(row)
            if name or stl_file:
                part = {'name': name, 'file': stl_file, 'color': color or self._default_color_for_part_name(name)}
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

    def _refresh_models_preview(self):
        if self._suspend_preview_refresh:
            return
        parts = self._model_table_to_parts()
        self._preview_controller.refresh_embedded_models_preview(
            parts,
            transform_edit_enabled=bool(self._assembly_transform_enabled),
            measurement_overlays=[],
            measurements_visible=False,
            measurement_drag_enabled=False,
        )

    def _on_viewer_transform_changed(self, index: int, transform: dict):
        self._part_transforms[index] = compact_transform_dict(normalize_transform_dict(transform))
        if index in self._selected_part_indices:
            self._refresh_transform_selection_state()

    def _on_viewer_part_selected(self, index: int):
        self._preview_controller.on_viewer_part_selected(index)

    def _on_viewer_part_selection_changed(self, indices: list[int]):
        self._preview_controller.on_viewer_part_selection_changed(indices)

    def _sync_model_table_selection(self):
        self._preview_controller.sync_model_table_selection()

    def _saved_transform_for_index(self, index: int) -> dict:
        return normalize_transform_dict(self._saved_part_transforms.get(index, {}))

    def _apply_preview_transforms_snapshot(self, snapshot, *, refresh_selection: bool = False) -> bool:
        if not isinstance(snapshot, list):
            return False
        row_count = self.model_table.rowCount() if hasattr(self, 'model_table') else 0
        if row_count <= 0:
            return False
        transformed = {}
        upper = min(row_count, len(snapshot))
        for index in range(upper):
            raw = snapshot[index]
            if not isinstance(raw, dict):
                continue
            compact = compact_transform_dict(normalize_transform_dict(raw))
            if compact:
                transformed[index] = compact
        self._part_transforms = transformed
        if refresh_selection:
            self._refresh_transform_selection_state()
        return True

    def _request_preview_transform_snapshot(self, *, refresh_selection: bool = False):
        if not self._assembly_transform_enabled or not hasattr(self, 'models_preview'):
            return
        try:
            self.models_preview.get_part_transforms(
                lambda snapshot: self._apply_preview_transforms_snapshot(snapshot, refresh_selection=refresh_selection)
            )
        except Exception:
            return

    def _sync_preview_transform_snapshot_for_save(self, timeout_ms: int = 350):
        if not self._assembly_transform_enabled or not hasattr(self, 'models_preview'):
            return
        result_holder = {'snapshot': None, 'done': False}
        loop = QEventLoop(self)
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)

        def _on_snapshot(snapshot):
            result_holder['snapshot'] = snapshot
            result_holder['done'] = True
            loop.quit()

        try:
            self.models_preview.get_part_transforms(_on_snapshot)
        except Exception:
            return
        timer.start(max(100, int(timeout_ms)))
        loop.exec()
        timer.stop()
        if result_holder['done']:
            self._apply_preview_transforms_snapshot(result_holder['snapshot'])

    def _refresh_transform_selection_state(self):
        count = len(self._selected_part_indices)
        single_selected = count == 1 and self._selected_part_index >= 0
        for widget in (self._transform_x, self._transform_y, self._transform_z):
            widget.setEnabled(single_selected)

        if count == 0:
            self.models_preview.set_selection_caption(None)
            self._transform_x.setText('0')
            self._transform_y.setText('0')
            self._transform_z.setText('0')
            self._reset_transform_btn.setEnabled(False)
            return

        self._reset_transform_btn.setEnabled(True)
        if single_selected:
            index = self._selected_part_index
            name_item = self.model_table.item(index, 0)
            name = name_item.text().strip() if name_item else f'Part {index + 1}'
            self.models_preview.set_selection_caption(name or f'Part {index + 1}')
            self._update_transform_fields(self._part_transforms.get(index, {}))
            return
        self.models_preview.set_selection_caption(
            self._t('tool_editor.preview.selection_count', '{count} models selected', count=count)
        )
        self._update_transform_fields(self._part_transforms.get(self._selected_part_index, {}))

    def _update_transform_fields(self, transform: dict):
        view_t = normalize_transform_dict(transform)
        if self._current_transform_mode == 'translate':
            self._transform_x.setText(str(view_t.get('x', 0)))
            self._transform_y.setText(str(view_t.get('y', 0)))
            self._transform_z.setText(str(view_t.get('z', 0)))
        else:
            self._transform_x.setText(str(view_t.get('rx', 0)))
            self._transform_y.setText(str(view_t.get('ry', 0)))
            self._transform_z.setText(str(view_t.get('rz', 0)))

    def _update_transform_row_sizes(self):
        if not hasattr(self, '_transform_x'):
            return
        btn_w = 42
        edit_w = 80
        self._mode_toggle_btn.setFixedWidth(btn_w)
        self._fine_transform_btn.setFixedWidth(btn_w)
        self._reset_transform_btn.setFixedWidth(btn_w)
        self._mode_toggle_btn.setIconSize(QSize(18, 18))
        self._fine_transform_btn.setIconSize(QSize(18, 18))
        self._reset_transform_btn.setIconSize(QSize(18, 18))
        self._transform_x.setFixedWidth(edit_w)
        self._transform_y.setFixedWidth(edit_w)
        self._transform_z.setFixedWidth(edit_w)

    def _on_mode_toggle_clicked(self):
        self._set_gizmo_mode('translate' if self._mode_toggle_btn.isChecked() else 'rotate')

    def _set_gizmo_mode(self, mode: str):
        self._current_transform_mode = mode
        self._update_mode_toggle_button_appearance()
        self.models_preview.set_transform_mode(mode)
        self._refresh_transform_selection_state()

    def _update_mode_toggle_button_appearance(self):
        if not hasattr(self, '_mode_toggle_btn'):
            return
        is_translate = self._current_transform_mode == 'translate'
        next_icon = 'rotate.svg' if is_translate else 'move.svg'
        tooltip = (
            self._t('tool_editor.transform.switch_to_rotate', 'Click to rotate')
            if is_translate
            else self._t('tool_editor.transform.switch_to_move', 'Click to move')
        )
        self._mode_toggle_btn.setChecked(is_translate)
        self._mode_toggle_btn.setText('')
        self._mode_toggle_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / next_icon)))
        self._mode_toggle_btn.setToolTip(tooltip)
        self._update_transform_row_sizes()

    def _update_fine_transform_button_appearance(self):
        if not hasattr(self, '_fine_transform_btn'):
            return
        icon_name = '1x.svg' if self._fine_transform_enabled else 'fine_tune.svg'
        tooltip = (
            self._t('tool_editor.transform.disable_fine', 'Click for 1x step')
            if self._fine_transform_enabled
            else self._t('tool_editor.transform.enable_fine', 'Click to fine tune')
        )
        self._fine_transform_btn.setText('')
        self._fine_transform_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
        self._fine_transform_btn.setIconSize(QSize(18, 18))
        self._fine_transform_btn.setToolTip(tooltip)
        self._update_transform_row_sizes()

    def _on_fine_transform_toggled(self, checked: bool):
        self._fine_transform_enabled = bool(checked)
        self._update_fine_transform_button_appearance()
        self.models_preview.set_fine_transform_enabled(self._fine_transform_enabled)

    def _reset_current_part_transform(self, target: str = 'origin'):
        if self._selected_part_index < 0:
            return
        indices = self._selected_part_indices or [self._selected_part_index]
        if target == 'saved':
            for idx in indices:
                baseline = self._saved_transform_for_index(idx)
                self._part_transforms[idx] = compact_transform_dict(baseline)
            self.models_preview.set_part_transforms(
                all_part_transforms_payload(self._part_transforms, self.model_table.rowCount())
            )
            self._refresh_transform_selection_state()
            return
        self.models_preview.reset_selected_part_transform()

    def _apply_manual_transform(self):
        if len(self._selected_part_indices) != 1 or self._selected_part_index < 0:
            return
        try:
            vx = float(self._transform_x.text().replace(',', '.'))
            vy = float(self._transform_y.text().replace(',', '.'))
            vz = float(self._transform_z.text().replace(',', '.'))
        except ValueError:
            return
        index = self._selected_part_index
        transform = normalize_transform_dict(self._part_transforms.get(index, {}))
        if self._current_transform_mode == 'translate':
            transform['x'] = vx
            transform['y'] = vy
            transform['z'] = vz
        else:
            transform['rx'] = vx
            transform['ry'] = vy
            transform['rz'] = vz
        self._part_transforms[index] = compact_transform_dict(transform)
        self.models_preview.set_part_transforms(
            all_part_transforms_payload(self._part_transforms, self.model_table.rowCount())
        )

    def _on_model_table_selection_changed(self):
        if not self._assembly_transform_enabled:
            return
        selection_model = self.model_table.selectionModel() if hasattr(self, 'model_table') else None
        if selection_model is None:
            return
        rows = sorted(index.row() for index in selection_model.selectedRows())
        self._selected_part_indices = rows
        self._selected_part_index = rows[-1] if rows else -1
        self._refresh_transform_selection_state()
        self.models_preview.select_parts(rows)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_transform_row_sizes()
        self._ensure_on_screen()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_transform_row_sizes()
        self._ensure_on_screen()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._ensure_on_screen()

    def _ensure_on_screen(self):
        if self._clamping_screen_bounds:
            return
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or self.screen()
        if screen is None:
            return
        self._clamping_screen_bounds = True
        try:
            available = screen.availableGeometry()
            geom = self.frameGeometry()
            frame_w_extra = max(0, geom.width() - self.width())
            frame_h_extra = max(0, geom.height() - self.height())
            max_client_w = max(320, available.width() - frame_w_extra)
            max_client_h = max(260, available.height() - frame_h_extra)

            width = min(self.width(), max_client_w)
            height = min(self.height(), max_client_h)
            if width != self.width() or height != self.height():
                self.resize(width, height)
                geom = self.frameGeometry()

            x = min(max(geom.x(), available.left()), available.right() - geom.width() + 1)
            y = min(max(geom.y(), available.top()), available.bottom() - geom.height() + 1)
            if x != geom.x() or y != geom.y():
                self.move(x, y)
        finally:
            self._clamping_screen_bounds = False

    def get_jaw_data(self):
        self._sync_preview_transform_snapshot_for_save()
        parts = self._model_table_to_parts()
        jaw = {
            'jaw_id': self.jaw_id.text().strip(),
            'jaw_type': self.jaw_type.currentData() or self.jaw_type.currentText(),
            'spindle_side': self.spindle_side.currentData() or self.spindle_side.currentText(),
            'clamping_diameter_text': self.clamping_diameter_text.text().strip(),
            'clamping_length': self.clamping_length.text().strip(),
            'used_in_work': '',
            'turning_washer': self.turning_washer.text().strip(),
            'last_modified': self.last_modified.text().strip(),
            'notes': self.notes.text().strip(),
            'stl_path': json.dumps(parts) if parts else '',
            'measurement_overlays': self._measurement_overlays_from_tables(),
            'preview_selected_part': self._selected_part_index,
            'preview_selected_parts': [idx for idx in self._selected_part_indices if isinstance(idx, int) and idx >= 0],
            'preview_transform_mode': self._current_transform_mode,
            'preview_fine_transform': bool(self._fine_transform_enabled),
        }

        if not jaw['jaw_id'] and not self._group_edit_mode:
            raise ValueError(self._t('jaw_editor.error.jaw_id_required', 'Jaw ID is required.'))
        if jaw['jaw_type'] not in self.JAW_TYPES:
            raise ValueError(self._t('jaw_editor.error.jaw_type_invalid', 'Jaw type is invalid.'))
        if jaw['spindle_side'] not in self.SPINDLE_SIDES:
            raise ValueError(self._t('jaw_editor.error.spindle_side_invalid', 'Spindle side is invalid.'))
        return jaw

    def accept(self):
        try:
            self.get_jaw_data()
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))
            return
        super().accept()
