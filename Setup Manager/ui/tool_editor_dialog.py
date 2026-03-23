import json
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox, QDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
    QFileDialog, QColorDialog, QTableWidgetItem, QHeaderView, QSplitter, QListWidget, QListWidgetItem
)
from config import ALL_TOOL_TYPES, TOOL_ICONS_DIR
from ui.widgets.parts_table import PartsTable
from ui.stl_preview import StlPreviewWidget
from ui.widgets.common import BorderOnlyComboItemDelegate, add_shadow


class ComponentPickerDialog(QDialog):
    def __init__(self, title: str, entries: list[dict], parent=None):
        super().__init__(parent)
        self._entries = entries
        self._selected_entry = None
        self.setWindowTitle(title)
        self.resize(640, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText('Search by name, code, link, or source...')
        self.search.textChanged.connect(self._refresh)
        root.addWidget(self.search)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _: self._accept_selected())
        root.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton('CANCEL')
        select_btn = QPushButton('SELECT')
        cancel_btn.setProperty('panelActionButton', True)
        select_btn.setProperty('panelActionButton', True)
        select_btn.setProperty('primaryAction', True)
        cancel_btn.clicked.connect(self.reject)
        select_btn.clicked.connect(self._accept_selected)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(select_btn)
        root.addLayout(btn_row)

        self._refresh()

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
            label = f"{entry.get('name', 'Part')} | {entry.get('code', '')}"
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
            QMessageBox.information(self, 'Select component', 'Select a component first.')
            return
        self._selected_entry = item.data(Qt.UserRole)
        self.accept()

    def selected_entry(self):
        return self._selected_entry


class AddEditToolDialog(QDialog):

    def __init__(self, parent=None, tool=None, tool_service=None):
        super().__init__(parent)
        self.tool = tool or {}
        self.tool_service = tool_service
        self._general_field_columns = None
        self._clamping_screen_bounds = False
        self.setWindowTitle('Add Tool' if not tool else f"Edit Tool - {tool['id']}")
        self.resize(920, 600)
        self.setMinimumSize(800, 520)
        self.setModal(True)
        self._build_ui()
        self._load_tool()
        self._update_cutting_label()
        self._update_tool_type_fields()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel('Tool Editor')
        title.setProperty('pageTitle', True)
        root.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(lambda _idx: self._commit_active_edits())
        root.addWidget(self.tabs, 1)

        # -------------------------
        # GENERAL TAB
        # -------------------------
        general_tab = QWidget()
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
        self.editor_header_title = QLabel('New tool')
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

        self.general_fields_host = QWidget()
        self.general_fields_host.setProperty('editorFieldsHost', True)
        self.general_fields_grid = QGridLayout(self.general_fields_host)
        self.general_fields_grid.setContentsMargins(2, 2, 2, 2)
        self.general_fields_grid.setHorizontalSpacing(22)
        self.general_fields_grid.setVerticalSpacing(16)
        form_layout.addWidget(self.general_fields_host)

        self.tool_id = QLineEdit()
        self.tool_type = QComboBox()
        add_shadow(self.tool_type)
        self.tool_type.addItems(ALL_TOOL_TYPES)
        self.tool_type.currentTextChanged.connect(self._update_tool_type_fields)
        self._apply_combobox_popup_style(self.tool_type)
        self.tool_type.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.tool_type.setMinimumWidth(220)
        self.tool_type.setMaximumWidth(320)

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
        add_shadow(self.cutting_type)
        self.cutting_type.addItems(['Insert', 'Drill', 'Mill'])
        self.cutting_type.currentTextChanged.connect(self._update_tool_type_fields)
        self._apply_combobox_popup_style(self.cutting_type)
        self.cutting_type.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.cutting_type.setMinimumWidth(220)
        self.cutting_type.setMaximumWidth(280)

        self.cutting_code = QLineEdit()
        self.cutting_link = QLineEdit()
        self.cutting_add_element = QLineEdit()
        self.cutting_add_element_link = QLineEdit()
        self.notes = QLineEdit()

        self.holder_code_row = self._build_picker_row(
            self.holder_code,
            self._pick_holder_component,
            'Pick holder from existing tools',
        )
        self.cutting_code_row = self._build_picker_row(
            self.cutting_code,
            self._pick_cutting_component,
            'Pick cutting component from existing tools',
        )

        self.cutting_type_row = QWidget()
        self.cutting_type_row.setProperty('editorInlineRow', True)
        ctl = QHBoxLayout(self.cutting_type_row)
        ctl.setContentsMargins(0, 0, 0, 0)
        ctl.addWidget(self.cutting_type)
        ctl.addStretch(1)

        self.cutting_code_label = QLabel('Insert code')

        self.drill_nose_angle = QLineEdit()
        self.mill_cutting_edges = QLineEdit()
        self.drill_row_label = QLabel('Nose angle')
        self.mill_row_label = QLabel('Cutting edges')

        # Make editor controls visually closer to detail value boxes.
        for w in [
            self.tool_id, self.tool_type, self.description, self.geom_x, self.geom_z,
            self.radius, self.nose_corner_radius, self.holder_code, self.holder_link,
            self.holder_add_element, self.holder_add_element_link, self.cutting_type,
            self.cutting_code, self.cutting_link, self.cutting_add_element,
            self.cutting_add_element_link, self.drill_nose_angle,
            self.mill_cutting_edges, self.notes
        ]:
            self._style_general_editor(w)

        self._general_field_order = []
        self._general_field_order.append(self._build_edit_field('Tool ID', self.tool_id))
        self._general_field_order.append(self._build_edit_field('Tool type', self.tool_type))
        self._general_field_order.append(self._build_edit_field('Description', self.description))
        self._general_field_order.append(self._build_edit_field('Geom X', self.geom_x))
        self._general_field_order.append(self._build_edit_field('Geom Z', self.geom_z))
        self._general_field_order.append(self._build_edit_field('Radius', self.radius))
        self._general_field_order.append(self._build_edit_field('Nose R / Corner R', self.nose_corner_radius))
        self._general_field_order.append(self._build_edit_field('Holder code', self.holder_code_row))
        self._general_field_order.append(self._build_edit_field('Holder link', self.holder_link))
        self._general_field_order.append(self._build_edit_field('Add. Element', self.holder_add_element))
        self._general_field_order.append(self._build_edit_field('Add. Element link', self.holder_add_element_link))
        self._general_field_order.append(self._build_edit_field('Cutting component type', self.cutting_type_row))
        self.cutting_code_field = self._build_edit_field('', self.cutting_code_row, key_label=self.cutting_code_label)
        self._general_field_order.append(self.cutting_code_field)
        self._general_field_order.append(self._build_edit_field('Cutting component link', self.cutting_link))
        self._general_field_order.append(self._build_edit_field('Add. Insert/Drill/Mill', self.cutting_add_element))
        self._general_field_order.append(self._build_edit_field('Add. Insert/Drill/Mill link', self.cutting_add_element_link))
        self.drill_field = self._build_edit_field('', self.drill_nose_angle, key_label=self.drill_row_label)
        self.mill_field = self._build_edit_field('', self.mill_cutting_edges, key_label=self.mill_row_label)
        self._general_field_order.append(self.drill_field)
        self._general_field_order.append(self.mill_field)
        self._general_field_order.append(self._build_edit_field('Notes', self.notes))
        self._reflow_general_fields()

        general_content_layout.addWidget(form_frame)
        general_content_layout.addStretch(1)
        self.tabs.addTab(general_tab, 'General')

        # -------------------------
        # ADDITIONAL PARTS TAB
        # -------------------------
        parts_tab = QWidget()
        parts_tab_layout = QVBoxLayout(parts_tab)
        parts_tab_layout.setContentsMargins(0, 0, 0, 0)

        parts_box = QGroupBox('Additional parts')
        p_layout = QVBoxLayout(parts_box)
        p_layout.setContentsMargins(8, 8, 8, 10)
        p_layout.setSpacing(8)

        self.parts_table = PartsTable(['Part name', 'Code', 'Link'])
        self.parts_table.horizontalHeader().setStretchLastSection(True)
        self.parts_table.verticalHeader().setDefaultSectionSize(32)
        self.parts_table.verticalHeader().setMinimumSectionSize(28)
        self.parts_table.setMinimumHeight(320)
        p_layout.addWidget(self.parts_table, 1)

        parts_btn_bar = QFrame()
        parts_btn_bar.setProperty('editorButtonBar', True)
        p_btns = QHBoxLayout(parts_btn_bar)
        p_btns.setContentsMargins(2, 6, 2, 2)
        p_btns.setSpacing(8)
        self.add_part_btn = QPushButton('ADD PART')
        self.remove_part_btn = QPushButton('REMOVE SELECTED PART')
        self._style_panel_action_button(self.add_part_btn)
        self._style_panel_action_button(self.remove_part_btn)
        self.part_up_btn = self._make_arrow_button('keyboard_arrow_up.svg', 'Move selected row up')
        self.part_down_btn = self._make_arrow_button('keyboard_arrow_down.svg', 'Move selected row down')
        self.pick_part_btn = self._make_arrow_button('menu_open.svg', 'Pick additional part from existing tools')
        self.add_part_btn.clicked.connect(lambda: self.parts_table.add_empty_row())
        self.remove_part_btn.clicked.connect(self.parts_table.remove_selected_row)
        self.part_up_btn.clicked.connect(lambda: self.parts_table.move_selected_row(-1))
        self.part_down_btn.clicked.connect(lambda: self.parts_table.move_selected_row(1))
        self.pick_part_btn.clicked.connect(self._pick_additional_part)
        p_btns.addWidget(self.add_part_btn)
        p_btns.addWidget(self.remove_part_btn)
        p_btns.addWidget(self.part_up_btn)
        p_btns.addWidget(self.part_down_btn)
        p_btns.addStretch(1)
        p_btns.addWidget(self.pick_part_btn)
        p_layout.addWidget(parts_btn_bar)

        parts_tab_layout.addWidget(parts_box, 1)
        self.tabs.addTab(parts_tab, 'Additional Parts')

        # -------------------------
        # 3D MODELS TAB
        # -------------------------
        models_tab = QWidget()
        models_tab.setProperty('editorTransparentPanel', True)
        models_layout = QVBoxLayout(models_tab)
        models_layout.setContentsMargins(0, 0, 0, 0)

        models_box = QGroupBox('3D models')
        m_layout = QVBoxLayout(models_box)
        m_layout.setContentsMargins(8, 8, 8, 10)
        m_layout.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setProperty('editorTransparentPanel', True)
        splitter.setHandleWidth(0)

        # Left side: table + buttons
        left_panel = QWidget()
        left_panel.setProperty('editorTransparentPanel', True)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.model_table = PartsTable(['Part Name', 'STL File', 'Color'])
        self.model_table.setMinimumHeight(360)
        self.model_table.verticalHeader().setDefaultSectionSize(32)
        self.model_table.verticalHeader().setMinimumSectionSize(28)
        self.model_table.setColumnCount(3)
        self.model_table.setHorizontalHeaderLabels(['Part Name', 'STL File', 'Color'])
        self.model_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.model_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.model_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.model_table.setColumnWidth(2, 86)
        self.model_table.itemChanged.connect(self._on_model_table_changed)

        left_layout.addWidget(self.model_table, 1)

        model_btn_bar = QFrame()
        model_btn_bar.setProperty('editorButtonBar', True)
        model_btns = QHBoxLayout(model_btn_bar)
        model_btns.setContentsMargins(2, 10, 2, 2)
        model_btns.setSpacing(8)
        self.add_model_btn = QPushButton('ADD MODEL')
        self.remove_model_btn = QPushButton('REMOVE SELECTED MODEL')
        self._style_panel_action_button(self.add_model_btn)
        self._style_panel_action_button(self.remove_model_btn)
        self.model_up_btn = self._make_arrow_button('keyboard_arrow_up.svg', 'Move selected row up')
        self.model_down_btn = self._make_arrow_button('keyboard_arrow_down.svg', 'Move selected row down')
        self.add_model_btn.clicked.connect(self._add_model_row)
        self.remove_model_btn.clicked.connect(self._remove_model_row)
        self.model_up_btn.clicked.connect(lambda: self._move_model_row(-1))
        self.model_down_btn.clicked.connect(lambda: self._move_model_row(1))
        model_btns.addWidget(self.add_model_btn)
        model_btns.addWidget(self.remove_model_btn)
        model_btns.addWidget(self.model_up_btn)
        model_btns.addWidget(self.model_down_btn)
        model_btns.addStretch(1)
        left_layout.addWidget(model_btn_bar)

        # Right side: preview
        right_panel = QWidget()
        right_panel.setProperty('editorTransparentPanel', True)
        right_panel.setProperty('previewColumn', True)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        preview_label = QLabel('3D Preview')
        preview_label.setProperty('previewHeader', True)
        right_layout.addWidget(preview_label)

        self.models_preview = StlPreviewWidget()
        self.models_preview.setProperty('previewBody', True)
        right_layout.addWidget(self.models_preview, 1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([620, 420])

        m_layout.addWidget(splitter, 1)
        models_layout.addWidget(models_box, 1)
        self.tabs.addTab(models_tab, '3D Models')

        # -------------------------
        # BOTTOM BUTTONS
        # -------------------------
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton('CANCEL')
        self.save_btn = QPushButton('SAVE TOOL')
        self.cancel_btn.setProperty('panelActionButton', True)
        self.save_btn.setProperty('panelActionButton', True)
        self.save_btn.setProperty('primaryAction', True)
        add_shadow(self.cancel_btn)
        add_shadow(self.save_btn)
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self.accept)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.save_btn)
        root.addLayout(buttons)

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

    def _build_edit_field(self, title: str, editor: QWidget, key_label: QLabel | None = None) -> QFrame:
        frame = QFrame()
        frame.setProperty('editorFieldCard', True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        label = key_label if key_label is not None else QLabel(title)
        label.setProperty('detailFieldKey', True)
        label.setWordWrap(False)
        layout.addWidget(label)
        layout.addWidget(editor)
        return frame

    def _style_general_editor(self, editor: QWidget):
        f = editor.font()
        # Keep this subtle so tabs/tables still look balanced.
        f.setPointSizeF(max(11.5, f.pointSizeF() + 1.0))
        editor.setFont(f)
        if isinstance(editor, QLineEdit):
            editor.setMinimumHeight(44)
        elif isinstance(editor, QComboBox):
            editor.setMinimumHeight(44)

    def _make_arrow_button(self, icon_name: str, tooltip: str) -> QPushButton:
        btn = QPushButton('')
        btn.setProperty('arrowMoveButton', True)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        icon_path = TOOL_ICONS_DIR / icon_name
        btn.setIcon(QIcon(str(icon_path)))
        btn.setIconSize(QSize(18, 18))
        btn.setMinimumSize(32, 32)
        btn.setMaximumSize(32, 32)
        add_shadow(btn)
        return btn

    def _style_panel_action_button(self, btn: QPushButton):
        btn.setProperty('panelActionButton', True)
        add_shadow(btn)

    def _build_picker_row(self, editor: QLineEdit, handler, tooltip: str) -> QWidget:
        row = QWidget()
        row.setProperty('editorInlineRow', True)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(editor, 1)

        btn = self._make_arrow_button('menu_open.svg', tooltip)
        btn.clicked.connect(handler)
        lay.addWidget(btn)
        return row

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

            add_entry('holder', 'Holder', tool.get('holder_code', ''), tool.get('holder_link', ''), source)
            add_entry('holder-extra', 'Add. Element', tool.get('holder_add_element', ''), tool.get('holder_add_element_link', ''), source)
            cutting_name = (tool.get('cutting_type', 'Insert') or 'Insert').strip()
            add_entry('cutting', cutting_name, tool.get('cutting_code', ''), tool.get('cutting_link', ''), source)
            add_entry('cutting-extra', f'Add. {cutting_name}', tool.get('cutting_add_element', ''), tool.get('cutting_add_element_link', ''), source)

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
                        part.get('name', 'Part'),
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
            QMessageBox.information(self, 'Component picker', 'No matching components found in existing tools.')
            return None

        dlg = ComponentPickerDialog(title, entries, self)
        if dlg.exec() != QDialog.Accepted:
            return None
        return dlg.selected_entry()

    def _pick_holder_component(self):
        entry = self._open_component_picker('Select holder', ('holder', 'holder-extra'))
        if not entry:
            return
        self.holder_code.setText(entry.get('code', ''))
        self.holder_link.setText(entry.get('link', ''))

    def _pick_cutting_component(self):
        entry = self._open_component_picker('Select cutting component', ('cutting', 'cutting-extra'))
        if not entry:
            return
        self.cutting_code.setText(entry.get('code', ''))
        self.cutting_link.setText(entry.get('link', ''))

    def _pick_additional_part(self):
        entry = self._open_component_picker(
            'Select additional part',
            ('support',),
        )
        if not entry:
            return
        self.parts_table.add_empty_row([
            entry.get('name', 'Part'),
            entry.get('code', ''),
            entry.get('link', ''),
        ])

    def _apply_combobox_popup_style(self, combo: QComboBox):
        view = combo.view()
        view.setMouseTracking(True)
        view.viewport().setMouseTracking(True)
        view.setItemDelegate(BorderOnlyComboItemDelegate(view))
        pal = view.palette()
        pal.setColor(QPalette.Base, QColor('#FCFCFC'))
        pal.setColor(QPalette.Text, QColor('#000000'))
        pal.setColor(QPalette.Highlight, QColor('#FCFCFC'))
        pal.setColor(QPalette.HighlightedText, QColor('#000000'))
        view.setPalette(pal)
        view.setStyleSheet(
            "QListView {"
            " background: #FCFCFC;"
            " color: #000000;"
            " selection-background-color: #FCFCFC;"
            " selection-color: #000000;"
            " outline: none;"
            "}"
            "QListView::item {"
            " background: #FCFCFC;"
            " color: #000000;"
            " border: none;"
            " padding: 8px 12px;"
            "}"
        )

    def _reflow_general_fields(self, force: bool = False):
        if not hasattr(self, 'general_fields_grid'):
            return
        width = self.width()
        columns = 1
        if not force and columns == self._general_field_columns:
            return
        self._general_field_columns = columns

        sb = self.general_scroll.verticalScrollBar() if hasattr(self, 'general_scroll') else None
        old_scroll = sb.value() if sb is not None else 0

        while self.general_fields_grid.count():
            item = self.general_fields_grid.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        # Always lay out all field cards; hidden drill/mill cards stay hidden automatically.
        visible_fields = list(self._general_field_order)
        if columns == 1:
            for row, field in enumerate(visible_fields):
                self.general_fields_grid.addWidget(field, row, 0, 1, 2)
            if sb is not None:
                QTimer.singleShot(0, lambda s=sb, v=old_scroll: s.setValue(min(v, s.maximum())))
            return
        left_count = (len(visible_fields) + 1) // 2
        right_count = len(visible_fields) - left_count
        for i in range(left_count):
            self.general_fields_grid.addWidget(visible_fields[i], i, 0, 1, 2)
        for j in range(right_count):
            self.general_fields_grid.addWidget(visible_fields[left_count + j], j, 2, 1, 2)
        if sb is not None:
            QTimer.singleShot(0, lambda s=sb, v=old_scroll: s.setValue(min(v, s.maximum())))

    def _update_general_header(self):
        if not hasattr(self, 'editor_header_title'):
            return
        description = self.description.text().strip()
        tool_id = self.tool_id.text().strip()
        tool_type = self.tool_type.currentText().strip()
        self.editor_header_title.setText(description or 'New tool')
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

        btn = QPushButton("")
        btn.setFixedSize(24, 24)
        btn.setToolTip(color_hex)
        btn.setCursor(Qt.PointingHandCursor)

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color_hex};
                border: 1px solid #6e7a86;
                border-radius: 6px;
                padding: 0px;
            }}
            QPushButton:hover {{
                border: 1px solid #2d6fa3;
            }}
            QPushButton:pressed {{
                border: 1px solid #1f5f92;
            }}
        """)

        btn.clicked.connect(lambda _, r=row: self._choose_model_color(r))

        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(0)
        lay.addStretch(1)
        lay.addWidget(btn, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.model_table.setCellWidget(row, 2, wrap)

    def _choose_model_color(self, row: int):
        current = self._get_model_row_color(row)
        qcolor = QColor(current if current else '#9ea7b3')
        chosen = QColorDialog.getColor(qcolor, self, 'Select part color')
        if not chosen.isValid():
            return
        color_hex = chosen.name()
        self._set_color_button(row, color_hex)
        self._refresh_models_preview()

    def _get_model_row_color(self, row: int) -> str:
        widget = self.model_table.cellWidget(row, 2)
        if isinstance(widget, QPushButton):
            return widget.toolTip() or '#9ea7b3'
        if isinstance(widget, QWidget):
            btn = widget.findChild(QPushButton)
            if btn is not None:
                return btn.toolTip() or '#9ea7b3'
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
        return pretty.title() if pretty else 'Model'


    def _add_model_row(self, checked=False, values=None):
        if isinstance(checked, dict) and values is None:
            values = checked

        if values is None:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                'Select STL model',
                '',
                'STL Files (*.stl)'
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
            'Select STL model',
            '',
            'STL Files (*.stl)'
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
        value = self.cutting_type.currentText().strip() or 'Insert'
        self.cutting_code_label.setText(f'{value} code')

    def _update_tool_type_fields(self):
        # cutting component type is user-controlled and independent from tool type
        cutting_type = self.cutting_type.currentText().strip() or 'Insert'
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
        self.tool_type.setCurrentText(self.tool.get('tool_type', 'O.D Turning'))
        self.description.setText(self.tool.get('description', ''))
        self.geom_x.setText(str(self.tool.get('geom_x', '')))
        self.geom_z.setText(str(self.tool.get('geom_z', '')))
        self.radius.setText(str(self.tool.get('radius', '')))
        self.nose_corner_radius.setText(str(self.tool.get('nose_corner_radius', '')))
        self.holder_code.setText(self.tool.get('holder_code', ''))
        self.holder_link.setText(self.tool.get('holder_link', ''))
        self.holder_add_element.setText(self.tool.get('holder_add_element', ''))
        self.holder_add_element_link.setText(self.tool.get('holder_add_element_link', ''))
        self.cutting_type.setCurrentText(self.tool.get('cutting_type', 'Insert'))
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
            self.parts_table.add_empty_row([part.get('name', ''), part.get('code', ''), part.get('link', '')])

        # Load 3D model data from stl_path
        stl_data = self.tool.get('stl_path', '')
        model_parts = []

        if isinstance(stl_data, str) and stl_data.strip():
            try:
                parsed = json.loads(stl_data)
                if isinstance(parsed, list):
                    model_parts = parsed
                elif isinstance(parsed, str):
                    model_parts = [{'name': 'Model', 'file': parsed, 'color': '#9ea7b3'}]
            except Exception:
                model_parts = [{'name': 'Model', 'file': stl_data, 'color': '#9ea7b3'}]

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
            raise ValueError('Tool ID is required.')

        def parse_float(value, field_name):
            text = value.text().strip()
            if not text:
                return 0.0
            try:
                return float(text.replace(',', '.'))
            except ValueError:
                raise ValueError(f'{field_name} must be a number.')

        def parse_int(value, field_name):
            text = value.text().strip()
            if not text:
                return 0
            try:
                return int(text)
            except ValueError:
                raise ValueError(f'{field_name} must be an integer.')

        selected_cutting = self.cutting_type.currentText().strip() or 'Insert'
        selected_type = self.tool_type.currentText().strip() or 'O.D Turning'
        model_parts = self._model_table_to_parts()

        return {
            'id': tool_id,
            'tool_type': selected_type,
            'description': self.description.text().strip(),
            'geom_x': parse_float(self.geom_x, 'Geom X'),
            'geom_z': parse_float(self.geom_z, 'Geom Z'),
            'radius': parse_float(self.radius, 'Radius'),
            'nose_corner_radius': parse_float(self.nose_corner_radius, 'Nose R / Corner R'),
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
            'drill_nose_angle': parse_float(self.drill_nose_angle, 'Nose angle') if selected_cutting == 'Drill' else 0.0,
            'mill_cutting_edges': parse_int(self.mill_cutting_edges, 'Cutting edges') if selected_cutting == 'Mill' else 0,
            'support_parts': self._table_to_parts(self.parts_table, ['name', 'code', 'link']),
            'stl_path': json.dumps(model_parts) if model_parts else '',
        }