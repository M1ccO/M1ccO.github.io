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
from shared.ui.editor_launch_debug import editor_launch_diag_enabled, editor_launch_debug, editor_launch_id
from shared.ui.runtime_trace import rtrace
from shared.ui.helpers.editor_helpers import create_titled_section, style_icon_action_button, style_move_arrow_button
from ui.widgets.parts_table import PartsTable


@dataclass(frozen=True)
class ModelsTabConfig:
    move_button_fallback_text: str = 'SIIRRA'
    reset_button_fallback_text: str = 'NOLLAA'
    bottom_row_spacing: int = 8
    bottom_left_host_width: int = 340
    bottom_left_box_width: int = 320


class _BypassedPreview(QWidget):
    """No-op preview used for launch diagnostics and lazy tab placeholders."""

    def clear(self):
        return None

    def load_parts(self, _parts):
        return None

    def load_stl(self, *_args, **_kwargs):
        return None

    def get_part_transforms(self, callback):
        callback([])

    def set_part_transforms(self, _transforms):
        return None

    def select_part(self, _index):
        return None

    def select_parts(self, _indices):
        return None

    def reset_selected_part_transform(self):
        return None

    def set_selection_caption(self, _text):
        return None

    def set_transform_edit_enabled(self, _enabled):
        return None

    def set_transform_mode(self, _mode):
        return None

    def set_fine_transform_enabled(self, _enabled):
        return None

    def set_measurement_overlays(self, _overlays):
        return None

    def set_measurements_visible(self, _visible):
        return None

    def set_measurement_drag_enabled(self, _enabled):
        return None

    def activate_web_view(self):
        return None


def _install_placeholder_models_hosts(dialog: Any) -> None:
    """Install lightweight placeholders so editor init can finish without 3D UI."""
    dialog.models_preview = _BypassedPreview(dialog)
    dialog._transform_frame = QFrame()
    dialog._transform_frame.hide()
    dialog._mode_toggle_btn = QPushButton('')
    dialog._fine_transform_btn = QPushButton('')
    dialog._reset_transform_btn = QPushButton('')
    dialog._transform_x = QLineEdit('0')
    dialog._transform_y = QLineEdit('0')
    dialog._transform_z = QLineEdit('0')
    dialog.measurement_summary_label = QLabel()
    dialog.measurement_summary_label.hide()
    dialog.add_model_btn = QPushButton('')
    dialog.remove_model_btn = QPushButton('')
    dialog.model_up_btn = QPushButton('')
    dialog.model_down_btn = QPushButton('')
    dialog.edit_measurements_btn = QPushButton('')


def _build_bypassed_models_tab(dialog: Any, root_tabs: QTabWidget) -> QWidget:
    launch_id = editor_launch_id(dialog)
    editor_launch_debug("models_tab.bypassed.build.begin", launch_id=launch_id)

    models_tab = QWidget()
    models_tab.setProperty('editorPageSurface', True)
    layout = QVBoxLayout(models_tab)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(10)

    notice = QLabel(
        "3D Models tab bypassed by NTX_EDITOR_DIAG_BYPASS_MODELS_TAB=1.\n"
        "Model rows are still loaded for save/load diagnostics; preview and transform UI are not built."
    )
    notice.setWordWrap(True)
    notice.setProperty('detailHint', True)
    layout.addWidget(notice)

    dialog.model_table = _configure_model_table(dialog)
    dialog.model_table.itemChanged.connect(dialog._on_model_table_changed)
    layout.addWidget(dialog.model_table, 1)

    _install_placeholder_models_hosts(dialog)

    root_tabs.addTab(models_tab, dialog._t('tool_editor.tab.models', '3D models'))
    dialog._update_measurement_summary_label()
    editor_launch_debug("models_tab.bypassed.build.done", launch_id=launch_id, tab_count=root_tabs.count())
    return models_tab


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
    launch_id = editor_launch_id(dialog)
    editor_launch_debug(
        "models_tab.transform_controls.build.begin",
        launch_id=launch_id,
        enabled=bool(getattr(dialog, "_assembly_transform_enabled", False)),
    )
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
        def _connect_transform_signals():
            editor_launch_debug(
                "models_tab.transform_controls.connect.begin",
                launch_id=editor_launch_id(dialog),
                preview_exists=hasattr(dialog, 'models_preview') and dialog.models_preview is not None,
                transform_visible=transform_frame.isVisible(),
            )
            if not hasattr(dialog, 'models_preview') or dialog.models_preview is None:
                return
            try:
                dialog.models_preview.set_fine_transform_enabled(dialog._fine_transform_enabled)
                dialog.models_preview.transform_changed.connect(dialog._on_viewer_transform_changed)
                dialog.models_preview.part_selected.connect(dialog._on_viewer_part_selected)
                dialog.models_preview.part_selection_changed.connect(dialog._on_viewer_part_selection_changed)
                editor_launch_debug(
                    "models_tab.transform_controls.connect.done",
                    launch_id=editor_launch_id(dialog),
                    preview_visible=dialog.models_preview.isVisible(),
                    transform_visible=transform_frame.isVisible(),
                )
            except Exception:
                editor_launch_debug("models_tab.transform_controls.connect.failed", launch_id=editor_launch_id(dialog))

        QTimer.singleShot(100, _connect_transform_signals)
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

    editor_launch_debug(
        "models_tab.transform_controls.build.done",
        launch_id=launch_id,
        visible=transform_frame.isVisible(),
        width=transform_frame.width(),
        height=transform_frame.height(),
    )
    return transform_frame


def _materialize_models_tab(
    dialog: Any,
    models_layout: QVBoxLayout,
    root_tabs: QTabWidget,
    config: ModelsTabConfig,
) -> None:
    if bool(getattr(dialog, '_models_tab_materialized', False)):
        if getattr(dialog, 'models_preview', None) is not None:
            _ensure_preview_ready(dialog, root_tabs)
        return

    launch_id = editor_launch_id(dialog)
    editor_launch_debug("models_tab.materialize.begin", launch_id=launch_id)
    rtrace("models_tab.materialize.begin", launch_id=launch_id, dialog_cls=type(dialog).__name__)
    dialog._models_tab_materialized = True

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
    models_panel_layout.addWidget(dialog.model_table, 1)

    preview_panel = QFrame()
    preview_panel.setProperty('editorPartsPanel', True)
    preview_panel.setMinimumWidth(300)
    preview_panel_layout = QVBoxLayout(preview_panel)
    preview_panel_layout.setContentsMargins(8, 8, 8, 8)
    preview_panel_layout.setSpacing(8)

    editor_launch_debug("models_tab.preview.create.before", launch_id=launch_id)
    from shared.ui.stl_preview import StlPreviewWidget
    dialog.models_preview = StlPreviewWidget(parent=dialog)
    dialog.models_preview.set_web_auto_start_enabled(False)
    editor_launch_debug(
        "models_tab.preview.create.after",
        launch_id=launch_id,
        preview_visible=dialog.models_preview.isVisible(),
    )
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
        dialog._t('work_editor.tools.move_up', 'Ã¢â€“Â²'),
        dialog._t('tool_editor.tooltip.move_row_up', 'Move selected row up'),
    )
    style_move_arrow_button(
        dialog.model_down_btn,
        dialog._t('work_editor.tools.move_down', 'Ã¢â€“Â¼'),
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

    placeholder = getattr(dialog, '_models_tab_placeholder_label', None)
    if placeholder is not None:
        models_layout.removeWidget(placeholder)
        placeholder.deleteLater()
        dialog._models_tab_placeholder_label = None

    models_layout.insertWidget(0, splitter, 1)
    models_layout.addLayout(bottom_row, 0)
    dialog._transform_frame.setVisible(dialog._assembly_transform_enabled)

    dialog._update_measurement_summary_label()
    dialog._update_mode_toggle_button_appearance()
    dialog._update_fine_transform_button_appearance()
    dialog._refresh_models_preview()
    dialog._refresh_transform_selection_state()
    if dialog._assembly_transform_enabled and getattr(dialog, '_selected_part_indices', None):
        dialog.models_preview.select_parts(dialog._selected_part_indices)
    _ensure_preview_ready(dialog, root_tabs)

    editor_launch_debug("models_tab.materialize.done", launch_id=launch_id, tab_count=root_tabs.count())
    rtrace(
        "models_tab.materialize.done",
        launch_id=launch_id,
        preview_cls=type(dialog.models_preview).__name__,
        dialog_cls=type(dialog).__name__,
    )


def _ensure_preview_ready(dialog: Any, root_tabs: QTabWidget) -> None:
    """Immediately activate preview WebEngine when Models tab materializes.

    The preview was lazily constructed to avoid editor-launch glitches.
    Now that the tab is being shown, activate immediately without delay.
    """
    try:
        preview = getattr(dialog, 'models_preview', None)
        if preview is None:
            return
        editor_launch_debug("models_tab.preview.activate", launch_id=editor_launch_id(dialog))
        preview.activate_web_view()
    except RuntimeError:
        return


def build_editor_models_tab(dialog: Any, root_tabs: QTabWidget, config: ModelsTabConfig | None = None) -> QWidget:
    config = config or ModelsTabConfig()
    launch_id = editor_launch_id(dialog)
    editor_launch_debug("models_tab.build.begin", launch_id=launch_id, tab_count=root_tabs.count())
    if editor_launch_diag_enabled("BYPASS_MODELS_TAB"):
        return _build_bypassed_models_tab(dialog, root_tabs)

    models_tab = QWidget()
    dialog._models_tab_widget = models_tab
    models_tab.setProperty('editorPageSurface', True)
    models_layout = QVBoxLayout(models_tab)
    models_layout.setContentsMargins(18, 18, 18, 18)
    models_layout.setSpacing(8)

    dialog.model_table = _configure_model_table(dialog)
    dialog.model_table.itemChanged.connect(dialog._on_model_table_changed)
    _install_placeholder_models_hosts(dialog)
    dialog._models_tab_materialized = False

    placeholder = QLabel(
        dialog._t(
            'tool_editor.models.loading_placeholder',
            '3D preview tools are prepared when this tab opens.',
        )
    )
    placeholder.setWordWrap(True)
    placeholder.setProperty('detailHint', True)
    models_layout.addWidget(placeholder, 1, Qt.AlignCenter)
    dialog._models_tab_placeholder_label = placeholder

    root_tabs.addTab(models_tab, dialog._t('tool_editor.tab.models', '3D models'))

    def _activate_preview_for_models_tab(index: int) -> None:
        if root_tabs.widget(index) is not models_tab:
            return
        editor_launch_debug("models_tab.preview.activate", launch_id=editor_launch_id(dialog), index=index)
        _materialize_models_tab(dialog, models_layout, root_tabs, config)

    root_tabs.currentChanged.connect(_activate_preview_for_models_tab)
    if root_tabs.currentWidget() is models_tab:
        QTimer.singleShot(0, lambda: _activate_preview_for_models_tab(root_tabs.currentIndex()))

    dialog._update_measurement_summary_label()
    editor_launch_debug("models_tab.build.done", launch_id=launch_id, tab_count=root_tabs.count())
    return models_tab


__all__ = ['ModelsTabConfig', 'build_editor_models_tab']
