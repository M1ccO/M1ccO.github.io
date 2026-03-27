import json
from typing import Callable
from PySide6.QtCore import QEvent, Qt, QTimer, QSize
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListView, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
    QFileDialog, QTableWidgetItem, QHeaderView, QSplitter, QListWidget, QListWidgetItem
)
from config import ALL_TOOL_TYPES, TOOL_ICONS_DIR, EDITOR_DROPDOWN_WIDTH
from ui.widgets.parts_table import PartsTable
from ui.stl_preview import StlPreviewWidget
from ui.widgets.color_picker_dialog import ColorPickerDialog
from ui.widgets.common import clear_focused_dropdown_on_outside_click, apply_shared_dropdown_style
from shared.editor_helpers import (
    add_shadow,
    setup_editor_dialog,
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
        self.setWindowTitle(title)
        self.resize(640, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText(self._t('tool_editor.component.search_placeholder', 'Search by name, code, link, or source...'))
        self.search.textChanged.connect(self._refresh)
        root.addWidget(self.search)

        self.list_widget = QListWidget()
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

        self._refresh()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

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
            label = f"{entry.get('name', self._t('tool_library.field.part', 'Part'))} | {entry.get('code', '')}"
            source = entry.get('source', '')
            if source:
                label += f" [{source}]"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entry)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _accept_selected(self):
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(
                self,
                self._t('tool_editor.component.select_title', 'Select component'),
                self._t('tool_editor.component.select_first', 'Select a component first.'),
            )
            return
        self._selected_entry = item.data(Qt.UserRole)
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
    ):
        super().__init__(parent)
        self.tool = tool or {}
        self.tool_service = tool_service
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self._general_field_columns = None
        self._clamping_screen_bounds = False
        self.setWindowTitle(
            self._t('tool_editor.window_title.add', 'Add Tool')
            if not tool
            else self._t('tool_editor.window_title.edit', 'Edit Tool - {tool_id}', tool_id=tool['id'])
        )
        self.resize(920, 600)
        self.setMinimumSize(800, 520)
        self.setModal(True)
        setup_editor_dialog(self)
        self._build_ui()
        self._load_tool()
        self._update_cutting_label()
        self._update_tool_type_fields()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _localized_tool_type(self, raw_tool_type: str) -> str:
        key = f"tool_library.tool_type.{(raw_tool_type or '').strip().lower().replace('.', '_').replace('/', '_').replace(' ', '_')}"
        return self._t(key, raw_tool_type)

    def _localized_cutting_type(self, raw_cutting_type: str) -> str:
        key = f"tool_library.cutting_type.{(raw_cutting_type or '').strip().lower().replace(' ', '_')}"
        return self._t(key, raw_cutting_type)

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
        self.tabs.currentChanged.connect(self._on_tab_changed)
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
        self.tool_head = QPushButton('HEAD1')
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
        type_popup_view = self.tool_type.view()
        type_popup_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        type_popup_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        type_popup_view.setMinimumHeight(0)
        type_popup_view.setMaximumHeight(8 * 40)
        type_popup_view.window().setMinimumHeight(0)
        type_popup_view.window().setMaximumHeight(8 * 40 + 8)

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
            self.mill_cutting_edges, self.notes
        ]:
            self._style_general_editor(w)

        # -- Build grouped field sections --

        # Group 1: Identity
        group1 = self._build_field_group([
            self._build_edit_field(self._t('tool_library.row.tool_id', 'Tool ID'), self.tool_id),
            self._build_edit_field(self._t('tool_editor.field.tool_type', 'Tool type'), self.tool_type_row),
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

        # Wire per-field label clicks to swap individual code/link pairs
        self._showing_links = False
        self._code_link_pairs = [
            (self.holder_code_field, self.holder_link_field),
            (self.holder_add_field, self.holder_add_link_field),
            (self.cutting_code_field, self.cutting_link_field),
            (self.cutting_add_field, self.cutting_add_link_field),
        ]
        for code_f, link_f in self._code_link_pairs:
            _cf, _lf = code_f, link_f
            lbl_c = getattr(_cf, '_field_label', None)
            lbl_l = getattr(_lf, '_field_label', None)
            if lbl_c:
                lbl_c.setProperty('swappableLabel', True)
                lbl_c.setCursor(Qt.PointingHandCursor)
                lbl_c.style().unpolish(lbl_c)
                lbl_c.style().polish(lbl_c)
                lbl_c.mousePressEvent = lambda _e, a=_cf, b=_lf: self._swap_field_pair(a, b)
            if lbl_l:
                lbl_l.setProperty('swappableLabel', True)
                lbl_l.setCursor(Qt.PointingHandCursor)
                lbl_l.style().unpolish(lbl_l)
                lbl_l.style().polish(lbl_l)
                lbl_l.mousePressEvent = lambda _e, a=_lf, b=_cf: self._swap_field_pair(a, b)

        # Dummy field order for compatibility
        self._general_field_order = []

        # Add groups to form layout
        form_layout.addWidget(group1)
        form_layout.addWidget(group2)
        form_layout.addWidget(group3)
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
            self._t('tool_editor.table.part_name', 'Part name'),
            self._t('tool_editor.table.code', 'Code'),
            self._t('tool_editor.table.link', 'Link'),
            self._t('tool_editor.table.group', 'Group'),
        ])
        self.parts_table.setObjectName('editorPartsTable')
        self.parts_table.setSelectionMode(PartsTable.ExtendedSelection)
        self.parts_table.horizontalHeader().setStretchLastSection(False)
        header = self.parts_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        self.parts_table.setColumnWidth(3, 120)
        self.parts_table.verticalHeader().setDefaultSectionSize(32)
        self.parts_table.verticalHeader().setMinimumSectionSize(28)
        self.parts_table.setMinimumHeight(320)
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
            self._t('tool_editor.action.add_part', 'Add part'),
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
        self.group_btn.setVisible(False)
        self.group_name_edit = QLineEdit()
        self.group_name_edit.setPlaceholderText(self._t('tool_editor.placeholder.group_name', 'Group name...'))
        self.group_name_edit.setVisible(False)
        self.group_name_edit.setMinimumHeight(34)
        self.group_name_edit.setMaximumWidth(160)
        self.group_hint_label = QLabel(self._t('tool_editor.hint.press_enter_to_add', 'Press Enter to add'))
        self.group_hint_label.setVisible(False)
        self.group_hint_label.setStyleSheet('background: transparent; font-size: 12px; color: #7a8a9a; font-style: italic;')
        self.group_select_hint_label = QLabel(self._t('tool_editor.hint.select_multiple', 'Select multiple parts to make a group'))
        self.group_select_hint_label.setStyleSheet('background: transparent; font-size: 12px; color: #9aabb8; font-style: italic;')
        self.add_part_btn.clicked.connect(lambda: self.parts_table.add_empty_row())
        self.remove_part_btn.clicked.connect(self.parts_table.remove_selected_row)
        self.part_up_btn.clicked.connect(lambda: self.parts_table.move_selected_row(-1))
        self.part_down_btn.clicked.connect(lambda: self.parts_table.move_selected_row(1))
        self.pick_part_btn.clicked.connect(self._pick_additional_part)
        self.group_btn.clicked.connect(self._toggle_group)
        self.group_name_edit.returnPressed.connect(self._apply_group_name)
        self.group_name_edit.installEventFilter(self)
        self.parts_table.itemSelectionChanged.connect(self._update_group_button_visibility)
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
        self.tabs.addTab(parts_tab, self._t('tool_editor.tab.additional_parts', 'Additional parts'))

        # -------------------------
        # 3D MODELS TAB
        # -------------------------
        models_tab = QWidget()
        models_tab.setProperty('editorPageSurface', True)
        models_layout = QVBoxLayout(models_tab)
        models_layout.setContentsMargins(18, 18, 18, 18)
        models_layout.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setProperty('editorTransparentPanel', True)
        splitter.setHandleWidth(8)

        # Left side: table in panel frame (same structure as spare parts tab)
        models_panel = QFrame()
        models_panel.setProperty('editorPartsPanel', True)
        models_panel.setMinimumWidth(320)
        models_panel_layout = QVBoxLayout(models_panel)
        models_panel_layout.setContentsMargins(8, 10, 8, 8)
        models_panel_layout.setSpacing(0)

        self.model_table = PartsTable(['Part Name', 'STL File', 'Color'])
        self.model_table.setObjectName('editorModelsTable')
        self.model_table.setMinimumHeight(320)
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
        self.model_table.setColumnWidth(0, 120)
        self.model_table.setColumnWidth(1, 260)
        self.model_table.setColumnWidth(2, 80)
        self.model_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.model_table.itemChanged.connect(self._on_model_table_changed)

        models_panel_layout.addWidget(self.model_table, 1)

        # Right side: preview panel
        preview_panel = QFrame()
        preview_panel.setProperty('editorPartsPanel', True)
        preview_panel.setMinimumWidth(240)
        preview_panel_layout = QVBoxLayout(preview_panel)
        preview_panel_layout.setContentsMargins(8, 8, 8, 8)
        preview_panel_layout.setSpacing(0)

        self.models_preview = StlPreviewWidget()
        preview_panel_layout.addWidget(self.models_preview, 1)

        splitter.addWidget(models_panel)
        splitter.addWidget(preview_panel)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setSizes([400, 300])

        models_layout.addWidget(splitter, 1)

        model_btn_bar = QFrame()
        model_btn_bar.setProperty('editorButtonBar', True)
        model_btns = QHBoxLayout(model_btn_bar)
        model_btns.setContentsMargins(2, 6, 2, 2)
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
        model_btns.addWidget(self.add_model_btn)
        model_btns.addWidget(self.remove_model_btn)
        model_btns.addWidget(self.model_up_btn)
        model_btns.addWidget(self.model_down_btn)
        model_btns.addStretch(1)
        models_layout.addWidget(model_btn_bar)

        self.tabs.addTab(models_tab, self._t('tool_editor.tab.models', '3D models'))

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

        self.code_link_toggle_btn = QPushButton()
        style_icon_action_button(
            self.code_link_toggle_btn,
            TOOL_ICONS_DIR / 'import_export.svg',
            self._t('tool_editor.action.show_links', 'Show links'),
        )
        self.code_link_toggle_btn.clicked.connect(self._toggle_code_link_mode)

        bottom_bar = QWidget()
        bottom_bar.setObjectName('dialogBottomBar')
        bottom_bar.setStyleSheet('#dialogBottomBar { background: transparent; }')
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)
        bottom_layout.addWidget(self.code_link_toggle_btn)
        bottom_layout.addWidget(self._dialog_buttons, 1)
        root.addWidget(bottom_bar)

        apply_secondary_button_theme(self, self._save_btn)

        QApplication.instance().installEventFilter(self)

        for le in [
            self.tool_id, self.description, self.geom_x, self.geom_z, self.radius,
            self.nose_corner_radius, self.holder_code, self.holder_link, self.holder_add_element,
            self.holder_add_element_link, self.cutting_code, self.cutting_link,
            self.cutting_add_element, self.cutting_add_element_link,
            self.drill_nose_angle, self.mill_cutting_edges, self.notes
        ]:
            le.returnPressed.connect(self.accept)

        self.tool_id.textChanged.connect(self._update_general_header)
        self.description.textChanged.connect(self._update_general_header)
        self.tool_type.currentTextChanged.connect(self._update_general_header)
        self._update_general_header()

    def eventFilter(self, obj, event):
        if obj is self.group_name_edit and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._apply_group_name()
                return True  # fully consume — prevent dialog default button from firing
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

    def _toggle_code_link_mode(self):
        self._showing_links = not self._showing_links
        for code_field, link_field in self._code_link_pairs:
            code_field.setVisible(not self._showing_links)
            link_field.setVisible(self._showing_links)
        if self._showing_links:
            self.code_link_toggle_btn.setToolTip(self._t('tool_editor.action.show_codes', 'Show codes'))
        else:
            self.code_link_toggle_btn.setToolTip(self._t('tool_editor.action.show_links', 'Show links'))

    def _style_combo(self, combo: QComboBox):
        apply_shared_dropdown_style(combo)

    def _set_tool_head_value(self, head: str):
        normalized = (head or 'HEAD1').strip().upper()
        if normalized not in {'HEAD1', 'HEAD2'}:
            normalized = 'HEAD1'
        is_head2 = normalized == 'HEAD2'
        self.tool_head.blockSignals(True)
        self.tool_head.setChecked(is_head2)
        self.tool_head.setText('HEAD2' if is_head2 else 'HEAD1')
        self.tool_head.blockSignals(False)

    def _toggle_tool_head(self, checked: bool):
        self.tool_head.setText('HEAD2' if checked else 'HEAD1')

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
            key = (entry.get('kind', ''), entry.get('name', ''), entry.get('code', ''), entry.get('link', ''))
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

    def _pick_holder_component(self):
        entry = self._open_component_picker(self._t('tool_editor.component.select_holder', 'Select holder'), ('holder', 'holder-extra'))
        if not entry:
            return
        self.holder_code.setText(entry.get('code', ''))
        self.holder_link.setText(entry.get('link', ''))

    def _pick_cutting_component(self):
        entry = self._open_component_picker(self._t('tool_editor.component.select_cutting', 'Select cutting component'), ('cutting', 'cutting-extra'))
        if not entry:
            return
        self.cutting_code.setText(entry.get('code', ''))
        self.cutting_link.setText(entry.get('link', ''))

    def _pick_additional_part(self):
        entry = self._open_component_picker(
            self._t('tool_editor.component.select_additional', 'Select additional part'),
            ('support',),
        )
        if not entry:
            return
        self.parts_table.add_empty_row([
            entry.get('name', self._t('tool_library.field.part', 'Part')),
            entry.get('code', ''),
            entry.get('link', ''),
        ])

    def _update_group_button_visibility(self):
        selected_rows = sorted(set(idx.row() for idx in self.parts_table.selectedIndexes()))
        if len(selected_rows) < 2:
            self.group_btn.setVisible(False)
            self.group_name_edit.setVisible(False)
            self.group_hint_label.setVisible(False)
            self.group_select_hint_label.setVisible(True)
            return

        self.group_btn.setVisible(True)
        self.group_select_hint_label.setVisible(False)

        groups = set()
        for row in selected_rows:
            item = self.parts_table.item(row, 3)
            groups.add(item.text().strip() if item else '')

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

    def _toggle_group(self):
        selected_rows = sorted(set(idx.row() for idx in self.parts_table.selectedIndexes()))
        if not selected_rows:
            return

        groups = set()
        for row in selected_rows:
            item = self.parts_table.item(row, 3)
            groups.add(item.text().strip() if item else '')

        non_empty = groups - {''}
        all_same_group = bool(non_empty) and len(non_empty) == 1 and '' not in groups

        if all_same_group:
            for row in selected_rows:
                item = self.parts_table.item(row, 3)
                if item:
                    item.setText('')
                else:
                    self.parts_table.setItem(row, 3, QTableWidgetItem(''))
            self.group_name_edit.setVisible(False)
            self.group_hint_label.setVisible(False)
        else:
            self.group_name_edit.setVisible(True)
            self.group_hint_label.setVisible(True)
            self.group_name_edit.clear()
            self.group_name_edit.setFocus()

    def _apply_group_name(self):
        name = self.group_name_edit.text().strip()
        if not name:
            self.group_name_edit.setVisible(False)
            self.group_hint_label.setVisible(False)
            return

        selected_rows = sorted(set(idx.row() for idx in self.parts_table.selectedIndexes()))
        for row in selected_rows:
            item = self.parts_table.item(row, 3)
            if item:
                item.setText(name)
            else:
                self.parts_table.setItem(row, 3, QTableWidgetItem(name))

        self.group_name_edit.setVisible(False)
        self.group_hint_label.setVisible(False)

    def _on_tab_changed(self, index: int):
        if hasattr(self, 'code_link_toggle_btn'):
            self.code_link_toggle_btn.setVisible(index == 0)

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
        self._ensure_on_screen()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._ensure_on_screen()

    def showEvent(self, event):
        super().showEvent(event)
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
        file_item = QTableWidgetItem(stl_file)

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


    def _add_model_row(self, checked=False, values=None):
        if isinstance(checked, dict) and values is None:
            values = checked

        if values is None:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                self._t('tool_editor.dialog.select_stl_model', 'Select STL model'),
                '',
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
        self._refresh_models_preview()

    def _browse_model_file_for_row(self, row: int):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._t('tool_editor.dialog.select_stl_model', 'Select STL model'),
            '',
            self._t('jaw_editor.dialog.stl_filter', 'STL Files (*.stl)')
        )
        if not file_path:
            return

        name_item = self.model_table.item(row, 0)
        file_item = self.model_table.item(row, 1)

        if file_item is None:
            file_item = QTableWidgetItem()
            self.model_table.setItem(row, 1, file_item)

        file_item.setText(file_path)

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
            self._refresh_models_preview()

    def _model_table_rows(self):
        rows = []
        for row in range(self.model_table.rowCount()):
            name_item = self.model_table.item(row, 0)
            file_item = self.model_table.item(row, 1)
            rows.append({
                'name': name_item.text().strip() if name_item else '',
                'file': file_item.text().strip() if file_item else '',
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

        if selected_row is not None and 0 <= selected_row < self.model_table.rowCount():
            self.model_table.selectRow(selected_row)

    def _move_model_row(self, delta: int):
        row = self.model_table.currentRow()
        if row < 0:
            return

        rows = self._model_table_rows()
        new_row = row + delta
        if new_row < 0 or new_row >= len(rows) or new_row == row:
            return

        moved = rows.pop(row)
        rows.insert(new_row, moved)
        self._restore_model_rows(rows, selected_row=new_row)
        self._refresh_models_preview()

    def _on_model_table_changed(self, item):
        if item.column() == 0:
            row = item.row()
            current_color = self._get_model_row_color(row)
            if not current_color or current_color == '#9ea7b3':
                auto_color = self._default_color_for_part_name(item.text().strip())
                self._set_color_button(row, auto_color)
        self._refresh_models_preview()

    def _model_table_to_parts(self):
        result = []
        for row in range(self.model_table.rowCount()):
            name_item = self.model_table.item(row, 0)
            file_item = self.model_table.item(row, 1)

            name = name_item.text().strip() if name_item else ''
            stl_file = file_item.text().strip() if file_item else ''
            color = self._get_model_row_color(row)

            if name or stl_file:
                result.append({
                    'name': name,
                    'file': stl_file,
                    'color': color or self._default_color_for_part_name(name),
                })
        return result

    def _refresh_models_preview(self):
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
        self.drill_nose_angle.setText(str(self.tool.get('drill_nose_angle', '')))
        self.mill_cutting_edges.setText(str(self.tool.get('mill_cutting_edges', '')))

        parts = self.tool.get('support_parts', [])
        if isinstance(parts, str):
            try:
                parts = json.loads(parts or '[]')
            except Exception:
                parts = []
        for part in parts:
            if isinstance(part, str):
                try:
                    part = json.loads(part)
                except Exception:
                    part = {'name': part, 'code': '', 'link': ''}
            if not isinstance(part, dict):
                continue
            self.parts_table.add_empty_row([part.get('name', ''), part.get('code', ''), part.get('link', ''), part.get('group', '')])

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

        for part in model_parts:
            self._add_model_row({
                'name': part.get('name', ''),
                'file': part.get('file', ''),
                'color': part.get('color', self._default_color_for_part_name(part.get('name', ''))),
            })

        self._update_tool_type_fields()
        self._refresh_models_preview()

    def _table_to_parts(self, table, mapping):
        result = []
        for row in range(table.rowCount()):
            entry = {}
            all_empty = True
            for col, key in enumerate(mapping):
                item = table.item(row, col)
                text = item.text().strip() if item else ''
                entry[key] = text
                if text:
                    all_empty = False
            if not all_empty:
                result.append(entry)
        return result

    def get_tool_data(self):
        self._commit_active_edits()
        tool_id = self.tool_id.text().strip()
        if not tool_id:
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

        return {
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
            'support_parts': self._table_to_parts(self.parts_table, ['name', 'code', 'link', 'group']),
            'stl_path': json.dumps(model_parts) if model_parts else '',
        }
