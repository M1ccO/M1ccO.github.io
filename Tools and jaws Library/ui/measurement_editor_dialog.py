"""
Measurement Editor Dialog - Visual measurement configuration in 3D space.

Allows users to add and configure distance measurements and diameter rings
with visual feedback in the 3D preview. Users can click in the 3D view to
select anchor points or manually enter coordinates.
"""

import math
from typing import Callable
from PySide6.QtCore import QEvent, Qt, QTimer, QSize, QPoint, QEventLoop
from PySide6.QtGui import QColor, QIcon, QCursor
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QCheckBox,
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QWidget, QFrame, QLabel, QGroupBox,
    QPushButton, QLineEdit, QSplitter, QListWidget, QListWidgetItem,
    QAbstractItemView, QStackedWidget, QSizePolicy,
)
from config import TOOL_ICONS_DIR
from shared.ui.stl_preview import StlPreviewWidget
from ui.measurement_editor.utils.coordinates import (
    xyz_to_tuple as _xyz_to_tuple,
    fmt_coord as _fmt_coord,
    float_or_default as _float_or_default,
)
from ui.measurement_editor.utils.edit_helpers import (
    set_xyz_edits as _set_xyz_edits_fn,
    xyz_text_from_edits as _xyz_text_from_edits_fn,
    focused_axis as _focused_axis_fn,
)
from ui.measurement_editor.utils.axis_math import (
    axis_xyz_text as _axis_xyz_text,
    normalize_axis_xyz_text as _normalize_axis_xyz_text,
    normalize_diameter_axis_mode as _normalize_diameter_axis_mode,
    rotation_deg_to_axis_xyz_text as _rotation_deg_to_axis_xyz_text,
    axis_xyz_to_rotation_deg_tuple as _axis_xyz_to_rotation_deg_tuple,
)
from ui.measurement_editor.models.distance import (
    compose_distance_commit_payload as _compose_distance_commit_payload,
    normalize_distance_measurement as _normalize_distance_measurement_model,
)
from ui.measurement_editor.models.angle import (
    normalize_angle_measurement as _normalize_angle_measurement_model,
)
from ui.measurement_editor.models.diameter import (
    compose_diameter_commit_payload as _compose_diameter_commit_payload,
    normalize_diameter_measurement as _normalize_diameter_measurement_model,
)
from ui.measurement_editor.models.radius import (
    normalize_radius_measurement as _normalize_radius_measurement_model,
)
from ui.measurement_editor.controllers.distance_controller import (
    distance_adjust_target_key as _distance_adjust_target_key_helper,
    distance_axis_sign as _distance_axis_sign_helper,
    distance_effective_point_xyz_text as _distance_effective_point_xyz_text_helper,
    distance_measured_value_text as _distance_measured_value_text_helper,
    distance_value_mode as _distance_value_mode_helper,
    normalize_distance_adjust_mode as _normalize_distance_adjust_mode_helper,
    normalize_distance_axis as _normalize_distance_axis_helper,
    normalize_distance_nudge_point as _normalize_distance_nudge_point_helper,
    toggle_distance_adjust_mode as _toggle_distance_adjust_mode_helper,
)
from ui.measurement_editor.controllers.diameter_controller import (
    diameter_adjust_mode as _diameter_adjust_mode_helper,
    diameter_adjust_target_key as _diameter_adjust_target_key_helper,
    diameter_geometry_target as _diameter_geometry_target_helper,
    normalize_diameter_adjust_mode as _normalize_diameter_adjust_mode_helper,
    normalize_diameter_geometry_target as _normalize_diameter_geometry_target_helper,
    toggle_diameter_adjust_mode as _toggle_diameter_adjust_mode_helper,
    toggle_diameter_geometry_target as _toggle_diameter_geometry_target_helper,
    diameter_visual_offset_mm as _diameter_visual_offset_mm_helper,
    diameter_measured_numeric as _diameter_measured_numeric_helper,
    diameter_has_manual_value as _diameter_has_manual_value_helper,
    diameter_is_complete as _diameter_is_complete_helper,
)
from ui.measurement_editor.forms.shared_sections import (
    apply_section_groupbox_style as _apply_section_groupbox_style,
    build_adjust_header_row as _build_adjust_header_row,
    build_xyz_header_row as _build_xyz_header_row_fn,
)
from ui.measurement_editor.forms.type_picker import (
    build_measurement_type_picker as _build_measurement_type_picker_fn,
)
from ui.measurement_editor.forms.radius_form import (
    build_radius_form as _build_radius_form_fn,
)
from ui.measurement_editor.forms.angle_form import (
    build_angle_form as _build_angle_form_fn,
)
from ui.measurement_editor.forms.distance_form import (
    build_distance_form as _build_distance_form_fn,
)
from ui.measurement_editor.forms.diameter_form import (
    build_diameter_form as _build_diameter_form_fn,
)
from ui.measurement_editor.controllers.measurement_registry import (
    measurement_kind_order as _measurement_kind_order_fn,
    find_item_by_uid as _find_item_by_uid_fn,
)
from ui.measurement_editor.bridge.preview_sync import (
    apply_diameter_overlay_update as _apply_diameter_overlay_update,
    apply_distance_overlay_update as _apply_distance_overlay_update,
    compose_preview_overlays as _compose_preview_overlays,
)
from ui.measurement_editor.coordinators.axis_overlay import (
    AxisOverlayController as _AxisOverlayController,
)
from ui.measurement_editor.coordinators.distance_editor import (
    DistanceEditorCoordinator as _DistanceEditorCoordinator,
)
from ui.measurement_editor.coordinators.diameter_editor import (
    DiameterEditorCoordinator as _DiameterEditorCoordinator,
)
from ui.measurement_editor.coordinators.list_manager import (
    MeasurementListManager as _MeasurementListManager,
)
from ui.measurement_editor.coordinators.pick_coordinator import (
    PickCoordinator as _PickCoordinator,
)
from ui.measurement_editor.coordinators.preview_coordinator import (
    refresh_preview_measurements as _refresh_preview_measurements_fn,
    sync_preview_before_save as _sync_preview_before_save_fn,
    on_measurement_updated as _on_measurement_updated_fn,
)
from shared.ui.helpers.editor_helpers import (
    apply_shared_checkbox_style,
    create_dialog_buttons,
    apply_secondary_button_theme,
    setup_editor_dialog,
)


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
        self._pick_coordinator = None
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
        self.setProperty('editorHostSurface', True)

        self._build_ui()
        self._distance_editor.preview_widget = self._preview_widget
        self._diameter_editor.preview_widget = self._preview_widget
        self._list_manager = _MeasurementListManager(
            all_list=self._measurement_all_list,
            distance_list=self._distance_list,
            diameter_list=self._diameter_list,
            radius_list=self._radius_list,
            angle_list=self._angle_list,
            edit_stack=self._edit_stack,
            add_type_picker_page_index=self._add_type_picker_page_index,
            translate=self._t,
            ensure_uid=self._ensure_measurement_uid,
            normalize_distance=self._normalize_distance_measurement,
            normalize_diameter=self._normalize_diameter_measurement,
            normalize_radius=self._normalize_radius_measurement,
            normalize_angle=self._normalize_angle_measurement,
            on_cancel_pick=self._cancel_pick,
            on_refresh_preview=self._refresh_preview_measurements,
            on_update_mode_controls=self._update_distance_mode_controls_visibility,
            on_populate_distance_form=self._populate_distance_form,
            on_populate_diameter_form=self._populate_diameter_form,
            on_populate_radius_form=self._populate_radius_form,
            on_populate_angle_form=self._populate_angle_form,
            on_start_distance_pick=self._start_distance_two_point_pick,
            on_auto_start_diameter_pick=self._auto_start_diameter_pick_if_needed,
            on_clear_current_refs=self._clear_current_measurement_refs,
            get_current_distance_item=lambda: self._current_distance_item,
            set_current_distance_item=self._set_current_distance_item,
            get_current_diameter_item=lambda: self._current_diameter_item,
            set_current_diameter_item=self._set_current_diameter_item,
            get_current_radius_item=lambda: self._current_radius_item,
            set_current_radius_item=self._set_current_radius_item,
            get_current_angle_item=lambda: self._current_angle_item,
            set_current_angle_item=self._set_current_angle_item,
            get_add_type_cancel_btn=lambda: getattr(self, '_add_type_cancel_top_btn', None),
        )
        self._pick_coordinator = _PickCoordinator(
            preview_widget=self._preview_widget,
            translate=self._t,
            icon=self._icon,
            dist_pick_btn=self._dist_pick_points_btn,
            diam_pick_btn=self._diam_pick_points_btn,
            radius_center_pick_btn=self._radius_center_pick_btn,
            angle_center_pick_btn=self._angle_center_pick_btn,
            angle_start_pick_btn=self._angle_start_pick_btn,
            angle_end_pick_btn=self._angle_end_pick_btn,
            radius_center_edits=(
                self._radius_center_x_edit,
                self._radius_center_y_edit,
                self._radius_center_z_edit,
            ),
            radius_part_edit=self._radius_part_edit,
            angle_center_edits=(
                self._angle_center_x_edit,
                self._angle_center_y_edit,
                self._angle_center_z_edit,
            ),
            angle_start_edits=(
                self._angle_start_x_edit,
                self._angle_start_y_edit,
                self._angle_start_z_edit,
            ),
            angle_end_edits=(
                self._angle_end_x_edit,
                self._angle_end_y_edit,
                self._angle_end_z_edit,
            ),
            angle_part_edit=self._angle_part_edit,
            diam_value_edit=self._diam_value_edit,
            distance_editor=self._distance_editor,
            diameter_editor=self._diameter_editor,
            get_current_distance_item=lambda: self._current_distance_item,
            get_current_diameter_item=lambda: self._current_diameter_item,
            focused_axis=self._focused_axis,
            on_commit_current_edit=self._commit_current_edit,
            on_sync_axis_overlay=self._sync_axis_pick_overlay_visibility,
        )
        self._axis_overlay_ctrl = _AxisOverlayController(
            axis_pick_overlay=self._axis_pick_overlay,
            axis_hint_overlay=self._axis_hint_overlay,
            axis_overlay_btns=self._axis_overlay_btns,
            preview_container=self._preview_container,
            preview_widget=self._preview_widget,
            active_kind=self._active_measurement_kind,
            dist_axis_value=self._distance_axis_value,
            diam_axis_value=self._diameter_axis_value,
            diam_is_complete=self._diameter_is_complete,
            current_diam_item=lambda: self._current_diameter_item,
            pick_target=lambda: self._pick_target,
            on_axis_selected=self._on_axis_overlay_selected_dispatch,
            precise_mode_enabled=self._distance_precise_mode_enabled,
        )
        self._populate_measurements()

        if self._parts:
            self._preview_widget.load_parts(self._parts)
        self._preview_widget.set_measurements_visible(True)
        self._preview_widget.set_measurement_drag_enabled(True)
        self._preview_widget.point_picked.connect(self._on_point_picked)
        self._preview_widget.measurement_updated.connect(self._on_measurement_updated)
        self._update_distance_mode_controls_visibility()
        self._refresh_preview_measurements()
        self._install_inline_enter_commit_behavior()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _icon(self, filename: str) -> QIcon:
        path = TOOL_ICONS_DIR / filename
        return QIcon(str(path)) if path.exists() else QIcon()

    def _install_inline_enter_commit_behavior(self):
        for edit in self.findChildren(QLineEdit):
            edit.installEventFilter(self)

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # UI BUILD
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setProperty('editorFamilySplitter', True)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)

        # â”€â”€ LEFT PANEL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        left_panel = QFrame()
        left_panel.setObjectName('measurementEditorLeftPanel')
        left_panel.setProperty('editorHostSurface', True)
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
        self._distance_detail_mode_lbl.setProperty('detailFieldKey', True)
        self._distance_detail_mode_btn = QCheckBox('')
        self._distance_detail_mode_btn.setChecked(False)
        self._distance_detail_mode_btn.stateChanged.connect(self._on_distance_detail_mode_changed)
        apply_shared_checkbox_style(self._distance_detail_mode_btn, indicator_size=14)
        self._distance_detail_mode_col = QWidget()
        self._distance_detail_mode_col.setProperty('hostTransparent', True)
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
        separator.setProperty('editorSeparator', True)
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
        placeholder.setProperty('detailHint', True)
        self._edit_stack.addWidget(placeholder)
        self._edit_stack.addWidget(self._build_distance_form())
        self._edit_stack.addWidget(self._build_diameter_form())
        self._edit_stack.addWidget(self._build_radius_form())
        self._edit_stack.addWidget(self._build_angle_form())
        self._add_type_picker_page_index = self._edit_stack.addWidget(self._build_measurement_type_picker())
        left_layout.addWidget(self._edit_stack)

        # â”€â”€ PREVIEW â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._preview_widget = StlPreviewWidget(parent=self)
        self._preview_widget.set_control_hint_text(
            self._t(
                'tool_editor.hint.rotate_pan_zoom',
                'Rotate: left mouse â€¢ Pan: right mouse â€¢ Zoom: mouse wheel',
            )
        )
        self._preview_container = QWidget()
        _preview_layout = QVBoxLayout(self._preview_container)
        _preview_layout.setContentsMargins(0, 0, 0, 0)
        _preview_layout.setSpacing(0)
        _preview_layout.addWidget(self._preview_widget)
        self._preview_container.installEventFilter(self)

        # Overlay is a direct child (no layout) â€” positioned via setGeometry in
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

        # â”€â”€ BOTTOM BUTTONS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
        container, refs = _build_distance_form_fn(
            self._t,
            icon=self._icon,
            on_schedule_commit=self._schedule_commit,
            on_pick_target=self._on_pick_target,
            on_value_mode_toggled=self._on_distance_value_mode_toggled,
            on_point_nudge=self._on_distance_point_nudge,
            on_adjust_mode_toggled=self._on_distance_adjust_mode_toggled,
            on_nudge_point_toggled=self._on_nudge_point_toggled,
            event_filter=self,
        )
        self._dist_refs = refs
        self._dist_basic_section = refs.basic_section
        self._dist_name_edit = refs.name_edit
        self._dist_pick_points_btn = refs.pick_points_btn
        self._dist_pick_status_label = refs.pick_status_label
        self._dist_value_mode_btn = refs.value_mode_btn
        self._dist_value_edit = refs.value_edit
        self._dist_adjust_section = refs.adjust_section
        self._dist_adjust_x_edit = refs.adjust_x_edit
        self._dist_adjust_y_edit = refs.adjust_y_edit
        self._dist_adjust_z_edit = refs.adjust_z_edit
        self._dist_adjust_axis_by_edit = refs.adjust_axis_by_edit
        self._dist_nudge_step_edit = refs.nudge_step_edit
        self._dist_nudge_minus_btn = refs.nudge_minus_btn
        self._dist_nudge_plus_btn = refs.nudge_plus_btn
        self._dist_adjust_mode_btn = refs.adjust_mode_btn
        self._dist_nudge_point_btn = refs.nudge_point_btn
        self._distance_editor = _DistanceEditorCoordinator(
            refs=refs,
            translate=self._t,
            icon=self._icon,
            precise_mode_enabled=self._distance_precise_mode_enabled,
            get_pick_target=lambda: self._pick_target,
            set_pick_target=self._set_pick_target_value,
            set_pick_stage=self._set_dist_pick_stage_value,
            cancel_pick=self._cancel_pick,
            ensure_uid=self._ensure_measurement_uid,
            on_commit_done=self._refresh_preview_measurements,
            on_name_changed=self._update_selected_measurement_name_in_all_list,
            on_axis_overlay_sync=self._sync_axis_pick_overlay_visibility,
            on_edit_mode_title_update=self._update_distance_edit_mode_title,
            on_update_measured_value=self._update_distance_measured_value_box,
            preview_widget=None,
            distance_list=self._distance_list,
            get_current_item=lambda: self._current_distance_item,
            get_focus_widget=self.focusWidget,
        )
        self._set_distance_axis('z', commit=False)
        self._set_distance_nudge_point('start', commit=False)
        self._set_distance_adjust_mode('offset', commit=False)
        self._set_distance_value_mode('measured', commit=False)
        self._update_distance_precise_visibility()
        self._update_distance_measured_value_box()
        self._update_distance_pick_status()
        return container

    def _set_pick_target_value(self, value: str | None):
        if self._pick_coordinator is not None:
            self._pick_coordinator.pick_target = value

    def _set_dist_pick_stage_value(self, value: str | None):
        if self._pick_coordinator is not None:
            self._pick_coordinator.dist_pick_stage = value

    def _build_diameter_form(self) -> QWidget:
        container, refs = _build_diameter_form_fn(
            self._t,
            icon=self._icon,
            on_schedule_commit=self._schedule_commit,
            on_pick_diameter_points=self._on_pick_diameter_points,
            on_value_mode_toggled=self._on_diameter_value_mode_toggled,
            on_offset_nudge=self._on_diameter_offset_nudge,
            on_adjust_mode_toggled=self._on_diameter_adjust_mode_toggled,
            on_geometry_target_toggled=self._on_diameter_geometry_target_toggled,
            event_filter=self,
        )
        self._diam_basic_section = refs.basic_section
        self._diam_name_edit = refs.name_edit
        self._diam_pick_points_btn = refs.pick_points_btn
        self._diam_pick_status_label = refs.pick_status_label
        self._diam_value_mode_btn = refs.value_mode_btn
        self._diam_value_edit = refs.value_edit
        self._diam_adjust_section = refs.adjust_section
        self._diam_adjust_x_edit = refs.adjust_x_edit
        self._diam_adjust_y_edit = refs.adjust_y_edit
        self._diam_adjust_z_edit = refs.adjust_z_edit
        self._diam_adjust_axis_by_edit = refs.adjust_axis_by_edit
        self._diam_adjust_active_axis = refs.adjust_active_axis
        self._diam_nudge_step_edit = refs.nudge_step_edit
        self._diam_adjust_step_unit_lbl = refs.adjust_step_unit_lbl
        self._diam_nudge_minus_btn = refs.nudge_minus_btn
        self._diam_nudge_plus_btn = refs.nudge_plus_btn
        self._diam_visual_offset_label = refs.visual_offset_label
        self._diam_visual_offset_edit = refs.visual_offset_edit
        self._diam_adjust_mode_btn = refs.adjust_mode_btn
        self._diam_geometry_target_btn = refs.geometry_target_btn
        self._diameter_editor = _DiameterEditorCoordinator(
            refs=refs,
            translate=self._t,
            icon=self._icon,
            get_pick_target=lambda: self._pick_target,
            set_pick_target=self._set_pick_target_value,
            set_pick_stage=self._set_diam_pick_stage_value,
            cancel_pick=self._cancel_pick,
            ensure_uid=self._ensure_measurement_uid,
            normalize_measurement=self._normalize_diameter_measurement,
            on_commit_done=self._refresh_preview_measurements,
            on_name_changed=self._update_selected_measurement_name_in_all_list,
            on_axis_overlay_sync=self._sync_axis_pick_overlay_visibility,
            on_axis_overlay_buttons_update=self._update_axis_overlay_buttons,
            on_edit_mode_title_update=self._update_distance_edit_mode_title,
            preview_widget=None,
            diameter_list=self._diameter_list,
            distance_list_count=self._distance_list.count,
            get_current_item=lambda: self._current_diameter_item,
            get_focus_widget=self.focusWidget,
            dialog_parent=self,
            dialog_setup=setup_editor_dialog,
            create_dialog_buttons=create_dialog_buttons,
            apply_secondary_button_theme=apply_secondary_button_theme,
        )
        self._set_diameter_geometry_target('axis', commit=False)
        self._set_diameter_adjust_mode('callout', commit=False)
        self._set_diameter_axis('z', commit=False, store_adjust_edits=False)
        self._set_diameter_value_mode('manual', commit=False)
        self._update_diameter_measured_value_box()
        self._update_diameter_pick_status()
        return container

    def _set_diam_pick_stage_value(self, value: str | None):
        if self._pick_coordinator is not None:
            self._pick_coordinator.diam_pick_stage = value

    def _build_radius_form(self) -> QWidget:
        container, refs = _build_radius_form_fn(
            translate=self._t,
            on_schedule_commit=self._schedule_commit,
            on_pick_center=self._on_pick_radius_center,
        )
        self._radius_name_edit = refs.name_edit
        self._radius_part_edit = refs.part_edit
        self._radius_center_x_edit = refs.center_x_edit
        self._radius_center_y_edit = refs.center_y_edit
        self._radius_center_z_edit = refs.center_z_edit
        self._radius_center_pick_btn = refs.center_pick_btn
        self._radius_axis_x_edit = refs.axis_x_edit
        self._radius_axis_y_edit = refs.axis_y_edit
        self._radius_axis_z_edit = refs.axis_z_edit
        self._radius_value_edit = refs.value_edit
        return container

    def _build_angle_form(self) -> QWidget:
        container, refs = _build_angle_form_fn(
            translate=self._t,
            on_schedule_commit=self._schedule_commit,
            on_pick_center=self._on_pick_angle_center,
            on_pick_start=self._on_pick_angle_start,
            on_pick_end=self._on_pick_angle_end,
        )
        self._angle_name_edit = refs.name_edit
        self._angle_part_edit = refs.part_edit
        self._angle_center_x_edit = refs.center_x_edit
        self._angle_center_y_edit = refs.center_y_edit
        self._angle_center_z_edit = refs.center_z_edit
        self._angle_center_pick_btn = refs.center_pick_btn
        self._angle_start_x_edit = refs.start_x_edit
        self._angle_start_y_edit = refs.start_y_edit
        self._angle_start_z_edit = refs.start_z_edit
        self._angle_start_pick_btn = refs.start_pick_btn
        self._angle_end_x_edit = refs.end_x_edit
        self._angle_end_y_edit = refs.end_y_edit
        self._angle_end_z_edit = refs.end_z_edit
        self._angle_end_pick_btn = refs.end_pick_btn
        return container

    def _build_measurement_type_picker(self) -> QWidget:
        return _build_measurement_type_picker_fn(
            translate=self._t,
            on_kind_clicked=self._add_measurement_of_kind,
        )

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # MEASUREMENT LIST MANAGEMENT
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _ensure_measurement_uid(self, payload: dict | None) -> str:
        data = payload if isinstance(payload, dict) else {}
        uid = str(data.get('_uid') or '').strip()
        if uid:
            return uid
        self._measurement_uid_counter += 1
        return f"m{self._measurement_uid_counter}"

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

    def _clear_current_measurement_refs(self):
        self._current_distance_item = None
        self._current_diameter_item = None
        self._current_radius_item = None
        self._current_angle_item = None
        self._distance_edit_model = None
        self._diameter_edit_model = None

    def _set_current_distance_item(self, item):
        self._current_distance_item = item
        if item is None:
            self._distance_edit_model = None

    def _set_current_diameter_item(self, item):
        self._current_diameter_item = item

    def _set_current_radius_item(self, item):
        self._current_radius_item = item

    def _set_current_angle_item(self, item):
        self._current_angle_item = item

    def _update_selected_measurement_name_in_all_list(self, kind: str, uid: str, name: str):
        if not hasattr(self, '_list_manager'):
            return
        self._list_manager.update_name_in_all_list(kind, uid, name)

    def _on_all_measurement_selected(self):
        self._list_manager.on_all_measurement_selected()

    def _add_measurement_of_kind(self, kind: str):
        self._list_manager.add_of_kind(kind)

    def _cancel_add_measurement_type_picker(self):
        self._list_manager.cancel_add_type_picker()

    def _show_add_measurement_type_picker(self):
        self._list_manager.show_add_type_picker()

    def _normalize_distance_measurement(self, meas: dict | None) -> dict:
        return _normalize_distance_measurement_model(
            meas,
            ensure_uid=self._ensure_measurement_uid,
            translate=self._t,
        )

    def _normalize_diameter_measurement(self, meas: dict | None) -> dict:
        return _normalize_diameter_measurement_model(
            meas,
            ensure_uid=self._ensure_measurement_uid,
            translate=self._t,
        )

    def _normalize_radius_measurement(self, meas: dict | None) -> dict:
        return _normalize_radius_measurement_model(
            meas,
            ensure_uid=self._ensure_measurement_uid,
            translate=self._t,
        )

    def _normalize_angle_measurement(self, meas: dict | None) -> dict:
        return _normalize_angle_measurement_model(
            meas,
            ensure_uid=self._ensure_measurement_uid,
            translate=self._t,
        )

    def _populate_measurements(self):
        self._list_manager.populate_from_tool_data(self._tool_data)

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # SELECTION & FORM POPULATION
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _distance_precise_mode_enabled(self) -> bool:
        if not hasattr(self, '_distance_detail_mode_btn'):
            return False
        return self._distance_detail_mode_btn.isChecked()

    def _update_distance_mode_controls_visibility(self):
        kind = self._active_measurement_kind()
        has_active = kind in {'length', 'diameter', 'radius', 'angle'}
        self._remove_measurement_btn.setEnabled(bool(has_active))
        if hasattr(self, '_distance_detail_mode_col'):
            self._distance_detail_mode_col.setVisible(kind in {'length', 'diameter'})
        self._update_distance_precise_visibility()
        self._sync_axis_pick_overlay_visibility()

    def _update_distance_edit_mode_title(self):
        kind = self._active_measurement_kind()
        if kind == 'diameter' and hasattr(self, '_diam_adjust_section'):
            if self._diameter_adjust_mode() == 'geometry':
                if self._diameter_geometry_target() == 'rotation':
                    mode_text = self._t(
                        'tool_editor.measurements.edit_mode_diameter_rotation',
                        'Axis rotation (deg)'
                    )
                else:
                    mode_text = self._t(
                        'tool_editor.measurements.edit_mode_diameter_axis_position',
                        'Axis position'
                    )
            else:
                mode_text = self._t('tool_editor.measurements.edit_mode_callout', 'Callout move')
            self._diam_adjust_section.setTitle(
                f"{self._t('tool_editor.measurements.edit_mode', 'Edit mode')}: {mode_text}"
            )
            return
        if hasattr(self, '_dist_adjust_section'):
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
        kind = self._active_measurement_kind()
        show_precise = self._distance_precise_mode_enabled()
        if hasattr(self, '_dist_adjust_section'):
            self._dist_adjust_section.setVisible(kind == 'length' and show_precise)
        if hasattr(self, '_diam_adjust_section'):
            self._diam_adjust_section.setVisible(kind == 'diameter' and show_precise)
        self._update_distance_edit_mode_title()
        self._update_axis_hint_overlay_visibility()
        self._sync_axis_pick_overlay_visibility()

    def _on_distance_detail_mode_changed(self, *_args):
        self._update_distance_precise_visibility()
        self._refresh_preview_measurements()

    def _set_diameter_value_mode(self, mode: str, commit: bool = True):
        self._diameter_editor.set_value_mode(mode, commit)

    def _on_diameter_value_mode_toggled(self):
        self._diameter_editor.on_value_mode_toggled()

    def _diameter_axis_value(self) -> str:
        return self._diameter_editor.axis_value

    def _set_diameter_axis(self, axis: str, commit: bool = True, store_adjust_edits: bool = True):
        self._diameter_editor.set_axis(axis, commit, store_adjust_edits)

    def _diameter_adjust_mode(self) -> str:
        return self._diameter_editor.adjust_mode()

    def _diameter_geometry_target(self) -> str:
        return self._diameter_editor.geometry_target()

    def _load_diameter_adjust_edits_from_model(self):
        self._diameter_editor.load_adjust_edits_from_model()

    def _set_diameter_adjust_mode(self, mode: str, commit: bool = True):
        self._diameter_editor.set_adjust_mode(mode, commit)

    def _on_diameter_adjust_mode_toggled(self):
        self._diameter_editor.on_adjust_mode_toggled()

    def _set_diameter_geometry_target(self, target: str, commit: bool = True):
        self._diameter_editor.set_geometry_target(target, commit)

    def _on_diameter_geometry_target_toggled(self):
        self._diameter_editor.on_geometry_target_toggled()

    def _update_diameter_measured_value_box(self):
        self._diameter_editor.update_measured_value_box()

    def _update_diameter_pick_status(self):
        self._diameter_editor.update_pick_status()

    def _diameter_is_complete(self, model: dict | None = None) -> bool:
        return self._diameter_editor.is_complete(model)

    def _auto_start_diameter_pick_if_needed(self):
        self._diameter_editor.auto_start_pick_if_needed()

    def _on_pick_diameter_points(self):
        self._diameter_editor.on_pick_points()

    def _sync_axis_pick_overlay_visibility(self):
        if hasattr(self, '_axis_overlay_ctrl'):
            self._axis_overlay_ctrl.sync_visibility()

    def _add_current_measurement(self):
        self._show_add_measurement_type_picker()

    def _remove_current_measurement(self):
        self._list_manager.remove_current()

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
            self._auto_start_diameter_pick_if_needed()
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
        self._distance_editor.populate_form(meas)

    def _populate_diameter_form(self, meas: dict):
        self._diameter_editor.populate_form(meas)

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

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # EDIT COMMIT
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
        if hasattr(self, '_distance_editor'):
            self._distance_editor.update_pick_status()

    def _update_distance_measured_value_box(self):
        if hasattr(self, '_distance_editor'):
            self._distance_editor.update_measured_value_box()

    def _start_distance_two_point_pick(self, reset_points: bool):
        self._distance_editor.start_two_point_pick(reset_points)

    def _commit_distance_edit(self, sync_adjust_edits: bool = True):
        self._distance_editor.commit_edit(sync_adjust_edits)

    def _set_distance_value_mode(self, mode: str, commit: bool = True):
        self._distance_editor.set_value_mode(mode, commit)

    def _on_distance_value_mode_toggled(self):
        self._distance_editor.on_value_mode_toggled()

    def _distance_adjust_mode(self) -> str:
        return self._distance_editor.adjust_mode()

    def _distance_nudge_point(self) -> str:
        return self._distance_editor.nudge_point()

    def _load_distance_adjust_edits_from_model(self):
        self._distance_editor.load_adjust_edits_from_model()

    def _set_distance_adjust_mode(self, mode: str, commit: bool = True):
        self._distance_editor.set_adjust_mode(mode, commit)

    def _on_distance_adjust_mode_toggled(self):
        self._distance_editor.on_adjust_mode_toggled()

    def _set_distance_nudge_point(self, point: str, commit: bool = True):
        self._distance_editor.set_nudge_point(point, commit)

    def _distance_axis_value(self) -> str:
        return self._distance_editor.axis_value

    def _set_distance_axis(self, axis: str, commit: bool = True):
        self._distance_editor.set_axis(axis, commit)
        self._update_axis_overlay_buttons()

    @property
    def _pick_target(self):
        return self._pick_coordinator.pick_target if self._pick_coordinator is not None else None

    @_pick_target.setter
    def _pick_target(self, value):
        if self._pick_coordinator is not None:
            self._pick_coordinator.pick_target = value

    @property
    def _dist_pick_stage(self):
        return self._pick_coordinator.dist_pick_stage if self._pick_coordinator is not None else None

    @_dist_pick_stage.setter
    def _dist_pick_stage(self, value):
        if self._pick_coordinator is not None:
            self._pick_coordinator.dist_pick_stage = value

    @property
    def _diam_pick_stage(self):
        return self._pick_coordinator.diam_pick_stage if self._pick_coordinator is not None else None

    @_diam_pick_stage.setter
    def _diam_pick_stage(self, value):
        if self._pick_coordinator is not None:
            self._pick_coordinator.diam_pick_stage = value

    @property
    def _distance_edit_model(self):
        return self._distance_editor.edit_model if hasattr(self, '_distance_editor') else None

    @_distance_edit_model.setter
    def _distance_edit_model(self, value):
        if hasattr(self, '_distance_editor'):
            self._distance_editor.edit_model = value

    @property
    def _dist_axis_value(self):
        if hasattr(self, '_distance_editor'):
            return self._distance_editor.axis_value
        return 'z'

    @_dist_axis_value.setter
    def _dist_axis_value(self, value):
        if hasattr(self, '_distance_editor'):
            self._distance_editor._axis_value = value

    @property
    def _dist_adjust_active_axis(self):
        if hasattr(self, '_distance_editor'):
            return self._distance_editor.adjust_active_axis
        return 'x'

    @_dist_adjust_active_axis.setter
    def _dist_adjust_active_axis(self, value):
        if hasattr(self, '_distance_editor'):
            self._distance_editor.adjust_active_axis = value

    @property
    def _diameter_edit_model(self):
        return self._diameter_editor.edit_model if hasattr(self, '_diameter_editor') else None

    @_diameter_edit_model.setter
    def _diameter_edit_model(self, value):
        if hasattr(self, '_diameter_editor'):
            self._diameter_editor.edit_model = value

    @property
    def _diam_axis_value(self):
        if hasattr(self, '_diameter_editor'):
            return self._diameter_editor.axis_value
        return 'z'

    @_diam_axis_value.setter
    def _diam_axis_value(self, value):
        if hasattr(self, '_diameter_editor'):
            self._diameter_editor._axis_value = value

    @property
    def _diam_adjust_active_axis(self):
        if hasattr(self, '_diameter_editor'):
            return self._diameter_editor.adjust_active_axis
        return 'x'

    @_diam_adjust_active_axis.setter
    def _diam_adjust_active_axis(self, value):
        if hasattr(self, '_diameter_editor'):
            self._diameter_editor.adjust_active_axis = value

    def _update_axis_overlay_buttons(self):
        if hasattr(self, '_axis_overlay_ctrl'):
            self._axis_overlay_ctrl.update_buttons()

    def _on_axis_overlay_selected_dispatch(self, axis_val: str, kind: str | None):
        if kind == 'diameter':
            self._set_diameter_axis(axis_val, commit=True)
            return
        self._set_distance_axis(axis_val, commit=True)

    def _on_axis_overlay_selected(self, axis_val: str):
        self._on_axis_overlay_selected_dispatch(axis_val, self._active_measurement_kind())

    def _position_axis_overlay(self):
        if hasattr(self, '_axis_overlay_ctrl'):
            self._axis_overlay_ctrl.position_axis_overlay()

    def _position_axis_hint_overlay(self):
        if hasattr(self, '_axis_overlay_ctrl'):
            self._axis_overlay_ctrl.position_axis_hint_overlay()

    def _update_axis_hint_overlay_visibility(self):
        if hasattr(self, '_axis_overlay_ctrl'):
            self._axis_overlay_ctrl.update_hint_visibility()

    def _commit_diameter_edit(self, sync_adjust_edits: bool = True):
        self._diameter_editor.commit_edit(sync_adjust_edits)

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
        _set_xyz_edits_fn(edits, value)

    def _xyz_text_from_edits(self, edits: tuple[QLineEdit, QLineEdit, QLineEdit]) -> str:
        return _xyz_text_from_edits_fn(edits)

    @staticmethod
    def _focused_axis(edits: tuple[QLineEdit, QLineEdit, QLineEdit]) -> str:
        return _focused_axis_fn(edits)

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # POINT PICKING
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _on_pick_target(self):
        self._pick_coordinator.on_pick_target()

    def _on_pick_radius_center(self):
        self._pick_coordinator.on_pick_radius_center()

    def _on_pick_angle_center(self):
        self._pick_coordinator.on_pick_angle_center()

    def _on_pick_angle_start(self):
        self._pick_coordinator.on_pick_angle_start()

    def _on_pick_angle_end(self):
        self._pick_coordinator.on_pick_angle_end()

    def _cancel_pick(self):
        if self._pick_coordinator is not None:
            self._pick_coordinator.cancel()

    def _on_nudge_point_toggled(self):
        self._distance_editor.on_nudge_point_toggled()

    def _on_distance_point_nudge(self, direction: str):
        self._distance_editor.on_point_nudge(direction)

    def _on_diameter_offset_nudge(self, direction: str):
        self._diameter_editor.on_offset_nudge(direction)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if isinstance(watched, QLineEdit):
                watched.clearFocus()
                return True
        if hasattr(self, '_dist_adjust_axis_by_edit') and watched in self._dist_adjust_axis_by_edit:
            if event.type() == QEvent.FocusIn:
                self._dist_adjust_active_axis = self._dist_adjust_axis_by_edit[watched]
        if hasattr(self, '_diam_adjust_axis_by_edit') and watched in self._diam_adjust_axis_by_edit:
            if event.type() == QEvent.FocusIn:
                self._diam_adjust_active_axis = self._diam_adjust_axis_by_edit[watched]
        if (hasattr(self, '_preview_container') and watched is self._preview_container
                and event.type() == QEvent.Resize):
            if hasattr(self, '_axis_pick_overlay') and self._axis_pick_overlay.isVisible():
                self._position_axis_overlay()
            if hasattr(self, '_axis_hint_overlay') and self._axis_hint_overlay.isVisible():
                self._position_axis_hint_overlay()
        return super().eventFilter(watched, event)

    def _on_point_picked(self, data: dict):
        self._pick_coordinator.on_point_picked(data)

    def _on_measurement_updated(self, payload: dict):
        def _on_distance_model_updated(current):
            self._distance_edit_model = dict(current)
            self._load_distance_adjust_edits_from_model()
            self._update_distance_pick_status()

        def _on_diameter_model_updated(current):
            self._diameter_edit_model = dict(current)
            self._set_diameter_axis(
                _normalize_diameter_axis_mode(
                    self._diameter_edit_model.get('diameter_axis_mode', ''),
                    self._diameter_edit_model.get('axis_xyz', '0, 0, 1'),
                    default='z',
                ),
                commit=False,
                store_adjust_edits=False,
            )
            self._load_diameter_adjust_edits_from_model()
            self._update_diameter_measured_value_box()
            self._update_diameter_pick_status()

        _on_measurement_updated_fn(
            payload=payload,
            distance_list=self._distance_list,
            diameter_list=self._diameter_list,
            current_distance_item=self._current_distance_item,
            current_diameter_item=self._current_diameter_item,
            on_distance_model_updated=_on_distance_model_updated,
            on_diameter_model_updated=_on_diameter_model_updated,
            on_refresh_preview=self._refresh_preview_measurements,
        )

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # PREVIEW REFRESH
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _refresh_preview_measurements(self):
        _refresh_preview_measurements_fn(
            preview_widget=self._preview_widget,
            distance_list=self._distance_list,
            diameter_list=self._diameter_list,
            radius_list=self._radius_list,
            angle_list=self._angle_list,
            current_distance_item=self._current_distance_item,
            normalize_distance=self._normalize_distance_measurement,
            normalize_diameter=self._normalize_diameter_measurement,
            normalize_radius=self._normalize_radius_measurement,
            normalize_angle=self._normalize_angle_measurement,
            distance_precise_mode_enabled=self._distance_precise_mode_enabled(),
            distance_adjust_mode=self._distance_adjust_mode(),
            distance_nudge_point=self._distance_nudge_point(),
        )

    def _sync_preview_measurements_before_save(self):
        if not hasattr(self, '_preview_widget'):
            return
        _sync_preview_before_save_fn(
            dialog_parent=self,
            preview_widget=self._preview_widget,
            on_measurement_updated=self._on_measurement_updated,
        )

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # OUTPUT
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
        self._sync_preview_measurements_before_save()
        self._commit_current_edit()
        super().accept()

