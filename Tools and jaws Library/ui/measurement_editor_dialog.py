"""
Measurement Editor Dialog - Visual measurement configuration in 3D space.

Allows users to add and configure distance measurements and diameter rings
with visual feedback in the 3D preview. Users can click in the 3D view to
select anchor points or manually enter coordinates.
"""

from typing import Callable
from PySide6.QtCore import QEvent, Qt, QTimer, QSize
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QCheckBox,
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QWidget, QFrame, QLabel, QGroupBox,
    QPushButton, QLineEdit, QSplitter, QListWidget, QListWidgetItem,
    QAbstractItemView, QStackedWidget, QSizePolicy,
)
from config import TOOL_ICONS_DIR
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

    text = (
        text.replace('[', ' ')
        .replace(']', ' ')
        .replace('(', ' ')
        .replace(')', ' ')
        .replace(';', ',')
    )
    parts = [p.strip() for p in text.split(',') if p.strip()]
    if len(parts) < 3:
        return 0.0, 0.0, 0.0
    try:
        return float(parts[0]), float(parts[1]), float(parts[2])
    except Exception:
        return 0.0, 0.0, 0.0


def _fmt_coord(value: float) -> str:
    return f"{float(value):.4g}"


def _xyz_to_text(value) -> str:
    x, y, z = _xyz_to_tuple(value)
    return f"{_fmt_coord(x)}, {_fmt_coord(y)}, {_fmt_coord(z)}"


def _xyz_to_text_optional(value) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    return _xyz_to_text(value)


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
        self._pending_add_return_meta: dict | None = None
        self._measurement_uid_counter = 0
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(350)
        self._commit_timer.timeout.connect(self._commit_current_edit)

        self.setWindowTitle(self._t('tool_editor.measurements.editor_title', 'Measurement Editor'))
        self.resize(1000, 720)
        self.setMinimumSize(700, 520)
        self.setObjectName('measurementEditorDialog')
        self.setProperty('workEditorDialog', True)
        self.setStyleSheet('QDialog#measurementEditorDialog { background-color: #ffffff; border: 1px solid #c8d4e0; }')

        self._build_ui()
        self._populate_measurements()

        if self._parts:
            self._preview_widget.load_parts(self._parts)
        self._preview_widget.set_measurements_visible(True)
        self._preview_widget.set_measurement_drag_enabled(True)
        self._preview_widget.point_picked.connect(self._on_point_picked)
        self._preview_widget.measurement_updated.connect(self._on_measurement_updated)
        self._update_distance_mode_controls_visibility()
        self._refresh_preview_measurements()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _icon(self, filename: str) -> QIcon:
        path = TOOL_ICONS_DIR / filename
        return QIcon(str(path)) if path.exists() else QIcon()

    # ─────────────────────────────────────────────────────────────────
    # UI BUILD
    # ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet(
            'QSplitter::handle:horizontal {'
            '  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,'
            '    stop:0 #ffffff, stop:0.46 #ffffff, stop:0.5 #c4d1dd, stop:0.54 #ffffff, stop:1 #ffffff'
            '  );'
            '  border: none;'
            '  margin: 0;'
            '}'
        )

        # ── LEFT PANEL ──────────────────────────────────────────────
        left_panel = QFrame()
        left_panel.setObjectName('measurementEditorLeftPanel')
        left_panel.setStyleSheet('''
            QFrame#measurementEditorLeftPanel { background-color: #ffffff; }
            QLabel { background-color: transparent; }
            QCheckBox { background-color: transparent; }
            QStackedWidget > QWidget { background-color: #ffffff; }
        ''')
        left_panel.setMinimumWidth(420)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # Keep type-specific backing lists for compatibility, but show one unified list in UI.
        self._distance_list = QListWidget()
        self._distance_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._distance_list.itemSelectionChanged.connect(self._on_distance_selected)
        self._diameter_list = QListWidget()
        self._diameter_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._diameter_list.itemSelectionChanged.connect(self._on_diameter_selected)
        self._radius_list = QListWidget()
        self._radius_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._radius_list.itemSelectionChanged.connect(self._on_radius_selected)
        self._angle_list = QListWidget()
        self._angle_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._angle_list.itemSelectionChanged.connect(self._on_angle_selected)
        self._measurement_all_list = QListWidget()
        self._measurement_all_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._measurement_all_list.itemSelectionChanged.connect(self._on_all_measurement_selected)
        left_layout.addWidget(self._measurement_all_list, 1)

        list_btn_row = QHBoxLayout()
        self._add_measurement_btn = QPushButton(self._t('common.add', 'Add'))
        self._remove_measurement_btn = QPushButton(self._t('common.remove', 'Remove'))
        self._add_measurement_btn.setText('')
        self._add_measurement_btn.setProperty('panelActionButton', True)
        self._add_measurement_btn.setIcon(self._icon('plus.svg'))
        self._add_measurement_btn.setIconSize(QSize(22, 22))
        self._add_measurement_btn.setFixedSize(48, 36)
        self._add_measurement_btn.setToolTip(self._t('common.add', 'Add'))
        self._remove_measurement_btn.setText('')
        self._remove_measurement_btn.setProperty('panelActionButton', True)
        self._remove_measurement_btn.setIcon(self._icon('remove.svg'))
        self._remove_measurement_btn.setIconSize(QSize(22, 22))
        self._remove_measurement_btn.setFixedSize(48, 36)
        self._remove_measurement_btn.setToolTip(self._t('common.remove', 'Remove'))
        self._add_measurement_btn.clicked.connect(self._add_current_measurement)
        self._remove_measurement_btn.clicked.connect(self._remove_current_measurement)
        list_btn_row.addWidget(self._add_measurement_btn)
        list_btn_row.addWidget(self._remove_measurement_btn)
        self._add_type_cancel_top_btn = QPushButton('')
        self._add_type_cancel_top_btn.setProperty('panelActionButton', True)
        self._add_type_cancel_top_btn.setIcon(self._icon('cancel.svg'))
        self._add_type_cancel_top_btn.setIconSize(QSize(24, 24))
        self._add_type_cancel_top_btn.setFixedSize(46, 36)
        self._add_type_cancel_top_btn.setToolTip(self._t('common.cancel', 'Cancel'))
        self._add_type_cancel_top_btn.clicked.connect(self._cancel_add_measurement_type_picker)
        self._add_type_cancel_top_btn.setVisible(False)
        list_btn_row.addWidget(self._add_type_cancel_top_btn)
        self._distance_detail_mode_lbl = QLabel(
            self._t('tool_editor.measurements.precise_mode', 'Precise')
        )
        self._distance_detail_mode_lbl.setStyleSheet('background: transparent; color: #1f2d3d;')
        self._distance_detail_mode_btn = QCheckBox('')
        self._distance_detail_mode_btn.setChecked(False)
        self._distance_detail_mode_btn.stateChanged.connect(self._on_distance_detail_mode_changed)
        _tick_icon_path = (TOOL_ICONS_DIR / 'check_small.svg').as_posix()
        self._distance_detail_mode_btn.setStyleSheet(
            'QCheckBox { background: transparent; }'
            'QCheckBox::indicator {'
            '  width: 14px;'
            '  height: 14px;'
            '  border: 1px solid #bfd0e2;'
            '  border-radius: 2px;'
            '  background: #ffffff;'
            '}'
            'QCheckBox::indicator:unchecked {'
            '  border: 1px solid #bfd0e2;'
            '  border-radius: 2px;'
            '  background: #ffffff;'
            '}'
            'QCheckBox::indicator:checked {'
            '  border: 1px solid #bfd0e2;'
            '  border-radius: 2px;'
            '  background: #ffffff;'
            f'  image: url("{_tick_icon_path}");'
            '}'
        )
        self._distance_detail_mode_col = QWidget()
        self._distance_detail_mode_col.setStyleSheet('background: transparent;')
        _detail_col_layout = QHBoxLayout(self._distance_detail_mode_col)
        _detail_col_layout.setContentsMargins(0, 0, 0, 0)
        _detail_col_layout.setSpacing(5)
        _detail_col_layout.addWidget(self._distance_detail_mode_lbl, 0, Qt.AlignVCenter)
        _detail_col_layout.addWidget(self._distance_detail_mode_btn, 0, Qt.AlignVCenter)
        list_btn_row.addStretch(1)
        list_btn_row.addWidget(self._distance_detail_mode_col)
        list_btn_row.addSpacing(10)
        left_layout.addLayout(list_btn_row)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        left_layout.addWidget(separator)

        # Edit form stack: 0 placeholder, 1 distance, 2 diameter, 3 radius, 4 angle
        self._edit_stack = QStackedWidget()
        self._edit_stack.setMinimumHeight(386)
        self._edit_stack.setMaximumHeight(386)
        self._edit_stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        placeholder = QLabel(self._t(
            'tool_editor.measurements.select_to_edit', 'Select a measurement to edit.'))
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet('color: #6b7b8e; font-size: 11px;')
        self._edit_stack.addWidget(placeholder)
        self._edit_stack.addWidget(self._build_distance_form())
        self._edit_stack.addWidget(self._build_diameter_form())
        self._edit_stack.addWidget(self._build_radius_form())
        self._edit_stack.addWidget(self._build_angle_form())
        self._add_type_picker_page_index = self._edit_stack.addWidget(self._build_measurement_type_picker())
        left_layout.addWidget(self._edit_stack)

        # ── PREVIEW ─────────────────────────────────────────────────
        self._preview_widget = StlPreviewWidget()
        self._preview_widget.set_control_hint_text(
            self._t(
                'tool_editor.hint.rotate_pan_zoom',
                'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
            )
        )
        self._preview_container = QWidget()
        _preview_layout = QVBoxLayout(self._preview_container)
        _preview_layout.setContentsMargins(0, 0, 0, 0)
        _preview_layout.setSpacing(0)
        _preview_layout.addWidget(self._preview_widget)
        self._preview_container.installEventFilter(self)

        # Overlay is a direct child (no layout) — positioned via setGeometry in
        # _position_axis_overlay(). WA_NativeWindow gives it its own HWND so it
        # renders on top of the QWebEngineView native window on Windows.
        self._axis_pick_overlay = QFrame(self._preview_container)
        self._axis_pick_overlay.setAttribute(Qt.WA_NativeWindow)
        self._axis_pick_overlay.setAttribute(Qt.WA_StyledBackground, True)
        self._axis_pick_overlay.setAutoFillBackground(True)
        self._axis_pick_overlay.setFocusPolicy(Qt.StrongFocus)
        self._axis_pick_overlay.setObjectName('axisPickOverlay')
        self._axis_pick_overlay.setStyleSheet(
            'QFrame#axisPickOverlay {'
            '  background: rgba(255, 255, 255, 0.94);'
            '  border: 1px solid #cfd8e2;'
            '  border-radius: 6px;'
            '}'
        )
        _overlay_layout = QVBoxLayout(self._axis_pick_overlay)
        _overlay_layout.setContentsMargins(8, 6, 8, 6)
        _overlay_layout.setSpacing(4)
        _axis_lbl = QLabel(self._t('tool_editor.measurements.axis', 'Axis') + ':')
        _axis_lbl.setStyleSheet('background: transparent; font-weight: 600; color: #3a4a5a;')
        _axis_lbl.setAlignment(Qt.AlignHCenter)
        _overlay_layout.addWidget(_axis_lbl)
        self._axis_overlay_btns = {}
        for _axis_text, _axis_val in [
            (self._t('tool_editor.measurements.axis_direct_short', '3D'), 'direct'),
            (self._t('tool_editor.measurements.axis_x', 'X'), 'x'),
            (self._t('tool_editor.measurements.axis_y', 'Y'), 'y'),
            (self._t('tool_editor.measurements.axis_z', 'Z'), 'z'),
        ]:
            _btn = QPushButton(_axis_text)
            _btn.setCheckable(True)
            _btn.setFixedSize(42, 28)
            _btn.setProperty('panelActionButton', True)
            _btn.setStyleSheet(
                'QPushButton:checked {'
                '  background-color: #2397e6;'
                '  border-color: #1680de;'
                '  color: #ffffff;'
                '}'
            )
            _btn.clicked.connect(lambda _checked, v=_axis_val: self._on_axis_overlay_selected(v))
            _btn.pressed.connect(lambda v=_axis_val: self._on_axis_overlay_selected(v))
            _overlay_layout.addWidget(_btn)
            self._axis_overlay_btns[_axis_val] = _btn
        self._axis_pick_overlay.setVisible(False)

        self._axis_hint_overlay = QFrame(self._preview_container)
        self._axis_hint_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._axis_hint_overlay.setObjectName('axisHintOverlay')
        self._axis_hint_overlay.setStyleSheet(
            'QFrame#axisHintOverlay {'
            '  background: rgba(255, 255, 255, 0.9);'
            '  border: 1px solid #d0d8e0;'
            '  border-radius: 6px;'
            '}'
            'QFrame#axisHintOverlay QLabel { background: transparent; }'
        )
        _axis_hint_layout = QVBoxLayout(self._axis_hint_overlay)
        _axis_hint_layout.setContentsMargins(6, 5, 6, 5)
        _axis_hint_layout.setSpacing(1)
        _axis_hint_title = QLabel(self._t('tool_editor.measurements.axis_hint', 'Axis'))
        _axis_hint_title.setStyleSheet('font-size: 8pt; font-weight: 600; color: #4a5a6a;')
        _axis_hint_layout.addWidget(_axis_hint_title, 0, Qt.AlignLeft)
        _axis_hint_x = QLabel('X \u2192')
        _axis_hint_x.setStyleSheet('font-size: 8pt; font-weight: 600; color: #cc3333;')
        _axis_hint_layout.addWidget(_axis_hint_x, 0, Qt.AlignLeft)
        _axis_hint_y = QLabel('Y \u2191')
        _axis_hint_y.setStyleSheet('font-size: 8pt; font-weight: 600; color: #2f8f2f;')
        _axis_hint_layout.addWidget(_axis_hint_y, 0, Qt.AlignLeft)
        _axis_hint_z = QLabel('Z \u2a00')
        _axis_hint_z.setStyleSheet('font-size: 8pt; font-weight: 600; color: #3366cc;')
        _axis_hint_layout.addWidget(_axis_hint_z, 0, Qt.AlignLeft)
        self._axis_hint_overlay.setVisible(False)

        splitter.addWidget(left_panel)
        splitter.addWidget(self._preview_container)
        splitter.setSizes([420, 580])
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
        root.addWidget(button_box)
        apply_secondary_button_theme(self, save_btn)

    def _build_distance_form(self) -> QWidget:
        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(4, 4, 4, 4)
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(4)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._dist_basic_section = QGroupBox(self._t('tool_editor.measurements.basic_functions', 'Basic functions'))
        self._dist_basic_section.setStyleSheet(
            'QGroupBox {'
            '  background-color: #f0f6fc;'
            '  border: 1px solid #d0d8e0;'
            '  border-radius: 6px;'
            '  margin-top: 10px;'
            '  padding-top: 8px;'
            '}'
            'QGroupBox::title {'
            '  subcontrol-origin: margin;'
            '  left: 10px;'
            '  padding: 0 4px;'
            '  color: #5a6b7c;'
            '  font-size: 8pt;'
            '  font-weight: 600;'
            '}'
        )
        basic_form = QFormLayout(self._dist_basic_section)
        basic_form.setContentsMargins(8, 6, 8, 6)
        basic_form.setHorizontalSpacing(6)
        basic_form.setVerticalSpacing(3)
        basic_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._dist_basic_section.setMinimumHeight(160)
        self._dist_basic_section.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._dist_name_edit = QLineEdit()
        self._dist_name_edit.setPlaceholderText('Distance 1')
        self._dist_name_edit.editingFinished.connect(self._schedule_commit)
        basic_form.addRow(self._t('common.name', 'Name') + ':', self._dist_name_edit)

        pick_row = QHBoxLayout()
        pick_row.setSpacing(6)
        self._dist_pick_points_btn = QPushButton(
            ''
        )
        self._dist_pick_points_btn.setIcon(self._icon('points_select.svg'))
        self._dist_pick_points_btn.setIconSize(QSize(24, 24))
        self._dist_pick_points_btn.setToolTip(self._t('tool_editor.measurements.pick', 'Pick'))
        self._dist_pick_points_btn.setFixedWidth(46)
        self._dist_pick_points_btn.clicked.connect(self._on_pick_target)
        self._dist_pick_status_label = QLabel('')
        self._dist_pick_status_label.setStyleSheet('color: #6b7b8e; background: transparent;')
        pick_row.addWidget(self._dist_pick_points_btn)
        pick_row.addWidget(self._dist_pick_status_label, 1)
        basic_form.addRow(self._t('tool_editor.measurements.points', 'Points') + ':', pick_row)

        value_row = QHBoxLayout()
        value_row.setSpacing(6)
        self._dist_value_mode_btn = QPushButton(self._t('tool_editor.measurements.value_mode_measured', 'Measured'))
        self._dist_value_mode_btn.setCheckable(True)
        self._dist_value_mode_btn.setChecked(False)  # checked = custom, unchecked = measured
        self._dist_value_mode_btn.setFixedWidth(100)
        self._dist_value_mode_btn.clicked.connect(self._on_distance_value_mode_toggled)
        self._dist_value_edit = QLineEdit()
        self._dist_value_edit.setPlaceholderText(
            self._t('tool_editor.measurements.value_placeholder', 'Measured or custom value')
        )
        self._dist_value_edit.editingFinished.connect(self._schedule_commit)
        value_row.addWidget(self._dist_value_mode_btn)
        value_row.addWidget(self._dist_value_edit, 1)
        _display_lbl = QLabel(self._t('tool_editor.measurements.display_value', 'Display\nValue') + ':')
        _display_lbl.setAlignment(Qt.AlignRight | Qt.AlignTop)
        _display_lbl.setStyleSheet('padding-top: 0px; margin-top: -2px;')
        basic_form.addRow(_display_lbl, value_row)
        form.addRow(self._dist_basic_section)

        self._dist_adjust_section = QGroupBox('')
        self._dist_adjust_section.setStyleSheet(
            'QGroupBox {'
            '  background-color: #f0f6fc;'
            '  border: 1px solid #d0d8e0;'
            '  border-radius: 6px;'
            '  margin-top: 10px;'
            '  padding-top: 8px;'
            '}'
            'QGroupBox::title {'
            '  subcontrol-origin: margin;'
            '  left: 10px;'
            '  padding: 0 4px;'
            '  color: #5a6b7c;'
            '  font-size: 8pt;'
            '  font-weight: 600;'
            '}'
        )
        adjust_section_layout = QVBoxLayout(self._dist_adjust_section)
        adjust_section_layout.setContentsMargins(8, 6, 8, 4)
        adjust_section_layout.setSpacing(2)

        # Keep each label in the same column as its value input for stable alignment.
        self._dist_adjust_x_edit = QLineEdit('0')
        self._dist_adjust_y_edit = QLineEdit('0')
        self._dist_adjust_z_edit = QLineEdit('0')
        self._dist_adjust_axis_by_edit = {
            self._dist_adjust_x_edit: 'x',
            self._dist_adjust_y_edit: 'y',
            self._dist_adjust_z_edit: 'z',
        }
        self._dist_adjust_active_axis = 'x'
        for _ae in (self._dist_adjust_x_edit, self._dist_adjust_y_edit, self._dist_adjust_z_edit):
            _ae.setFixedWidth(74)
            _ae.editingFinished.connect(self._schedule_commit)
            _ae.installEventFilter(self)
        self._dist_nudge_step_edit = QLineEdit('1.0')
        self._dist_nudge_step_edit.setFixedWidth(74)

        _adjust_label_style = (
            'color: #6b7b8e; font-size: 9pt; background: transparent; '
            'padding: 0px 0px 1px 0px;'
        )
        precise_top_row = QHBoxLayout()
        precise_top_row.setSpacing(4)
        precise_top_row.setContentsMargins(0, 0, 0, 0)
        for _hdr_key, _hdr_fallback, _edit in [
            ('tool_editor.measurements.axis_x', 'X', self._dist_adjust_x_edit),
            ('tool_editor.measurements.axis_y', 'Y', self._dist_adjust_y_edit),
            ('tool_editor.measurements.axis_z', 'Z', self._dist_adjust_z_edit),
            (None, 'mm', self._dist_nudge_step_edit),
        ]:
            _col = QVBoxLayout()
            _col.setSpacing(1)
            _col.setContentsMargins(0, 0, 0, 0)
            _hdr_lbl = QLabel(self._t(_hdr_key, _hdr_fallback) if _hdr_key else _hdr_fallback)
            _hdr_lbl.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            _hdr_lbl.setStyleSheet(_adjust_label_style)
            _col.addWidget(_hdr_lbl)
            _col.addWidget(_edit)
            precise_top_row.addLayout(_col)

        self._dist_nudge_minus_btn = QPushButton('-')
        self._dist_nudge_minus_btn.setText('\u2212')
        self._dist_nudge_minus_btn.setFixedSize(34, 34)
        self._dist_nudge_minus_btn.setStyleSheet('font-size: 19px; font-weight: 700; padding: 0px 0px 2px 0px;')
        self._dist_nudge_minus_btn.setProperty('arrowMoveButton', True)
        self._dist_nudge_minus_btn.clicked.connect(lambda: self._on_distance_point_nudge('-'))
        self._dist_nudge_minus_btn.setFocusPolicy(Qt.NoFocus)
        self._dist_nudge_plus_btn = QPushButton('+')
        self._dist_nudge_plus_btn.setFixedSize(34, 34)
        self._dist_nudge_plus_btn.setStyleSheet('font-size: 19px; font-weight: 700; padding: 0px 0px 1px 0px;')
        self._dist_nudge_plus_btn.setProperty('arrowMoveButton', True)
        self._dist_nudge_plus_btn.clicked.connect(lambda: self._on_distance_point_nudge('+'))
        self._dist_nudge_plus_btn.setFocusPolicy(Qt.NoFocus)
        _pm_container = QWidget()
        _pm_layout = QVBoxLayout(_pm_container)
        _pm_layout.setContentsMargins(0, 0, 0, 0)
        _pm_layout.setSpacing(2)
        _pm_layout.addWidget(self._dist_nudge_plus_btn)
        _pm_layout.addWidget(self._dist_nudge_minus_btn)
        precise_top_row.addSpacing(4)
        precise_top_row.addWidget(_pm_container, 0, Qt.AlignBottom)
        precise_top_row.addStretch(1)
        adjust_section_layout.addLayout(precise_top_row)

        adjust_bottom_row = QHBoxLayout()
        adjust_bottom_row.setSpacing(6)
        adjust_bottom_row.setContentsMargins(0, 0, 0, 0)
        self._dist_adjust_mode_btn = QPushButton('')
        self._dist_adjust_mode_btn.setCheckable(True)
        self._dist_adjust_mode_btn.setChecked(False)  # checked = nudge, unchecked = arrow offset
        self._dist_adjust_mode_btn.setFixedWidth(46)
        self._dist_adjust_mode_btn.setIconSize(QSize(24, 24))
        self._dist_adjust_mode_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._dist_adjust_mode_btn.clicked.connect(self._on_distance_adjust_mode_toggled)
        self._dist_adjust_mode_btn.setFocusPolicy(Qt.NoFocus)
        self._dist_nudge_point_btn = QPushButton('')
        self._dist_nudge_point_btn.setCheckable(True)
        self._dist_nudge_point_btn.setChecked(False)  # checked = end, unchecked = start
        self._dist_nudge_point_btn.setFixedWidth(46)
        self._dist_nudge_point_btn.setIconSize(QSize(24, 24))
        self._dist_nudge_point_btn.clicked.connect(self._on_nudge_point_toggled)
        self._dist_nudge_point_btn.setVisible(False)
        self._dist_nudge_point_btn.setFocusPolicy(Qt.NoFocus)
        adjust_bottom_row.addWidget(self._dist_adjust_mode_btn)
        adjust_bottom_row.addWidget(self._dist_nudge_point_btn)
        adjust_bottom_row.addStretch(1)
        adjust_section_layout.addLayout(adjust_bottom_row)

        form.addRow(self._dist_adjust_section)
        self._dist_adjust_section.setVisible(False)

        self._distance_edit_model = None
        self._dist_pick_stage = None
        self._set_distance_axis('z', commit=False)
        self._set_distance_nudge_point('start', commit=False)
        self._set_distance_adjust_mode('offset', commit=False)
        self._set_distance_value_mode('measured', commit=False)
        self._update_distance_precise_visibility()
        self._update_distance_measured_value_box()
        self._update_distance_pick_status()

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

    def _build_xyz_header_row(self, with_pick: bool, axis_order: list = None) -> QWidget:
        if axis_order is None:
            axis_order = ['x', 'y', 'z']
        
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        for axis in axis_order:
            key = f'tool_editor.measurements.axis_{axis}'
            fallback = axis.upper()
            lbl = QLabel(self._t(key, fallback))
            lbl.setFixedWidth(56)
            lbl.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            lbl.setStyleSheet('color: #6b7b8e; font-size: 10px; background: transparent;')
            row_layout.addWidget(lbl)

        row_layout.addStretch(1)
        if with_pick:
            row_layout.addSpacing(50)
        return row_widget

    def _build_measurement_type_picker(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel(self._t('tool_editor.measurements.select_type_to_add', 'Select measurement type to add'))
        title.setStyleSheet('color: #5f7082; font-size: 10.5pt; font-weight: 600; background: transparent;')
        layout.addWidget(title)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        buttons = [
            (self._t('tool_editor.measurements.type_length', 'Length'), 'length', top_row),
            (self._t('tool_editor.measurements.type_diameter', 'Diameter'), 'diameter', top_row),
            (self._t('tool_editor.measurements.type_radius', 'Radius'), 'radius', bottom_row),
            (self._t('tool_editor.measurements.type_angle', 'Angle'), 'angle', bottom_row),
        ]
        for text, kind, row in buttons:
            btn = QPushButton(text)
            btn.setProperty('panelActionButton', True)
            btn.setMinimumHeight(34)
            btn.clicked.connect(lambda _checked=False, k=kind: self._add_measurement_of_kind(k))
            row.addWidget(btn, 1)

        layout.addLayout(top_row)
        layout.addLayout(bottom_row)
        layout.addStretch(1)
        return container

    # ─────────────────────────────────────────────────────────────────
    # MEASUREMENT LIST MANAGEMENT
    # ─────────────────────────────────────────────────────────────────

    def _ensure_measurement_uid(self, payload: dict | None) -> str:
        data = payload if isinstance(payload, dict) else {}
        uid = str(data.get('_uid') or '').strip()
        if uid:
            return uid
        self._measurement_uid_counter += 1
        return f"m{self._measurement_uid_counter}"

    @staticmethod
    def _measurement_kind_order() -> tuple[str, ...]:
        return ('length', 'diameter', 'radius', 'angle')

    def _hidden_list_for_kind(self, kind: str) -> QListWidget | None:
        return {
            'length': self._distance_list,
            'diameter': self._diameter_list,
            'radius': self._radius_list,
            'angle': self._angle_list,
        }.get(kind)

    def _active_measurement_kind(self) -> str | None:
        if self._current_distance_item is not None:
            return 'length'
        if self._current_diameter_item is not None:
            return 'diameter'
        if self._current_radius_item is not None:
            return 'radius'
        if self._current_angle_item is not None:
            return 'angle'
        return None

    def _selected_measurement_meta(self) -> dict | None:
        if not hasattr(self, '_measurement_all_list'):
            return None
        item = self._measurement_all_list.currentItem()
        if item is None:
            return None
        meta = item.data(Qt.UserRole)
        return meta if isinstance(meta, dict) else None

    def _find_item_by_uid(self, src_list: QListWidget, uid: str) -> tuple[int, QListWidgetItem | None]:
        uid_str = str(uid or '').strip()
        if not uid_str:
            return -1, None
        for row in range(src_list.count()):
            item = src_list.item(row)
            data = dict(item.data(Qt.UserRole) or {})
            if str(data.get('_uid') or '').strip() == uid_str:
                return row, item
        return -1, None

    def _clear_current_measurement_refs(self):
        self._current_distance_item = None
        self._current_diameter_item = None
        self._current_radius_item = None
        self._current_angle_item = None
        self._distance_edit_model = None

    def _rebuild_measurement_all_list(self, preferred_kind: str | None = None, preferred_uid: str | None = None):
        preferred_kind = str(preferred_kind or '').strip().lower()
        preferred_uid = str(preferred_uid or '').strip()
        self._measurement_all_list.blockSignals(True)
        self._measurement_all_list.clear()

        for kind in self._measurement_kind_order():
            src_list = self._hidden_list_for_kind(kind)
            if src_list is None:
                continue
            for row in range(src_list.count()):
                src_item = src_list.item(row)
                data = dict(src_item.data(Qt.UserRole) or {})
                uid = self._ensure_measurement_uid(data)
                data['_uid'] = uid
                src_item.setData(Qt.UserRole, data)
                list_item = QListWidgetItem(str(data.get('name') or 'Unnamed'))
                list_item.setData(Qt.UserRole, {'kind': kind, 'uid': uid})
                self._measurement_all_list.addItem(list_item)

        self._measurement_all_list.blockSignals(False)

        if self._measurement_all_list.count() <= 0:
            self._clear_current_measurement_refs()
            self._edit_stack.setCurrentIndex(0)
            self._update_distance_mode_controls_visibility()
            return

        if preferred_uid and preferred_kind:
            for idx in range(self._measurement_all_list.count()):
                item = self._measurement_all_list.item(idx)
                meta = item.data(Qt.UserRole) or {}
                if str(meta.get('kind')) == preferred_kind and str(meta.get('uid')) == preferred_uid:
                    self._measurement_all_list.setCurrentRow(idx)
                    return

        self._measurement_all_list.setCurrentRow(0)

    def _update_selected_measurement_name_in_all_list(self, kind: str, uid: str, name: str):
        if not hasattr(self, '_measurement_all_list'):
            return
        for idx in range(self._measurement_all_list.count()):
            item = self._measurement_all_list.item(idx)
            meta = item.data(Qt.UserRole) or {}
            if str(meta.get('kind')) == str(kind) and str(meta.get('uid')) == str(uid):
                item.setText(str(name or 'Unnamed'))
                return

    def _on_all_measurement_selected(self):
        meta = self._selected_measurement_meta()
        self._cancel_pick()

        if not meta:
            if hasattr(self, '_add_type_cancel_top_btn'):
                self._add_type_cancel_top_btn.setVisible(False)
            self._clear_current_measurement_refs()
            self._edit_stack.setCurrentIndex(0)
            self._update_distance_mode_controls_visibility()
            return

        if hasattr(self, '_add_type_cancel_top_btn'):
            self._add_type_cancel_top_btn.setVisible(False)
        kind = str(meta.get('kind') or '').strip().lower()
        uid = str(meta.get('uid') or '').strip()
        src_list = self._hidden_list_for_kind(kind)
        if src_list is None:
            self._edit_stack.setCurrentIndex(0)
            self._update_distance_mode_controls_visibility()
            return

        _, src_item = self._find_item_by_uid(src_list, uid)
        if src_item is None:
            self._rebuild_measurement_all_list()
            return

        for other_kind in self._measurement_kind_order():
            other_list = self._hidden_list_for_kind(other_kind)
            if other_list is None:
                continue
            other_list.blockSignals(True)
            if other_kind == kind:
                other_list.setCurrentItem(src_item)
            else:
                other_list.clearSelection()
            other_list.blockSignals(False)

        self._clear_current_measurement_refs()
        if kind == 'length':
            self._current_distance_item = src_item
            self._populate_distance_form(src_item.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(1)
            meas = dict(src_item.data(Qt.UserRole) or {})
            if not str(meas.get('start_xyz') or '').strip() or not str(meas.get('end_xyz') or '').strip():
                self._start_distance_two_point_pick(reset_points=False)
        elif kind == 'diameter':
            self._current_diameter_item = src_item
            self._populate_diameter_form(src_item.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(2)
        elif kind == 'radius':
            self._current_radius_item = src_item
            self._populate_radius_form(src_item.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(3)
        elif kind == 'angle':
            self._current_angle_item = src_item
            self._populate_angle_form(src_item.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(4)
        else:
            self._edit_stack.setCurrentIndex(0)

        self._update_distance_mode_controls_visibility()

    def _add_measurement_of_kind(self, kind: str):
        normalized = str(kind or '').strip().lower()
        self._pending_add_return_meta = None
        if hasattr(self, '_add_type_cancel_top_btn'):
            self._add_type_cancel_top_btn.setVisible(False)
        if normalized == 'length':
            new_item = self._add_distance_measurement()
        elif normalized == 'diameter':
            new_item = self._add_diameter_measurement()
        elif normalized == 'radius':
            new_item = self._add_radius_measurement()
        elif normalized == 'angle':
            new_item = self._add_angle_measurement()
        else:
            return

        data = dict(new_item.data(Qt.UserRole) or {})
        self._rebuild_measurement_all_list(preferred_kind=normalized, preferred_uid=str(data.get('_uid') or ''))

    def _cancel_add_measurement_type_picker(self):
        self._cancel_pick()
        if hasattr(self, '_add_type_cancel_top_btn'):
            self._add_type_cancel_top_btn.setVisible(False)
        meta = dict(self._pending_add_return_meta or {})
        self._pending_add_return_meta = None
        if meta:
            self._rebuild_measurement_all_list(
                preferred_kind=str(meta.get('kind') or '').strip().lower(),
                preferred_uid=str(meta.get('uid') or '').strip(),
            )
            return
        if self._measurement_all_list.count() > 0:
            self._measurement_all_list.setCurrentRow(0)
        else:
            self._edit_stack.setCurrentIndex(0)
            self._update_distance_mode_controls_visibility()

    def _show_add_measurement_type_picker(self):
        self._cancel_pick()
        current_meta = self._selected_measurement_meta()
        self._pending_add_return_meta = dict(current_meta) if current_meta else None
        self._measurement_all_list.clearSelection()
        self._clear_current_measurement_refs()
        self._edit_stack.setCurrentIndex(self._add_type_picker_page_index)
        self._update_distance_mode_controls_visibility()
        if hasattr(self, '_add_type_cancel_top_btn'):
            self._add_type_cancel_top_btn.setVisible(True)

    def _normalize_distance_measurement(self, meas: dict | None) -> dict:
        data = dict(meas or {})
        uid = self._ensure_measurement_uid(data)
        axis = str(data.get('distance_axis', 'z')).strip().lower()
        if axis not in {'direct', 'x', 'y', 'z'}:
            axis = 'z'
        value_mode = str(data.get('label_value_mode', 'measured')).strip().lower()
        if value_mode not in {'measured', 'custom'}:
            value_mode = 'measured'
        return {
            'name': str(data.get('name', '')).strip() or self._t('tool_editor.measurements.new_distance', 'New Distance'),
            'start_part': str(data.get('start_part', '')).strip(),
            'start_part_index': int(data.get('start_part_index', -1) or -1),
            'start_xyz': _xyz_to_text_optional(data.get('start_xyz', '')),
            'start_space': str(data.get('start_space', 'world')).strip() or 'world',
            'end_part': str(data.get('end_part', '')).strip(),
            'end_part_index': int(data.get('end_part_index', -1) or -1),
            'end_xyz': _xyz_to_text_optional(data.get('end_xyz', '')),
            'end_space': str(data.get('end_space', 'world')).strip() or 'world',
            'distance_axis': axis,
            'label_value_mode': value_mode,
            'label_custom_value': str(data.get('label_custom_value', '')).strip(),
            'offset_xyz': _xyz_to_text_optional(data.get('offset_xyz', '')),
            'start_shift': str(data.get('start_shift', '0')).strip() or '0',
            'end_shift': str(data.get('end_shift', '0')).strip() or '0',
            'type': 'distance',
            '_uid': uid,
        }

    def _normalize_diameter_measurement(self, meas: dict | None) -> dict:
        data = dict(meas or {})
        uid = self._ensure_measurement_uid(data)
        return {
            'name': str(data.get('name', '')).strip() or self._t('tool_editor.measurements.new_diameter', 'New Diameter'),
            'part': str(data.get('part', '')).strip(),
            'center_xyz': _xyz_to_text(data.get('center_xyz', '0, 0, 0')),
            'axis_xyz': _xyz_to_text(data.get('axis_xyz', '0, 1, 0')),
            'diameter': str(data.get('diameter', '10')).strip() or '10',
            'type': 'diameter_ring',
            '_uid': uid,
        }

    def _normalize_radius_measurement(self, meas: dict | None) -> dict:
        data = dict(meas or {})
        uid = self._ensure_measurement_uid(data)
        return {
            'name': str(data.get('name', '')).strip() or self._t('tool_editor.measurements.new_radius', 'New Radius'),
            'part': str(data.get('part', '')).strip(),
            'center_xyz': _xyz_to_text(data.get('center_xyz', '0, 0, 0')),
            'axis_xyz': _xyz_to_text(data.get('axis_xyz', '0, 1, 0')),
            'radius': str(data.get('radius', '5')).strip() or '5',
            'type': 'radius',
            '_uid': uid,
        }

    def _normalize_angle_measurement(self, meas: dict | None) -> dict:
        data = dict(meas or {})
        uid = self._ensure_measurement_uid(data)
        return {
            'name': str(data.get('name', '')).strip() or self._t('tool_editor.measurements.new_angle', 'New Angle'),
            'part': str(data.get('part', '')).strip(),
            'center_xyz': _xyz_to_text(data.get('center_xyz', '0, 0, 0')),
            'start_xyz': _xyz_to_text(data.get('start_xyz', '1, 0, 0')),
            'end_xyz': _xyz_to_text(data.get('end_xyz', '0, 1, 0')),
            'type': 'angle',
            '_uid': uid,
        }

    def _populate_measurements(self):
        self._distance_list.clear()
        for meas in self._tool_data.get('distance_measurements', []):
            normalized = self._normalize_distance_measurement(meas)
            item = QListWidgetItem(normalized.get('name', 'Unnamed'))
            item.setData(Qt.UserRole, normalized)
            self._distance_list.addItem(item)

        self._diameter_list.clear()
        for meas in self._tool_data.get('diameter_measurements', []):
            normalized = self._normalize_diameter_measurement(meas)
            item = QListWidgetItem(normalized.get('name', 'Unnamed'))
            item.setData(Qt.UserRole, normalized)
            self._diameter_list.addItem(item)

        self._radius_list.clear()
        for meas in self._tool_data.get('radius_measurements', []):
            normalized = self._normalize_radius_measurement(meas)
            item = QListWidgetItem(normalized.get('name', 'Unnamed'))
            item.setData(Qt.UserRole, normalized)
            self._radius_list.addItem(item)

        self._angle_list.clear()
        for meas in self._tool_data.get('angle_measurements', []):
            normalized = self._normalize_angle_measurement(meas)
            item = QListWidgetItem(normalized.get('name', 'Unnamed'))
            item.setData(Qt.UserRole, normalized)
            self._angle_list.addItem(item)

        self._rebuild_measurement_all_list()

    def _add_distance_measurement(self):
        new_meas = {
            'name': self._t('tool_editor.measurements.new_distance', 'New Distance'),
            'start_part': '',
            'start_part_index': -1,
            'start_xyz': '',
            'start_space': 'world',
            'end_part': '',
            'end_part_index': -1,
            'end_xyz': '',
            'end_space': 'world',
            'distance_axis': 'z',
            'label_value_mode': 'measured',
            'label_custom_value': '',
            'type': 'distance',
            '_uid': self._ensure_measurement_uid({}),
        }
        item = QListWidgetItem(new_meas['name'])
        item.setData(Qt.UserRole, new_meas)
        self._distance_list.addItem(item)
        self._distance_list.setCurrentItem(item)
        self._refresh_preview_measurements()
        self._start_distance_two_point_pick(reset_points=True)
        return item

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
            '_uid': self._ensure_measurement_uid({}),
        }
        item = QListWidgetItem(new_meas['name'])
        item.setData(Qt.UserRole, new_meas)
        self._diameter_list.addItem(item)
        self._diameter_list.setCurrentItem(item)
        self._refresh_preview_measurements()
        return item

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
            '_uid': self._ensure_measurement_uid({}),
        }
        item = QListWidgetItem(new_meas['name'])
        item.setData(Qt.UserRole, new_meas)
        self._radius_list.addItem(item)
        self._radius_list.setCurrentItem(item)
        self._refresh_preview_measurements()
        return item

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
            '_uid': self._ensure_measurement_uid({}),
        }
        item = QListWidgetItem(new_meas['name'])
        item.setData(Qt.UserRole, new_meas)
        self._angle_list.addItem(item)
        self._angle_list.setCurrentItem(item)
        self._refresh_preview_measurements()
        return item

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

    def _distance_precise_mode_enabled(self) -> bool:
        if not hasattr(self, '_distance_detail_mode_btn'):
            return False
        return self._distance_detail_mode_btn.isChecked()

    def _update_distance_mode_controls_visibility(self):
        kind = self._active_measurement_kind()
        has_active = kind in {'length', 'diameter', 'radius', 'angle'}
        self._remove_measurement_btn.setEnabled(bool(has_active))
        if hasattr(self, '_distance_detail_mode_col'):
            self._distance_detail_mode_col.setVisible(kind == 'length')
        self._update_distance_precise_visibility()

    def _update_distance_edit_mode_title(self):
        if not hasattr(self, '_dist_adjust_section'):
            return
        if not self._distance_precise_mode_enabled():
            mode_text = self._t('tool_editor.measurements.edit_mode_helpers', 'Helpers move')
        elif self._distance_adjust_mode() == 'point':
            mode_text = self._t('tool_editor.measurements.edit_mode_points', 'Points')
        else:
            mode_text = self._t('tool_editor.measurements.edit_mode_arrow', 'Arrow move')
        self._dist_adjust_section.setTitle(
            f"{self._t('tool_editor.measurements.edit_mode', 'Edit mode')}: {mode_text}"
        )

    def _update_distance_precise_visibility(self):
        if not hasattr(self, '_dist_adjust_section'):
            return
        kind = self._active_measurement_kind()
        show_adjust = kind == 'length' and self._distance_precise_mode_enabled()
        self._dist_adjust_section.setVisible(show_adjust)
        self._update_distance_edit_mode_title()
        self._update_axis_hint_overlay_visibility()

    def _on_distance_detail_mode_changed(self, *_args):
        self._update_distance_precise_visibility()
        self._refresh_preview_measurements()

    def _add_current_measurement(self):
        self._show_add_measurement_type_picker()

    def _remove_current_measurement(self):
        meta = self._selected_measurement_meta()
        if not meta:
            return

        kind = str(meta.get('kind') or '').strip().lower()
        uid = str(meta.get('uid') or '').strip()
        src_list = self._hidden_list_for_kind(kind)
        if src_list is None:
            return

        visual_row = self._measurement_all_list.currentRow()
        row, item = self._find_item_by_uid(src_list, uid)
        if item is None or row < 0:
            return

        src_list.takeItem(row)
        self._cancel_pick()
        if kind == 'length':
            self._current_distance_item = None
            self._distance_edit_model = None
        elif kind == 'diameter':
            self._current_diameter_item = None
        elif kind == 'radius':
            self._current_radius_item = None
        elif kind == 'angle':
            self._current_angle_item = None

        self._refresh_preview_measurements()
        self._rebuild_measurement_all_list()
        if self._measurement_all_list.count() > 0:
            self._measurement_all_list.setCurrentRow(max(0, min(visual_row, self._measurement_all_list.count() - 1)))
        else:
            self._edit_stack.setCurrentIndex(0)
            self._update_distance_mode_controls_visibility()

    def _on_distance_selected(self):
        current = self._distance_list.currentItem()
        self._current_distance_item = current
        if current:
            self._populate_distance_form(current.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(1)
            meas = dict(current.data(Qt.UserRole) or {})
            if not str(meas.get('start_xyz') or '').strip() or not str(meas.get('end_xyz') or '').strip():
                self._start_distance_two_point_pick(reset_points=False)
        else:
            self._edit_stack.setCurrentIndex(0)
        self._update_distance_mode_controls_visibility()

    def _on_diameter_selected(self):
        current = self._diameter_list.currentItem()
        self._current_diameter_item = current
        if current:
            self._populate_diameter_form(current.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(2)
        else:
            self._edit_stack.setCurrentIndex(0)
        self._update_distance_mode_controls_visibility()

    def _on_radius_selected(self):
        current = self._radius_list.currentItem()
        self._current_radius_item = current
        if current:
            self._populate_radius_form(current.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(3)
        else:
            self._edit_stack.setCurrentIndex(0)
        self._update_distance_mode_controls_visibility()

    def _on_angle_selected(self):
        current = self._angle_list.currentItem()
        self._current_angle_item = current
        if current:
            self._populate_angle_form(current.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(4)
        else:
            self._edit_stack.setCurrentIndex(0)
        self._update_distance_mode_controls_visibility()

    def _populate_distance_form(self, meas: dict):
        self._distance_edit_model = dict(meas or {})
        self._dist_name_edit.setText(meas.get('name', ''))
        self._set_distance_axis(str(meas.get('distance_axis', 'z')).lower(), commit=False)
        self._set_distance_value_mode(str(meas.get('label_value_mode', 'measured')).lower(), commit=False)
        self._set_distance_nudge_point('start', commit=False)
        self._set_distance_adjust_mode('offset', commit=False)
        self._load_distance_adjust_edits_from_model()
        self._update_distance_measured_value_box()
        self._update_distance_pick_status()

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
        kind = self._active_measurement_kind()
        if kind == 'length':
            self._commit_distance_edit()
        elif kind == 'diameter':
            self._commit_diameter_edit()
        elif kind == 'radius':
            self._commit_radius_edit()
        elif kind == 'angle':
            self._commit_angle_edit()

    def _update_distance_pick_status(self):
        if not hasattr(self, '_dist_pick_status_label'):
            return
        model = self._distance_edit_model or {}
        has_start = bool(str(model.get('start_xyz') or '').strip())
        has_end = bool(str(model.get('end_xyz') or '').strip())
        self._update_distance_measured_value_box()
        if self._pick_target and self._pick_target.startswith('target_xyz:start'):
            self._dist_pick_status_label.setText(
                self._t('tool_editor.measurements.pick_start_status', 'Click start point in preview')
            )
        elif self._pick_target and self._pick_target.startswith('target_xyz:end'):
            self._dist_pick_status_label.setText(
                self._t('tool_editor.measurements.pick_end_status', 'Click end point in preview')
            )
        elif has_start and has_end:
            self._dist_pick_status_label.setText(
                self._t('tool_editor.measurements.points_set', 'Start and end points set')
            )
        elif has_start:
            self._dist_pick_status_label.setText(
                self._t('tool_editor.measurements.start_set', 'Start point set, end point missing')
            )
        else:
            self._dist_pick_status_label.setText(
                self._t('tool_editor.measurements.points_missing', 'No points set yet')
            )

    def _distance_measured_value_text(self) -> str:
        model = self._distance_edit_model or {}
        start_text = str(model.get('start_xyz') or '').strip()
        end_text = str(model.get('end_xyz') or '').strip()
        if not start_text or not end_text:
            return ''

        sx, sy, sz = _xyz_to_tuple(start_text)
        ex, ey, ez = _xyz_to_tuple(end_text)
        axis = self._distance_axis_value()
        if axis == 'x':
            value = abs(ex - sx)
        elif axis == 'y':
            value = abs(ey - sy)
        elif axis == 'z':
            value = abs(ez - sz)
        else:
            dx = ex - sx
            dy = ey - sy
            dz = ez - sz
            value = (dx * dx + dy * dy + dz * dz) ** 0.5
        return f"{value:.3f} mm"

    def _update_distance_measured_value_box(self):
        if not hasattr(self, '_dist_value_edit'):
            return
        mode = self._distance_value_mode()
        if mode == 'measured':
            text = self._distance_measured_value_text()
            self._dist_value_edit.setText(text)
        else:
            custom_text = str(self._distance_edit_model.get('label_custom_value', '') if self._distance_edit_model else '')
            self._dist_value_edit.setText(custom_text)

        if self._current_distance_item is None:
            return

        index = self._distance_list.row(self._current_distance_item)
        if index < 0:
            return

        if mode == 'measured' and hasattr(self._preview_widget, 'get_distance_measured_value'):
            def _apply_measured_value(value):
                if self._current_distance_item is None:
                    return
                if self._distance_list.row(self._current_distance_item) != index:
                    return
                try:
                    measured = float(value)
                except (TypeError, ValueError):
                    return
                if hasattr(self, '_dist_value_edit'):
                    self._dist_value_edit.setText(f"{measured:.3f} mm")

            self._preview_widget.get_distance_measured_value(index, _apply_measured_value)

    def _start_distance_two_point_pick(self, reset_points: bool):
        if not self._current_distance_item:
            return
        if self._distance_edit_model is None:
            self._distance_edit_model = dict(self._current_distance_item.data(Qt.UserRole) or {})

        if reset_points:
            self._distance_edit_model['start_part'] = ''
            self._distance_edit_model['start_part_index'] = -1
            self._distance_edit_model['start_xyz'] = ''
            self._distance_edit_model['start_space'] = 'world'
            self._distance_edit_model['end_part'] = ''
            self._distance_edit_model['end_part_index'] = -1
            self._distance_edit_model['end_xyz'] = ''
            self._distance_edit_model['end_space'] = 'world'

        self._pick_target = 'target_xyz:start:all'
        self._dist_pick_stage = 'start'
        self._preview_widget.set_point_picking_enabled(True)
        self._show_axis_pick_overlay()
        if hasattr(self, '_dist_pick_points_btn'):
            self._dist_pick_points_btn.setText('')
            self._dist_pick_points_btn.setIcon(self._icon('cancel.svg'))
            self._dist_pick_points_btn.setIconSize(QSize(24, 24))
            self._dist_pick_points_btn.setToolTip(self._t('common.cancel', 'Cancel'))
        self._update_distance_pick_status()

    def _commit_distance_edit(self, sync_adjust_edits: bool = True):
        if not self._current_distance_item:
            return
        if self._distance_edit_model is None:
            self._distance_edit_model = dict(self._current_distance_item.data(Qt.UserRole) or {})
        model = self._distance_edit_model
        uid = self._ensure_measurement_uid(model)
        if sync_adjust_edits:
            self._store_distance_adjust_edits_to_model()
        mode = self._distance_value_mode()
        custom_text = self._dist_value_edit.text().strip() if mode == 'custom' else ''
        meas = {
            'name': self._dist_name_edit.text() or self._t(
                'tool_editor.measurements.new_distance', 'New Distance'),
            'start_part': str(model.get('start_part', '')).strip(),
            'start_part_index': int(model.get('start_part_index', -1) or -1),
            'start_xyz': str(model.get('start_xyz', '')).strip(),
            'start_space': str(model.get('start_space', 'world')).strip() or 'world',
            'end_part': str(model.get('end_part', '')).strip(),
            'end_part_index': int(model.get('end_part_index', -1) or -1),
            'end_xyz': str(model.get('end_xyz', '')).strip(),
            'end_space': str(model.get('end_space', 'world')).strip() or 'world',
            'distance_axis': self._distance_axis_value(),
            'label_value_mode': mode,
            'label_custom_value': custom_text,
            'offset_xyz': str(model.get('offset_xyz', '')).strip(),
            'start_shift': str(model.get('start_shift', '0')).strip(),
            'end_shift': str(model.get('end_shift', '0')).strip(),
            'type': 'distance',
            '_uid': uid,
        }
        self._distance_edit_model = dict(meas)
        self._current_distance_item.setData(Qt.UserRole, meas)
        self._current_distance_item.setText(meas['name'])
        self._update_selected_measurement_name_in_all_list('length', uid, meas['name'])
        self._refresh_preview_measurements()
        self._update_distance_pick_status()

    def _distance_value_mode(self) -> str:
        if self._dist_value_mode_btn.isChecked():
            return 'custom'
        return 'measured'

    def _set_distance_value_mode(self, mode: str, commit: bool = True):
        normalized = mode if mode in {'measured', 'custom'} else 'measured'
        is_custom = normalized == 'custom'
        self._dist_value_mode_btn.blockSignals(True)
        self._dist_value_mode_btn.setChecked(is_custom)
        if is_custom:
            self._dist_value_mode_btn.setText(self._t('tool_editor.measurements.value_mode_custom', 'Custom'))
        else:
            self._dist_value_mode_btn.setText(self._t('tool_editor.measurements.value_mode_measured', 'Measured'))
        self._dist_value_mode_btn.blockSignals(False)
        self._dist_value_edit.setReadOnly(not is_custom)
        self._update_distance_measured_value_box()
        if commit:
            self._commit_distance_edit()

    def _on_distance_value_mode_toggled(self):
        """Toggle between measured and custom mode with button text change."""
        is_custom = self._dist_value_mode_btn.isChecked()
        if is_custom:
            self._dist_value_mode_btn.setText(self._t('tool_editor.measurements.value_mode_custom', 'Custom'))
        else:
            self._dist_value_mode_btn.setText(self._t('tool_editor.measurements.value_mode_measured', 'Measured'))
        self._dist_value_edit.setReadOnly(not is_custom)
        self._update_distance_measured_value_box()
        self._commit_distance_edit()

    def _distance_adjust_mode(self) -> str:
        if self._dist_adjust_mode_btn.isChecked():
            return 'point'
        return 'offset'

    def _distance_nudge_point(self) -> str:
        if self._dist_nudge_point_btn.isChecked():
            return 'end'
        return 'start'

    def _distance_adjust_edits(self) -> tuple[QLineEdit, QLineEdit, QLineEdit]:
        return self._dist_adjust_x_edit, self._dist_adjust_y_edit, self._dist_adjust_z_edit

    def _distance_adjust_target_key(self, mode: str | None = None, point: str | None = None) -> str:
        effective_mode = mode or self._distance_adjust_mode()
        effective_point = point or self._distance_nudge_point()
        if effective_mode == 'point':
            return f'{effective_point}_xyz'
        return 'offset_xyz'

    def _distance_adjust_active_axis_value(self) -> str:
        focused_axis = self._focused_axis(self._distance_adjust_edits())
        if focused_axis in {'x', 'y', 'z'}:
            self._dist_adjust_active_axis = focused_axis
            return focused_axis
        focus_widget = self.focusWidget()
        if focus_widget in {self._dist_nudge_minus_btn, self._dist_nudge_plus_btn}:
            return self._dist_adjust_active_axis
        return 'all'

    def _update_distance_adjust_tooltips(self):
        if self._distance_adjust_mode() == 'point':
            tooltip = self._t(
                'tool_editor.measurements.point_nudge_tooltip',
                'Edit the selected point coordinates. Focus X, Y, or Z, then use + or -.'
            )
        else:
            tooltip = self._t(
                'tool_editor.measurements.offset_tooltip',
                'Drag the arrow in the preview, or type here to fine-tune'
            )
        for axis_edit in self._distance_adjust_edits():
            axis_edit.setToolTip(tooltip)

    def _load_distance_adjust_edits_from_model(self):
        if not hasattr(self, '_dist_adjust_x_edit'):
            return
        model = self._distance_edit_model or {}
        self._set_xyz_edits(self._distance_adjust_edits(), model.get(self._distance_adjust_target_key(), '0, 0, 0'))
        self._update_distance_adjust_tooltips()

    def _store_distance_adjust_edits_to_model(self, target_key: str | None = None):
        if self._distance_edit_model is None or not hasattr(self, '_dist_adjust_x_edit'):
            return
        self._distance_edit_model[target_key or self._distance_adjust_target_key()] = self._xyz_text_from_edits(
            self._distance_adjust_edits()
        )

    def _update_distance_adjust_controls(self, refresh_values: bool = True):
        is_point_mode = self._distance_adjust_mode() == 'point'
        self._dist_adjust_mode_btn.blockSignals(True)
        self._dist_adjust_mode_btn.setChecked(is_point_mode)
        self._dist_adjust_mode_btn.setText('')
        self._dist_adjust_mode_btn.setIcon(self._icon('edit_arrow.svg' if is_point_mode else 'fine_tune.svg'))
        self._dist_adjust_mode_btn.setToolTip(
            self._t('tool_editor.measurements.arrow_offset', 'Arrow offset')
            if is_point_mode else self._t('tool_editor.measurements.nudge', 'Nudge')
        )
        self._dist_adjust_mode_btn.blockSignals(False)
        self._dist_nudge_point_btn.setVisible(is_point_mode)
        is_end = self._distance_nudge_point() == 'end'
        self._dist_nudge_point_btn.setText('')
        self._dist_nudge_point_btn.setIcon(self._icon('end_point.svg' if is_end else 'start_point.svg'))
        self._dist_nudge_point_btn.setToolTip(
            self._t('tool_editor.measurements.click_edit_start_point', 'Click to edit start point')
            if is_end else
            self._t('tool_editor.measurements.click_edit_end_point', 'Click to edit end point')
        )
        self._update_distance_edit_mode_title()
        if refresh_values:
            self._load_distance_adjust_edits_from_model()

    def _set_distance_adjust_mode(self, mode: str, commit: bool = True):
        normalized = 'point' if mode == 'point' else 'offset'
        self._dist_adjust_mode_btn.blockSignals(True)
        self._dist_adjust_mode_btn.setChecked(normalized == 'point')
        self._dist_adjust_mode_btn.blockSignals(False)
        self._update_distance_adjust_controls(refresh_values=True)
        if commit:
            self._commit_distance_edit()

    def _on_distance_adjust_mode_toggled(self):
        previous_mode = 'offset' if self._distance_adjust_mode() == 'point' else 'point'
        previous_target = self._distance_adjust_target_key(mode=previous_mode, point=self._distance_nudge_point())
        self._store_distance_adjust_edits_to_model(previous_target)
        self._update_distance_adjust_controls(refresh_values=True)
        self._commit_distance_edit(sync_adjust_edits=False)

    def _set_distance_nudge_point(self, point: str, commit: bool = True):
        normalized = 'end' if point == 'end' else 'start'
        self._dist_nudge_point_btn.blockSignals(True)
        self._dist_nudge_point_btn.setChecked(normalized == 'end')
        self._dist_nudge_point_btn.blockSignals(False)
        self._update_distance_adjust_controls(refresh_values=True)
        if commit:
            self._commit_distance_edit()

    def _distance_axis_value(self) -> str:
        return getattr(self, '_dist_axis_value', 'z')

    def _set_distance_axis(self, axis: str, commit: bool = True):
        normalized = axis if axis in {'direct', 'x', 'y', 'z'} else 'z'
        self._dist_axis_value = normalized
        self._update_axis_overlay_buttons()
        if commit:
            self._commit_distance_edit()

    def _update_axis_overlay_buttons(self):
        if not hasattr(self, '_axis_overlay_btns'):
            return
        active = getattr(self, '_dist_axis_value', 'z')
        for val, btn in self._axis_overlay_btns.items():
            btn.setChecked(val == active)

    def _on_axis_overlay_selected(self, axis_val: str):
        self._set_distance_axis(axis_val, commit=True)

    def _position_axis_overlay(self):
        """Place the overlay on the left-middle side of the preview container."""
        if not hasattr(self, '_axis_pick_overlay') or not hasattr(self, '_preview_container'):
            return
        self._axis_pick_overlay.adjustSize()
        sh = self._axis_pick_overlay.sizeHint()
        margin = 8
        ow = max(sh.width(), 10)
        oh = max(sh.height(), 10)
        ch = self._preview_container.height()
        target_center_y = int(ch * 0.68)
        y = max(margin, min(ch - oh - margin, target_center_y - (oh // 2)))
        self._axis_pick_overlay.setGeometry(margin, y, ow, oh)

    def _position_axis_hint_overlay(self):
        if not hasattr(self, '_axis_hint_overlay') or not hasattr(self, '_preview_container'):
            return
        self._axis_hint_overlay.adjustSize()
        sh = self._axis_hint_overlay.sizeHint()
        margin = 10
        ow = max(sh.width(), 10)
        oh = max(sh.height(), 10)
        self._axis_hint_overlay.setGeometry(margin, margin, ow, oh)

    def _update_axis_hint_overlay_visibility(self):
        kind = self._active_measurement_kind()
        show = kind in {'length', 'diameter', 'radius', 'angle'} and self._distance_precise_mode_enabled()
        if hasattr(self, '_preview_widget'):
            try:
                self._preview_widget.set_axis_orbit_visible(bool(show))
            except Exception:
                pass
        if hasattr(self, '_axis_hint_overlay'):
            self._axis_hint_overlay.setVisible(False)

    def _show_axis_pick_overlay(self):
        if hasattr(self, '_axis_pick_overlay'):
            self._update_axis_overlay_buttons()
            self._position_axis_overlay()
            self._axis_pick_overlay.setVisible(True)
            self._axis_pick_overlay.raise_()

    def _commit_diameter_edit(self):
        if not self._current_diameter_item:
            return
        current_data = dict(self._current_diameter_item.data(Qt.UserRole) or {})
        uid = self._ensure_measurement_uid(current_data)
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
            '_uid': uid,
        }
        self._current_diameter_item.setData(Qt.UserRole, meas)
        self._current_diameter_item.setText(meas['name'])
        self._update_selected_measurement_name_in_all_list('diameter', uid, meas['name'])
        self._refresh_preview_measurements()

    def _commit_radius_edit(self):
        if not self._current_radius_item:
            return
        current_data = dict(self._current_radius_item.data(Qt.UserRole) or {})
        uid = self._ensure_measurement_uid(current_data)
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
            '_uid': uid,
        }
        self._current_radius_item.setData(Qt.UserRole, meas)
        self._current_radius_item.setText(meas['name'])
        self._update_selected_measurement_name_in_all_list('radius', uid, meas['name'])
        self._refresh_preview_measurements()

    def _commit_angle_edit(self):
        if not self._current_angle_item:
            return
        current_data = dict(self._current_angle_item.data(Qt.UserRole) or {})
        uid = self._ensure_measurement_uid(current_data)
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
            '_uid': uid,
        }
        self._current_angle_item.setData(Qt.UserRole, meas)
        self._current_angle_item.setText(meas['name'])
        self._update_selected_measurement_name_in_all_list('angle', uid, meas['name'])
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
        if self._pick_target and self._pick_target.startswith('target_xyz:'):
            self._cancel_pick()
            return
        self._start_distance_two_point_pick(reset_points=True)

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
        self._dist_pick_stage = None
        if hasattr(self, '_preview_widget'):
            self._preview_widget.set_point_picking_enabled(False)
        if hasattr(self, '_axis_pick_overlay'):
            self._axis_pick_overlay.setVisible(False)
        pick_label = self._t('tool_editor.measurements.pick', 'Pick')
        if hasattr(self, '_dist_pick_points_btn'):
            self._dist_pick_points_btn.setText('')
            self._dist_pick_points_btn.setIcon(self._icon('points_select.svg'))
            self._dist_pick_points_btn.setIconSize(QSize(24, 24))
            self._dist_pick_points_btn.setToolTip(pick_label)
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
        self._update_distance_pick_status()

    def _on_nudge_point_toggled(self):
        """Switch shared XYZ row between start and end point values."""
        previous_point = 'start' if self._distance_nudge_point() == 'end' else 'end'
        previous_target = self._distance_adjust_target_key(mode='point', point=previous_point)
        self._store_distance_adjust_edits_to_model(previous_target)
        self._update_distance_adjust_controls(refresh_values=True)
        self._commit_distance_edit(sync_adjust_edits=False)

    def _on_distance_point_nudge(self, direction: str):
        """Adjust the focused shared XYZ field for either arrow offset or selected point."""
        if not self._current_distance_item or self._distance_edit_model is None:
            return

        nudge_axis = self._distance_adjust_active_axis_value()
        if nudge_axis not in {'x', 'y', 'z'}:
            return

        try:
            step = float(self._dist_nudge_step_edit.text().strip().replace(',', '.')) or 1.0
        except (ValueError, AttributeError):
            step = 1.0

        self._store_distance_adjust_edits_to_model()
        delta = step if direction == '+' else -step
        point_key = self._distance_adjust_target_key()

        x, y, z = _xyz_to_tuple(self._distance_edit_model.get(point_key, '0, 0, 0'))
        if nudge_axis == 'x':
            x += delta
        elif nudge_axis == 'y':
            y += delta
        elif nudge_axis == 'z':
            z += delta

        self._distance_edit_model[point_key] = f"{_fmt_coord(x)}, {_fmt_coord(y)}, {_fmt_coord(z)}"
        self._load_distance_adjust_edits_from_model()
        self._update_distance_measured_value_box()
        self._commit_distance_edit(sync_adjust_edits=False)

    def eventFilter(self, watched, event):
        if hasattr(self, '_dist_adjust_axis_by_edit') and watched in self._dist_adjust_axis_by_edit:
            if event.type() == QEvent.FocusIn:
                self._dist_adjust_active_axis = self._dist_adjust_axis_by_edit[watched]
        if (hasattr(self, '_preview_container') and watched is self._preview_container
                and event.type() == QEvent.Resize):
            if hasattr(self, '_axis_pick_overlay') and self._axis_pick_overlay.isVisible():
                self._position_axis_overlay()
            if hasattr(self, '_axis_hint_overlay') and self._axis_hint_overlay.isVisible():
                self._position_axis_hint_overlay()
        return super().eventFilter(watched, event)

    def _on_point_picked(self, data: dict):
        target = self._pick_target
        if not target:
            return
        x = data.get('x', 0)
        y = data.get('y', 0)
        z = data.get('z', 0)
        values = {'x': float(x), 'y': float(y), 'z': float(z)}
        local_values = {
            'x': float(data.get('local_x', values['x'])),
            'y': float(data.get('local_y', values['y'])),
            'z': float(data.get('local_z', values['z'])),
        }
        part_name = data.get('partName', '')
        try:
            part_index = int(data.get('partIndex', -1))
        except Exception:
            part_index = -1

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
            if self._distance_edit_model is None:
                self._distance_edit_model = dict(self._current_distance_item.data(Qt.UserRole) or {}) if self._current_distance_item else {}
            side = 'start'
            parts = target.split(':')
            if len(parts) >= 2 and parts[1] in {'start', 'end'}:
                side = parts[1]
            if part_index >= 0 or str(part_name or '').strip():
                picked = local_values
                side_part = str(part_name or '').strip()
                side_part_index = part_index
                side_space = 'local'
            else:
                picked = values
                side_part = ''
                side_part_index = -1
                side_space = 'world'

            xyz_value = f"{_fmt_coord(picked['x'])}, {_fmt_coord(picked['y'])}, {_fmt_coord(picked['z'])}"
            self._distance_edit_model[f'{side}_xyz'] = xyz_value
            self._distance_edit_model[f'{side}_part'] = side_part
            self._distance_edit_model[f'{side}_part_index'] = side_part_index
            self._distance_edit_model[f'{side}_space'] = side_space
            if self._distance_adjust_mode() == 'point' and self._distance_nudge_point() == side:
                self._load_distance_adjust_edits_from_model()

            if side == 'start':
                self._pick_target = 'target_xyz:end:all'
                self._dist_pick_stage = 'end'
                self._preview_widget.set_point_picking_enabled(True)
                self._update_distance_pick_status()
            else:
                self._cancel_pick()
            self._commit_distance_edit(sync_adjust_edits=False)
            return
        elif target_name == 'center_xyz':
            self._cancel_pick()
            apply_pick_to_edits((self._diam_center_x_edit, self._diam_center_y_edit, self._diam_center_z_edit))
            if part_name:
                self._diam_part_edit.setText(part_name)
        elif target_name == 'radius_center_xyz':
            self._cancel_pick()
            apply_pick_to_edits((self._radius_center_x_edit, self._radius_center_y_edit, self._radius_center_z_edit))
            if part_name:
                self._radius_part_edit.setText(part_name)
        elif target_name == 'angle_center_xyz':
            self._cancel_pick()
            apply_pick_to_edits((self._angle_center_x_edit, self._angle_center_y_edit, self._angle_center_z_edit))
            if part_name:
                self._angle_part_edit.setText(part_name)
        elif target_name == 'angle_start_xyz':
            self._cancel_pick()
            apply_pick_to_edits((self._angle_start_x_edit, self._angle_start_y_edit, self._angle_start_z_edit))
            if part_name:
                self._angle_part_edit.setText(part_name)
        elif target_name == 'angle_end_xyz':
            self._cancel_pick()
            apply_pick_to_edits((self._angle_end_x_edit, self._angle_end_y_edit, self._angle_end_z_edit))
            if part_name:
                self._angle_part_edit.setText(part_name)
        else:
            self._cancel_pick()

        self._commit_current_edit()

    def _on_measurement_updated(self, payload: dict):
        if not isinstance(payload, dict):
            return
        index = payload.get('index')
        overlay = payload.get('overlay')
        if not isinstance(index, int) or index < 0 or not isinstance(overlay, dict):
            return
        if str(overlay.get('type') or '').strip().lower() != 'distance':
            return

        if index >= self._distance_list.count():
            return
        item = self._distance_list.item(index)
        if item is None:
            return

        current = dict(item.data(Qt.UserRole) or {})
        current.update({
            'start_part': str(overlay.get('start_part', current.get('start_part', ''))),
            'start_part_index': int(overlay.get('start_part_index', current.get('start_part_index', -1)) or -1),
            'start_xyz': _xyz_to_text(overlay.get('start_xyz', current.get('start_xyz', ''))),
            'start_space': str(overlay.get('start_space', current.get('start_space', 'world'))),
            'end_part': str(overlay.get('end_part', current.get('end_part', ''))),
            'end_part_index': int(overlay.get('end_part_index', current.get('end_part_index', -1)) or -1),
            'end_xyz': _xyz_to_text(overlay.get('end_xyz', current.get('end_xyz', ''))),
            'end_space': str(overlay.get('end_space', current.get('end_space', 'world'))),
            'distance_axis': str(overlay.get('distance_axis', current.get('distance_axis', 'z'))),
            'label_value_mode': str(overlay.get('label_value_mode', current.get('label_value_mode', 'measured'))),
            'label_custom_value': str(overlay.get('label_custom_value', current.get('label_custom_value', ''))),
            'offset_xyz': _xyz_to_text(overlay.get('offset_xyz', current.get('offset_xyz', ''))),
            'start_shift': str(overlay.get('start_shift', current.get('start_shift', '0'))),
            'end_shift': str(overlay.get('end_shift', current.get('end_shift', '0'))),
            'type': 'distance',
        })
        item.setData(Qt.UserRole, current)
        if item is self._current_distance_item:
            self._distance_edit_model = dict(current)
            if self._distance_adjust_mode() == 'offset':
                self._load_distance_adjust_edits_from_model()
            self._update_distance_pick_status()

    # ─────────────────────────────────────────────────────────────────
    # PREVIEW REFRESH
    # ─────────────────────────────────────────────────────────────────

    def _refresh_preview_measurements(self):
        overlays = []
        active_uid = ''
        active_point = ''
        if self._current_distance_item is not None:
            current_data = dict(self._current_distance_item.data(Qt.UserRole) or {})
            active_uid = str(current_data.get('_uid') or '').strip()
            if (
                active_uid
                and self._distance_precise_mode_enabled()
                and self._distance_adjust_mode() == 'point'
            ):
                active_point = self._distance_nudge_point()
        for i in range(self._distance_list.count()):
            overlay = self._normalize_distance_measurement(self._distance_list.item(i).data(Qt.UserRole))
            if active_uid and str(overlay.get('_uid') or '').strip() == active_uid:
                overlay['active_point'] = active_point
            else:
                overlay['active_point'] = ''
            overlays.append(overlay)
        for i in range(self._diameter_list.count()):
            overlays.append(self._normalize_diameter_measurement(self._diameter_list.item(i).data(Qt.UserRole)))
        for i in range(self._radius_list.count()):
            overlays.append(self._normalize_radius_measurement(self._radius_list.item(i).data(Qt.UserRole)))
        for i in range(self._angle_list.count()):
            overlays.append(self._normalize_angle_measurement(self._angle_list.item(i).data(Qt.UserRole)))
        self._preview_widget.set_measurement_overlays(overlays)

    # ─────────────────────────────────────────────────────────────────
    # OUTPUT
    # ─────────────────────────────────────────────────────────────────

    def get_measurements(self) -> dict:
        """Return all measurements from the dialog."""
        distance_meas = [
            self._normalize_distance_measurement(self._distance_list.item(i).data(Qt.UserRole))
            for i in range(self._distance_list.count())
        ]
        diameter_meas = [
            self._normalize_diameter_measurement(self._diameter_list.item(i).data(Qt.UserRole))
            for i in range(self._diameter_list.count())
        ]
        radius_meas = [
            self._normalize_radius_measurement(self._radius_list.item(i).data(Qt.UserRole))
            for i in range(self._radius_list.count())
        ]
        angle_meas = [
            self._normalize_angle_measurement(self._angle_list.item(i).data(Qt.UserRole))
            for i in range(self._angle_list.count())
        ]
        return {
            'distance_measurements': distance_meas,
            'diameter_measurements': diameter_meas,
            'radius_measurements': radius_meas,
            'angle_measurements': angle_meas,
        }

    def accept(self):
        # Flush any delayed editor changes so Save always persists the latest values.
        if self._commit_timer.isActive():
            self._commit_timer.stop()
        self._commit_current_edit()
        super().accept()
