"""Shared 3D models tab builder for editor dialogs (Tool/Jaw)."""

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import TOOL_ICONS_DIR
from shared.ui.helpers.editor_helpers import create_titled_section, style_icon_action_button, style_move_arrow_button
from shared.ui.stl_preview import StlPreviewWidget
from ui.widgets.parts_table import PartsTable


@dataclass(frozen=True)
class ModelsTabConfig:
    move_button_fallback_text: str = 'SIIRRA'
    reset_button_fallback_text: str = 'NOLLAA'
    bottom_row_spacing: int = 8
    bottom_left_host_width: int = 340
    bottom_left_box_width: int = 320


def _configure_model_table(dialog: Any) -> PartsTable:
    model_table = PartsTable(['Part Name', 'STL File', 'Color'])
    model_table.setObjectName('editorModelsTable')
    model_table.setMinimumHeight(240)
    model_table.setMaximumHeight(16777215)
    model_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    model_table.verticalHeader().setDefaultSectionSize(44)
    model_table.verticalHeader().setMinimumSectionSize(28)
    model_table.setColumnCount(3)
    model_table.setHorizontalHeaderLabels([
        dialog._t('tool_editor.table.part_name', 'Part Name'),
        dialog._t('jaw_editor.field.stl_file', 'STL File'),
        dialog._t('tool_editor.table.color', 'Color'),
    ])
    header = model_table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.Interactive)
    header.setSectionResizeMode(1, QHeaderView.Stretch)
    header.setSectionResizeMode(2, QHeaderView.Interactive)
    header.setStretchLastSection(False)
    model_table.setColumnWidth(0, 100)
    model_table.setColumnWidth(1, 170)
    model_table.setColumnWidth(2, 70)
    model_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    model_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    model_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    return model_table


def _build_transform_controls(dialog: Any, model_table: PartsTable, config: ModelsTabConfig) -> QFrame:
    transform_frame = create_titled_section(dialog._t('tool_editor.transform.toolbar_title', 'Muunnos'))
    transform_frame.setMinimumWidth(488)
    transform_frame.setMaximumWidth(488)
    transform_frame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    transform_layout = QVBoxLayout(transform_frame)
    transform_layout.setContentsMargins(8, 4, 8, 6)
    transform_layout.setSpacing(4)

    mode_row = QHBoxLayout()
    mode_row.setSpacing(0)
    mode_row.setContentsMargins(0, 0, 0, 0)

    dialog._mode_toggle_btn = QPushButton('')
    dialog._fine_transform_btn = QPushButton('')
    dialog._reset_transform_btn = QPushButton('')

    style_icon_action_button(
        dialog._mode_toggle_btn,
        TOOL_ICONS_DIR / 'move.svg',
        dialog._t('tool_editor.transform.move', config.move_button_fallback_text),
    )
    style_icon_action_button(
        dialog._fine_transform_btn,
        TOOL_ICONS_DIR / '1x.svg',
        dialog._t('tool_editor.transform.fine_tooltip', 'Toggle fine transform increments'),
    )
    style_icon_action_button(
        dialog._reset_transform_btn,
        TOOL_ICONS_DIR / 'reset.svg',
        dialog._t('tool_editor.transform.reset', config.reset_button_fallback_text),
    )

    dialog._mode_toggle_btn.setCheckable(True)
    dialog._mode_toggle_btn.setChecked(True)
    dialog._fine_transform_btn.setCheckable(True)
    dialog._fine_transform_btn.setChecked(dialog._fine_transform_enabled)
    dialog._reset_transform_btn.setFixedWidth(42)
    dialog._mode_toggle_btn.setFixedWidth(42)
    dialog._fine_transform_btn.setFixedWidth(42)
    dialog._reset_transform_btn.setToolTip(
        dialog._t(
            'tool_editor.transform.reset_tooltip',
            'Left click: reset to original position. Right click: restore saved position.',
        )
    )
    dialog._update_mode_toggle_button_appearance()
    dialog._update_fine_transform_button_appearance()

    lbl_x = QLabel('X')
    lbl_x.setProperty('detailFieldKey', True)
    lbl_x.setFixedWidth(16)
    lbl_x.setAlignment(Qt.AlignCenter)
    dialog._transform_x = QLineEdit('0')
    dialog._transform_x.setFixedWidth(80)
    dialog._transform_x.setAlignment(Qt.AlignRight)

    lbl_y = QLabel('Y')
    lbl_y.setProperty('detailFieldKey', True)
    lbl_y.setFixedWidth(16)
    lbl_y.setAlignment(Qt.AlignCenter)
    dialog._transform_y = QLineEdit('0')
    dialog._transform_y.setFixedWidth(80)
    dialog._transform_y.setAlignment(Qt.AlignRight)

    lbl_z = QLabel('Z')
    lbl_z.setProperty('detailFieldKey', True)
    lbl_z.setFixedWidth(16)
    lbl_z.setAlignment(Qt.AlignCenter)
    dialog._transform_z = QLineEdit('0')
    dialog._transform_z.setFixedWidth(80)
    dialog._transform_z.setAlignment(Qt.AlignRight)

    mode_row.addWidget(dialog._mode_toggle_btn)
    mode_row.addSpacing(3)
    mode_row.addWidget(dialog._fine_transform_btn)
    mode_row.addSpacing(4)
    mode_row.addWidget(lbl_x)
    mode_row.addWidget(dialog._transform_x)
    mode_row.addSpacing(4)
    mode_row.addWidget(lbl_y)
    mode_row.addWidget(dialog._transform_y)
    mode_row.addSpacing(4)
    mode_row.addWidget(lbl_z)
    mode_row.addWidget(dialog._transform_z)
    mode_row.addSpacing(6)
    mode_row.addWidget(dialog._reset_transform_btn)
    transform_layout.addLayout(mode_row)

    transform_frame.setVisible(dialog._assembly_transform_enabled)

    if dialog._assembly_transform_enabled:
        dialog.models_preview.set_fine_transform_enabled(dialog._fine_transform_enabled)
        dialog.models_preview.transform_changed.connect(dialog._on_viewer_transform_changed)
        dialog.models_preview.part_selected.connect(dialog._on_viewer_part_selected)
        dialog.models_preview.part_selection_changed.connect(dialog._on_viewer_part_selection_changed)
        dialog._mode_toggle_btn.clicked.connect(dialog._on_mode_toggle_clicked)
        dialog._fine_transform_btn.toggled.connect(dialog._on_fine_transform_toggled)
        dialog._reset_transform_btn.clicked.connect(dialog._reset_current_part_transform)
        dialog._transform_x.editingFinished.connect(dialog._apply_manual_transform)
        dialog._transform_y.editingFinished.connect(dialog._apply_manual_transform)
        dialog._transform_z.editingFinished.connect(dialog._apply_manual_transform)
        dialog._transform_x.returnPressed.connect(dialog._transform_x.editingFinished.emit)
        dialog._transform_y.returnPressed.connect(dialog._transform_y.editingFinished.emit)
        dialog._transform_z.returnPressed.connect(dialog._transform_z.editingFinished.emit)
        model_table.itemSelectionChanged.connect(dialog._on_model_table_selection_changed)
        QTimer.singleShot(0, dialog._update_transform_row_sizes)

    return transform_frame


def build_editor_models_tab(dialog: Any, root_tabs: QTabWidget, config: ModelsTabConfig | None = None) -> QWidget:
    config = config or ModelsTabConfig()

    models_tab = QWidget()
    models_tab.setProperty('editorPageSurface', True)
    models_layout = QVBoxLayout(models_tab)
    models_layout.setContentsMargins(18, 18, 18, 18)
    models_layout.setSpacing(8)

    splitter = QSplitter(Qt.Horizontal)
    splitter.setProperty('editorTransparentPanel', True)
    splitter.setHandleWidth(8)

    models_panel = QFrame()
    models_panel.setProperty('editorPartsPanel', True)
    models_panel.setMinimumWidth(260)
    models_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    models_panel_layout = QVBoxLayout(models_panel)
    models_panel_layout.setContentsMargins(8, 10, 8, 8)
    models_panel_layout.setSpacing(0)

    dialog.model_table = _configure_model_table(dialog)
    dialog.model_table.itemChanged.connect(dialog._on_model_table_changed)
    models_panel_layout.addWidget(dialog.model_table, 1)

    preview_panel = QFrame()
    preview_panel.setProperty('editorPartsPanel', True)
    preview_panel.setMinimumWidth(300)
    preview_panel_layout = QVBoxLayout(preview_panel)
    preview_panel_layout.setContentsMargins(8, 8, 8, 8)
    preview_panel_layout.setSpacing(8)

    dialog.models_preview = StlPreviewWidget(parent=dialog)
    dialog.models_preview.set_control_hint_text(
        dialog._t(
            'tool_editor.hint.rotate_pan_zoom',
            'Rotate: left mouse . Pan: right mouse . Zoom: mouse wheel',
        )
    )
    preview_panel_layout.addWidget(dialog.models_preview, 1)

    dialog._transform_frame = _build_transform_controls(dialog, dialog.model_table, config)

    model_btn_bar = create_titled_section(dialog._t('tool_editor.models.actions_title', 'Mallien toiminnot'))
    model_btn_bar_layout = QVBoxLayout(model_btn_bar)
    model_btn_bar_layout.setContentsMargins(8, 4, 8, 6)
    model_btn_bar_layout.setSpacing(4)

    model_meta_row = QHBoxLayout()
    model_meta_row.setContentsMargins(0, 0, 0, 0)
    model_meta_row.setSpacing(6)

    model_btns = QHBoxLayout()
    model_btns.setContentsMargins(0, 0, 0, 0)
    model_btns.setSpacing(8)

    dialog.add_model_btn = QPushButton(dialog._t('tool_editor.action.add_model', 'ADD MODEL'))
    dialog.remove_model_btn = QPushButton(dialog._t('tool_editor.action.remove_selected_model', 'REMOVE SELECTED MODEL'))
    style_icon_action_button(
        dialog.add_model_btn,
        TOOL_ICONS_DIR / 'add_file.svg',
        dialog._t('tool_editor.action.add_model', 'Add model'),
    )
    style_icon_action_button(
        dialog.remove_model_btn,
        TOOL_ICONS_DIR / 'remove.svg',
        dialog._t('tool_editor.action.remove_selected_model', 'Remove selected model'),
        danger=True,
    )
    dialog.model_up_btn = QPushButton()
    dialog.model_down_btn = QPushButton()
    style_move_arrow_button(
        dialog.model_up_btn,
        dialog._t('work_editor.tools.move_up', 'â–²'),
        dialog._t('tool_editor.tooltip.move_row_up', 'Move selected row up'),
    )
    style_move_arrow_button(
        dialog.model_down_btn,
        dialog._t('work_editor.tools.move_down', 'â–¼'),
        dialog._t('tool_editor.tooltip.move_row_down', 'Move selected row down'),
    )
    dialog.add_model_btn.clicked.connect(dialog._add_model_row)
    dialog.remove_model_btn.clicked.connect(dialog._remove_model_row)
    dialog.model_up_btn.clicked.connect(lambda: dialog._move_model_row(-1))
    dialog.model_down_btn.clicked.connect(lambda: dialog._move_model_row(1))

    dialog.edit_measurements_btn = QPushButton('')
    style_icon_action_button(
        dialog.edit_measurements_btn,
        TOOL_ICONS_DIR / 'measure.svg',
        dialog._t('tool_editor.measurements.open_editor', 'Edit measurements'),
    )
    dialog.edit_measurements_btn.clicked.connect(dialog._open_measurement_editor)

    dialog.measurement_summary_label = QLabel()
    dialog.measurement_summary_label.setProperty('detailHint', True)
    dialog.measurement_summary_label.setStyleSheet('background: transparent; color: #6b7b8e; font-size: 11px;')
    dialog.measurement_summary_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    model_meta_row.addWidget(dialog.measurement_summary_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
    model_meta_row.addStretch(1)
    model_btn_bar_layout.addLayout(model_meta_row)

    model_btns.addWidget(dialog.add_model_btn)
    model_btns.addWidget(dialog.remove_model_btn)
    model_btns.addWidget(dialog.model_up_btn)
    model_btns.addWidget(dialog.model_down_btn)
    model_btns.addWidget(dialog.edit_measurements_btn)
    model_btns.addStretch(1)
    model_btn_bar_layout.addLayout(model_btns)

    splitter.addWidget(models_panel)
    splitter.addWidget(preview_panel)
    splitter.setCollapsible(0, False)
    splitter.setCollapsible(1, False)
    splitter.setSizes([420, 540])
    models_layout.addWidget(splitter, 1)

    bottom_row = QHBoxLayout()
    bottom_row.setContentsMargins(0, 0, 0, 0)
    bottom_row.setSpacing(config.bottom_row_spacing)

    left_toolbar_host = QWidget()
    left_toolbar_host.setObjectName('leftToolbarHost')
    left_toolbar_host.setFixedWidth(config.bottom_left_host_width)
    left_toolbar_host.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    left_toolbar_host.setAutoFillBackground(False)
    left_toolbar_host.setStyleSheet('#leftToolbarHost { background: transparent; border: none; }')
    left_toolbar_host_layout = QHBoxLayout(left_toolbar_host)
    left_toolbar_host_layout.setContentsMargins(0, 0, 0, 0)
    left_toolbar_host_layout.setSpacing(0)
    model_btn_bar.setFixedWidth(config.bottom_left_box_width)
    left_toolbar_host_layout.addStretch(1)
    left_toolbar_host_layout.addWidget(model_btn_bar, 0, Qt.AlignTop)
    left_toolbar_host_layout.addStretch(1)

    bottom_row.addWidget(left_toolbar_host, 0, Qt.AlignLeft | Qt.AlignTop)
    bottom_row.addStretch(1)
    bottom_row.addWidget(dialog._transform_frame, 0, Qt.AlignRight | Qt.AlignTop)
    models_layout.addLayout(bottom_row, 0)
    dialog._transform_frame.setVisible(dialog._assembly_transform_enabled)

    root_tabs.addTab(models_tab, dialog._t('tool_editor.tab.models', '3D models'))
    dialog._update_measurement_summary_label()
    return models_tab


__all__ = ['ModelsTabConfig', 'build_editor_models_tab']

