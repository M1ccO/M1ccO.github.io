import json
import math
from typing import Callable
from PySide6.QtCore import QEvent, Qt, QTimer, QSize, QItemSelectionModel, QEventLoop
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListView, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
    QFileDialog, QTableWidgetItem, QHeaderView, QSplitter, QTreeWidget, QTreeWidgetItem
)
from config import (
    ALL_TOOL_TYPES,
    EDITOR_DROPDOWN_WIDTH,
    JAW_MODELS_ROOT_DEFAULT,
    SHARED_UI_PREFERENCES_PATH,
    TOOL_ICONS_DIR,
    TOOL_MODELS_ROOT_DEFAULT,
)
from shared.model_paths import format_model_path_for_display, read_model_roots
from ui.widgets.parts_table import PartsTable
from ui.stl_preview import StlPreviewWidget
from ui.measurement_editor_dialog import MeasurementEditorDialog
from ui.widgets.color_picker_dialog import ColorPickerDialog
from ui.widgets.common import clear_focused_dropdown_on_outside_click, apply_shared_dropdown_style
from shared.editor_helpers import (
    add_shadow,
    setup_editor_dialog,
    create_titled_section,
    create_dialog_buttons,
    apply_secondary_button_theme,
    make_arrow_button,
    style_panel_action_button,
    style_icon_action_button,
    style_move_arrow_button,
    reflow_fields_grid,
    build_picker_row,
)


class ComponentPickerDialog(QDialog):
    def __init__(
        self,
        title: str,
        entries: list[dict],
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self._entries = entries
        self._selected_entry = None
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self._picker_syncing_widths = False
        self._picker_min_widths = [72, 110, 64]
        self._picker_name_ratio = 0.31
        self._picker_code_ratio = 0.68
        self.setWindowTitle(title)
        self.resize(560, 520)
        self.setMinimumSize(360, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText(self._t('tool_editor.component.search_placeholder', 'Search by name, code, link, or source...'))
        self.search.textChanged.connect(self._refresh)
        root.addWidget(self.search)

        self.list_widget = QTreeWidget()
        self.list_widget.setObjectName('componentPickerTable')
        self.list_widget.setColumnCount(3)
        self.list_widget.setHeaderLabels([
            self._t('tool_editor.table.part_name', 'Part name'),
            self._t('tool_editor.table.code', 'Code'),
            self._t('tool_editor.component.column_tcode', 'T-code'),
        ])
        self.list_widget.setRootIsDecorated(False)
        self.list_widget.setUniformRowHeights(True)
        self.list_widget.setAlternatingRowColors(False)
        self.list_widget.setIndentation(0)
        self.list_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.list_widget.setAllColumnsShowFocus(False)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setSortingEnabled(True)
        picker_style = """
            QTreeWidget#componentPickerTable {
                background-color: #ffffff;
                border: 1px solid #d8e0e8;
                outline: none;
                selection-background-color: #cfe4f8;
                selection-color: #16334e;
                show-decoration-selected: 1;
            }
            QTreeWidget#componentPickerTable::item {
                padding: 7px 10px;
                border: none;
                border-left: none;
                border-right: none;
                border-top: none;
                border-bottom: 1px solid #d8e0e8;
                background-color: #ffffff;
                color: #25313b;
            }
            QTreeWidget#componentPickerTable::item:selected,
            QTreeWidget#componentPickerTable::item:selected:active,
            QTreeWidget#componentPickerTable::item:selected:!active {
                background-color: #cfe4f8;
                color: #16334e;
                border: none;
                border-left: none;
                border-right: none;
                border-top: none;
                border-bottom: 1px solid #d8e0e8;
            }
            QTreeWidget#componentPickerTable QHeaderView::section {
                background-color: #f3f6f8;
                border: 1px solid #d9e0e6;
                padding: 7px 8px;
                font-weight: 700;
                color: #25313b;
            }
            QTreeWidget#componentPickerTable QHeaderView::up-arrow,
            QTreeWidget#componentPickerTable QHeaderView::down-arrow {
                width: 14px;
                height: 14px;
            }
            """
        self.list_widget.setStyleSheet(picker_style)
        header = self.list_widget.header()
        header.setMinimumSectionSize(32)
        header.setStretchLastSection(False)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.sectionResized.connect(self._on_picker_header_resized)
        self.list_widget.itemDoubleClicked.connect(lambda _: self._accept_selected())
        root.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton(self._t('common.cancel', 'Cancel').upper())
        select_btn = QPushButton(self._t('tool_editor.component.select', 'SELECT'))
        cancel_btn.setProperty('panelActionButton', True)
        select_btn.setProperty('panelActionButton', True)
        select_btn.setProperty('primaryAction', True)
        cancel_btn.clicked.connect(self.reject)
        select_btn.clicked.connect(self._accept_selected)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(select_btn)
        root.addLayout(btn_row)

        # Use the same shared button theme as other editor dialogs.
        apply_secondary_button_theme(self, select_btn)

        QTimer.singleShot(0, self._set_picker_initial_widths)
        self.list_widget.sortItems(0, Qt.AscendingOrder)
        header.setSortIndicator(0, Qt.AscendingOrder)
        self._refresh()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_picker_column_widths()

    def _set_picker_initial_widths(self):
        if not hasattr(self, 'list_widget'):
            return
        self._picker_syncing_widths = True
        header = self.list_widget.header()
        header.blockSignals(True)
        try:
            self.list_widget.setColumnWidth(0, 176)
            self.list_widget.setColumnWidth(1, 230)
        finally:
            header.blockSignals(False)
            self._picker_syncing_widths = False
        self._capture_picker_column_layout()
        self._apply_picker_column_widths()

    def _capture_picker_column_layout(self):
        if not hasattr(self, 'list_widget'):
            return
        widths = [max(1, self.list_widget.columnWidth(idx)) for idx in range(self.list_widget.columnCount())]
        total = sum(widths)
        if total <= 0:
            return
        self._picker_name_ratio = widths[0] / total
        remaining = widths[1] + widths[2]
        if remaining <= 0:
            return
        self._picker_code_ratio = widths[1] / remaining

    def _apply_picker_column_widths(self):
        if not hasattr(self, 'list_widget') or self._picker_syncing_widths:
            return
        viewport_width = self.list_widget.viewport().width()
        if viewport_width <= 0:
            return

        min_name, min_code, min_tcode = self._picker_min_widths
        max_name_width = max(min_name, viewport_width - min_code - min_tcode)
        name_width = min(max_name_width, max(min_name, int(viewport_width * self._picker_name_ratio)))

        remaining = max(min_code + min_tcode, viewport_width - name_width)
        code_width = int(remaining * self._picker_code_ratio)
        code_width = max(min_code, min(code_width, remaining - min_tcode))
        tcode_width = viewport_width - name_width - code_width

        if tcode_width < min_tcode:
            tcode_width = min_tcode
            code_width = max(min_code, viewport_width - name_width - tcode_width)
            name_width = max(min_name, viewport_width - code_width - tcode_width)

        self._picker_syncing_widths = True
        header = self.list_widget.header()
        header.blockSignals(True)
        try:
            self.list_widget.setColumnWidth(0, max(min_name, name_width))
            self.list_widget.setColumnWidth(1, code_width)
            self.list_widget.setColumnWidth(2, tcode_width)
        finally:
            header.blockSignals(False)
            self._picker_syncing_widths = False

    def _on_picker_header_resized(self, _logical_index: int, _old_size: int, _new_size: int):
        if self._picker_syncing_widths:
            return
        self._capture_picker_column_layout()
        self._apply_picker_column_widths()

    def _refresh(self):
        text = self.search.text().strip().lower()
        self.list_widget.clear()
        for entry in self._entries:
            searchable = ' '.join([
                entry.get('name', ''),
                entry.get('code', ''),
                entry.get('link', ''),
                entry.get('source', ''),
            ]).lower()
            if text and text not in searchable:
                continue
            source = entry.get('source', '')
            item = QTreeWidgetItem([
                entry.get('name', self._t('tool_library.field.part', 'Part')),
                entry.get('code', ''),
                source,
            ])
            item.setData(0, Qt.UserRole, entry)
            self.list_widget.addTopLevelItem(item)

        if self.list_widget.topLevelItemCount() > 0:
            self.list_widget.setCurrentItem(self.list_widget.topLevelItem(0))

    def _accept_selected(self):
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(
                self,
                self._t('tool_editor.component.select_title', 'Select component'),
                self._t('tool_editor.component.select_first', 'Select a component first.'),
            )
            return
        self._selected_entry = item.data(0, Qt.UserRole)
        self.accept()

    def selected_entry(self):
        return self._selected_entry


class AddEditToolDialog(QDialog):

    def __init__(
        self,
        parent=None,
        tool=None,
        tool_service=None,
        translate: Callable[[str, str | None], str] | None = None,
        batch_label: str | None = None,
        group_edit_mode: bool = False,
        group_count: int | None = None,
    ):
        super().__init__(parent)
        self.tool = tool or {}
        self.original_uid = self.tool.get('uid') if isinstance(self.tool, dict) else None
        self.tool_service = tool_service
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self._batch_label = (batch_label or '').strip()
        self._group_edit_mode = bool(group_edit_mode)
        self._group_count = int(group_count or 0)
        self._assembly_transform_enabled = self._is_assembly_transform_enabled()
        self._part_transforms = {}
        self._saved_part_transforms = {}
        self._measurement_editor_state = self._empty_measurement_editor_state()
        self._current_transform_mode = 'translate'
        self._fine_transform_enabled = False
        self._selected_part_index = -1
        self._selected_part_indices = []
        self._group_target_rows: list[int] = []
        self._general_field_columns = None
        self._clamping_screen_bounds = False
        self._suspend_preview_refresh = False
        self._spare_refresh_timer = QTimer(self)
        self._spare_refresh_timer.setSingleShot(True)
        self._spare_refresh_timer.setInterval(75)
        self._spare_refresh_timer.timeout.connect(self._refresh_spare_component_dropdowns)
        self.setWindowTitle(self._dialog_title())
        self.resize(1120, 760)
        self.setMinimumSize(900, 660)
        self.setModal(True)
        setup_editor_dialog(self)
        self._build_ui()
        self._load_tool()
        self._update_cutting_label()
        self._update_tool_type_fields()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _dialog_title(self) -> str:
        if self._group_edit_mode:
            if self._group_count > 1:
                return self._t(
                    'tool_editor.window_title.group',
                    'Group Edit ({count} items)',
                    count=self._group_count,
                )
            return self._t('tool_editor.window_title.group', 'Group Edit')
        if self.tool:
            tool_id = (self.tool.get('id') or '').strip() if isinstance(self.tool, dict) else ''
            base = self._t('tool_editor.window_title.edit', 'Edit Tool - {tool_id}', tool_id=tool_id)
        else:
            base = self._t('tool_editor.window_title.add', 'Add Tool')
        if self._batch_label:
            return f"{base} ({self._batch_label})"
        return base

    def _localized_tool_type(self, raw_tool_type: str) -> str:
        key = f"tool_library.tool_type.{(raw_tool_type or '').strip().lower().replace('.', '_').replace('/', '_').replace(' ', '_')}"
        return self._t(key, raw_tool_type)

    def _localized_cutting_type(self, raw_cutting_type: str) -> str:
        key = f"tool_library.cutting_type.{(raw_cutting_type or '').strip().lower().replace(' ', '_')}"
        return self._t(key, raw_cutting_type)

    def _localized_tool_head(self, head: str) -> str:
        normalized = (head or 'HEAD1').strip().upper()
        if normalized == 'HEAD2':
            return self._t('tool_editor.tool_head.head2', 'Head 2')
        return self._t('tool_editor.tool_head.head1', 'Head 1')

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: str):
        target = (value or '').strip()
        for idx in range(combo.count()):
            if (combo.itemData(idx) or '').strip() == target:
                combo.setCurrentIndex(idx)
                return

    def _build_ui(self):
        root = QVBoxLayout(self)
        combo_width = EDITOR_DROPDOWN_WIDTH

        self.tabs = QTabWidget()
        self.tabs.setObjectName('toolEditorTabs')
        self.tabs.currentChanged.connect(lambda _idx: self._commit_active_edits())
        root.addWidget(self.tabs, 1)

        # -------------------------
        # GENERAL TAB
        # -------------------------
        general_tab = QWidget()
        general_tab.setProperty('editorPageSurface', True)
        general_layout = QVBoxLayout(general_tab)
        general_layout.setContentsMargins(0, 0, 0, 0)
        general_layout.setSpacing(0)

        general_scroll = QScrollArea()
        self.general_scroll = general_scroll
        general_scroll.setWidgetResizable(True)
        general_scroll.setFrameShape(QFrame.NoFrame)
        general_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        general_layout.addWidget(general_scroll, 1)

        general_content = QWidget()
        general_content.setProperty('editorFieldsViewport', True)
        general_content.setProperty('editorPageSurface', True)
        general_content_layout = QVBoxLayout(general_content)
        general_content_layout.setContentsMargins(0, 0, 0, 0)
        general_content_layout.setSpacing(0)
        general_scroll.setWidget(general_content)

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
        self.editor_header_title = QLabel(self._t('tool_editor.header.new_tool', 'New tool'))
        self.editor_header_title.setProperty('detailHeroTitle', True)
        self.editor_header_title.setWordWrap(True)
        self.editor_header_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.editor_header_id = QLabel('')
        self.editor_header_id.setProperty('detailHeroTitle', True)
        self.editor_header_id.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title_row.addWidget(self.editor_header_title, 1)
        title_row.addWidget(self.editor_header_id, 0, Qt.AlignRight)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        self.editor_type_badge = QLabel('')
        self.editor_type_badge.setProperty('toolBadge', True)
        meta_row.addWidget(self.editor_type_badge, 0, Qt.AlignLeft)
        meta_row.addStretch(1)

        header_layout.addLayout(title_row)
        header_layout.addLayout(meta_row)
        form_layout.addWidget(header)

        self.general_fields_grid = None  # Groups handle layout directly

        self.tool_id = QLineEdit()
        self.tool_head = QPushButton(self._localized_tool_head('HEAD1'))
        self.tool_head.setCheckable(True)
        self.tool_head.clicked.connect(self._toggle_tool_head)
        apply_secondary_button_theme(self.tool_head)
        self.tool_head.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.tool_head.setFixedWidth(118)

        self.tool_type = QComboBox()
        for raw_type in ALL_TOOL_TYPES:
            self.tool_type.addItem(self._localized_tool_type(raw_type), raw_type)
        self.tool_type.currentTextChanged.connect(self._update_tool_type_fields)
        self._style_combo(self.tool_type)
        self.tool_type.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.tool_type.setFixedWidth(330)
        self.tool_type.setMaxVisibleItems(8)
        self._configure_combo_popup(self.tool_type, max_rows=8, row_height=40)

        self.tool_type_row = QWidget()
        self.tool_type_row.setProperty('editorInlineRow', True)
        ttl = QHBoxLayout(self.tool_type_row)
        ttl.setContentsMargins(0, 0, 0, 0)
        ttl.setSpacing(10)
        ttl.addWidget(self.tool_type)
        ttl.addWidget(self.tool_head)
        ttl.addStretch(1)

        self.description = QLineEdit()
        self.geom_x = QLineEdit()
        self.geom_z = QLineEdit()
        self.radius = QLineEdit()
        self.nose_corner_radius = QLineEdit()
        self.holder_code = QLineEdit()
        self.holder_link = QLineEdit()
        self.holder_add_element = QLineEdit()
        self.holder_add_element_link = QLineEdit()

        self.cutting_type = QComboBox()
        self.cutting_type.setObjectName('cuttingTypeCombo')
        for raw_cutting in ['Insert', 'Drill', 'Mill']:
            self.cutting_type.addItem(self._localized_cutting_type(raw_cutting), raw_cutting)
        self.cutting_type.currentTextChanged.connect(self._update_tool_type_fields)
        self._style_combo(self.cutting_type)
        self.cutting_type.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.cutting_type.setMinimumWidth(180)

        self.cutting_code = QLineEdit()
        self.cutting_link = QLineEdit()
        self.cutting_add_element = QLineEdit()
        self.cutting_add_element_link = QLineEdit()
        self.notes = QLineEdit()
        self.default_pot = QLineEdit()

        self.holder_code_row = self._build_picker_row(
            self.holder_code,
            self._pick_holder_component,
            self._t('tool_editor.tooltip.pick_holder', 'Pick holder from existing tools'),
        )
        self.cutting_code_row = self._build_picker_row(
            self.cutting_code,
            self._pick_cutting_component,
            self._t('tool_editor.tooltip.pick_cutting', 'Pick cutting component from existing tools'),
        )

        self.cutting_type_row = QWidget()
        self.cutting_type_row.setProperty('editorInlineRow', True)
        ctl = QHBoxLayout(self.cutting_type_row)
        ctl.setContentsMargins(0, 0, 0, 0)
        ctl.addWidget(self.cutting_type)
        ctl.addStretch(1)

        self.cutting_code_label = QLabel(self._t('tool_library.field.cutting_code', '{cutting_type} code', cutting_type=self._localized_cutting_type('Insert')))

        self.drill_nose_angle = QLineEdit()
        self.mill_cutting_edges = QLineEdit()
        self.drill_row_label = QLabel(self._t('tool_library.field.nose_angle', 'Nose angle'))
        self.mill_row_label = QLabel(self._t('tool_library.field.cutting_edges', 'Cutting edges'))

        # Make editor controls visually closer to detail value boxes.
        for w in [
            self.tool_id, self.tool_head, self.tool_type, self.description, self.geom_x, self.geom_z,
            self.radius, self.nose_corner_radius, self.holder_code, self.holder_link,
            self.holder_add_element, self.holder_add_element_link, self.cutting_type,
            self.cutting_code, self.cutting_link, self.cutting_add_element,
            self.cutting_add_element_link, self.drill_nose_angle,
            self.mill_cutting_edges, self.notes, self.default_pot
        ]:
            self._style_general_editor(w)

        # -- Build grouped field sections --

        # Group 1: Identity
        group1 = self._build_field_group([
            self._build_edit_field(self._t('tool_library.row.tool_id', 'Tool ID'), self.tool_id),
            self._build_edit_field(self._t('tool_editor.field.tool_type', 'Tool type'), self.tool_type_row),
            self._build_edit_field(self._t('tool_editor.field.default_pot', 'Default pot'), self.default_pot),
            self._build_edit_field(self._t('setup_page.field.description', 'Description'), self.description),
        ])

        # Group 2: Geometry
        group2 = self._build_field_group([
            self._build_edit_field(self._t('tool_library.field.geom_x', 'Geom X'), self.geom_x),
            self._build_edit_field(self._t('tool_library.field.geom_z', 'Geom Z'), self.geom_z),
            self._build_edit_field(self._t('tool_library.field.radius', 'Radius'), self.radius),
            self._build_edit_field(self._t('tool_library.field.nose_corner_radius', 'Nose R / Corner R'), self.nose_corner_radius),
        ])

        # Group 3: Holder (code/link toggle)
        self.holder_code_field = self._build_edit_field(self._t('tool_library.field.holder_code', 'Holder code'), self.holder_code_row)
        self.holder_link_field = self._build_edit_field(self._t('tool_editor.field.holder_link', 'Holder link'), self.holder_link)
        self.holder_add_field = self._build_edit_field(self._t('tool_library.field.add_element', 'Add. Element'), self.holder_add_element)
        self.holder_add_link_field = self._build_edit_field(self._t('tool_editor.field.add_element_link', 'Add. Element link'), self.holder_add_element_link)
        self.holder_link_field.setVisible(False)
        self.holder_add_link_field.setVisible(False)
        group3 = self._build_field_group([
            self.holder_code_field, self.holder_link_field,
            self.holder_add_field, self.holder_add_link_field,
        ])

        # Group 4: Cutting (code/link toggle)
        cutting_type_field = self._build_edit_field(self._t('tool_editor.field.cutting_component_type', 'Cutting component type'), self.cutting_type_row)
        self.cutting_code_field = self._build_edit_field('', self.cutting_code_row, key_label=self.cutting_code_label)
        self.cutting_link_field = self._build_edit_field(self._t('tool_editor.field.cutting_component_link', 'Cutting component link'), self.cutting_link)
        self.cutting_add_field = self._build_edit_field(self._t('tool_editor.field.add_cutting_any', 'Add. Insert/Drill/Mill'), self.cutting_add_element)
        self.cutting_add_link_field = self._build_edit_field(self._t('tool_editor.field.add_cutting_any_link', 'Add. Insert/Drill/Mill link'), self.cutting_add_element_link)
        self.cutting_link_field.setVisible(False)
        self.cutting_add_link_field.setVisible(False)
        self.drill_field = self._build_edit_field('', self.drill_nose_angle, key_label=self.drill_row_label)
        self.mill_field = self._build_edit_field('', self.mill_cutting_edges, key_label=self.mill_row_label)
        group4 = self._build_field_group([
            cutting_type_field,
            self.cutting_code_field, self.cutting_link_field,
            self.cutting_add_field, self.cutting_add_link_field,
            self.drill_field, self.mill_field,
        ])

        # Group 5: Notes
        group5 = self._build_field_group([
            self._build_edit_field(self._t('tool_library.field.notes', 'Notes'), self.notes),
        ])

        # Dummy field order for compatibility
        self._general_field_order = []

        # Add groups to form layout
        form_layout.addWidget(group1)
        form_layout.addWidget(group2)
        group3.setVisible(False)
        form_layout.addWidget(group3)
        group4.setVisible(False)
        form_layout.addWidget(group4)
        form_layout.addWidget(group5)

        general_content_layout.addWidget(form_frame)
        general_content_layout.addStretch(1)
        self.tabs.addTab(general_tab, self._t('tool_editor.tab.general', 'General'))

        # -------------------------
        # ADDITIONAL PARTS TAB
        # -------------------------
        parts_tab = QWidget()
        parts_tab.setProperty('editorPageSurface', True)
        parts_tab_layout = QVBoxLayout(parts_tab)
        parts_tab_layout.setContentsMargins(18, 18, 18, 18)
        parts_tab_layout.setSpacing(8)

        p_layout = parts_tab_layout
        p_layout.setSpacing(8)

        parts_panel = QFrame()
        parts_panel.setProperty('editorPartsPanel', True)
        parts_panel_layout = QVBoxLayout(parts_panel)
        parts_panel_layout.setContentsMargins(8, 10, 8, 8)
        parts_panel_layout.setSpacing(8)

        self.parts_table = PartsTable([
            self._t('tool_editor.table.role', 'Role'),
            self._t('tool_editor.table.part_name', 'Label'),
            self._t('tool_editor.table.code', 'Code'),
            self._t('tool_editor.table.link', 'Link'),
            self._t('tool_editor.table.group', 'Group'),
        ])
        self.parts_table.set_column_keys(['role', 'label', 'code', 'link', 'group'])
        self.parts_table.setObjectName('editorPartsTable')
        self.parts_table.setSelectionMode(PartsTable.ExtendedSelection)
        self.parts_table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.parts_table.horizontalHeader().setStretchLastSection(False)
        header = self.parts_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Interactive)
        self.parts_table.setColumnWidth(0, 90)
        self.parts_table.setColumnWidth(1, 190)
        self.parts_table.setColumnWidth(2, 230)
        self.parts_table.setColumnWidth(4, 120)
        self.parts_table.verticalHeader().setDefaultSectionSize(32)
        self.parts_table.verticalHeader().setMinimumSectionSize(28)
        self.parts_table.setMinimumHeight(320)
        self.parts_table.setColumnHidden(0, True)
        parts_panel_layout.addWidget(self.parts_table, 1)
        p_layout.addWidget(parts_panel, 1)

        parts_btn_bar = QFrame()
        parts_btn_bar.setProperty('editorButtonBar', True)
        p_btns = QHBoxLayout(parts_btn_bar)
        p_btns.setContentsMargins(2, 6, 2, 2)
        p_btns.setSpacing(8)
        self.add_part_btn = QPushButton()
        self.remove_part_btn = QPushButton()
        style_icon_action_button(
            self.add_part_btn,
            TOOL_ICONS_DIR / 'Plus_icon.svg',
            self._t('tool_editor.action.add_component', 'Add component'),
        )
        style_icon_action_button(
            self.remove_part_btn,
            TOOL_ICONS_DIR / 'remove.svg',
            self._t('tool_editor.action.remove_selected_part', 'Remove selected part'),
            danger=True,
        )
        self.part_up_btn = QPushButton()
        self.part_down_btn = QPushButton()
        style_move_arrow_button(self.part_up_btn, self._t('work_editor.tools.move_up', '▲'), self._t('tool_editor.tooltip.move_row_up', 'Move selected row up'))
        style_move_arrow_button(self.part_down_btn, self._t('work_editor.tools.move_down', '▼'), self._t('tool_editor.tooltip.move_row_down', 'Move selected row down'))
        self.pick_part_btn = self._make_arrow_button('menu_open.svg', self._t('tool_editor.tooltip.pick_additional_part', 'Pick additional part from existing tools'))
        self.group_btn = QPushButton()
        style_icon_action_button(
            self.group_btn,
            TOOL_ICONS_DIR / 'assemblies_icon.svg',
            self._t('tool_editor.action.group_parts', 'Group selected parts'),
        )
        self.group_btn.setVisible(True)
        self.group_name_edit = QLineEdit()
        self.group_name_edit.setPlaceholderText(self._t('tool_editor.placeholder.group_name', 'Group name...'))
        self.group_name_edit.setVisible(False)
        self.group_name_edit.setMinimumHeight(34)
        self.group_name_edit.setMaximumWidth(160)
        self.group_hint_label = QLabel(self._t('tool_editor.hint.press_enter_to_add', 'Press Enter to add'))
        self.group_hint_label.setVisible(False)
        self.group_hint_label.setStyleSheet('background: transparent; font-size: 12px; color: #7a8a9a; font-style: italic;')
        self.group_select_hint_label = QLabel(self._t('tool_editor.hint.select_multiple', 'Select part(s) to make a group'))
        self.group_select_hint_label.setStyleSheet('background: transparent; font-size: 12px; color: #9aabb8; font-style: italic;')
        self.add_part_btn.clicked.connect(lambda: self._add_component_row('holder'))
        self.remove_part_btn.clicked.connect(self._remove_component_row)
        self.part_up_btn.clicked.connect(lambda: self._move_component_row(-1))
        self.part_down_btn.clicked.connect(lambda: self._move_component_row(1))
        self.pick_part_btn.clicked.connect(self._pick_additional_part)
        self.group_btn.clicked.connect(self._toggle_group)
        self.group_name_edit.returnPressed.connect(self._apply_group_name)
        self.group_name_edit.installEventFilter(self)
        self.parts_table.itemSelectionChanged.connect(self._update_group_button_visibility)
        self.parts_table.itemChanged.connect(self._schedule_spare_component_refresh)
        p_btns.addWidget(self.add_part_btn)
        p_btns.addWidget(self.remove_part_btn)
        p_btns.addWidget(self.part_up_btn)
        p_btns.addWidget(self.part_down_btn)
        p_btns.addWidget(self.group_btn)
        p_btns.addWidget(self.group_name_edit)
        p_btns.addWidget(self.group_hint_label)
        p_btns.addWidget(self.group_select_hint_label)
        p_btns.addStretch(1)
        p_btns.addWidget(self.pick_part_btn)
        p_layout.addWidget(parts_btn_bar)
        self.tabs.addTab(parts_tab, self._t('tool_editor.tab.components', 'Components'))

        # -------------------------
        # SPARE PARTS TAB
        # -------------------------
        spare_tab = QWidget()
        spare_tab.setProperty('editorPageSurface', True)
        spare_tab_layout = QVBoxLayout(spare_tab)
        spare_tab_layout.setContentsMargins(18, 18, 18, 18)
        spare_tab_layout.setSpacing(8)

        spare_panel = QFrame()
        spare_panel.setProperty('editorPartsPanel', True)
        spare_panel_layout = QVBoxLayout(spare_panel)
        spare_panel_layout.setContentsMargins(8, 10, 8, 8)
        spare_panel_layout.setSpacing(8)

        self.spare_parts_table = PartsTable([
            self._t('tool_editor.table.part_name', 'Part name'),
            self._t('tool_editor.table.code', 'Code'),
            self._t('tool_editor.table.link', 'Link'),
            self._t('tool_editor.table.linked_component', 'Linked Component'),
            self._t('tool_editor.table.group', 'Group'),
        ])
        self.spare_parts_table.set_column_keys(['name', 'code', 'link', 'linked_component', 'group'])
        self.spare_parts_table.set_read_only_columns(['linked_component'])
        self.spare_parts_table.setObjectName('editorSparePartsTable')
        self.spare_parts_table.setSelectionMode(PartsTable.ExtendedSelection)
        self.spare_parts_table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.spare_parts_table.setCornerButtonEnabled(False)
        spare_header = self.spare_parts_table.horizontalHeader()
        spare_header.setStretchLastSection(False)
        spare_header.setSectionResizeMode(0, QHeaderView.Interactive)
        spare_header.setSectionResizeMode(1, QHeaderView.Interactive)
        spare_header.setSectionResizeMode(2, QHeaderView.Stretch)
        spare_header.setSectionResizeMode(3, QHeaderView.Interactive)
        spare_header.setSectionResizeMode(4, QHeaderView.Interactive)
        self.spare_parts_table.setColumnWidth(0, 190)
        self.spare_parts_table.setColumnWidth(1, 220)
        self.spare_parts_table.setColumnWidth(3, 200)
        self.spare_parts_table.setColumnWidth(4, 120)
        self.spare_parts_table.verticalHeader().setDefaultSectionSize(32)
        self.spare_parts_table.verticalHeader().setMinimumSectionSize(28)
        self.spare_parts_table.setMinimumHeight(320)
        self.spare_parts_table.setColumnHidden(4, True)
        spare_panel_layout.addWidget(self.spare_parts_table, 1)
        spare_tab_layout.addWidget(spare_panel, 1)

        spare_btn_bar = QFrame()
        spare_btn_bar.setProperty('editorButtonBar', True)
        s_btns = QHBoxLayout(spare_btn_bar)
        s_btns.setContentsMargins(2, 6, 2, 2)
        s_btns.setSpacing(8)

        self.add_spare_btn = QPushButton()
        self.remove_spare_btn = QPushButton()
        style_icon_action_button(
            self.add_spare_btn,
            TOOL_ICONS_DIR / 'Plus_icon.svg',
            self._t('tool_editor.action.add_spare_part', 'Add spare part'),
        )
        style_icon_action_button(
            self.remove_spare_btn,
            TOOL_ICONS_DIR / 'remove.svg',
            self._t('tool_editor.action.remove_selected_part', 'Remove selected part'),
            danger=True,
        )
        self.spare_up_btn = QPushButton()
        self.spare_down_btn = QPushButton()
        style_move_arrow_button(self.spare_up_btn, self._t('work_editor.tools.move_up', '▲'), self._t('tool_editor.tooltip.move_row_up', 'Move selected row up'))
        style_move_arrow_button(self.spare_down_btn, self._t('work_editor.tools.move_down', '▼'), self._t('tool_editor.tooltip.move_row_down', 'Move selected row down'))

        self.pick_spare_btn = self._make_arrow_button('menu_open.svg', self._t('tool_editor.tooltip.pick_additional_part', 'Pick additional part from existing tools'))
        self.link_spare_btn = QPushButton()
        style_icon_action_button(
            self.link_spare_btn,
            TOOL_ICONS_DIR / 'assemblies_icon.svg',
            self._t('tool_editor.action.link_spare_to_component', 'Link to selected component'),
        )
        self.spare_link_hint_label = QLabel(
            self._t(
                'tool_editor.hint.link_spares_from_table',
                'Link part(s) to components by selecting them in the table',
            )
        )
        self.spare_link_hint_label.setStyleSheet(
            'background: transparent; font-size: 12px; color: #9aabb8; font-style: italic;'
        )

        self.add_spare_btn.clicked.connect(self._add_spare_part_row)
        self.remove_spare_btn.clicked.connect(self.spare_parts_table.remove_selected_row)
        self.spare_up_btn.clicked.connect(lambda: self.spare_parts_table.move_selected_row(-1))
        self.spare_down_btn.clicked.connect(lambda: self.spare_parts_table.move_selected_row(1))
        self.pick_spare_btn.clicked.connect(self._pick_spare_part)
        self.link_spare_btn.clicked.connect(self._link_spares_to_selected_component)

        s_btns.addWidget(self.add_spare_btn)
        s_btns.addWidget(self.remove_spare_btn)
        s_btns.addWidget(self.spare_up_btn)
        s_btns.addWidget(self.spare_down_btn)
        s_btns.addWidget(self.link_spare_btn)
        s_btns.addWidget(self.spare_link_hint_label)
        s_btns.addStretch(1)
        s_btns.addWidget(self.pick_spare_btn)
        spare_tab_layout.addWidget(spare_btn_bar)
        self.tabs.addTab(spare_tab, self._t('tool_editor.tab.spare_parts', 'Spare parts'))

        # -------------------------
        # 3D MODELS TAB
        # -------------------------
        models_tab = QWidget()
        models_tab.setProperty('editorPageSurface', True)
        models_layout = QVBoxLayout(models_tab)
        models_layout.setContentsMargins(18, 18, 18, 18)
        models_layout.setSpacing(8)

        models_columns_spacing = 8
        models_bottom_left_width = 340
        models_bottom_left_box_width = 320
        models_bottom_right_width = 488

        splitter = QSplitter(Qt.Horizontal)
        splitter.setProperty('editorTransparentPanel', True)
        splitter.setHandleWidth(8)

        # Left side: table in panel frame (same structure as spare parts tab)
        models_panel = QFrame()
        models_panel.setProperty('editorPartsPanel', True)
        models_panel.setMinimumWidth(260)
        models_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        models_panel_layout = QVBoxLayout(models_panel)
        models_panel_layout.setContentsMargins(8, 10, 8, 8)
        models_panel_layout.setSpacing(0)

        self.model_table = PartsTable(['Part Name', 'STL File', 'Color'])
        self.model_table.setObjectName('editorModelsTable')
        self.model_table.setMinimumHeight(240)
        self.model_table.setMaximumHeight(420)
        self.model_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.model_table.verticalHeader().setDefaultSectionSize(44)
        self.model_table.verticalHeader().setMinimumSectionSize(28)
        self.model_table.setColumnCount(3)
        self.model_table.setHorizontalHeaderLabels([
            self._t('tool_editor.table.part_name', 'Part Name'),
            self._t('jaw_editor.field.stl_file', 'STL File'),
            self._t('tool_editor.table.color', 'Color'),
        ])
        model_header = self.model_table.horizontalHeader()
        model_header.setSectionResizeMode(0, QHeaderView.Interactive)
        model_header.setSectionResizeMode(1, QHeaderView.Stretch)
        model_header.setSectionResizeMode(2, QHeaderView.Interactive)
        model_header.setStretchLastSection(False)
        self.model_table.setColumnWidth(0, 100)
        self.model_table.setColumnWidth(1, 170)
        self.model_table.setColumnWidth(2, 70)
        self.model_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.model_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.model_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.model_table.itemChanged.connect(self._on_model_table_changed)

        models_panel_layout.addWidget(self.model_table, 0)
        models_panel_layout.addStretch(1)

        # Right side: preview panel
        preview_panel = QFrame()
        preview_panel.setProperty('editorPartsPanel', True)
        preview_panel.setMinimumWidth(300)
        preview_panel_layout = QVBoxLayout(preview_panel)
        preview_panel_layout.setContentsMargins(8, 8, 8, 8)
        preview_panel_layout.setSpacing(8)

        self.models_preview = StlPreviewWidget()
        self.models_preview.set_control_hint_text(
            self._t(
                'tool_editor.hint.rotate_pan_zoom',
                'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
            )
        )
        preview_panel_layout.addWidget(self.models_preview, 1)

        # Transform controls (visible only when preference is on)
        self._transform_frame = create_titled_section(
            self._t('tool_editor.transform.toolbar_title', 'Muunnos')
        )
        self._transform_frame.setMinimumWidth(models_bottom_right_width)
        self._transform_frame.setMaximumWidth(models_bottom_right_width)
        self._transform_frame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        _tf_layout = QVBoxLayout(self._transform_frame)
        _tf_layout.setContentsMargins(8, 4, 8, 6)
        _tf_layout.setSpacing(4)

        _mode_row = QHBoxLayout()
        _mode_row.setSpacing(0)
        _mode_row.setContentsMargins(0, 0, 0, 0)
        self._mode_toggle_btn = QPushButton('')
        self._fine_transform_btn = QPushButton('')
        self._reset_transform_btn = QPushButton()
        style_icon_action_button(
            self._mode_toggle_btn,
            TOOL_ICONS_DIR / 'move.svg',
            self._t('tool_editor.transform.move', 'SIIRRÄ'),
        )
        style_icon_action_button(
            self._fine_transform_btn,
            TOOL_ICONS_DIR / '1x.svg',
            self._t('tool_editor.transform.fine_tooltip', 'Toggle fine transform increments'),
        )
        style_icon_action_button(
            self._reset_transform_btn,
            TOOL_ICONS_DIR / 'reset.svg',
            self._t('tool_editor.transform.reset', 'NOLLAA'),
        )
        self._mode_toggle_btn.setCheckable(True)
        self._mode_toggle_btn.setChecked(True)
        self._fine_transform_btn.setCheckable(True)
        self._fine_transform_btn.setChecked(self._fine_transform_enabled)
        self._reset_transform_btn.setFixedWidth(42)
        self._mode_toggle_btn.setFixedWidth(42)
        self._fine_transform_btn.setFixedWidth(42)
        self._reset_transform_btn.setToolTip(
            self._t(
                'tool_editor.transform.reset_tooltip',
                'Left click: reset to original position. Right click: restore saved position.',
            )
        )
        self._update_mode_toggle_button_appearance()
        self._update_fine_transform_button_appearance()

        _lbl_x = QLabel('X')
        _lbl_x.setProperty('detailFieldKey', True)
        _lbl_x.setFixedWidth(16)
        _lbl_x.setAlignment(Qt.AlignCenter)

        self._transform_x = QLineEdit('0')
        self._transform_x.setFixedWidth(80)
        self._transform_x.setAlignment(Qt.AlignRight)

        _lbl_y = QLabel('Y')
        _lbl_y.setProperty('detailFieldKey', True)
        _lbl_y.setFixedWidth(16)
        _lbl_y.setAlignment(Qt.AlignCenter)

        self._transform_y = QLineEdit('0')
        self._transform_y.setFixedWidth(80)
        self._transform_y.setAlignment(Qt.AlignRight)

        _lbl_z = QLabel('Z')
        _lbl_z.setProperty('detailFieldKey', True)
        _lbl_z.setFixedWidth(16)
        _lbl_z.setAlignment(Qt.AlignCenter)

        self._transform_z = QLineEdit('0')
        self._transform_z.setFixedWidth(80)
        self._transform_z.setAlignment(Qt.AlignRight)

        _mode_row.addWidget(self._mode_toggle_btn)
        _mode_row.addSpacing(3)
        _mode_row.addWidget(self._fine_transform_btn)
        _mode_row.addSpacing(4)
        _mode_row.addWidget(_lbl_x)
        _mode_row.addWidget(self._transform_x)
        _mode_row.addSpacing(4)
        _mode_row.addWidget(_lbl_y)
        _mode_row.addWidget(self._transform_y)
        _mode_row.addSpacing(4)
        _mode_row.addWidget(_lbl_z)
        _mode_row.addWidget(self._transform_z)

        _mode_row.addSpacing(6)
        _mode_row.addWidget(self._reset_transform_btn)
        _tf_layout.addLayout(_mode_row)

        self._transform_frame.setVisible(self._assembly_transform_enabled)

        if self._assembly_transform_enabled:
            self.models_preview.set_fine_transform_enabled(self._fine_transform_enabled)
            self.models_preview.transform_changed.connect(self._on_viewer_transform_changed)
            self.models_preview.part_selected.connect(self._on_viewer_part_selected)
            self.models_preview.part_selection_changed.connect(self._on_viewer_part_selection_changed)
            self._mode_toggle_btn.clicked.connect(self._on_mode_toggle_clicked)
            self._fine_transform_btn.toggled.connect(self._on_fine_transform_toggled)
            self._reset_transform_btn.clicked.connect(self._reset_current_part_transform)
            self._transform_x.editingFinished.connect(self._apply_manual_transform)
            self._transform_y.editingFinished.connect(self._apply_manual_transform)
            self._transform_z.editingFinished.connect(self._apply_manual_transform)
            self._transform_x.returnPressed.connect(self._transform_x.editingFinished.emit)
            self._transform_y.returnPressed.connect(self._transform_y.editingFinished.emit)
            self._transform_z.returnPressed.connect(self._transform_z.editingFinished.emit)
            self.model_table.itemSelectionChanged.connect(self._on_model_table_selection_changed)
            QTimer.singleShot(0, self._update_transform_row_sizes)

        model_btn_bar = create_titled_section(
            self._t('tool_editor.models.actions_title', 'Mallien toiminnot')
        )
        model_btn_bar_layout = QVBoxLayout(model_btn_bar)
        model_btn_bar_layout.setContentsMargins(8, 4, 8, 6)
        model_btn_bar_layout.setSpacing(4)

        model_meta_row = QHBoxLayout()
        model_meta_row.setContentsMargins(0, 0, 0, 0)
        model_meta_row.setSpacing(6)

        model_btns = QHBoxLayout()
        model_btns.setContentsMargins(0, 0, 0, 0)
        model_btns.setSpacing(8)
        self.add_model_btn = QPushButton(self._t('tool_editor.action.add_model', 'ADD MODEL'))
        self.remove_model_btn = QPushButton(self._t('tool_editor.action.remove_selected_model', 'REMOVE SELECTED MODEL'))
        style_icon_action_button(
            self.add_model_btn,
            TOOL_ICONS_DIR / 'add_file.svg',
            self._t('tool_editor.action.add_model', 'Add model'),
        )
        style_icon_action_button(
            self.remove_model_btn,
            TOOL_ICONS_DIR / 'remove.svg',
            self._t('tool_editor.action.remove_selected_model', 'Remove selected model'),
            danger=True,
        )
        self.model_up_btn = QPushButton()
        self.model_down_btn = QPushButton()
        style_move_arrow_button(self.model_up_btn, self._t('work_editor.tools.move_up', '▲'), self._t('tool_editor.tooltip.move_row_up', 'Move selected row up'))
        style_move_arrow_button(self.model_down_btn, self._t('work_editor.tools.move_down', '▼'), self._t('tool_editor.tooltip.move_row_down', 'Move selected row down'))
        self.add_model_btn.clicked.connect(self._add_model_row)
        self.remove_model_btn.clicked.connect(self._remove_model_row)
        self.model_up_btn.clicked.connect(lambda: self._move_model_row(-1))
        self.model_down_btn.clicked.connect(lambda: self._move_model_row(1))
        self.edit_measurements_btn = QPushButton('')
        style_icon_action_button(
            self.edit_measurements_btn,
            TOOL_ICONS_DIR / 'measure.svg',
            self._t('tool_editor.measurements.open_editor', 'Edit measurements'),
        )
        self.edit_measurements_btn.clicked.connect(self._open_measurement_editor)
        self.measurement_summary_label = QLabel()
        self.measurement_summary_label.setProperty('detailHint', True)
        self.measurement_summary_label.setStyleSheet(
            'background: transparent; color: #6b7b8e; font-size: 11px;'
        )
        self.measurement_summary_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        model_meta_row.addWidget(self.measurement_summary_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        model_meta_row.addStretch(1)
        model_btn_bar_layout.addLayout(model_meta_row)
        model_btns.addWidget(self.add_model_btn)
        model_btns.addWidget(self.remove_model_btn)
        model_btns.addWidget(self.model_up_btn)
        model_btns.addWidget(self.model_down_btn)
        model_btns.addWidget(self.edit_measurements_btn)
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
        bottom_row.setSpacing(models_columns_spacing)
        left_toolbar_host = QWidget()
        left_toolbar_host.setObjectName('leftToolbarHost')
        left_toolbar_host.setFixedWidth(models_bottom_left_width)
        left_toolbar_host.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        left_toolbar_host.setAutoFillBackground(False)
        left_toolbar_host.setStyleSheet(
            '#leftToolbarHost { background: transparent; border: none; }'
        )
        left_toolbar_host_layout = QHBoxLayout(left_toolbar_host)
        left_toolbar_host_layout.setContentsMargins(0, 0, 0, 0)
        left_toolbar_host_layout.setSpacing(0)
        model_btn_bar.setFixedWidth(models_bottom_left_box_width)
        left_toolbar_host_layout.addStretch(1)
        left_toolbar_host_layout.addWidget(model_btn_bar, 0, Qt.AlignTop)
        left_toolbar_host_layout.addStretch(1)
        bottom_row.addWidget(left_toolbar_host, 0, Qt.AlignLeft | Qt.AlignTop)
        bottom_row.addStretch(1)
        bottom_row.addWidget(self._transform_frame, 0, Qt.AlignRight | Qt.AlignTop)
        models_layout.addLayout(bottom_row, 0)
        self._transform_frame.setVisible(self._assembly_transform_enabled)

        self.tabs.addTab(models_tab, self._t('tool_editor.tab.models', '3D models'))
        self._update_measurement_summary_label()

        # -------------------------
        # BOTTOM BUTTONS
        # -------------------------
        self._dialog_buttons = create_dialog_buttons(
            self,
            save_text=self._t('tool_editor.action.save_tool', 'SAVE TOOL'),
            cancel_text=self._t('common.cancel', 'Cancel').upper(),
            on_save=self.accept,
            on_cancel=self.reject,
        )
        self._save_btn = self._dialog_buttons.button(QDialogButtonBox.Save)

        root.addWidget(self._dialog_buttons)

        apply_secondary_button_theme(self, self._save_btn)

        QApplication.instance().installEventFilter(self)

        for le in [
            self.tool_id, self.description, self.geom_x, self.geom_z, self.radius,
            self.nose_corner_radius, self.holder_code, self.holder_link, self.holder_add_element,
            self.holder_add_element_link, self.cutting_code, self.cutting_link,
            self.cutting_add_element, self.cutting_add_element_link,
            self.drill_nose_angle, self.mill_cutting_edges, self.notes, self.default_pot
        ]:
            le.returnPressed.connect(le.clearFocus)

        self.tool_id.textChanged.connect(self._update_general_header)
        self.description.textChanged.connect(self._update_general_header)
        self.tool_type.currentTextChanged.connect(self._update_general_header)
        self._update_general_header()

    def eventFilter(self, obj, event):
        if obj is self.group_name_edit and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._apply_group_name()
                return True  # fully consume — prevent dialog default button from firing
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            focused = QApplication.focusWidget()
            if isinstance(focused, QLineEdit) and self.isAncestorOf(focused):
                focused.clearFocus()
                return True
        if obj is getattr(self, '_reset_transform_btn', None):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.RightButton:
                self._reset_current_part_transform(target='saved')
                return True
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.RightButton:
                return True
        if event.type() == QEvent.MouseButtonPress:
            clear_focused_dropdown_on_outside_click(obj, self)
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)

    def _build_edit_field(self, title: str, editor: QWidget, key_label: QLabel | None = None) -> QFrame:
        frame = QFrame()
        frame.setProperty('editorFieldCard', True)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)
        label = key_label if key_label is not None else QLabel(title)
        label.setProperty('detailFieldKey', True)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        label.setMinimumWidth(200)
        label.setMaximumWidth(200)
        label.mousePressEvent = lambda event, w=editor: self._focus_editor(w)
        layout.addWidget(label, 0)
        layout.addWidget(editor, 1)
        frame._field_label = label
        return frame

    def _build_field_group(self, fields: list) -> QFrame:
        group = QFrame()
        group.setProperty('editorFieldGroup', True)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        for f in fields:
            layout.addWidget(f)
        return group

    def _focus_editor(self, widget: QWidget):
        if isinstance(widget, QLineEdit):
            widget.setFocus()
            widget.selectAll()
            return
        if isinstance(widget, QComboBox):
            widget.setFocus()
            return
        if isinstance(widget, QPushButton):
            widget.setFocus()
            return
        for child in widget.findChildren(QLineEdit):
            child.setFocus()
            child.selectAll()
            return
        for child in widget.findChildren(QComboBox):
            child.setFocus()
            return
        for child in widget.findChildren(QPushButton):
            child.setFocus()
            return

    def _swap_field_pair(self, hide_field: QFrame, show_field: QFrame):
        hide_field.setVisible(False)
        show_field.setVisible(True)

    def _style_combo(self, combo: QComboBox):
        apply_shared_dropdown_style(combo)
        self._configure_combo_popup(combo, max_rows=8, row_height=40)

    def _configure_combo_popup(self, combo: QComboBox, max_rows: int = 8, row_height: int = 40):
        view = combo.view()
        if view is None:
            return
        max_height = max_rows * row_height
        view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setMinimumHeight(0)
        view.setMaximumHeight(max_height)
        popup = view.window()
        popup.setMinimumHeight(0)
        popup.setMaximumHeight(max_height + 8)

    def _set_tool_head_value(self, head: str):
        normalized = (head or 'HEAD1').strip().upper()
        if normalized not in {'HEAD1', 'HEAD2'}:
            normalized = 'HEAD1'
        is_head2 = normalized == 'HEAD2'
        self.tool_head.blockSignals(True)
        self.tool_head.setChecked(is_head2)
        self.tool_head.setText(self._localized_tool_head('HEAD2' if is_head2 else 'HEAD1'))
        self.tool_head.blockSignals(False)

    def _toggle_tool_head(self, checked: bool):
        self.tool_head.setText(self._localized_tool_head('HEAD2' if checked else 'HEAD1'))

    def _get_tool_head_value(self) -> str:
        return 'HEAD2' if self.tool_head.isChecked() else 'HEAD1'

    def _style_general_editor(self, editor: QWidget):
        pass

    def _make_arrow_button(self, icon_name: str, tooltip: str) -> QPushButton:
        icon_path = TOOL_ICONS_DIR / icon_name
        return make_arrow_button(icon_path, tooltip)

    def _style_panel_action_button(self, btn: QPushButton):
        style_panel_action_button(btn)

    def _build_picker_row(self, editor: QLineEdit, handler, tooltip: str) -> QWidget:
        icon_path = TOOL_ICONS_DIR / 'menu_open.svg'
        return build_picker_row(editor, handler, tooltip, icon_path)

    def _get_tool_service(self):
        if self.tool_service is not None:
            return self.tool_service
        parent = self.parent()
        return getattr(parent, 'tool_service', None)

    def _iter_known_components(self) -> list[dict]:
        service = self._get_tool_service()
        if service is None:
            return []

        try:
            tools = service.list_tools()
        except Exception:
            return []

        entries = []

        def add_entry(kind: str, name: str, code: str, link: str, source: str):
            code = (code or '').strip()
            link = (link or '').strip()
            if not code:
                return
            entries.append({
                'kind': kind,
                'name': (name or kind.title()).strip(),
                'code': code,
                'link': link,
                'source': source,
            })

        for tool in tools:
            source = (tool.get('id', '') or '').strip()

            component_items = tool.get('component_items', [])
            if isinstance(component_items, str):
                try:
                    component_items = json.loads(component_items or '[]')
                except Exception:
                    component_items = []

            if isinstance(component_items, list) and component_items:
                for item in component_items:
                    if not isinstance(item, dict):
                        continue
                    role = (item.get('role') or '').strip().lower()
                    if role not in {'holder', 'cutting', 'support'}:
                        continue
                    add_entry(
                        role,
                        item.get('label', self._t('tool_library.field.part', 'Part')),
                        item.get('code', ''),
                        item.get('link', ''),
                        source,
                    )
            else:
                add_entry('holder', self._t('tool_library.field.holder', 'Holder'), tool.get('holder_code', ''), tool.get('holder_link', ''), source)
                add_entry('holder-extra', self._t('tool_library.field.add_element', 'Add. Element'), tool.get('holder_add_element', ''), tool.get('holder_add_element_link', ''), source)
                cutting_name = (tool.get('cutting_type', 'Insert') or 'Insert').strip()
                add_entry('cutting', self._localized_cutting_type(cutting_name), tool.get('cutting_code', ''), tool.get('cutting_link', ''), source)
                add_entry(
                    'cutting-extra',
                    self._t('tool_library.field.add_cutting', 'Add. {cutting_type}', cutting_type=self._localized_cutting_type(cutting_name)),
                    tool.get('cutting_add_element', ''),
                    tool.get('cutting_add_element_link', ''),
                    source,
                )

            support_parts = tool.get('support_parts', [])
            if isinstance(support_parts, str):
                try:
                    support_parts = json.loads(support_parts or '[]')
                except Exception:
                    support_parts = []
            if isinstance(support_parts, list):
                for part in support_parts:
                    if isinstance(part, str):
                        try:
                            part = json.loads(part)
                        except Exception:
                            part = {'name': part, 'code': '', 'link': ''}
                    if not isinstance(part, dict):
                        continue
                    add_entry(
                        'support',
                        part.get('name', self._t('tool_library.field.part', 'Part')),
                        part.get('code', ''),
                        part.get('link', ''),
                        source,
                    )

        dedup = {}
        for entry in entries:
            key = (
                entry.get('kind', ''),
                entry.get('name', ''),
                entry.get('code', ''),
                entry.get('link', ''),
                entry.get('source', ''),
            )
            if key not in dedup:
                dedup[key] = entry
        return list(dedup.values())

    def _open_component_picker(self, title: str, allowed_kinds: tuple[str, ...]) -> dict | None:
        entries = [e for e in self._iter_known_components() if e.get('kind') in allowed_kinds]
        if not entries:
            QMessageBox.information(
                self,
                self._t('tool_editor.component.picker_title', 'Component picker'),
                self._t('tool_editor.component.none_found', 'No matching components found in existing tools.'),
            )
            return None

        dlg = ComponentPickerDialog(title, entries, self, translate=self._t)
        if dlg.exec() != QDialog.Accepted:
            return None
        return dlg.selected_entry()

    def _sync_component_pick_to_table(self, role: str, name: str, code: str, link: str):
        """Update the first matching-role row in parts_table, or insert a new one."""
        for row in range(self.parts_table.rowCount()):
            row_data = self.parts_table.row_dict(row)
            if (row_data.get('role') or '').strip().lower() == role:
                self.parts_table.set_cell_text(row, 'label', name)
                self.parts_table.set_cell_text(row, 'code', code)
                self.parts_table.set_cell_text(row, 'link', link)
                return
        self.parts_table.add_row_dict({'role': role, 'label': name, 'code': code, 'link': link, 'group': ''})
        self._schedule_spare_component_refresh()

    def _pick_holder_component(self):
        entry = self._open_component_picker(self._t('tool_editor.component.select_holder', 'Select holder'), ('holder', 'holder-extra'))
        if not entry:
            return
        code = entry.get('code', '')
        link = entry.get('link', '')
        name = entry.get('name', self._t('tool_library.field.holder', 'Holder'))
        self.holder_code.setText(code)
        self.holder_link.setText(link)
        self._sync_component_pick_to_table('holder', name, code, link)

    def _pick_cutting_component(self):
        entry = self._open_component_picker(self._t('tool_editor.component.select_cutting', 'Select cutting component'), ('cutting', 'cutting-extra'))
        if not entry:
            return
        code = entry.get('code', '')
        link = entry.get('link', '')
        name = entry.get('name', self._localized_cutting_type('Insert'))
        self.cutting_code.setText(code)
        self.cutting_link.setText(link)
        self._sync_component_pick_to_table('cutting', name, code, link)

    def _pick_additional_part(self):
        entry = self._open_component_picker(
            self._t('tool_editor.component.select_additional', 'Select component'),
            ('holder', 'holder-extra', 'cutting', 'cutting-extra'),
        )
        if not entry:
            return
        kind = (entry.get('kind') or 'holder').strip().lower()
        if kind.startswith('holder'):
            role = 'holder'
        elif kind.startswith('cutting'):
            role = 'cutting'
        else:
            role = 'holder'
        self.parts_table.add_row_dict({
            'role': role,
            'label': entry.get('name', self._t('tool_library.field.part', 'Part')),
            'code': entry.get('code', ''),
            'link': entry.get('link', ''),
            'group': '',
        })
        self._schedule_spare_component_refresh()

    def _pick_spare_part(self):
        entry = self._open_component_picker(
            self._t('tool_editor.component.select_additional', 'Select additional part'),
            ('support',),
        )
        if not entry:
            return
        self._add_spare_part_row(
            {
                'name': entry.get('name', self._t('tool_library.field.part', 'Part')),
                'code': entry.get('code', ''),
                'link': entry.get('link', ''),
                'component_key': '',
                'group': '',
            }
        )

    def _component_dropdown_values(self):
        values = []
        seen = set()
        for entry in self.parts_table.row_dicts():
            role = (entry.get('role') or 'component').strip().lower()
            label = (entry.get('label') or '').strip()
            code = (entry.get('code') or '').strip()
            if not code:
                continue
            key = f"{role}:{code}"
            if key in seen:
                continue
            seen.add(key)
            display = f"{label} ({code})" if label else code
            values.append((display, key))
        return values

    def _component_display_for_key(self, key: str) -> str:
        """Return a user-friendly display string for a component_key like 'holder:CODE'."""
        key = (key or '').strip()
        if not key:
            return '-'
        for entry in self.parts_table.row_dicts():
            role = (entry.get('role') or 'component').strip().lower()
            label = (entry.get('label') or '').strip()
            code = (entry.get('code') or '').strip()
            if not code:
                continue
            if f"{role}:{code}" == key:
                return f"{label} ({code})" if label else code
        # Fallback: strip the role prefix for readability
        if ':' in key:
            return key.split(':', 1)[1]
        return key

    def _get_spare_component_key(self, row: int) -> str:
        return str(self.spare_parts_table.cell_user_data(row, 'linked_component', Qt.UserRole, '') or '').strip()

    def _set_spare_component_key(self, row: int, current_key: str = ''):
        current_key = (current_key or '').strip()
        # Keep linked-component column as plain item data to avoid item/widget desync.
        existing_widget = self.spare_parts_table.cellWidget(row, 3)
        if existing_widget is not None:
            self.spare_parts_table.removeCellWidget(row, 3)

        self.spare_parts_table.set_cell_text(row, 'linked_component', self._component_display_for_key(current_key))
        self.spare_parts_table.set_cell_user_data(row, 'linked_component', Qt.UserRole, current_key)

    def _schedule_spare_component_refresh(self, *_args):
        if hasattr(self, '_spare_refresh_timer'):
            self._spare_refresh_timer.start()

    def _refresh_spare_component_dropdowns(self):
        options = self._component_dropdown_values()
        option_map = {key: display for display, key in options}
        for row in range(self.spare_parts_table.rowCount()):
            current_key = self._get_spare_component_key(row)
            display = option_map.get(current_key, self._component_display_for_key(current_key))
            self.spare_parts_table.set_cell_text(row, 'linked_component', display)
            self.spare_parts_table.set_cell_user_data(row, 'linked_component', Qt.UserRole, current_key)

    def _add_spare_part_row(self, part: dict | None = None):
        part = part or {}
        self.spare_parts_table.add_row_dict(
            {
                'name': (part.get('name') or '').strip(),
                'code': (part.get('code') or '').strip(),
                'link': (part.get('link') or '').strip(),
                'linked_component': '',
                'group': (part.get('group') or '').strip(),
            }
        )
        row = self.spare_parts_table.rowCount() - 1
        self._set_spare_component_key(row, (part.get('component_key') or '').strip())

    def _remove_component_row(self):
        self.parts_table.remove_selected_row()
        self._schedule_spare_component_refresh()

    def _move_component_row(self, delta: int):
        self.parts_table.move_selected_row(delta)
        self._schedule_spare_component_refresh()

    def _selected_component_ref(self) -> str:
        row = self.parts_table.currentRow()
        if row < 0:
            return ''
        entry = self.parts_table.row_dict(row)
        role = (entry.get('role') or 'component').strip().lower()
        code = (entry.get('code') or '').strip()
        if not code:
            return ''
        return f"{role}:{code}"

    def _link_spares_to_selected_component(self):
        options = self._component_dropdown_values()
        if not options:
            QMessageBox.information(
                self,
                self._t('tool_editor.component.picker_title', 'Component picker'),
                self._t('tool_editor.component.no_components', 'No components defined. Add components in the Components tab first.'),
            )
            return

        selected_rows = sorted(set(idx.row() for idx in self.spare_parts_table.selectedIndexes()))
        if not selected_rows:
            QMessageBox.information(
                self,
                self._t('tool_editor.component.picker_title', 'Component picker'),
                self._t('tool_editor.component.select_spare_first', 'Select one or more spare part rows first.'),
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(self._t('tool_editor.component.picker_title', 'Component picker'))
        dlg.setProperty('workEditorDialog', True)
        dlg.resize(460, 0)
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(18, 18, 18, 18)
        dlg_layout.setSpacing(12)

        prompt = QLabel(self._t('tool_editor.component.pick_component', 'Link selected spare parts to:'))
        prompt.setProperty('detailSectionTitle', True)
        dlg_layout.addWidget(prompt)

        combo = QComboBox()
        for display, key in options:
            combo.addItem(display, key)

        preselected = self._selected_component_ref()
        if preselected:
            for idx in range(combo.count()):
                if str(combo.itemData(idx) or '').strip() == preselected:
                    combo.setCurrentIndex(idx)
                    break

        self._style_combo(combo)
        combo.setMinimumHeight(28)
        combo.setMaximumHeight(28)
        combo.setMaxVisibleItems(8)
        self._configure_combo_popup(combo, max_rows=8, row_height=40)

        combo_field = QFrame()
        combo_field.setProperty('editorFieldCard', True)
        combo_field_layout = QHBoxLayout(combo_field)
        combo_field_layout.setContentsMargins(2, 2, 2, 2)
        combo_field_layout.setSpacing(0)
        combo_field_layout.addWidget(combo, 1)
        dlg_layout.addWidget(combo_field)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = btn_box.button(QDialogButtonBox.Ok)
        cancel_btn = btn_box.button(QDialogButtonBox.Cancel)
        if ok_btn is not None:
            ok_btn.setProperty('panelActionButton', True)
            ok_btn.setProperty('primaryAction', True)
            ok_btn.setText(self._t('common.ok', 'OK'))
        if cancel_btn is not None:
            cancel_btn.setProperty('panelActionButton', True)
            cancel_btn.setProperty('secondaryAction', True)
            cancel_btn.setText(self._t('common.cancel', 'Cancel'))

        apply_secondary_button_theme(dlg, ok_btn)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        dlg_layout.addWidget(btn_box)

        if dlg.exec() != QDialog.Accepted:
            return

        component_ref = str(combo.currentData() or '').strip()
        if not component_ref:
            return

        for row in selected_rows:
            self._set_spare_component_key(row, component_ref)
        self._schedule_spare_component_refresh()

    def _add_component_row(self, role: str = 'support'):
        normalized_role = (role or 'support').strip().lower()
        if normalized_role not in {'holder', 'cutting', 'support'}:
            normalized_role = 'support'
        default_label = self._t('tool_library.field.part', 'Part')
        if normalized_role == 'holder':
            default_label = self._t('tool_library.field.holder', 'Holder')
        elif normalized_role == 'cutting':
            default_label = self._localized_cutting_type('Insert')
        self.parts_table.add_row_dict(
            {
                'role': normalized_role,
                'label': default_label,
                'code': '',
                'link': '',
                'group': '',
            }
        )
        self._schedule_spare_component_refresh()

    def _update_group_button_visibility(self):
        if self.group_name_edit.isVisible():
            self.group_btn.setVisible(True)
            self.group_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / 'assemblies_icon.svg')))
            self.group_btn.setToolTip(self._t('tool_editor.action.group_parts', 'Group selected parts'))
            self.group_btn.setProperty('dangerAction', False)
            self.group_hint_label.setVisible(True)
            self._set_group_select_hint_visible(False)
            self.group_btn.style().unpolish(self.group_btn)
            self.group_btn.style().polish(self.group_btn)
            return

        selected_rows = self._selected_component_rows()
        if len(selected_rows) < 1:
            self.group_btn.setVisible(True)
            self.group_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / 'assemblies_icon.svg')))
            self.group_btn.setToolTip(self._t('tool_editor.action.group_parts', 'Group selected parts'))
            self.group_btn.setProperty('dangerAction', False)
            self.group_name_edit.setVisible(False)
            self.group_hint_label.setVisible(False)
            self._set_group_select_hint_visible(True)
            self._group_target_rows = []
            self.group_btn.style().unpolish(self.group_btn)
            self.group_btn.style().polish(self.group_btn)
            return

        self.group_btn.setVisible(True)
        self._set_group_select_hint_visible(True)

        groups = set()
        for row in selected_rows:
            groups.add(self.parts_table.cell_text(row, 'group'))

        non_empty = groups - {''}
        all_same_group = bool(non_empty) and len(non_empty) == 1 and '' not in groups

        if all_same_group:
            self.group_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / 'delete.svg')))
            self.group_btn.setToolTip(self._t('tool_editor.action.remove_group', 'Remove group from selected parts'))
            self.group_btn.setProperty('dangerAction', True)
            self.group_name_edit.setVisible(False)
            self.group_hint_label.setVisible(False)
        else:
            self.group_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / 'assemblies_icon.svg')))
            self.group_btn.setToolTip(self._t('tool_editor.action.group_parts', 'Group selected parts'))
            self.group_btn.setProperty('dangerAction', False)

        self.group_btn.style().unpolish(self.group_btn)
        self.group_btn.style().polish(self.group_btn)

    def _set_group_select_hint_visible(self, visible: bool):
        self.group_select_hint_label.setVisible(bool(visible) and not self.group_name_edit.isVisible())

    def _selected_component_rows(self) -> list[int]:
        selected = sorted(set(idx.row() for idx in self.parts_table.selectedIndexes()))
        if selected:
            return selected
        row = self.parts_table.currentRow()
        return [row] if row >= 0 else []

    def _toggle_group(self):
        # If name editor is already open, clicking the same button should apply.
        if self.group_name_edit.isVisible():
            self._apply_group_name()
            return

        selected_rows = self._selected_component_rows()
        if not selected_rows:
            return

        self._group_target_rows = list(selected_rows)

        groups = set()
        for row in selected_rows:
            groups.add(self.parts_table.cell_text(row, 'group'))

        non_empty = groups - {''}
        all_same_group = bool(non_empty) and len(non_empty) == 1 and '' not in groups

        if all_same_group:
            for row in selected_rows:
                self.parts_table.set_cell_text(row, 'group', '')
            self.group_name_edit.setVisible(False)
            self.group_hint_label.setVisible(False)
            self._set_group_select_hint_visible(True)
            self._group_target_rows = []
            self._update_group_button_visibility()
        else:
            self.group_name_edit.setVisible(True)
            self.group_hint_label.setVisible(True)
            self._set_group_select_hint_visible(False)
            self.group_name_edit.clear()
            self.group_name_edit.setFocus()

    def _apply_group_name(self):
        name = self.group_name_edit.text().strip()

        target_rows = self._selected_component_rows()
        if not target_rows:
            target_rows = [
                row
                for row in self._group_target_rows
                if 0 <= row < self.parts_table.rowCount()
            ]

        if not name:
            self.group_name_edit.setVisible(False)
            self.group_hint_label.setVisible(False)
            self._set_group_select_hint_visible(True)
            self._group_target_rows = []
            return

        if not target_rows:
            self.group_name_edit.setVisible(False)
            self.group_hint_label.setVisible(False)
            self._set_group_select_hint_visible(True)
            self._group_target_rows = []
            return

        for row in target_rows:
            self.parts_table.set_cell_text(row, 'group', name)

        self.group_name_edit.setVisible(False)
        self.group_hint_label.setVisible(False)
        self._set_group_select_hint_visible(True)
        self._group_target_rows = []
        self._update_group_button_visibility()

    def _reflow_general_fields(self, force: bool = False):
        pass  # Field groups handle their own layout

    def _update_general_header(self):
        if not hasattr(self, 'editor_header_title'):
            return
        description = self.description.text().strip()
        tool_id = self.tool_id.text().strip()
        tool_type = self.tool_type.currentText().strip()
        self.editor_header_title.setText(description or self._t('tool_editor.header.new_tool', 'New tool'))
        self.editor_header_id.setText(tool_id)
        self.editor_type_badge.setText(tool_type)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_general_fields()
        self._update_transform_row_sizes()
        self._ensure_on_screen()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._ensure_on_screen()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_transform_row_sizes()
        self._ensure_on_screen()

    def _ensure_on_screen(self):
        if self._clamping_screen_bounds:
            return
        # Keep the dialog fully within the screen's available area (above taskbar/dock).
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or self.screen()
        if screen is None:
            return
        self._clamping_screen_bounds = True
        try:
            available = screen.availableGeometry()
            geom = self.frameGeometry()

            # Convert available frame-space into client-size limits.
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

    # -------------------------
    # MODEL TAB HELPERS
    # -------------------------
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
        # Use a minimal inset so the swatch fills the cell while keeping a small edge gap.
        container = QWidget()
        container.setStyleSheet('background: transparent;')
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        c_layout = QHBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)

        btn = QPushButton("")
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
        if chosen is None:
            return
        if not chosen.isValid():
            return
        color_hex = chosen.name()
        self._set_color_button(row, color_hex)
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

        if not color_hex:
            color_hex = self._default_color_for_part_name(name)

        self._set_color_button(row, color_hex)

        self.model_table.blockSignals(False)

    def _guess_part_name_from_file(self, file_path: str) -> str:
        import os
        base = os.path.splitext(os.path.basename(file_path))[0]
        pretty = base.replace('_', ' ').replace('-', ' ').strip()
        return pretty.title() if pretty else self._t('tool_editor.model.default_name', 'Model')

    def _tools_models_root(self):
        tools_models_root, _ = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            JAW_MODELS_ROOT_DEFAULT,
        )
        tools_models_root.mkdir(parents=True, exist_ok=True)
        return tools_models_root

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
                str(self._tools_models_root()),
                self._t('jaw_editor.dialog.stl_filter', 'STL Files (*.stl)')
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
        self._refresh_measurement_part_dropdowns()
        self._refresh_models_preview()

    def _browse_model_file_for_row(self, row: int):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._t('tool_editor.dialog.select_stl_model', 'Select STL model'),
            str(self._tools_models_root()),
            self._t('jaw_editor.dialog.stl_filter', 'STL Files (*.stl)')
        )
        if not file_path:
            return

        name_item = self.model_table.item(row, 0)
        file_item = self.model_table.item(row, 1)

        if file_item is None:
            file_item = QTableWidgetItem()
            self.model_table.setItem(row, 1, file_item)

        file_item.setData(Qt.UserRole, file_path)
        file_item.setText(self._display_model_path(file_path))

        if name_item is None or not name_item.text().strip():
            if name_item is None:
                name_item = QTableWidgetItem()
                self.model_table.setItem(row, 0, name_item)
            name_item.setText(self._guess_part_name_from_file(file_path))

        self._refresh_models_preview()


    def _remove_model_row(self):
        row = self.model_table.currentRow()
        if row >= 0:
            self.model_table.removeRow(row)
            self._refresh_measurement_part_dropdowns()
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
        self._refresh_measurement_part_dropdowns()

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

        reordered_rows = [entry['data'] for entry in rows_with_index]
        self._restore_model_rows(reordered_rows, selected_row=target)

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
                auto_color = self._default_color_for_part_name(item.text().strip())
                self._set_color_button(row, auto_color)
            self._refresh_measurement_part_dropdowns()
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

    def _refresh_models_preview(self):
        if self._suspend_preview_refresh:
            return

        parts = self._model_table_to_parts()

        if not parts:
            if hasattr(self.models_preview, 'clear'):
                self.models_preview.clear()
            return

        if hasattr(self.models_preview, 'load_parts'):
            self.models_preview.load_parts(parts)
        elif hasattr(self.models_preview, 'load_stl'):
            # temporary fallback for current single-model preview
            first_existing = next((p.get('file') for p in parts if p.get('file')), None)
            self.models_preview.load_stl(first_existing)

        if hasattr(self.models_preview, 'set_measurement_overlays'):
            self.models_preview.set_measurement_overlays([])
        if hasattr(self.models_preview, 'set_measurements_visible'):
            self.models_preview.set_measurements_visible(False)
        if hasattr(self.models_preview, 'set_measurement_drag_enabled'):
            self.models_preview.set_measurement_drag_enabled(False)

        if self._assembly_transform_enabled:
            self.models_preview.set_transform_edit_enabled(True)

    def _empty_measurement_editor_state(self):
        return {
            'distance_measurements': [],
            'diameter_measurements': [],
            'radius_measurements': [],
            'angle_measurements': [],
        }

    @staticmethod
    def _normalize_xyz_text(value) -> str:
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            try:
                x = float(value[0])
                y = float(value[1])
                z = float(value[2])
                if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                    return ''
                return f"{x:.4g}, {y:.4g}, {z:.4g}"
            except Exception:
                return ''

        text = str(value or '').strip()
        if not text:
            return ''

        text = (
            text.replace('[', ' ')
            .replace(']', ' ')
            .replace('(', ' ')
            .replace(')', ' ')
            .replace(';', ',')
        )
        parts = [p.strip() for p in text.split(',') if p.strip()]
        if len(parts) < 3:
            return ''
        try:
            x = float(parts[0])
            y = float(parts[1])
            z = float(parts[2])
        except Exception:
            return ''
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            return ''
        return f"{x:.4g}, {y:.4g}, {z:.4g}"

    @staticmethod
    def _normalize_float_value(value, default: float = 0.0) -> float:
        try:
            numeric = float(str(value).strip().replace(',', '.'))
        except Exception:
            return float(default)
        return numeric if math.isfinite(numeric) else float(default)

    @staticmethod
    def _normalize_distance_space(part_name, part_index, point_space) -> str:
        has_part_ref = bool(str(part_name or '').strip())
        if not has_part_ref:
            try:
                has_part_ref = int(part_index) >= 0
            except Exception:
                has_part_ref = False
        normalized = str(point_space or '').strip().lower()
        if normalized not in {'local', 'world'}:
            return 'local' if has_part_ref else 'world'
        if normalized == 'world' and has_part_ref:
            # Legacy migration: part-anchored points should remain local.
            return 'local'
        return normalized

    def _normalize_measurement_editor_state(self, tool_data):
        normalized = self._empty_measurement_editor_state()
        if not isinstance(tool_data, dict):
            return normalized

        for key in normalized:
            values = tool_data.get(key, [])
            if isinstance(values, list):
                normalized[key] = [dict(item) for item in values if isinstance(item, dict)]

        return normalized

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

        self._measurement_editor_state = self._normalize_measurement_editor_state(
            dialog.get_measurements()
        )
        self._update_measurement_summary_label()
        self._refresh_models_preview()

    def _is_assembly_transform_enabled(self):
        try:
            with open(SHARED_UI_PREFERENCES_PATH, 'r') as f:
                prefs = json.load(f)
            return bool(prefs.get('enable_assembly_transform', False))
        except Exception:
            return False

    def _on_viewer_transform_changed(self, index: int, transform: dict):
        self._part_transforms[index] = self._compact_transform_dict(
            self._normalized_transform_dict(transform)
        )
        if index in self._selected_part_indices:
            self._refresh_transform_selection_state()

    def _on_viewer_part_selected(self, index: int):
        self._selected_part_indices = [index] if index >= 0 else []
        self._selected_part_index = index
        self._refresh_transform_selection_state()
        self._sync_model_table_selection()
        self._request_preview_transform_snapshot(refresh_selection=True)

    def _on_viewer_part_selection_changed(self, indices: list[int]):
        normalized = [idx for idx in indices if isinstance(idx, int) and idx >= 0]
        self._selected_part_indices = normalized
        self._selected_part_index = normalized[-1] if normalized else -1
        self._refresh_transform_selection_state()
        self._sync_model_table_selection()
        self._request_preview_transform_snapshot(refresh_selection=True)

    def _sync_model_table_selection(self):
        if not hasattr(self, 'model_table'):
            return
        selection_model = self.model_table.selectionModel()
        if selection_model is None:
            return
        selection_model.blockSignals(True)
        self.model_table.blockSignals(True)
        selection_model.clearSelection()
        for index in self._selected_part_indices:
            model_index = self.model_table.model().index(index, 0)
            if not model_index.isValid():
                continue
            selection_model.select(
                model_index,
                QItemSelectionModel.Select | QItemSelectionModel.Rows,
            )
        if self._selected_part_index >= 0:
            current_index = self.model_table.model().index(self._selected_part_index, 0)
            if current_index.isValid():
                selection_model.setCurrentIndex(current_index, QItemSelectionModel.NoUpdate)
        self.model_table.blockSignals(False)
        selection_model.blockSignals(False)

    @staticmethod
    def _normalized_transform_dict(transform: dict | None) -> dict:
        src = transform if isinstance(transform, dict) else {}
        return {
            'x': float(src.get('x', 0) or 0),
            'y': float(src.get('y', 0) or 0),
            'z': float(src.get('z', 0) or 0),
            'rx': float(src.get('rx', 0) or 0),
            'ry': float(src.get('ry', 0) or 0),
            'rz': float(src.get('rz', 0) or 0),
        }

    def _saved_transform_for_index(self, index: int) -> dict:
        return self._normalized_transform_dict(self._saved_part_transforms.get(index, {}))

    def _display_transform_for_index(self, index: int, transform: dict) -> dict:
        _ = index  # keep index arg for future per-part display modes
        return self._normalized_transform_dict(transform)

    @staticmethod
    def _compact_transform_dict(transform: dict) -> dict:
        compact = {}
        for key in ('x', 'y', 'z', 'rx', 'ry', 'rz'):
            value = float(transform.get(key, 0) or 0)
            if abs(value) > 1e-9:
                compact[key] = value
        return compact

    def _all_part_transforms_payload(self) -> list[dict]:
        payload = []
        for i in range(self.model_table.rowCount()):
            payload.append(self._normalized_transform_dict(self._part_transforms.get(i, {})))
        return payload

    def _apply_preview_transforms_snapshot(self, snapshot, *, refresh_selection: bool = False) -> bool:
        if not isinstance(snapshot, list):
            return False
        if len(snapshot) <= 0:
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
            compact = self._compact_transform_dict(self._normalized_transform_dict(raw))
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
                lambda snapshot: self._apply_preview_transforms_snapshot(
                    snapshot,
                    refresh_selection=refresh_selection,
                )
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
            if hasattr(self, 'models_preview'):
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
            if hasattr(self, 'models_preview'):
                self.models_preview.set_selection_caption(name or f'Part {index + 1}')
            t = self._part_transforms.get(index, {})
            self._update_transform_fields(t, index=index)
            return

        if hasattr(self, 'models_preview'):
            self.models_preview.set_selection_caption(
                self._t(
                    'tool_editor.preview.selection_count',
                    '{count} models selected',
                    count=count,
                )
            )
        t = self._part_transforms.get(self._selected_part_index, {})
        self._update_transform_fields(t, index=self._selected_part_index)

    def _update_transform_fields(self, t: dict, index: int | None = None):
        idx = self._selected_part_index if index is None else int(index)
        view_t = self._display_transform_for_index(idx, t)
        if self._current_transform_mode == 'translate':
            self._transform_x.setText(str(view_t.get('x', 0)))
            self._transform_y.setText(str(view_t.get('y', 0)))
            self._transform_z.setText(str(view_t.get('z', 0)))
        else:
            self._transform_x.setText(str(view_t.get('rx', 0)))
            self._transform_y.setText(str(view_t.get('ry', 0)))
            self._transform_z.setText(str(view_t.get('rz', 0)))

    def _update_transform_row_sizes(self):
        if not hasattr(self, '_transform_frame') or not hasattr(self, '_transform_x'):
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
        next_tooltip = (
            self._t('tool_editor.transform.switch_to_rotate', 'Click to rotate')
            if is_translate else
            self._t('tool_editor.transform.switch_to_move', 'Click to move')
        )
        self._mode_toggle_btn.setChecked(is_translate)
        self._mode_toggle_btn.setText('')
        self._mode_toggle_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / next_icon)))
        self._mode_toggle_btn.setIconSize(QSize(18, 18))
        self._mode_toggle_btn.setToolTip(next_tooltip)
        self._update_transform_row_sizes()

    def _update_fine_transform_button_appearance(self):
        if not hasattr(self, '_fine_transform_btn'):
            return
        icon_name = '1x.svg' if self._fine_transform_enabled else 'fine_tune.svg'
        tooltip = (
            self._t('tool_editor.transform.disable_fine', 'Click for 1x step')
            if self._fine_transform_enabled else
            self._t('tool_editor.transform.enable_fine', 'Click to fine tune')
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
                self._part_transforms[idx] = self._compact_transform_dict(baseline)
            self.models_preview.set_part_transforms(self._all_part_transforms_payload())
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
        t = self._normalized_transform_dict(self._part_transforms.get(index, {}))
        if self._current_transform_mode == 'translate':
            t['x'] = vx
            t['y'] = vy
            t['z'] = vz
        else:
            t['rx'] = vx
            t['ry'] = vy
            t['rz'] = vz
        self._part_transforms[index] = self._compact_transform_dict(t)
        self.models_preview.set_part_transforms(self._all_part_transforms_payload())

    def _on_model_table_selection_changed(self):
        if not self._assembly_transform_enabled:
            return
        if not hasattr(self, 'model_table'):
            return
        selection_model = self.model_table.selectionModel()
        if selection_model is None:
            return
        rows = sorted(index.row() for index in selection_model.selectedRows())
        self._selected_part_indices = rows
        self._selected_part_index = rows[-1] if rows else -1
        self._refresh_transform_selection_state()
        self.models_preview.select_parts(rows)

    def _measurement_part_options(self):
        options = [
            (
                self._t('tool_editor.measurements.assembly_coords', 'Assembly coordinates'),
                '',
            )
        ]
        seen = set()
        for row in range(self.model_table.rowCount()):
            item = self.model_table.item(row, 0)
            name = item.text().strip() if item else ''
            if not name or name in seen:
                continue
            seen.add(name)
            options.append((name, name))
        return options

    def _measurement_combo_row(self, table: PartsTable, column_key: str, combo: QComboBox) -> int:
        column = table.column_index(column_key)
        if column < 0:
            return -1
        for row in range(table.rowCount()):
            if table.cellWidget(row, column) is combo:
                return row
        return -1

    def _on_measurement_part_combo_changed(self, table: PartsTable, column_key: str, combo: QComboBox):
        row = self._measurement_combo_row(table, column_key, combo)
        if row < 0:
            return
        value = str(combo.currentData() or '').strip()
        table.set_cell_text(row, column_key, value)
        combo.setToolTip(
            value or self._t('tool_editor.measurements.assembly_coords', 'Assembly coordinates')
        )

    def _ensure_measurement_part_combo(self, table: PartsTable, row: int, column_key: str):
        column = table.column_index(column_key)
        if row < 0 or column < 0:
            return

        item = table.item(row, column)
        if item is None:
            item = QTableWidgetItem('')
            table.setItem(row, column, item)

        combo = table.cellWidget(row, column)
        if not isinstance(combo, QComboBox):
            combo = QComboBox(table)
            combo.setObjectName('measurementPartCombo')
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            combo.setMinimumHeight(28)
            combo.setMaxVisibleItems(8)
            self._style_combo(combo)
            self._configure_combo_popup(combo, max_rows=8, row_height=40)
            combo.currentIndexChanged.connect(
                lambda _idx, t=table, key=column_key, c=combo: self._on_measurement_part_combo_changed(t, key, c)
            )
            table.setCellWidget(row, column, combo)

        current_value = item.text().strip()
        options = self._measurement_part_options()

        combo.blockSignals(True)
        combo.clear()
        for display, value in options:
            combo.addItem(display, value)

        target_index = 0
        for idx in range(combo.count()):
            if str(combo.itemData(idx) or '').strip() == current_value:
                target_index = idx
                break
        combo.setCurrentIndex(target_index)
        combo.blockSignals(False)

        resolved_value = str(combo.currentData() or '').strip()
        table.set_cell_text(row, column_key, resolved_value)
        combo.setToolTip(
            resolved_value or self._t('tool_editor.measurements.assembly_coords', 'Assembly coordinates')
        )

    def _refresh_measurement_part_dropdowns(self):
        if not hasattr(self, 'distance_measurements_table') or not hasattr(self, 'ring_measurements_table'):
            return

        for row in range(self.distance_measurements_table.rowCount()):
            self._ensure_measurement_part_combo(self.distance_measurements_table, row, 'start_part')
            self._ensure_measurement_part_combo(self.distance_measurements_table, row, 'end_part')

        for row in range(self.ring_measurements_table.rowCount()):
            self._ensure_measurement_part_combo(self.ring_measurements_table, row, 'part')

    def _add_distance_measurement_row(self, values=None):
        row_data = {
            'name': self._t('tool_editor.measurements.default_distance', 'Distance'),
            'start_part': '',
            'start_xyz': '0, 0, 0',
            'end_part': '',
            'end_xyz': '0, 0, 0',
        }
        if isinstance(values, dict):
            row_data.update(values)
        self.distance_measurements_table.add_row_dict(row_data)
        row = self.distance_measurements_table.rowCount() - 1
        if row >= 0:
            self._refresh_measurement_part_dropdowns()
            self.distance_measurements_table.setCurrentCell(row, 0)
            self.distance_measurements_table.selectRow(row)

    def _add_ring_measurement_row(self, values=None):
        row_data = {
            'name': self._t('tool_editor.measurements.default_ring', 'Diameter'),
            'part': '',
            'center_xyz': '0, 0, 0',
            'axis_xyz': '0, 1, 0',
            'diameter': '0',
        }
        if isinstance(values, dict):
            row_data.update(values)
        self.ring_measurements_table.add_row_dict(row_data)
        row = self.ring_measurements_table.rowCount() - 1
        if row >= 0:
            self._refresh_measurement_part_dropdowns()
            self.ring_measurements_table.setCurrentCell(row, 0)
            self.ring_measurements_table.selectRow(row)

    def _load_measurement_overlays(self, overlays):
        state = self._empty_measurement_editor_state()
        raw_overlays = overlays
        if isinstance(raw_overlays, str):
            try:
                raw_overlays = json.loads(raw_overlays or '[]')
            except Exception:
                raw_overlays = []

        if not isinstance(raw_overlays, list):
            self._measurement_editor_state = state
            self._update_measurement_summary_label()
            return

        for overlay in raw_overlays:
            if not isinstance(overlay, dict):
                continue
            overlay_type = (overlay.get('type') or '').strip().lower()
            if overlay_type == 'distance':
                start_part = overlay.get('start_part', '')
                end_part = overlay.get('end_part', '')
                try:
                    start_part_index = int(overlay.get('start_part_index', -1) or -1)
                except Exception:
                    start_part_index = -1
                try:
                    end_part_index = int(overlay.get('end_part_index', -1) or -1)
                except Exception:
                    end_part_index = -1
                state['distance_measurements'].append(
                    {
                        'name': overlay.get('name', ''),
                        'start_part': start_part,
                        'start_part_index': start_part_index,
                        'start_xyz': self._normalize_xyz_text(overlay.get('start_xyz', '')),
                        'start_space': self._normalize_distance_space(
                            start_part,
                            start_part_index,
                            overlay.get('start_space', ''),
                        ),
                        'end_part': end_part,
                        'end_part_index': end_part_index,
                        'end_xyz': self._normalize_xyz_text(overlay.get('end_xyz', '')),
                        'end_space': self._normalize_distance_space(
                            end_part,
                            end_part_index,
                            overlay.get('end_space', ''),
                        ),
                        'distance_axis': overlay.get('distance_axis', 'z'),
                        'label_value_mode': overlay.get('label_value_mode', 'measured'),
                        'label_custom_value': overlay.get('label_custom_value', ''),
                        'offset_xyz': self._normalize_xyz_text(overlay.get('offset_xyz', '')),
                        'start_shift': overlay.get('start_shift', '0'),
                        'end_shift': overlay.get('end_shift', '0'),
                    }
                )
            elif overlay_type == 'diameter_ring':
                state['diameter_measurements'].append(
                    {
                        'name': overlay.get('name', ''),
                        'part': overlay.get('part', ''),
                        'part_index': overlay.get('part_index', -1),
                        'center_xyz': self._normalize_xyz_text(overlay.get('center_xyz', '')),
                        'edge_xyz': self._normalize_xyz_text(overlay.get('edge_xyz', '')),
                        'axis_xyz': self._normalize_xyz_text(overlay.get('axis_xyz', '0, 0, 1')),
                        'diameter_axis_mode': str(overlay.get('diameter_axis_mode') or '').strip().lower(),
                        'offset_xyz': self._normalize_xyz_text(overlay.get('offset_xyz', '')),
                        'diameter_visual_offset_mm': self._normalize_float_value(
                            overlay.get('diameter_visual_offset_mm', 1.0),
                            1.0,
                        ),
                        'diameter_mode': overlay.get('diameter_mode', 'manual'),
                        'diameter': overlay.get('diameter', ''),
                    }
                )
            elif overlay_type == 'radius':
                state['radius_measurements'].append(
                    {
                        'name': overlay.get('name', ''),
                        'part': overlay.get('part', ''),
                        'center_xyz': self._normalize_xyz_text(overlay.get('center_xyz', '')),
                        'axis_xyz': self._normalize_xyz_text(overlay.get('axis_xyz', '')),
                        'radius': overlay.get('radius', ''),
                    }
                )
            elif overlay_type == 'angle':
                state['angle_measurements'].append(
                    {
                        'name': overlay.get('name', ''),
                        'part': overlay.get('part', ''),
                        'center_xyz': self._normalize_xyz_text(overlay.get('center_xyz', '')),
                        'start_xyz': self._normalize_xyz_text(overlay.get('start_xyz', '')),
                        'end_xyz': self._normalize_xyz_text(overlay.get('end_xyz', '')),
                    }
                )

        self._measurement_editor_state = self._normalize_measurement_editor_state(state)
        self._update_measurement_summary_label()

    def _measurement_overlays_from_tables(self):
        overlays = []

        for entry in self._measurement_editor_state.get('distance_measurements', []):
            name = (entry.get('name') or '').strip()
            start_part = (entry.get('start_part') or '').strip()
            start_xyz = self._normalize_xyz_text(entry.get('start_xyz') or '')
            end_part = (entry.get('end_part') or '').strip()
            end_xyz = self._normalize_xyz_text(entry.get('end_xyz') or '')
            try:
                start_part_index = int(entry.get('start_part_index', -1) or -1)
            except Exception:
                start_part_index = -1
            try:
                end_part_index = int(entry.get('end_part_index', -1) or -1)
            except Exception:
                end_part_index = -1
            if not (name or start_part or start_xyz or end_part or end_xyz):
                continue
            overlays.append(
                {
                    'type': 'distance',
                    'name': name or self._t('tool_editor.measurements.default_distance', 'Distance'),
                    'start_part': start_part,
                    'start_part_index': start_part_index,
                    'start_xyz': start_xyz,
                    'start_space': self._normalize_distance_space(
                        start_part,
                        start_part_index,
                        entry.get('start_space', ''),
                    ),
                    'end_part': end_part,
                    'end_part_index': end_part_index,
                    'end_xyz': end_xyz,
                    'end_space': self._normalize_distance_space(
                        end_part,
                        end_part_index,
                        entry.get('end_space', ''),
                    ),
                    'distance_axis': (entry.get('distance_axis') or 'z').strip() or 'z',
                    'label_value_mode': (entry.get('label_value_mode') or 'measured').strip() or 'measured',
                    'label_custom_value': (entry.get('label_custom_value') or '').strip(),
                    'offset_xyz': self._normalize_xyz_text(entry.get('offset_xyz') or ''),
                    'start_shift': str(entry.get('start_shift') or '0').strip(),
                    'end_shift': str(entry.get('end_shift') or '0').strip(),
                    'order': len(overlays),
                }
            )

        for entry in self._measurement_editor_state.get('diameter_measurements', []):
            name = (entry.get('name') or '').strip()
            part = (entry.get('part') or '').strip()
            center_xyz = self._normalize_xyz_text(entry.get('center_xyz') or '')
            edge_xyz = self._normalize_xyz_text(entry.get('edge_xyz') or '')
            axis_xyz = self._normalize_xyz_text(entry.get('axis_xyz') or '0, 0, 1')
            diameter_axis_mode = str(entry.get('diameter_axis_mode') or '').strip().lower()
            if diameter_axis_mode not in {'x', 'y', 'z', 'direct'}:
                diameter_axis_mode = 'direct'
                axis_tokens = [token.strip() for token in axis_xyz.split(',')]
                if len(axis_tokens) >= 3:
                    try:
                        ax = abs(float(axis_tokens[0]))
                        ay = abs(float(axis_tokens[1]))
                        az = abs(float(axis_tokens[2]))
                    except Exception:
                        ax, ay, az = 0.0, 0.0, 1.0
                    tol = 1e-3
                    if abs(ax - 1.0) <= tol and ay <= tol and az <= tol:
                        diameter_axis_mode = 'x'
                    elif abs(ay - 1.0) <= tol and ax <= tol and az <= tol:
                        diameter_axis_mode = 'y'
                    elif abs(az - 1.0) <= tol and ax <= tol and ay <= tol:
                        diameter_axis_mode = 'z'
            offset_xyz = self._normalize_xyz_text(entry.get('offset_xyz') or '')
            diameter_mode = str(entry.get('diameter_mode') or ('measured' if edge_xyz else 'manual')).strip().lower()
            if diameter_mode not in {'measured', 'manual'}:
                diameter_mode = 'manual'
            diameter = str(entry.get('diameter') or '').strip()
            if not (name or part or center_xyz or edge_xyz or axis_xyz or offset_xyz or diameter):
                continue
            overlays.append(
                {
                    'type': 'diameter_ring',
                    'name': name or self._t('tool_editor.measurements.default_ring', 'Diameter'),
                    'part': part,
                    'part_index': int(entry.get('part_index', -1) or -1),
                    'center_xyz': center_xyz,
                    'edge_xyz': edge_xyz,
                    'axis_xyz': axis_xyz,
                    'diameter_axis_mode': diameter_axis_mode,
                    'offset_xyz': offset_xyz,
                    'diameter_visual_offset_mm': self._normalize_float_value(
                        entry.get('diameter_visual_offset_mm', 1.0),
                        1.0,
                    ),
                    'diameter_mode': diameter_mode,
                    'diameter': diameter,
                    'order': len(overlays),
                }
            )

        for entry in self._measurement_editor_state.get('radius_measurements', []):
            name = (entry.get('name') or '').strip()
            part = (entry.get('part') or '').strip()
            center_xyz = self._normalize_xyz_text(entry.get('center_xyz') or '')
            axis_xyz = self._normalize_xyz_text(entry.get('axis_xyz') or '')
            radius = (entry.get('radius') or '').strip()
            if not (name or part or center_xyz or axis_xyz or radius):
                continue
            overlays.append(
                {
                    'type': 'radius',
                    'name': name or self._t('tool_editor.measurements.default_radius', 'Radius'),
                    'part': part,
                    'center_xyz': center_xyz,
                    'axis_xyz': axis_xyz,
                    'radius': radius,
                    'order': len(overlays),
                }
            )

        for entry in self._measurement_editor_state.get('angle_measurements', []):
            name = (entry.get('name') or '').strip()
            part = (entry.get('part') or '').strip()
            center_xyz = self._normalize_xyz_text(entry.get('center_xyz') or '')
            start_xyz = self._normalize_xyz_text(entry.get('start_xyz') or '')
            end_xyz = self._normalize_xyz_text(entry.get('end_xyz') or '')
            if not (name or part or center_xyz or start_xyz or end_xyz):
                continue
            overlays.append(
                {
                    'type': 'angle',
                    'name': name or self._t('tool_editor.measurements.default_angle', 'Angle'),
                    'part': part,
                    'center_xyz': center_xyz,
                    'start_xyz': start_xyz,
                    'end_xyz': end_xyz,
                    'order': len(overlays),
                }
            )

        return overlays

    # -------------------------
    # EXISTING HELPERS
    # -------------------------
    def _update_cutting_label(self):
        raw_value = (self.cutting_type.currentData() or self.cutting_type.currentText() or 'Insert').strip() or 'Insert'
        localized = self._localized_cutting_type(raw_value)
        self.cutting_code_label.setText(self._t('tool_library.field.cutting_code', '{cutting_type} code', cutting_type=localized))

    def _update_tool_type_fields(self):
        # cutting component type is user-controlled and independent from tool type
        cutting_type = (self.cutting_type.currentData() or self.cutting_type.currentText() or 'Insert').strip() or 'Insert'
        show_drill = cutting_type == 'Drill'
        show_mill = cutting_type == 'Mill'
        self.drill_field.setVisible(show_drill)
        self.mill_field.setVisible(show_mill)
        self._update_cutting_label()
        self._reflow_general_fields(force=True)

    def _commit_active_edits(self):
        """Commit in-place editors (table cells, line edits) before tab switch/save."""
        fw = QApplication.focusWidget()
        if fw is not None:
            fw.clearFocus()

    def _load_tool(self):
        if not self.tool:
            return

        self.tool_id.setText(self.tool.get('id', ''))
        self._set_tool_head_value(self.tool.get('tool_head', 'HEAD1'))
        self._set_combo_by_data(self.tool_type, self.tool.get('tool_type', 'O.D Turning'))
        self.description.setText(self.tool.get('description', ''))
        self.geom_x.setText(str(self.tool.get('geom_x', '')))
        self.geom_z.setText(str(self.tool.get('geom_z', '')))
        self.radius.setText(str(self.tool.get('radius', '')))
        self.nose_corner_radius.setText(str(self.tool.get('nose_corner_radius', '')))
        self.holder_code.setText(self.tool.get('holder_code', ''))
        self.holder_link.setText(self.tool.get('holder_link', ''))
        self.holder_add_element.setText(self.tool.get('holder_add_element', ''))
        self.holder_add_element_link.setText(self.tool.get('holder_add_element_link', ''))
        self._set_combo_by_data(self.cutting_type, self.tool.get('cutting_type', 'Insert'))
        self.cutting_code.setText(self.tool.get('cutting_code', ''))
        self.cutting_link.setText(self.tool.get('cutting_link', ''))
        self.cutting_add_element.setText(self.tool.get('cutting_add_element', ''))
        self.cutting_add_element_link.setText(self.tool.get('cutting_add_element_link', ''))
        self.notes.setText(self.tool.get('notes', self.tool.get('spare_parts', '')))
        self.default_pot.setText(self.tool.get('default_pot', ''))
        self.drill_nose_angle.setText(str(self.tool.get('drill_nose_angle', '')))
        self.mill_cutting_edges.setText(str(self.tool.get('mill_cutting_edges', '')))

        component_items = self.tool.get('component_items', [])
        if isinstance(component_items, str):
            try:
                component_items = json.loads(component_items or '[]')
            except Exception:
                component_items = []
        if not isinstance(component_items, list):
            component_items = []

        if not component_items:
            # Legacy fallback for older rows without component_items.
            cutting_type = (self.tool.get('cutting_type', 'Insert') or 'Insert').strip() or 'Insert'
            component_items = [
                {
                    'role': 'holder',
                    'label': self._t('tool_library.field.holder', 'Holder'),
                    'code': self.tool.get('holder_code', ''),
                    'link': self.tool.get('holder_link', ''),
                },
                {
                    'role': 'holder',
                    'label': self._t('tool_library.field.add_element', 'Add. Element'),
                    'code': self.tool.get('holder_add_element', ''),
                    'link': self.tool.get('holder_add_element_link', ''),
                },
                {
                    'role': 'cutting',
                    'label': cutting_type,
                    'code': self.tool.get('cutting_code', ''),
                    'link': self.tool.get('cutting_link', ''),
                },
                {
                    'role': 'cutting',
                    'label': self._t('tool_library.field.add_cutting', 'Add. {cutting_type}', cutting_type=self._localized_cutting_type(cutting_type)),
                    'code': self.tool.get('cutting_add_element', ''),
                    'link': self.tool.get('cutting_add_element_link', ''),
                },
            ]

        for item in component_items:
            if not isinstance(item, dict):
                continue
            role = (item.get('role') or '').strip().lower()
            if role not in {'holder', 'cutting', 'support'}:
                continue
            code = (item.get('code') or '').strip()
            if not code:
                continue
            self.parts_table.add_empty_row([
                role,
                (item.get('label') or '').strip() or self._t('tool_library.field.part', 'Part'),
                code,
                (item.get('link') or '').strip(),
                (item.get('group') or '').strip(),
            ])

        spare_parts = self.tool.get('support_parts', [])
        if isinstance(spare_parts, str):
            try:
                spare_parts = json.loads(spare_parts or '[]')
            except Exception:
                spare_parts = []
        if isinstance(spare_parts, list):
            for part in spare_parts:
                if isinstance(part, str):
                    try:
                        part = json.loads(part)
                    except Exception:
                        part = {'name': part, 'code': '', 'link': '', 'component_key': '', 'group': ''}
                if not isinstance(part, dict):
                    continue
                self._add_spare_part_row(part)

        self._refresh_spare_component_dropdowns()

        # Load 3D model data from stl_path
        stl_data = self.tool.get('stl_path', '')
        model_parts = []

        if isinstance(stl_data, str) and stl_data.strip():
            try:
                parsed = json.loads(stl_data)
                if isinstance(parsed, list):
                    model_parts = parsed
                elif isinstance(parsed, str):
                    model_parts = [{'name': self._t('tool_editor.model.default_name', 'Model'), 'file': parsed, 'color': '#9ea7b3'}]
            except Exception:
                model_parts = [{'name': self._t('tool_editor.model.default_name', 'Model'), 'file': stl_data, 'color': '#9ea7b3'}]

        self._suspend_preview_refresh = True
        try:
            for part in model_parts:
                self._add_model_row({
                    'name': part.get('name', ''),
                    'file': part.get('file', ''),
                    'color': part.get('color', self._default_color_for_part_name(part.get('name', ''))),
                })
        finally:
            self._suspend_preview_refresh = False

        # Load per-part transforms
        self._part_transforms = {}
        self._saved_part_transforms = {}
        for i, part in enumerate(model_parts):
            t = {}
            for src, dst in [('offset_x', 'x'), ('offset_y', 'y'), ('offset_z', 'z'),
                             ('rot_x', 'rx'), ('rot_y', 'ry'), ('rot_z', 'rz')]:
                v = part.get(src, 0)
                if v:
                    t[dst] = v
            normalized = self._normalized_transform_dict(t)
            compact = self._compact_transform_dict(normalized)
            if compact:
                self._part_transforms[i] = dict(compact)
                self._saved_part_transforms[i] = dict(compact)

        self._load_measurement_overlays(self.tool.get('measurement_overlays', []))

        self._update_tool_type_fields()
        self._refresh_models_preview()
        if self._assembly_transform_enabled:
            selection_model = self.model_table.selectionModel()
            if selection_model is not None:
                rows = sorted(index.row() for index in selection_model.selectedRows())
                if not rows:
                    current_row = self.model_table.currentRow()
                    if current_row >= 0:
                        rows = [current_row]
                self._selected_part_indices = rows
                self._selected_part_index = rows[-1] if rows else -1
            self._refresh_transform_selection_state()
            self.models_preview.select_parts(self._selected_part_indices)
            QTimer.singleShot(0, lambda: self._request_preview_transform_snapshot(refresh_selection=True))

    def _component_items_from_table(self):
        items = []
        for entry in self.parts_table.row_dicts():
            role = (entry.get('role') or 'support').strip().lower()
            if role not in {'holder', 'cutting', 'support'}:
                role = 'support'
            code = (entry.get('code') or '').strip()
            if not code:
                continue
            label = (entry.get('label') or '').strip()
            if not label:
                if role == 'holder':
                    label = self._t('tool_library.field.holder', 'Holder')
                elif role == 'cutting':
                    label = self._localized_cutting_type('Insert')
                else:
                    label = self._t('tool_library.field.part', 'Part')

            items.append(
                {
                    'role': role,
                    'label': label,
                    'code': code,
                    'link': (entry.get('link') or '').strip(),
                    'group': (entry.get('group') or '').strip(),
                    'component_key': f"{role}:{code}",
                    'order': len(items),
                }
            )
        return items

    def _spare_parts_from_table(self):
        result = []
        for row in range(self.spare_parts_table.rowCount()):
            entry = self.spare_parts_table.row_dict(row)

            name = (entry.get('name') or '').strip()
            code = (entry.get('code') or '').strip()
            link = (entry.get('link') or '').strip()
            component_key = self._get_spare_component_key(row)
            group = (entry.get('group') or '').strip()

            if not (name or code or link or component_key):
                continue

            result.append(
                {
                    'name': name,
                    'code': code,
                    'link': link,
                    'component_key': component_key,
                    'group': group,
                }
            )
        return result

    def get_tool_data(self):
        self._commit_active_edits()
        self._sync_preview_transform_snapshot_for_save()
        tool_id = self.tool_id.text().strip()
        if not tool_id and not self._group_edit_mode:
            raise ValueError(self._t('tool_editor.error.tool_id_required', 'Tool ID is required.'))

        def parse_float(value, field_name):
            text = value.text().strip()
            if not text:
                return 0.0
            try:
                return float(text.replace(',', '.'))
            except ValueError:
                raise ValueError(self._t('tool_editor.error.must_be_number', '{field_name} must be a number.', field_name=field_name))

        def parse_int(value, field_name):
            text = value.text().strip()
            if not text:
                return 0
            try:
                return int(text)
            except ValueError:
                raise ValueError(self._t('tool_editor.error.must_be_integer', '{field_name} must be an integer.', field_name=field_name))

        selected_cutting = (self.cutting_type.currentData() or self.cutting_type.currentText() or 'Insert').strip() or 'Insert'
        selected_type = (self.tool_type.currentData() or self.tool_type.currentText() or 'O.D Turning').strip() or 'O.D Turning'
        model_parts = self._model_table_to_parts()
        component_items = self._component_items_from_table()
        support_parts = self._spare_parts_from_table()

        return {
            'uid': self.original_uid,
            'id': tool_id,
            'tool_head': self._get_tool_head_value(),
            'tool_type': selected_type,
            'description': self.description.text().strip(),
            'geom_x': parse_float(self.geom_x, self._t('tool_library.field.geom_x', 'Geom X')),
            'geom_z': parse_float(self.geom_z, self._t('tool_library.field.geom_z', 'Geom Z')),
            'radius': parse_float(self.radius, self._t('tool_library.field.radius', 'Radius')),
            'nose_corner_radius': parse_float(self.nose_corner_radius, self._t('tool_library.field.nose_corner_radius', 'Nose R / Corner R')),
            'holder_code': self.holder_code.text().strip(),
            'holder_link': self.holder_link.text().strip(),
            'holder_add_element': self.holder_add_element.text().strip(),
            'holder_add_element_link': self.holder_add_element_link.text().strip(),
            'cutting_type': selected_cutting,
            'cutting_code': self.cutting_code.text().strip(),
            'cutting_link': self.cutting_link.text().strip(),
            'cutting_add_element': self.cutting_add_element.text().strip(),
            'cutting_add_element_link': self.cutting_add_element_link.text().strip(),
            'notes': self.notes.text().strip(),
            'drill_nose_angle': parse_float(self.drill_nose_angle, self._t('tool_library.field.nose_angle', 'Nose angle')) if selected_cutting == 'Drill' else 0.0,
            'mill_cutting_edges': parse_int(self.mill_cutting_edges, self._t('tool_library.field.cutting_edges', 'Cutting edges')) if selected_cutting == 'Mill' else 0,
            'support_parts': support_parts,
            'component_items': component_items,
            'measurement_overlays': self._measurement_overlays_from_tables(),
            'stl_path': json.dumps(model_parts) if model_parts else '',
            'default_pot': self.default_pot.text().strip(),
        }
