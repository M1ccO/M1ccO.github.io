from typing import Callable

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QComboBox,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import JAW_MODELS_ROOT_DEFAULT, SHARED_UI_PREFERENCES_PATH, TOOL_MODELS_ROOT_DEFAULT
from shared.model_paths import read_model_roots
from ui.stl_preview import StlPreviewWidget
from ui.widgets.common import clear_focused_dropdown_on_outside_click, apply_shared_dropdown_style
from shared.editor_helpers import (
    add_shadow,
    setup_editor_dialog,
    create_dialog_buttons,
    apply_secondary_button_theme,
    build_editor_field_card,
    build_editor_field_group,
    focus_editor_widget,
)


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
        self._preview_rotation_steps = {'x': 0, 'y': 0, 'z': 0}
        self.setWindowTitle(self._dialog_title())
        self.resize(920, 640)
        self.setMinimumSize(820, 540)
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
        self.tabs.addTab(self._build_model_tab(), self._t('jaw_editor.tab.model', '3D Model'))

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

        # Header
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

        # Build field widgets
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

        for w in [
            self.jaw_id, self.jaw_type, self.spindle_side,
            self.clamping_diameter_text, self.clamping_length,
            self.turning_washer, self.last_modified,
            self.notes,
        ]:
            self._style_field_editor(w)

        # Group 1: Identity
        group1 = self._build_field_group([
            self._build_edit_field(self._t('jaw_library.field.jaw_id', 'Jaw ID'), self.jaw_id),
            self._build_edit_field(self._t('jaw_library.field.jaw_type', 'Jaw type'), self.jaw_type),
            self._build_edit_field(self._t('jaw_library.field.spindle_side', 'Spindle side'), self.spindle_side),
        ])

        # Group 2: Clamping geometry
        group2 = self._build_field_group([
            self._build_edit_field(self._t('jaw_library.field.clamping_diameter', 'Clamping diameter'), self.clamping_diameter_text),
            self._build_edit_field(self._t('jaw_library.field.clamping_length', 'Clamping length'), self.clamping_length),
            self._build_edit_field(self._t('jaw_library.field.turning_ring', 'Turning ring'), self.turning_washer),
        ])

        # Group 3: Meta
        self._last_modified_field = self._build_edit_field(self._t('jaw_library.field.last_modified', 'Last modified'), self.last_modified)
        group3 = self._build_field_group([
            self._last_modified_field,
            self._build_edit_field(self._t('jaw_library.field.notes', 'Notes'), self.notes),
        ])

        self._general_field_order = []  # kept for compatibility

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

    def _style_field_editor(self, editor: QWidget):
        pass

    def _build_model_tab(self):
        tab = QWidget()
        tab.setProperty('editorPageSurface', True)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        path_row = QHBoxLayout()
        path_lbl = QLabel(self._t('jaw_editor.field.stl_file', 'STL file'))
        path_lbl.setProperty('detailFieldKey', True)
        self.stl_path = QLineEdit()
        self.stl_path.setPlaceholderText(self._t('jaw_editor.placeholder.stl_path', 'Path to jaw STL model'))
        self.browse_btn = QPushButton(self._t('jaw_editor.action.browse', 'BROWSE'))
        self.browse_btn.setProperty('panelActionButton', True)
        add_shadow(self.browse_btn)

        path_row.addWidget(path_lbl)
        path_row.addWidget(self.stl_path, 1)
        path_row.addWidget(self.browse_btn)
        layout.addLayout(path_row)

        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(8)

        plane_lbl = QLabel(self._t('jaw_editor.field.alignment_plane', 'Alignment plane'))
        plane_lbl.setProperty('detailFieldKey', True)
        self.alignment_plane = QComboBox()
        self.alignment_plane.addItems(['XZ', 'XY', 'YZ'])
        self._style_combo(self.alignment_plane)
        self.alignment_plane.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.alignment_plane.setMinimumWidth(120)
        self.alignment_plane.setMaximumWidth(140)

        self.rotate_x_btn = QPushButton(self._t('jaw_editor.action.rotate_x', 'ROT X +90'))
        self.rotate_y_btn = QPushButton(self._t('jaw_editor.action.rotate_y', 'ROT Y +90'))
        self.rotate_z_btn = QPushButton(self._t('jaw_editor.action.rotate_z', 'ROT Z +90'))
        self.reset_rot_btn = QPushButton(self._t('jaw_editor.action.reset_rotation', 'RESET ROT'))
        for btn in [self.rotate_x_btn, self.rotate_y_btn, self.rotate_z_btn, self.reset_rot_btn]:
            btn.setProperty('panelActionButton', True)
            add_shadow(btn)

        controls_row.addWidget(plane_lbl)
        controls_row.addWidget(self.alignment_plane)
        controls_row.addSpacing(8)
        controls_row.addWidget(self.rotate_x_btn)
        controls_row.addWidget(self.rotate_y_btn)
        controls_row.addWidget(self.rotate_z_btn)
        controls_row.addWidget(self.reset_rot_btn)
        controls_row.addStretch(1)
        layout.addLayout(controls_row)

        self.preview_widget = StlPreviewWidget()
        self.preview_widget.set_control_hint_text(
            self._t(
                'tool_editor.hint.rotate_pan_zoom',
                'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
            )
        )
        layout.addWidget(self.preview_widget, 1)

        self.browse_btn.clicked.connect(self._pick_stl_file)
        self.stl_path.editingFinished.connect(self._refresh_preview)
        self.alignment_plane.currentTextChanged.connect(self._on_alignment_plane_changed)
        self.rotate_x_btn.clicked.connect(lambda: self._rotate_preview_axis('x'))
        self.rotate_y_btn.clicked.connect(lambda: self._rotate_preview_axis('y'))
        self.rotate_z_btn.clicked.connect(lambda: self._rotate_preview_axis('z'))
        self.reset_rot_btn.clicked.connect(self._reset_preview_rotation)

        return tab

    def _style_combo(self, combo: QComboBox):
        apply_shared_dropdown_style(combo)

    def _load_jaw(self):
        if not self.jaw:
            return
        self.jaw_id.setText(self.jaw.get('jaw_id', ''))
        self._set_combo_by_data(self.jaw_type, self.jaw.get('jaw_type', 'Soft jaws'))
        self._set_combo_by_data(self.spindle_side, self.jaw.get('spindle_side', 'Main spindle'))
        self.clamping_diameter_text.setText(self.jaw.get('clamping_diameter_text', ''))
        self.clamping_length.setText(self.jaw.get('clamping_length', ''))
        self.turning_washer.setText(self.jaw.get('turning_washer', ''))
        self.last_modified.setText(self.jaw.get('last_modified', ''))
        self.notes.setText(self.jaw.get('notes', ''))
        self.stl_path.setText(self.jaw.get('stl_path', ''))
        # Restore saved preview orientation
        plane = (self.jaw.get('preview_plane', '') or 'XZ').strip()
        if plane not in ('XZ', 'XY', 'YZ'):
            plane = 'XZ'
        self.alignment_plane.setCurrentText(plane)
        self._preview_rotation_steps = {
            'x': int(self.jaw.get('preview_rot_x', 0) or 0) % 360,
            'y': int(self.jaw.get('preview_rot_y', 0) or 0) % 360,
            'z': int(self.jaw.get('preview_rot_z', 0) or 0) % 360,
        }
        self._refresh_preview()
        self._update_header()

    def _update_header(self):
        jaw_id = self.jaw_id.text().strip()
        self.header_title.setText(self._t('jaw_editor.header.new_jaw', 'New jaw') if not jaw_id else self._t('jaw_editor.header.jaw_with_id', 'Jaw {jaw_id}', jaw_id=jaw_id))
        self.header_id.setText(jaw_id)
        self.type_badge.setText(self.jaw_type.currentText())

    def _pick_stl_file(self):
        _, jaws_models_root = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            JAW_MODELS_ROOT_DEFAULT,
        )
        jaws_models_root.mkdir(parents=True, exist_ok=True)

        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t('jaw_editor.dialog.select_stl_title', 'Select STL file'),
            str(jaws_models_root),
            self._t('jaw_editor.dialog.stl_filter', 'STL Files (*.stl)'),
        )
        if not path:
            return
        self.stl_path.setText(path)
        self._refresh_preview()

    def _refresh_preview(self):
        path = self.stl_path.text().strip()
        if not path:
            self.preview_widget.clear()
            return
        self.preview_widget.load_stl(path, label=self.jaw_id.text().strip() or self._t('jaw_editor.preview.label', 'Jaw Preview'))
        self._apply_preview_transform_state()

    def _apply_preview_transform_state(self):
        self.preview_widget.set_alignment_plane(self.alignment_plane.currentText())
        self.preview_widget.reset_model_rotation()
        for axis in ('x', 'y', 'z'):
            deg = self._preview_rotation_steps[axis]
            if deg:
                self.preview_widget.rotate_model(axis, deg)

    def _on_alignment_plane_changed(self, plane: str):
        self.preview_widget.set_alignment_plane(plane)

    def _rotate_preview_axis(self, axis: str):
        key = (axis or '').strip().lower()
        if key not in self._preview_rotation_steps:
            return
        self._preview_rotation_steps[key] += 90
        self.preview_widget.rotate_model(key, 90)

    def _reset_preview_rotation(self):
        self._preview_rotation_steps = {'x': 0, 'y': 0, 'z': 0}
        self.preview_widget.reset_model_rotation()

    def get_jaw_data(self):
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
            'stl_path': self.stl_path.text().strip(),
            'preview_plane': self.alignment_plane.currentText(),
            'preview_rot_x': self._preview_rotation_steps.get('x', 0) % 360,
            'preview_rot_y': self._preview_rotation_steps.get('y', 0) % 360,
            'preview_rot_z': self._preview_rotation_steps.get('z', 0) % 360,
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
