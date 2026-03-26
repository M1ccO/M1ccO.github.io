from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
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

from ui.stl_preview import StlPreviewWidget
from ui.widgets.common import apply_shared_dropdown_style, clear_focused_dropdown_on_outside_click
from editor_helpers import (
    add_shadow,
    setup_editor_dialog,
    create_dialog_buttons,
    apply_secondary_button_theme,
    reflow_fields_grid,
)


class AddEditJawDialog(QDialog):
    JAW_TYPES = ['Soft jaws', 'Hard jaws', 'Spiked jaws', 'Special jaws']
    SPINDLE_SIDES = ['SP1', 'SP2', 'Both']

    def __init__(self, parent=None, jaw=None):
        super().__init__(parent)
        self.jaw = jaw or {}
        self._general_field_columns = None
        self._preview_rotation_steps = {'x': 0, 'y': 0, 'z': 0}
        jaw_id = self.jaw.get('jaw_id', '').strip()
        self.setWindowTitle('Add Jaw' if not jaw_id else f'Edit Jaw - {jaw_id}')
        self.resize(920, 640)
        self.setMinimumSize(820, 540)
        self.setModal(True)
        setup_editor_dialog(self)
        self._build_ui()
        self._load_jaw()

    def _build_ui(self):
        root = QVBoxLayout(self)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_general_tab(), 'General')
        self.tabs.addTab(self._build_model_tab(), '3D Model')

        self._dialog_buttons = create_dialog_buttons(
            self,
            save_text='SAVE JAW',
            cancel_text='CANCEL',
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
        self.header_title = QLabel('New jaw')
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

        # Fields host
        self.general_fields_host = QWidget()
        self.general_fields_host.setProperty('editorFieldsHost', True)
        self.general_fields_grid = QGridLayout(self.general_fields_host)
        self.general_fields_grid.setContentsMargins(2, 2, 2, 2)
        self.general_fields_grid.setHorizontalSpacing(22)
        self.general_fields_grid.setVerticalSpacing(16)
        form_layout.addWidget(self.general_fields_host)

        # Build field widgets
        self.jaw_id = QLineEdit()
        self.jaw_type = QComboBox()
        self.jaw_type.addItems(self.JAW_TYPES)
        self.spindle_side = QComboBox()
        self.spindle_side.addItems(self.SPINDLE_SIDES)
        self.clamping_diameter_text = QLineEdit()
        self.clamping_length = QLineEdit()
        self.used_in_work = QLineEdit()
        self.turning_washer = QLineEdit()
        self.last_modified = QLineEdit()
        self.notes = QLineEdit()

        self.clamping_diameter_text.setPlaceholderText('52.40 mm or 50-58 mm')
        self.clamping_length.setPlaceholderText('e.g. 24.0 mm')

        self._style_combo(self.jaw_type)
        self._style_combo(self.spindle_side)

        # Keep jaw comboboxes visually tighter than full-width fields.
        self.jaw_type.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.jaw_type.setMinimumWidth(180)
        self.jaw_type.setMaximumWidth(240)
        self.spindle_side.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.spindle_side.setMinimumWidth(180)
        self.spindle_side.setMaximumWidth(240)

        for w in [
            self.jaw_id, self.jaw_type, self.spindle_side,
            self.clamping_diameter_text, self.clamping_length,
            self.used_in_work, self.turning_washer, self.last_modified,
            self.notes,
        ]:
            self._style_field_editor(w)

        self._general_field_order = []
        self._general_field_order.append(self._build_edit_field('Jaw ID', self.jaw_id))
        self._general_field_order.append(self._build_edit_field('Jaw type', self.jaw_type))
        self._general_field_order.append(self._build_edit_field('Spindle side', self.spindle_side))
        self._general_field_order.append(self._build_edit_field('Clamping diameter', self.clamping_diameter_text))
        self._general_field_order.append(self._build_edit_field('Clamping length', self.clamping_length))
        self._general_field_order.append(self._build_edit_field('Used in works:', self.used_in_work))
        self._general_field_order.append(self._build_edit_field('Turning ring', self.turning_washer))
        self._general_field_order.append(self._build_edit_field('Last modified', self.last_modified))
        self._general_field_order.append(self._build_edit_field('Notes', self.notes))

        self._reflow_general_fields()

        general_content_layout.addWidget(form_frame)
        general_content_layout.addStretch(1)

        self.jaw_id.textChanged.connect(self._update_header)
        self.jaw_type.currentTextChanged.connect(self._update_header)
        self._update_header()

        return tab

    def _build_edit_field(self, title: str, editor: QWidget) -> QFrame:
        frame = QFrame()
        frame.setProperty('editorFieldCard', True)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        label = QLabel(title)
        label.setProperty('detailFieldKey', True)
        label.setWordWrap(False)
        lay.addWidget(label)
        lay.addWidget(editor)
        return frame

    def _style_field_editor(self, editor: QWidget):
        f = editor.font()
        f.setPointSizeF(max(11.5, f.pointSizeF() + 1.0))
        editor.setFont(f)
        if isinstance(editor, QLineEdit):
            editor.setMinimumHeight(44)
        elif isinstance(editor, QComboBox):
            editor.setMinimumHeight(44)

    def _reflow_general_fields(self, force: bool = False):
        if not hasattr(self, 'general_fields_grid'):
            return
        columns = 1
        if not force and columns == self._general_field_columns:
            return
        self._general_field_columns = columns
        reflow_fields_grid(
            self.general_fields_grid,
            self._general_field_order,
            columns,
            scroll=getattr(self, 'general_scroll', None),
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_general_fields()

    def _build_model_tab(self):
        tab = QWidget()
        tab.setProperty('editorPageSurface', True)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        path_row = QHBoxLayout()
        path_lbl = QLabel('STL file')
        path_lbl.setProperty('detailFieldKey', True)
        self.stl_path = QLineEdit()
        self.stl_path.setPlaceholderText('Path to jaw STL model')
        self.browse_btn = QPushButton('BROWSE')
        self.browse_btn.setProperty('panelActionButton', True)
        add_shadow(self.browse_btn)

        path_row.addWidget(path_lbl)
        path_row.addWidget(self.stl_path, 1)
        path_row.addWidget(self.browse_btn)
        layout.addLayout(path_row)

        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(8)

        plane_lbl = QLabel('Alignment plane')
        plane_lbl.setProperty('detailFieldKey', True)
        self.alignment_plane = QComboBox()
        self.alignment_plane.addItems(['XZ', 'XY', 'YZ'])
        self._style_combo(self.alignment_plane)
        self.alignment_plane.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.alignment_plane.setMinimumWidth(120)
        self.alignment_plane.setMaximumWidth(140)

        self.rotate_x_btn = QPushButton('ROT X +90')
        self.rotate_y_btn = QPushButton('ROT Y +90')
        self.rotate_z_btn = QPushButton('ROT Z +90')
        self.reset_rot_btn = QPushButton('RESET ROT')
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
        self.jaw_type.setCurrentText(self.jaw.get('jaw_type', 'Soft jaws'))
        current_spindle = (self.jaw.get('spindle_side', 'SP1') or 'SP1').strip()
        if current_spindle == 'Main spindle':
            current_spindle = 'SP1'
        elif current_spindle == 'Sub spindle':
            current_spindle = 'SP2'
        self.spindle_side.setCurrentText(current_spindle)
        self.clamping_diameter_text.setText(self.jaw.get('clamping_diameter_text', ''))
        self.clamping_length.setText(self.jaw.get('clamping_length', ''))
        self.used_in_work.setText(self.jaw.get('used_in_work', ''))
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
        self.header_title.setText('New jaw' if not jaw_id else f'Jaw {jaw_id}')
        self.header_id.setText(jaw_id)
        self.type_badge.setText(self.jaw_type.currentText())

    def _pick_stl_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select STL file', '', 'STL Files (*.stl)')
        if not path:
            return
        self.stl_path.setText(path)
        self._refresh_preview()

    def _refresh_preview(self):
        path = self.stl_path.text().strip()
        if not path:
            self.preview_widget.clear()
            return
        self.preview_widget.load_stl(path, label=self.jaw_id.text().strip() or 'Jaw Preview')
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
            'jaw_type': self.jaw_type.currentText(),
            'spindle_side': self.spindle_side.currentText(),
            'clamping_diameter_text': self.clamping_diameter_text.text().strip(),
            'clamping_length': self.clamping_length.text().strip(),
            'used_in_work': self.used_in_work.text().strip(),
            'turning_washer': self.turning_washer.text().strip(),
            'last_modified': self.last_modified.text().strip(),
            'notes': self.notes.text().strip(),
            'stl_path': self.stl_path.text().strip(),
            'preview_plane': self.alignment_plane.currentText(),
            'preview_rot_x': self._preview_rotation_steps.get('x', 0) % 360,
            'preview_rot_y': self._preview_rotation_steps.get('y', 0) % 360,
            'preview_rot_z': self._preview_rotation_steps.get('z', 0) % 360,
        }

        if not jaw['jaw_id']:
            raise ValueError('Jaw ID is required.')

        if jaw['jaw_type'] not in self.JAW_TYPES:
            raise ValueError('Jaw type is invalid.')

        if jaw['spindle_side'] not in self.SPINDLE_SIDES:
            raise ValueError('Spindle side is invalid.')

        return jaw

    def accept(self):
        try:
            self.get_jaw_data()
        except ValueError as exc:
            QMessageBox.warning(self, 'Invalid data', str(exc))
            return
        super().accept()
