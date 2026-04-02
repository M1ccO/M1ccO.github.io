"""
Measurement Editor Dialog - Visual measurement configuration in 3D space.

Allows users to add and configure distance measurements and diameter rings
with visual feedback in the 3D preview. Users can click in the 3D view to
select anchor points or manually enter coordinates.
"""

from typing import Callable
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QWidget, QFrame, QLabel,
    QPushButton, QLineEdit, QComboBox, QSplitter, QListWidget, QListWidgetItem,
    QAbstractItemView, QStackedWidget,
)
try:
    from ui.occt_preview import OcctPreviewWidget as StlPreviewWidget
except Exception:
    from ui.stl_preview import StlPreviewWidget
from shared.editor_helpers import (
    create_dialog_buttons,
    apply_secondary_button_theme,
)


def _xyz_to_tuple(value) -> tuple[float, float, float]:
    """Convert xyz value (list or string) into a float triplet."""
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return float(value[0]), float(value[1]), float(value[2])
        except Exception:
            return 0.0, 0.0, 0.0

    text = str(value or '').strip()
    if not text:
        return 0.0, 0.0, 0.0

    text = text.replace(';', ',')
    parts = [p.strip() for p in text.split(',') if p.strip()]
    if len(parts) < 3:
        return 0.0, 0.0, 0.0
    try:
        return float(parts[0]), float(parts[1]), float(parts[2])
    except Exception:
        return 0.0, 0.0, 0.0


def _fmt_coord(value: float) -> str:
    return f"{float(value):.4g}"


class MeasurementEditorDialog(QDialog):
    """Dialog for editing measurements with visual 3D feedback and point-picking."""

    def __init__(
        self,
        tool_data: dict,
        parts: list | None = None,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self._tool_data = tool_data or {}
        self._parts = parts or []
        self._translate = translate or (lambda key, default=None, **_kwargs: default or '')
        self._pick_target: str | None = None
        self._current_distance_item: QListWidgetItem | None = None
        self._current_diameter_item: QListWidgetItem | None = None
        self._current_radius_item: QListWidgetItem | None = None
        self._current_angle_item: QListWidgetItem | None = None
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(350)
        self._commit_timer.timeout.connect(self._commit_current_edit)

        self.setWindowTitle(self._t('tool_editor.measurements.editor_title', 'Measurement Editor'))
        self.resize(1000, 720)
        self.setMinimumSize(700, 520)

        self._build_ui()
        self._populate_measurements()

        if self._parts:
            self._preview_widget.load_parts(self._parts)
        self._preview_widget.set_measurements_visible(True)
        self._preview_widget.point_picked.connect(self._on_point_picked)
        self._on_measurement_kind_changed()
        self._refresh_preview_measurements()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    # ─────────────────────────────────────────────────────────────────
    # UI BUILD
    # ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── LEFT PANEL ──────────────────────────────────────────────
        left_panel = QFrame()
        left_panel.setMinimumWidth(300)
        left_panel.setMaximumWidth(420)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        type_row = QHBoxLayout()
        type_row.setContentsMargins(4, 2, 4, 2)
        type_row.setSpacing(6)
        type_row.addWidget(QLabel(self._t('tool_editor.measurements.type', 'Type') + ':'))
        self._measurement_type_combo = QComboBox()
        self._measurement_type_combo.addItem(self._t('tool_editor.measurements.type_length', 'Length'), 'length')
        self._measurement_type_combo.addItem(self._t('tool_editor.measurements.type_diameter', 'Diameter'), 'diameter')
        self._measurement_type_combo.addItem(self._t('tool_editor.measurements.type_radius', 'Radius'), 'radius')
        self._measurement_type_combo.addItem(self._t('tool_editor.measurements.type_angle', 'Angle'), 'angle')
        self._measurement_type_combo.currentIndexChanged.connect(self._on_measurement_kind_changed)
        type_row.addWidget(self._measurement_type_combo, 1)
        left_layout.addLayout(type_row)

        self._measurement_list_stack = QStackedWidget()

        # Length list page
        dist_page = QWidget()
        dist_tab_layout = QVBoxLayout(dist_page)
        dist_tab_layout.setContentsMargins(4, 4, 4, 4)
        dist_tab_layout.setSpacing(6)
        self._distance_list = QListWidget()
        self._distance_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._distance_list.itemSelectionChanged.connect(self._on_distance_selected)
        dist_tab_layout.addWidget(self._distance_list, 1)
        self._measurement_list_stack.addWidget(dist_page)

        # Diameter list page
        diam_page = QWidget()
        diam_tab_layout = QVBoxLayout(diam_page)
        diam_tab_layout.setContentsMargins(4, 4, 4, 4)
        diam_tab_layout.setSpacing(6)
        self._diameter_list = QListWidget()
        self._diameter_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._diameter_list.itemSelectionChanged.connect(self._on_diameter_selected)
        diam_tab_layout.addWidget(self._diameter_list, 1)
        self._measurement_list_stack.addWidget(diam_page)

        # Radius list page
        radius_page = QWidget()
        radius_layout = QVBoxLayout(radius_page)
        radius_layout.setContentsMargins(4, 4, 4, 4)
        radius_layout.setSpacing(6)
        self._radius_list = QListWidget()
        self._radius_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._radius_list.itemSelectionChanged.connect(self._on_radius_selected)
        radius_layout.addWidget(self._radius_list, 1)
        self._measurement_list_stack.addWidget(radius_page)

        # Angle list page
        angle_page = QWidget()
        angle_layout = QVBoxLayout(angle_page)
        angle_layout.setContentsMargins(4, 4, 4, 4)
        angle_layout.setSpacing(6)
        self._angle_list = QListWidget()
        self._angle_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._angle_list.itemSelectionChanged.connect(self._on_angle_selected)
        angle_layout.addWidget(self._angle_list, 1)
        self._measurement_list_stack.addWidget(angle_page)

        left_layout.addWidget(self._measurement_list_stack, 1)

        list_btn_row = QHBoxLayout()
        self._add_measurement_btn = QPushButton(self._t('common.add', 'Add'))
        self._remove_measurement_btn = QPushButton(self._t('common.remove', 'Remove'))
        self._add_measurement_btn.clicked.connect(self._add_current_measurement)
        self._remove_measurement_btn.clicked.connect(self._remove_current_measurement)
        list_btn_row.addWidget(self._add_measurement_btn)
        list_btn_row.addWidget(self._remove_measurement_btn)
        list_btn_row.addStretch(1)
        left_layout.addLayout(list_btn_row)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        left_layout.addWidget(separator)

        # Edit form stack: 0 placeholder, 1 distance, 2 diameter, 3 radius, 4 angle
        self._edit_stack = QStackedWidget()
        self._edit_stack.setMinimumHeight(220)
        placeholder = QLabel(self._t(
            'tool_editor.measurements.select_to_edit', 'Select a measurement to edit.'))
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet('color: #6b7b8e; font-size: 11px;')
        self._edit_stack.addWidget(placeholder)
        self._edit_stack.addWidget(self._build_distance_form())
        self._edit_stack.addWidget(self._build_diameter_form())
        self._edit_stack.addWidget(self._build_radius_form())
        self._edit_stack.addWidget(self._build_angle_form())
        left_layout.addWidget(self._edit_stack)

        # ── PREVIEW ─────────────────────────────────────────────────
        self._preview_widget = StlPreviewWidget()
        splitter.addWidget(left_panel)
        splitter.addWidget(self._preview_widget)
        splitter.setSizes([340, 660])
        root.addWidget(splitter, 1)

        # ── BOTTOM BUTTONS ──────────────────────────────────────────
        button_box = create_dialog_buttons(
            self,
            save_text=self._t('common.save', 'Save').upper(),
            cancel_text=self._t('common.cancel', 'Cancel').upper(),
            on_save=self.accept,
            on_cancel=self.reject,
        )
        save_btn = button_box.button(QDialogButtonBox.Save)
        apply_secondary_button_theme(self, save_btn)
        root.addWidget(button_box)

    def _build_distance_form(self) -> QWidget:
        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._dist_name_edit = QLineEdit()
        self._dist_name_edit.setPlaceholderText('Distance 1')
        self._dist_name_edit.editingFinished.connect(self._schedule_commit)
        form.addRow(self._t('common.name', 'Name') + ':', self._dist_name_edit)

        target_row = QHBoxLayout()
        target_row.setSpacing(6)
        self._dist_target_start_btn = QPushButton(self._t('tool_editor.measurements.start_short', 'START'))
        self._dist_target_end_btn = QPushButton(self._t('tool_editor.measurements.end_short', 'END'))
        self._dist_target_start_btn.setCheckable(True)
        self._dist_target_end_btn.setCheckable(True)
        self._dist_target_start_btn.clicked.connect(lambda: self._set_distance_target_side('start'))
        self._dist_target_end_btn.clicked.connect(lambda: self._set_distance_target_side('end'))
        target_row.addWidget(self._dist_target_start_btn)
        target_row.addWidget(self._dist_target_end_btn)
        target_row.addStretch(1)
        form.addRow(self._t('tool_editor.measurements.target', 'Target') + ':', target_row)

        self._dist_target_part_edit = QLineEdit()
        self._dist_target_part_edit.setPlaceholderText(
            self._t('tool_editor.measurements.part_placeholder', '(part name, blank = assembly)'))
        self._dist_target_part_edit.editingFinished.connect(self._schedule_commit)
        form.addRow(self._t('tool_editor.measurements.part', 'Part') + ':',
                    self._dist_target_part_edit)

        form.addRow('', self._build_xyz_header_row(with_pick=True))
        xyz_row = QHBoxLayout()
        self._dist_target_x_edit = QLineEdit('0')
        self._dist_target_y_edit = QLineEdit('0')
        self._dist_target_z_edit = QLineEdit('0')
        for axis_edit in (self._dist_target_x_edit, self._dist_target_y_edit, self._dist_target_z_edit):
            axis_edit.setFixedWidth(56)
            axis_edit.editingFinished.connect(self._schedule_commit)
        self._dist_target_pick_btn = QPushButton(self._t('tool_editor.measurements.pick', 'Pick'))
        self._dist_target_pick_btn.setFixedWidth(50)
        self._dist_target_pick_btn.setToolTip(
            self._t('tool_editor.measurements.pick_tooltip', 'Click a point on the 3D model'))
        self._dist_target_pick_btn.clicked.connect(self._on_pick_target)
        xyz_row.addWidget(self._dist_target_x_edit)
        xyz_row.addWidget(self._dist_target_y_edit)
        xyz_row.addWidget(self._dist_target_z_edit)
        xyz_row.addStretch(1)
        xyz_row.addWidget(self._dist_target_pick_btn)
        form.addRow(self._t('tool_editor.measurements.xyz', 'XYZ') + ':', xyz_row)

        axis_row = QHBoxLayout()
        axis_row.setSpacing(6)
        self._dist_axis_direct_btn = QPushButton(self._t('tool_editor.measurements.axis_direct_short', '3D'))
        self._dist_axis_x_btn = QPushButton(self._t('tool_editor.measurements.axis_x', 'X'))
        self._dist_axis_y_btn = QPushButton(self._t('tool_editor.measurements.axis_y', 'Y'))
        self._dist_axis_z_btn = QPushButton(self._t('tool_editor.measurements.axis_z', 'Z'))
        for axis_btn in (self._dist_axis_direct_btn, self._dist_axis_x_btn, self._dist_axis_y_btn, self._dist_axis_z_btn):
            axis_btn.setCheckable(True)
            axis_btn.setFixedWidth(42)
        self._dist_axis_direct_btn.setToolTip(self._t('tool_editor.measurements.axis_direct_tooltip', 'Direct 3D point-to-point'))
        self._dist_axis_direct_btn.clicked.connect(lambda: self._set_distance_axis('direct'))
        self._dist_axis_x_btn.clicked.connect(lambda: self._set_distance_axis('x'))
        self._dist_axis_y_btn.clicked.connect(lambda: self._set_distance_axis('y'))
        self._dist_axis_z_btn.clicked.connect(lambda: self._set_distance_axis('z'))
        axis_row.addWidget(self._dist_axis_direct_btn)
        axis_row.addWidget(self._dist_axis_x_btn)
        axis_row.addWidget(self._dist_axis_y_btn)
        axis_row.addWidget(self._dist_axis_z_btn)
        axis_row.addStretch(1)
        form.addRow(self._t('tool_editor.measurements.axis', 'Axis') + ':', axis_row)

        value_row = QHBoxLayout()
        value_row.setSpacing(6)
        self._dist_value_mode_combo = QComboBox()
        self._dist_value_mode_combo.addItem(
            self._t('tool_editor.measurements.value_mode_measured', 'Measured'),
            'measured',
        )
        self._dist_value_mode_combo.addItem(
            self._t('tool_editor.measurements.value_mode_custom', 'Custom'),
            'custom',
        )
        self._dist_value_mode_combo.currentIndexChanged.connect(self._on_distance_value_mode_changed)
        self._dist_custom_value_edit = QLineEdit()
        self._dist_custom_value_edit.setPlaceholderText(
            self._t('tool_editor.measurements.custom_value_placeholder', 'e.g. 180.0 mm')
        )
        self._dist_custom_value_edit.editingFinished.connect(self._schedule_commit)
        value_row.addWidget(self._dist_value_mode_combo)
        value_row.addWidget(self._dist_custom_value_edit, 1)
        form.addRow(self._t('tool_editor.measurements.display_value', 'Display Value') + ':', value_row)

        self._distance_edit_model = None
        self._dist_target_side = 'start'
        self._set_distance_axis('z', commit=False)
        self._set_distance_value_mode('measured', commit=False)
        self._set_distance_target_side('start', commit=False)

        return container

    def _build_diameter_form(self) -> QWidget:
        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._diam_name_edit = QLineEdit()
        self._diam_name_edit.setPlaceholderText('Diameter 1')
        self._diam_name_edit.editingFinished.connect(self._schedule_commit)
        form.addRow(self._t('common.name', 'Name') + ':', self._diam_name_edit)

        self._diam_part_edit = QLineEdit()
        self._diam_part_edit.setPlaceholderText(
            self._t('tool_editor.measurements.part_placeholder', '(part name, blank = assembly)'))
        self._diam_part_edit.editingFinished.connect(self._schedule_commit)
        form.addRow(self._t('tool_editor.measurements.part', 'Part') + ':', self._diam_part_edit)

        form.addRow('', self._build_xyz_header_row(with_pick=True))
        center_row = QHBoxLayout()
        self._diam_center_x_edit = QLineEdit('0')
        self._diam_center_y_edit = QLineEdit('0')
        self._diam_center_z_edit = QLineEdit('0')
        for axis_edit in (self._diam_center_x_edit, self._diam_center_y_edit, self._diam_center_z_edit):
            axis_edit.setFixedWidth(56)
            axis_edit.editingFinished.connect(self._schedule_commit)
        self._diam_center_pick_btn = QPushButton(self._t('tool_editor.measurements.pick', 'Pick'))
        self._diam_center_pick_btn.setFixedWidth(50)
        self._diam_center_pick_btn.setToolTip(
            self._t('tool_editor.measurements.pick_tooltip', 'Click a point on the 3D model'))
        self._diam_center_pick_btn.clicked.connect(self._on_pick_center)
        center_row.addWidget(self._diam_center_x_edit)
        center_row.addWidget(self._diam_center_y_edit)
        center_row.addWidget(self._diam_center_z_edit)
        center_row.addStretch(1)
        center_row.addWidget(self._diam_center_pick_btn)
        form.addRow(self._t('tool_editor.measurements.center_xyz', 'Center XYZ') + ':', center_row)

        form.addRow('', self._build_xyz_header_row(with_pick=False))
        axis_row = QHBoxLayout()
        self._diam_axis_x_edit = QLineEdit('0')
        self._diam_axis_y_edit = QLineEdit('1')
        self._diam_axis_z_edit = QLineEdit('0')
        for axis_edit in (self._diam_axis_x_edit, self._diam_axis_y_edit, self._diam_axis_z_edit):
            axis_edit.setFixedWidth(56)
            axis_edit.editingFinished.connect(self._schedule_commit)
            axis_row.addWidget(axis_edit)
        axis_row.addStretch(1)
        form.addRow(self._t('tool_editor.measurements.axis_xyz', 'Axis XYZ') + ':', axis_row)

        self._diam_diameter_edit = QLineEdit()
        self._diam_diameter_edit.setPlaceholderText('10.0')
        self._diam_diameter_edit.editingFinished.connect(self._schedule_commit)
        form.addRow(self._t('tool_editor.measurements.diameter', 'Diameter (mm)') + ':',
                    self._diam_diameter_edit)

        return container

    def _build_radius_form(self) -> QWidget:
        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._radius_name_edit = QLineEdit()
        self._radius_name_edit.setPlaceholderText('Radius 1')
        self._radius_name_edit.editingFinished.connect(self._schedule_commit)
        form.addRow(self._t('common.name', 'Name') + ':', self._radius_name_edit)

        self._radius_part_edit = QLineEdit()
        self._radius_part_edit.setPlaceholderText(
            self._t('tool_editor.measurements.part_placeholder', '(part name, blank = assembly)'))
        self._radius_part_edit.editingFinished.connect(self._schedule_commit)
        form.addRow(self._t('tool_editor.measurements.part', 'Part') + ':', self._radius_part_edit)

        form.addRow('', self._build_xyz_header_row(with_pick=True))
        center_row = QHBoxLayout()
        self._radius_center_x_edit = QLineEdit('0')
        self._radius_center_y_edit = QLineEdit('0')
        self._radius_center_z_edit = QLineEdit('0')
        for axis_edit in (self._radius_center_x_edit, self._radius_center_y_edit, self._radius_center_z_edit):
            axis_edit.setFixedWidth(56)
            axis_edit.editingFinished.connect(self._schedule_commit)
        self._radius_center_pick_btn = QPushButton(self._t('tool_editor.measurements.pick', 'Pick'))
        self._radius_center_pick_btn.setFixedWidth(50)
        self._radius_center_pick_btn.clicked.connect(self._on_pick_radius_center)
        center_row.addWidget(self._radius_center_x_edit)
        center_row.addWidget(self._radius_center_y_edit)
        center_row.addWidget(self._radius_center_z_edit)
        center_row.addStretch(1)
        center_row.addWidget(self._radius_center_pick_btn)
        form.addRow(self._t('tool_editor.measurements.center_xyz', 'Center XYZ') + ':', center_row)

        form.addRow('', self._build_xyz_header_row(with_pick=False))
        axis_row = QHBoxLayout()
        self._radius_axis_x_edit = QLineEdit('0')
        self._radius_axis_y_edit = QLineEdit('1')
        self._radius_axis_z_edit = QLineEdit('0')
        for axis_edit in (self._radius_axis_x_edit, self._radius_axis_y_edit, self._radius_axis_z_edit):
            axis_edit.setFixedWidth(56)
            axis_edit.editingFinished.connect(self._schedule_commit)
            axis_row.addWidget(axis_edit)
        axis_row.addStretch(1)
        form.addRow(self._t('tool_editor.measurements.axis_xyz', 'Axis XYZ') + ':', axis_row)

        self._radius_value_edit = QLineEdit('10')
        self._radius_value_edit.editingFinished.connect(self._schedule_commit)
        form.addRow(self._t('tool_editor.measurements.radius', 'Radius (mm)') + ':', self._radius_value_edit)

        return container

    def _build_angle_form(self) -> QWidget:
        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._angle_name_edit = QLineEdit()
        self._angle_name_edit.setPlaceholderText('Angle 1')
        self._angle_name_edit.editingFinished.connect(self._schedule_commit)
        form.addRow(self._t('common.name', 'Name') + ':', self._angle_name_edit)

        self._angle_part_edit = QLineEdit()
        self._angle_part_edit.setPlaceholderText(
            self._t('tool_editor.measurements.part_placeholder', '(part name, blank = assembly)'))
        self._angle_part_edit.editingFinished.connect(self._schedule_commit)
        form.addRow(self._t('tool_editor.measurements.part', 'Part') + ':', self._angle_part_edit)

        form.addRow('', self._build_xyz_header_row(with_pick=True))
        center_row = QHBoxLayout()
        self._angle_center_x_edit = QLineEdit('0')
        self._angle_center_y_edit = QLineEdit('0')
        self._angle_center_z_edit = QLineEdit('0')
        for axis_edit in (self._angle_center_x_edit, self._angle_center_y_edit, self._angle_center_z_edit):
            axis_edit.setFixedWidth(56)
            axis_edit.editingFinished.connect(self._schedule_commit)
        self._angle_center_pick_btn = QPushButton(self._t('tool_editor.measurements.pick', 'Pick'))
        self._angle_center_pick_btn.setFixedWidth(50)
        self._angle_center_pick_btn.clicked.connect(self._on_pick_angle_center)
        center_row.addWidget(self._angle_center_x_edit)
        center_row.addWidget(self._angle_center_y_edit)
        center_row.addWidget(self._angle_center_z_edit)
        center_row.addStretch(1)
        center_row.addWidget(self._angle_center_pick_btn)
        form.addRow(self._t('tool_editor.measurements.center_xyz', 'Center XYZ') + ':', center_row)

        form.addRow('', self._build_xyz_header_row(with_pick=True))
        start_row = QHBoxLayout()
        self._angle_start_x_edit = QLineEdit('0')
        self._angle_start_y_edit = QLineEdit('0')
        self._angle_start_z_edit = QLineEdit('0')
        for axis_edit in (self._angle_start_x_edit, self._angle_start_y_edit, self._angle_start_z_edit):
            axis_edit.setFixedWidth(56)
            axis_edit.editingFinished.connect(self._schedule_commit)
        self._angle_start_pick_btn = QPushButton(self._t('tool_editor.measurements.pick', 'Pick'))
        self._angle_start_pick_btn.setFixedWidth(50)
        self._angle_start_pick_btn.clicked.connect(self._on_pick_angle_start)
        start_row.addWidget(self._angle_start_x_edit)
        start_row.addWidget(self._angle_start_y_edit)
        start_row.addWidget(self._angle_start_z_edit)
        start_row.addStretch(1)
        start_row.addWidget(self._angle_start_pick_btn)
        form.addRow(self._t('tool_editor.measurements.start_xyz', 'Start XYZ') + ':', start_row)

        form.addRow('', self._build_xyz_header_row(with_pick=True))
        end_row = QHBoxLayout()
        self._angle_end_x_edit = QLineEdit('0')
        self._angle_end_y_edit = QLineEdit('0')
        self._angle_end_z_edit = QLineEdit('0')
        for axis_edit in (self._angle_end_x_edit, self._angle_end_y_edit, self._angle_end_z_edit):
            axis_edit.setFixedWidth(56)
            axis_edit.editingFinished.connect(self._schedule_commit)
        self._angle_end_pick_btn = QPushButton(self._t('tool_editor.measurements.pick', 'Pick'))
        self._angle_end_pick_btn.setFixedWidth(50)
        self._angle_end_pick_btn.clicked.connect(self._on_pick_angle_end)
        end_row.addWidget(self._angle_end_x_edit)
        end_row.addWidget(self._angle_end_y_edit)
        end_row.addWidget(self._angle_end_z_edit)
        end_row.addStretch(1)
        end_row.addWidget(self._angle_end_pick_btn)
        form.addRow(self._t('tool_editor.measurements.end_xyz', 'End XYZ') + ':', end_row)

        return container

    def _build_xyz_header_row(self, with_pick: bool) -> QWidget:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        for key, fallback in (
            ('tool_editor.measurements.axis_x', 'X'),
            ('tool_editor.measurements.axis_y', 'Y'),
            ('tool_editor.measurements.axis_z', 'Z'),
        ):
            lbl = QLabel(self._t(key, fallback))
            lbl.setFixedWidth(56)
            lbl.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            lbl.setStyleSheet('color: #6b7b8e; font-size: 10px; background: transparent;')
            row_layout.addWidget(lbl)

        row_layout.addStretch(1)
        if with_pick:
            row_layout.addSpacing(50)
        return row_widget

    # ─────────────────────────────────────────────────────────────────
    # MEASUREMENT LIST MANAGEMENT
    # ─────────────────────────────────────────────────────────────────

    def _populate_measurements(self):
        self._distance_list.clear()
        for meas in self._tool_data.get('distance_measurements', []):
            item = QListWidgetItem(meas.get('name', 'Unnamed'))
            item.setData(Qt.UserRole, dict(meas))
            self._distance_list.addItem(item)

        self._diameter_list.clear()
        for meas in self._tool_data.get('diameter_measurements', []):
            item = QListWidgetItem(meas.get('name', 'Unnamed'))
            item.setData(Qt.UserRole, dict(meas))
            self._diameter_list.addItem(item)

        self._radius_list.clear()
        for meas in self._tool_data.get('radius_measurements', []):
            item = QListWidgetItem(meas.get('name', 'Unnamed'))
            item.setData(Qt.UserRole, dict(meas))
            self._radius_list.addItem(item)

        self._angle_list.clear()
        for meas in self._tool_data.get('angle_measurements', []):
            item = QListWidgetItem(meas.get('name', 'Unnamed'))
            item.setData(Qt.UserRole, dict(meas))
            self._angle_list.addItem(item)

    def _add_distance_measurement(self):
        new_meas = {
            'name': self._t('tool_editor.measurements.new_distance', 'New Distance'),
            'start_part': '',
            'start_xyz': '0, 0, 0',
            'end_part': '',
            'end_xyz': '0, 0, 0',
            'distance_axis': 'z',
            'label_value_mode': 'measured',
            'label_custom_value': '',
            'type': 'distance',
        }
        item = QListWidgetItem(new_meas['name'])
        item.setData(Qt.UserRole, new_meas)
        self._distance_list.addItem(item)
        self._distance_list.setCurrentItem(item)
        self._refresh_preview_measurements()

    def _remove_distance_measurement(self):
        current = self._distance_list.currentItem()
        if current:
            self._distance_list.takeItem(self._distance_list.row(current))
            self._current_distance_item = None
            self._edit_stack.setCurrentIndex(0)
            self._refresh_preview_measurements()

    def _add_diameter_measurement(self):
        new_meas = {
            'name': self._t('tool_editor.measurements.new_diameter', 'New Diameter'),
            'part': '',
            'center_xyz': '0, 0, 0',
            'axis_xyz': '0, 1, 0',
            'diameter': '10',
            'type': 'diameter_ring',
        }
        item = QListWidgetItem(new_meas['name'])
        item.setData(Qt.UserRole, new_meas)
        self._diameter_list.addItem(item)
        self._diameter_list.setCurrentItem(item)
        self._refresh_preview_measurements()

    def _remove_diameter_measurement(self):
        current = self._diameter_list.currentItem()
        if current:
            self._diameter_list.takeItem(self._diameter_list.row(current))
            self._current_diameter_item = None
            self._edit_stack.setCurrentIndex(0)
            self._refresh_preview_measurements()

    def _add_radius_measurement(self):
        new_meas = {
            'name': self._t('tool_editor.measurements.new_radius', 'New Radius'),
            'part': '',
            'center_xyz': '0, 0, 0',
            'axis_xyz': '0, 1, 0',
            'radius': '5',
            'type': 'radius',
        }
        item = QListWidgetItem(new_meas['name'])
        item.setData(Qt.UserRole, new_meas)
        self._radius_list.addItem(item)
        self._radius_list.setCurrentItem(item)
        self._refresh_preview_measurements()

    def _remove_radius_measurement(self):
        current = self._radius_list.currentItem()
        if current:
            self._radius_list.takeItem(self._radius_list.row(current))
            self._current_radius_item = None
            self._edit_stack.setCurrentIndex(0)
            self._refresh_preview_measurements()

    def _add_angle_measurement(self):
        new_meas = {
            'name': self._t('tool_editor.measurements.new_angle', 'New Angle'),
            'part': '',
            'center_xyz': '0, 0, 0',
            'start_xyz': '1, 0, 0',
            'end_xyz': '0, 1, 0',
            'type': 'angle',
        }
        item = QListWidgetItem(new_meas['name'])
        item.setData(Qt.UserRole, new_meas)
        self._angle_list.addItem(item)
        self._angle_list.setCurrentItem(item)
        self._refresh_preview_measurements()

    def _remove_angle_measurement(self):
        current = self._angle_list.currentItem()
        if current:
            self._angle_list.takeItem(self._angle_list.row(current))
            self._current_angle_item = None
            self._edit_stack.setCurrentIndex(0)
            self._refresh_preview_measurements()

    # ─────────────────────────────────────────────────────────────────
    # SELECTION & FORM POPULATION
    # ─────────────────────────────────────────────────────────────────

    def _on_measurement_kind_changed(self, *_args):
        self._cancel_pick()
        kind = str(self._measurement_type_combo.currentData() or 'length')
        is_supported = kind in {'length', 'diameter', 'radius', 'angle'}
        self._add_measurement_btn.setEnabled(is_supported)
        self._remove_measurement_btn.setEnabled(is_supported)
        index_map = {'length': 0, 'diameter': 1, 'radius': 2, 'angle': 3}
        self._measurement_list_stack.setCurrentIndex(index_map.get(kind, 0))
        if kind == 'length':
            if self._distance_list.currentItem():
                self._edit_stack.setCurrentIndex(1)
            else:
                self._edit_stack.setCurrentIndex(0)
        elif kind == 'diameter':
            if self._diameter_list.currentItem():
                self._edit_stack.setCurrentIndex(2)
            else:
                self._edit_stack.setCurrentIndex(0)
        elif kind == 'radius':
            if self._radius_list.currentItem():
                self._edit_stack.setCurrentIndex(3)
            else:
                self._edit_stack.setCurrentIndex(0)
        elif kind == 'angle':
            if self._angle_list.currentItem():
                self._edit_stack.setCurrentIndex(4)
            else:
                self._edit_stack.setCurrentIndex(0)
        else:
            self._edit_stack.setCurrentIndex(0)

    def _add_current_measurement(self):
        kind = str(self._measurement_type_combo.currentData() or 'length')
        if kind == 'length':
            self._add_distance_measurement()
        elif kind == 'diameter':
            self._add_diameter_measurement()
        elif kind == 'radius':
            self._add_radius_measurement()
        elif kind == 'angle':
            self._add_angle_measurement()

    def _remove_current_measurement(self):
        kind = str(self._measurement_type_combo.currentData() or 'length')
        if kind == 'length':
            self._remove_distance_measurement()
        elif kind == 'diameter':
            self._remove_diameter_measurement()
        elif kind == 'radius':
            self._remove_radius_measurement()
        elif kind == 'angle':
            self._remove_angle_measurement()

    def _on_distance_selected(self):
        current = self._distance_list.currentItem()
        self._current_distance_item = current
        if current:
            self._populate_distance_form(current.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(1)
        else:
            self._edit_stack.setCurrentIndex(0)

    def _on_diameter_selected(self):
        current = self._diameter_list.currentItem()
        self._current_diameter_item = current
        if current:
            self._populate_diameter_form(current.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(2)
        else:
            self._edit_stack.setCurrentIndex(0)

    def _on_radius_selected(self):
        current = self._radius_list.currentItem()
        self._current_radius_item = current
        if current:
            self._populate_radius_form(current.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(3)
        else:
            self._edit_stack.setCurrentIndex(0)

    def _on_angle_selected(self):
        current = self._angle_list.currentItem()
        self._current_angle_item = current
        if current:
            self._populate_angle_form(current.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(4)
        else:
            self._edit_stack.setCurrentIndex(0)

    def _populate_distance_form(self, meas: dict):
        self._distance_edit_model = dict(meas or {})
        self._dist_name_edit.setText(meas.get('name', ''))
        self._set_distance_axis(str(meas.get('distance_axis', 'z')).lower(), commit=False)
        self._dist_custom_value_edit.setText(str(meas.get('label_custom_value', '')))
        self._set_distance_value_mode(str(meas.get('label_value_mode', 'measured')).lower(), commit=False)
        self._set_distance_target_side(self._dist_target_side, commit=False)

    def _populate_diameter_form(self, meas: dict):
        self._diam_name_edit.setText(meas.get('name', ''))
        self._diam_part_edit.setText(meas.get('part', ''))
        self._set_xyz_edits(
            (self._diam_center_x_edit, self._diam_center_y_edit, self._diam_center_z_edit),
            meas.get('center_xyz', '0, 0, 0')
        )
        self._set_xyz_edits(
            (self._diam_axis_x_edit, self._diam_axis_y_edit, self._diam_axis_z_edit),
            meas.get('axis_xyz', '0, 1, 0')
        )
        self._diam_diameter_edit.setText(str(meas.get('diameter', '10')))

    def _populate_radius_form(self, meas: dict):
        self._radius_name_edit.setText(meas.get('name', ''))
        self._radius_part_edit.setText(meas.get('part', ''))
        self._set_xyz_edits(
            (self._radius_center_x_edit, self._radius_center_y_edit, self._radius_center_z_edit),
            meas.get('center_xyz', '0, 0, 0')
        )
        self._set_xyz_edits(
            (self._radius_axis_x_edit, self._radius_axis_y_edit, self._radius_axis_z_edit),
            meas.get('axis_xyz', '0, 1, 0')
        )
        self._radius_value_edit.setText(str(meas.get('radius', '5')))

    def _populate_angle_form(self, meas: dict):
        self._angle_name_edit.setText(meas.get('name', ''))
        self._angle_part_edit.setText(meas.get('part', ''))
        self._set_xyz_edits(
            (self._angle_center_x_edit, self._angle_center_y_edit, self._angle_center_z_edit),
            meas.get('center_xyz', '0, 0, 0')
        )
        self._set_xyz_edits(
            (self._angle_start_x_edit, self._angle_start_y_edit, self._angle_start_z_edit),
            meas.get('start_xyz', '1, 0, 0')
        )
        self._set_xyz_edits(
            (self._angle_end_x_edit, self._angle_end_y_edit, self._angle_end_z_edit),
            meas.get('end_xyz', '0, 1, 0')
        )

    # ─────────────────────────────────────────────────────────────────
    # EDIT COMMIT
    # ─────────────────────────────────────────────────────────────────

    def _schedule_commit(self):
        self._commit_timer.start()

    def _commit_current_edit(self):
        kind = str(self._measurement_type_combo.currentData() or 'length')
        if kind == 'length':
            self._commit_distance_edit()
        elif kind == 'diameter':
            self._commit_diameter_edit()
        elif kind == 'radius':
            self._commit_radius_edit()
        elif kind == 'angle':
            self._commit_angle_edit()

    def _set_distance_target_side(self, side: str, commit: bool = True):
        normalized = 'end' if side == 'end' else 'start'
        if getattr(self, '_distance_edit_model', None):
            self._store_distance_target_fields(self._dist_target_side)
        self._dist_target_side = normalized
        self._dist_target_start_btn.setChecked(normalized == 'start')
        self._dist_target_end_btn.setChecked(normalized == 'end')
        self._load_distance_target_fields(normalized)
        if commit:
            self._commit_distance_edit()

    def _store_distance_target_fields(self, side: str):
        if self._distance_edit_model is None:
            self._distance_edit_model = {}
        part_value = self._dist_target_part_edit.text().strip()
        xyz_value = self._xyz_text_from_edits(
            (self._dist_target_x_edit, self._dist_target_y_edit, self._dist_target_z_edit)
        )
        if side == 'end':
            self._distance_edit_model['end_part'] = part_value
            self._distance_edit_model['end_xyz'] = xyz_value
        else:
            self._distance_edit_model['start_part'] = part_value
            self._distance_edit_model['start_xyz'] = xyz_value

    def _load_distance_target_fields(self, side: str):
        model = self._distance_edit_model or {}
        if side == 'end':
            self._dist_target_part_edit.setText(str(model.get('end_part', '')))
            self._set_xyz_edits(
                (self._dist_target_x_edit, self._dist_target_y_edit, self._dist_target_z_edit),
                model.get('end_xyz', '0, 0, 0')
            )
        else:
            self._dist_target_part_edit.setText(str(model.get('start_part', '')))
            self._set_xyz_edits(
                (self._dist_target_x_edit, self._dist_target_y_edit, self._dist_target_z_edit),
                model.get('start_xyz', '0, 0, 0')
            )

    def _commit_distance_edit(self):
        if not self._current_distance_item:
            return
        if self._distance_edit_model is None:
            self._distance_edit_model = dict(self._current_distance_item.data(Qt.UserRole) or {})
        self._store_distance_target_fields(self._dist_target_side)
        model = self._distance_edit_model
        meas = {
            'name': self._dist_name_edit.text() or self._t(
                'tool_editor.measurements.new_distance', 'New Distance'),
            'start_part': str(model.get('start_part', '')).strip(),
            'start_xyz': str(model.get('start_xyz', '0, 0, 0')).strip() or '0, 0, 0',
            'end_part': str(model.get('end_part', '')).strip(),
            'end_xyz': str(model.get('end_xyz', '0, 0, 0')).strip() or '0, 0, 0',
            'distance_axis': self._distance_axis_value(),
            'label_value_mode': self._distance_value_mode(),
            'label_custom_value': self._dist_custom_value_edit.text().strip(),
            'type': 'distance',
        }
        self._distance_edit_model = dict(meas)
        self._current_distance_item.setData(Qt.UserRole, meas)
        self._current_distance_item.setText(meas['name'])
        self._refresh_preview_measurements()

    def _distance_value_mode(self) -> str:
        mode = str(self._dist_value_mode_combo.currentData() or 'measured').strip().lower()
        return mode if mode in {'measured', 'custom'} else 'measured'

    def _set_distance_value_mode(self, mode: str, commit: bool = True):
        normalized = mode if mode in {'measured', 'custom'} else 'measured'
        idx = 0 if normalized == 'measured' else 1
        self._dist_value_mode_combo.blockSignals(True)
        self._dist_value_mode_combo.setCurrentIndex(idx)
        self._dist_value_mode_combo.blockSignals(False)
        self._dist_custom_value_edit.setEnabled(normalized == 'custom')
        if commit:
            self._commit_distance_edit()

    def _on_distance_value_mode_changed(self, *_args):
        self._set_distance_value_mode(self._distance_value_mode(), commit=True)

    def _distance_axis_value(self) -> str:
        if getattr(self, '_dist_axis_direct_btn', None) and self._dist_axis_direct_btn.isChecked():
            return 'direct'
        if getattr(self, '_dist_axis_x_btn', None) and self._dist_axis_x_btn.isChecked():
            return 'x'
        if getattr(self, '_dist_axis_y_btn', None) and self._dist_axis_y_btn.isChecked():
            return 'y'
        return 'z'

    def _set_distance_axis(self, axis: str, commit: bool = True):
        normalized = axis if axis in {'direct', 'x', 'y', 'z'} else 'z'
        self._dist_axis_direct_btn.setChecked(normalized == 'direct')
        self._dist_axis_x_btn.setChecked(normalized == 'x')
        self._dist_axis_y_btn.setChecked(normalized == 'y')
        self._dist_axis_z_btn.setChecked(normalized == 'z')
        if commit:
            self._commit_distance_edit()

    def _commit_diameter_edit(self):
        if not self._current_diameter_item:
            return
        meas = {
            'name': self._diam_name_edit.text() or self._t(
                'tool_editor.measurements.new_diameter', 'New Diameter'),
            'part': self._diam_part_edit.text().strip(),
            'center_xyz': self._xyz_text_from_edits(
                (self._diam_center_x_edit, self._diam_center_y_edit, self._diam_center_z_edit)
            ),
            'axis_xyz': self._xyz_text_from_edits(
                (self._diam_axis_x_edit, self._diam_axis_y_edit, self._diam_axis_z_edit)
            ),
            'diameter': self._diam_diameter_edit.text().strip() or '10',
            'type': 'diameter_ring',
        }
        self._current_diameter_item.setData(Qt.UserRole, meas)
        self._current_diameter_item.setText(meas['name'])
        self._refresh_preview_measurements()

    def _commit_radius_edit(self):
        if not self._current_radius_item:
            return
        meas = {
            'name': self._radius_name_edit.text() or self._t('tool_editor.measurements.new_radius', 'New Radius'),
            'part': self._radius_part_edit.text().strip(),
            'center_xyz': self._xyz_text_from_edits(
                (self._radius_center_x_edit, self._radius_center_y_edit, self._radius_center_z_edit)
            ),
            'axis_xyz': self._xyz_text_from_edits(
                (self._radius_axis_x_edit, self._radius_axis_y_edit, self._radius_axis_z_edit)
            ),
            'radius': self._radius_value_edit.text().strip() or '5',
            'type': 'radius',
        }
        self._current_radius_item.setData(Qt.UserRole, meas)
        self._current_radius_item.setText(meas['name'])
        self._refresh_preview_measurements()

    def _commit_angle_edit(self):
        if not self._current_angle_item:
            return
        meas = {
            'name': self._angle_name_edit.text() or self._t('tool_editor.measurements.new_angle', 'New Angle'),
            'part': self._angle_part_edit.text().strip(),
            'center_xyz': self._xyz_text_from_edits(
                (self._angle_center_x_edit, self._angle_center_y_edit, self._angle_center_z_edit)
            ),
            'start_xyz': self._xyz_text_from_edits(
                (self._angle_start_x_edit, self._angle_start_y_edit, self._angle_start_z_edit)
            ),
            'end_xyz': self._xyz_text_from_edits(
                (self._angle_end_x_edit, self._angle_end_y_edit, self._angle_end_z_edit)
            ),
            'type': 'angle',
        }
        self._current_angle_item.setData(Qt.UserRole, meas)
        self._current_angle_item.setText(meas['name'])
        self._refresh_preview_measurements()

    def _set_xyz_edits(self, edits: tuple[QLineEdit, QLineEdit, QLineEdit], value):
        x, y, z = _xyz_to_tuple(value)
        edits[0].setText(_fmt_coord(x))
        edits[1].setText(_fmt_coord(y))
        edits[2].setText(_fmt_coord(z))

    def _xyz_text_from_edits(self, edits: tuple[QLineEdit, QLineEdit, QLineEdit]) -> str:
        values = []
        defaults = [0.0, 0.0, 0.0]
        for i, axis_edit in enumerate(edits):
            text = axis_edit.text().strip().replace(',', '.')
            try:
                values.append(float(text))
            except Exception:
                values.append(defaults[i])
        return f"{_fmt_coord(values[0])}, {_fmt_coord(values[1])}, {_fmt_coord(values[2])}"

    @staticmethod
    def _focused_axis(edits: tuple[QLineEdit, QLineEdit, QLineEdit]) -> str:
        if edits[0].hasFocus():
            return 'x'
        if edits[1].hasFocus():
            return 'y'
        if edits[2].hasFocus():
            return 'z'
        return 'all'

    # ─────────────────────────────────────────────────────────────────
    # POINT PICKING
    # ─────────────────────────────────────────────────────────────────

    def _on_pick_target(self):
        side = self._dist_target_side if self._dist_target_side in {'start', 'end'} else 'start'
        if self._pick_target and self._pick_target.startswith(f'target_xyz:{side}:'):
            self._cancel_pick()
            return
        self._cancel_pick()
        axis = self._focused_axis((self._dist_target_x_edit, self._dist_target_y_edit, self._dist_target_z_edit))
        self._pick_target = f'target_xyz:{side}:{axis}'
        self._preview_widget.set_point_picking_enabled(True)
        self._dist_target_pick_btn.setText('\u2716')

    def _on_pick_center(self):
        if self._pick_target and self._pick_target.startswith('center_xyz'):
            self._cancel_pick()
            return
        self._cancel_pick()
        axis = self._focused_axis((self._diam_center_x_edit, self._diam_center_y_edit, self._diam_center_z_edit))
        self._pick_target = f'center_xyz:{axis}'
        self._preview_widget.set_point_picking_enabled(True)
        self._diam_center_pick_btn.setText('\u2716')

    def _on_pick_radius_center(self):
        if self._pick_target and self._pick_target.startswith('radius_center_xyz'):
            self._cancel_pick()
            return
        self._cancel_pick()
        axis = self._focused_axis((self._radius_center_x_edit, self._radius_center_y_edit, self._radius_center_z_edit))
        self._pick_target = f'radius_center_xyz:{axis}'
        self._preview_widget.set_point_picking_enabled(True)
        self._radius_center_pick_btn.setText('\u2716')

    def _on_pick_angle_center(self):
        self._start_angle_pick('angle_center_xyz', self._angle_center_pick_btn, (self._angle_center_x_edit, self._angle_center_y_edit, self._angle_center_z_edit))

    def _on_pick_angle_start(self):
        self._start_angle_pick('angle_start_xyz', self._angle_start_pick_btn, (self._angle_start_x_edit, self._angle_start_y_edit, self._angle_start_z_edit))

    def _on_pick_angle_end(self):
        self._start_angle_pick('angle_end_xyz', self._angle_end_pick_btn, (self._angle_end_x_edit, self._angle_end_y_edit, self._angle_end_z_edit))

    def _start_angle_pick(self, target_prefix: str, btn: QPushButton, edits: tuple[QLineEdit, QLineEdit, QLineEdit]):
        if self._pick_target and self._pick_target.startswith(target_prefix):
            self._cancel_pick()
            return
        self._cancel_pick()
        axis = self._focused_axis(edits)
        self._pick_target = f'{target_prefix}:{axis}'
        self._preview_widget.set_point_picking_enabled(True)
        btn.setText('\u2716')

    def _cancel_pick(self):
        self._pick_target = None
        if hasattr(self, '_preview_widget'):
            self._preview_widget.set_point_picking_enabled(False)
        pick_label = self._t('tool_editor.measurements.pick', 'Pick')
        if hasattr(self, '_dist_target_pick_btn'):
            self._dist_target_pick_btn.setText(pick_label)
        if hasattr(self, '_diam_center_pick_btn'):
            self._diam_center_pick_btn.setText(pick_label)
        if hasattr(self, '_radius_center_pick_btn'):
            self._radius_center_pick_btn.setText(pick_label)
        if hasattr(self, '_angle_center_pick_btn'):
            self._angle_center_pick_btn.setText(pick_label)
        if hasattr(self, '_angle_start_pick_btn'):
            self._angle_start_pick_btn.setText(pick_label)
        if hasattr(self, '_angle_end_pick_btn'):
            self._angle_end_pick_btn.setText(pick_label)

    def _on_point_picked(self, data: dict):
        target = self._pick_target  # save before _cancel_pick clears it
        self._cancel_pick()
        if not target:
            return
        x = data.get('x', 0)
        y = data.get('y', 0)
        z = data.get('z', 0)
        values = {'x': float(x), 'y': float(y), 'z': float(z)}
        part_name = data.get('partName', '')

        target_parts = target.split(':')
        target_name = target_parts[0] if target_parts else ''
        axis = target_parts[-1] if len(target_parts) >= 2 else 'all'

        def apply_pick_to_edits(edits: tuple[QLineEdit, QLineEdit, QLineEdit]):
            if axis == 'x':
                edits[0].setText(_fmt_coord(values['x']))
                return
            if axis == 'y':
                edits[1].setText(_fmt_coord(values['y']))
                return
            if axis == 'z':
                edits[2].setText(_fmt_coord(values['z']))
                return
            edits[0].setText(_fmt_coord(values['x']))
            edits[1].setText(_fmt_coord(values['y']))
            edits[2].setText(_fmt_coord(values['z']))

        if target_name == 'target_xyz':
            side = 'start'
            if ':' in target:
                parts = target.split(':')
                if len(parts) >= 2 and parts[1] in {'start', 'end'}:
                    side = parts[1]
            if side != self._dist_target_side:
                self._set_distance_target_side(side, commit=False)
            apply_pick_to_edits((self._dist_target_x_edit, self._dist_target_y_edit, self._dist_target_z_edit))
            if part_name:
                self._dist_target_part_edit.setText(part_name)
            self._store_distance_target_fields(side)
        elif target_name == 'center_xyz':
            apply_pick_to_edits((self._diam_center_x_edit, self._diam_center_y_edit, self._diam_center_z_edit))
            if part_name:
                self._diam_part_edit.setText(part_name)
        elif target_name == 'radius_center_xyz':
            apply_pick_to_edits((self._radius_center_x_edit, self._radius_center_y_edit, self._radius_center_z_edit))
            if part_name:
                self._radius_part_edit.setText(part_name)
        elif target_name == 'angle_center_xyz':
            apply_pick_to_edits((self._angle_center_x_edit, self._angle_center_y_edit, self._angle_center_z_edit))
            if part_name:
                self._angle_part_edit.setText(part_name)
        elif target_name == 'angle_start_xyz':
            apply_pick_to_edits((self._angle_start_x_edit, self._angle_start_y_edit, self._angle_start_z_edit))
            if part_name:
                self._angle_part_edit.setText(part_name)
        elif target_name == 'angle_end_xyz':
            apply_pick_to_edits((self._angle_end_x_edit, self._angle_end_y_edit, self._angle_end_z_edit))
            if part_name:
                self._angle_part_edit.setText(part_name)

        self._commit_current_edit()

    # ─────────────────────────────────────────────────────────────────
    # PREVIEW REFRESH
    # ─────────────────────────────────────────────────────────────────

    def _refresh_preview_measurements(self):
        overlays = []
        for i in range(self._distance_list.count()):
            meas = dict(self._distance_list.item(i).data(Qt.UserRole))
            meas['type'] = 'distance'
            overlays.append(meas)
        for i in range(self._diameter_list.count()):
            meas = dict(self._diameter_list.item(i).data(Qt.UserRole))
            meas['type'] = 'diameter_ring'
            overlays.append(meas)
        for i in range(self._radius_list.count()):
            meas = dict(self._radius_list.item(i).data(Qt.UserRole))
            meas['type'] = 'radius'
            overlays.append(meas)
        for i in range(self._angle_list.count()):
            meas = dict(self._angle_list.item(i).data(Qt.UserRole))
            meas['type'] = 'angle'
            overlays.append(meas)
        self._preview_widget.set_measurement_overlays(overlays)

    # ─────────────────────────────────────────────────────────────────
    # OUTPUT
    # ─────────────────────────────────────────────────────────────────

    def get_measurements(self) -> dict:
        """Return all measurements from the dialog."""
        distance_meas = [
            self._distance_list.item(i).data(Qt.UserRole)
            for i in range(self._distance_list.count())
        ]
        diameter_meas = [
            self._diameter_list.item(i).data(Qt.UserRole)
            for i in range(self._diameter_list.count())
        ]
        radius_meas = [
            self._radius_list.item(i).data(Qt.UserRole)
            for i in range(self._radius_list.count())
        ]
        angle_meas = [
            self._angle_list.item(i).data(Qt.UserRole)
            for i in range(self._angle_list.count())
        ]
        return {
            'distance_measurements': distance_meas,
            'diameter_measurements': diameter_meas,
            'radius_measurements': radius_meas,
            'angle_measurements': angle_meas,
        }
