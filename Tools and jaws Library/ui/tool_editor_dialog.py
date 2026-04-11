import json
from typing import Callable
from PySide6.QtCore import QEvent, Qt, QTimer, QSize, QItemSelectionModel, QEventLoop
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
    QFileDialog, QTableWidgetItem, QHeaderView, QTreeWidget, QTreeWidgetItem
)
from config import (
    MILLING_TOOL_TYPES,
    TURNING_TOOL_TYPES,
    JAW_MODELS_ROOT_DEFAULT,
    SHARED_UI_PREFERENCES_PATH,
    TOOL_ICONS_DIR,
    TOOL_MODELS_ROOT_DEFAULT,
)
from shared.model_paths import format_model_path_for_display, read_model_roots
from ui.widgets.parts_table import PartsTable
from ui.measurement_editor_dialog import MeasurementEditorDialog
from ui.widgets.color_picker_dialog import ColorPickerDialog
from ui.widgets.common import clear_focused_dropdown_on_outside_click, apply_shared_dropdown_style
from ui.tool_editor_support.components_tab import build_components_tab, build_spare_parts_tab
from ui.tool_editor_support.general_tab import build_general_tab
from ui.tool_editor_support.models_tab import build_models_tab
from ui.tool_editor_support import (
    ToolEditorPayloadAdapter,
    all_part_transforms_payload,
    build_tool_type_field_state,
    compact_transform_dict,
    component_display_for_key,
    component_dropdown_values,
    is_mill_tool_type,
    is_turning_drill_tool_type,
    known_components_from_tools,
    normalize_transform_dict,
)
from ui.tool_editor_support.detail_layout_rules import build_tool_type_layout_update
from ui.tool_editor_support.measurement_rules import (
    empty_measurement_editor_state,
    measurement_overlays_from_state,
    normalize_distance_space,
    normalize_float_value,
    normalize_measurement_editor_state,
    normalize_xyz_text,
    parse_measurement_overlays,
)
from shared.editor_helpers import (
    setup_editor_dialog,
    create_dialog_buttons,
    apply_secondary_button_theme,
    make_arrow_button,
    focus_editor_widget,
    build_editor_field_card,
    build_editor_field_group,
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
        self._turning_drill_geometry_mode = False
        self._spindle_orientation_mode = 'main'
        self._suspend_preview_refresh = False
        self._spare_refresh_timer = QTimer(self)
        self._spare_refresh_timer.setSingleShot(True)
        self._spare_refresh_timer.setInterval(75)
        self._spare_refresh_timer.timeout.connect(self._refresh_spare_component_dropdowns)
        self._payload_adapter = ToolEditorPayloadAdapter(
            translate=self._t,
            localized_cutting_type=self._localized_cutting_type,
            tool_id_editor_value=self._tool_id_editor_value,
            tool_id_storage_value=self._tool_id_storage_value,
            turning_tool_types=TURNING_TOOL_TYPES,
            milling_tool_types=MILLING_TOOL_TYPES,
        )
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
    def _strip_tool_id_prefix(value: str) -> str:
        raw = str(value or '').strip()
        if raw.lower().startswith('t'):
            raw = raw[1:].strip()
        return ''.join(ch for ch in raw if ch.isdigit())

    @classmethod
    def _tool_id_storage_value(cls, value: str) -> str:
        stripped = cls._strip_tool_id_prefix(value)
        return f'T{stripped}' if stripped else ''

    @classmethod
    def _tool_id_display_value(cls, value: str) -> str:
        storage = cls._tool_id_storage_value(value)
        return storage if storage else ''

    @classmethod
    def _tool_id_editor_value(cls, value: str) -> str:
        return cls._strip_tool_id_prefix(value)

    def _localized_spindle_orientation(self, orientation: str) -> str:
        normalized = (orientation or 'main').strip().lower()
        if normalized in {'both', 'both spindles', 'main/sub'}:
            return self._t('tool_editor.spindle_orientation.both', 'Both spindles')
        if normalized in {'sub', 'sub spindle', 'subspindle'}:
            return self._t('tool_editor.spindle_orientation.sub', 'Sub spindle')
        return self._t('tool_editor.spindle_orientation.main', 'Main spindle')

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: str):
        target = (value or '').strip()
        for idx in range(combo.count()):
            if (combo.itemData(idx) or '').strip() == target:
                combo.setCurrentIndex(idx)
                return

    def _build_ui(self):
        root = QVBoxLayout(self)
        self._build_ui_modular(root)

    def _build_ui_modular(self, root: QVBoxLayout) -> None:
        """Build the editor through tab modules while keeping dialog-owned state."""
        self.tabs = QTabWidget()
        self.tabs.setObjectName('toolEditorTabs')
        self.tabs.currentChanged.connect(lambda _idx: self._commit_active_edits())
        root.addWidget(self.tabs, 1)

        # The dialog remains the controller; builder modules only construct
        # widgets and attach them back to ``self`` for the existing behavior.
        build_general_tab(self, self.tabs)
        build_components_tab(self, self.tabs)
        build_spare_parts_tab(self, self.tabs)
        build_models_tab(self, self.tabs)

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

        # The dialog-level event filter coordinates Enter handling, right-click
        # transform reset, and outside-click dropdown cleanup across tabs.
        QApplication.instance().installEventFilter(self)

        for le in [
            self.tool_id,
            self.description,
            self.geom_x,
            self.geom_z,
            self.b_axis_angle,
            self.radius,
            self.nose_corner_radius,
            self.holder_code,
            self.holder_link,
            self.holder_add_element,
            self.holder_add_element_link,
            self.cutting_code,
            self.cutting_link,
            self.cutting_add_element,
            self.cutting_add_element_link,
            self.drill_nose_angle,
            self.mill_cutting_edges,
            self.default_pot,
        ]:
            le.returnPressed.connect(le.clearFocus)

        self.tool_id.textChanged.connect(self._update_general_header)
        self.tool_id.textEdited.connect(self._normalize_tool_id_input)
        self.description.textChanged.connect(self._update_general_header)
        self.tool_type.currentTextChanged.connect(self._update_general_header)
        for numeric_editor in [
            self.geom_x,
            self.geom_z,
            self.radius,
            self.nose_corner_radius,
            self.drill_nose_angle,
            self.mill_cutting_edges,
        ]:
            numeric_editor.textEdited.connect(
                lambda text, editor=numeric_editor: self._normalize_decimal_comma_input(editor, text)
            )

        self._update_general_header()
        self._update_spindle_orientation_visibility()
        self._update_notes_editor_height()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            focused = QApplication.focusWidget()
            if focused is self.group_name_edit:
                self._apply_group_name()
                return True  # fully consume — prevent dialog default button from firing
            if focused is self.notes:
                if event.modifiers() & Qt.ShiftModifier:
                    return False
                focused.clearFocus()
                return True
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
        return build_editor_field_card(
            title,
            editor,
            key_label=key_label,
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

    def _style_combo(self, combo: QComboBox):
        apply_shared_dropdown_style(combo)
        self._configure_combo_popup(combo, max_rows=8, row_height=44)

    def _configure_combo_popup(self, combo: QComboBox, max_rows: int = 8, row_height: int = 44):
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
        self._update_spindle_orientation_visibility()

    def _toggle_tool_head(self, checked: bool):
        self.tool_head.setText(self._localized_tool_head('HEAD2' if checked else 'HEAD1'))
        self._update_spindle_orientation_visibility()
        self._update_tool_type_fields()

    def _get_tool_head_value(self) -> str:
        return 'HEAD2' if self.tool_head.isChecked() else 'HEAD1'

    def _set_spindle_orientation_value(self, orientation: str):
        normalized = (orientation or 'main').strip().lower().replace('_', ' ')
        if normalized in {'both', 'both spindles', 'main/sub'}:
            mode = 'both'
        elif normalized in {'sub', 'sub spindle', 'subspindle', 'counter spindle'}:
            mode = 'sub'
        else:
            mode = 'main'
        self._spindle_orientation_mode = mode
        self.spindle_orientation_btn.blockSignals(True)
        self.spindle_orientation_btn.setChecked(mode == 'sub')
        self.spindle_orientation_btn.setText(self._localized_spindle_orientation(mode))
        self.spindle_orientation_btn.blockSignals(False)

    def _toggle_spindle_orientation(self, checked: bool):
        self._spindle_orientation_mode = 'sub' if checked else 'main'
        self.spindle_orientation_btn.setText(self._localized_spindle_orientation(self._spindle_orientation_mode))

    def _set_spindle_orientation_both(self):
        self._spindle_orientation_mode = 'both'
        self.spindle_orientation_btn.blockSignals(True)
        self.spindle_orientation_btn.setChecked(False)
        self.spindle_orientation_btn.setText(self._localized_spindle_orientation('both'))
        self.spindle_orientation_btn.blockSignals(False)

    def _get_spindle_orientation_value(self) -> str:
        return self._spindle_orientation_mode if self._spindle_orientation_mode in {'main', 'sub', 'both'} else 'main'

    def _update_spindle_orientation_visibility(self):
        # Orientation is relevant for tools on Head 2.
        self.spindle_orientation_btn.setVisible(self._get_tool_head_value() == 'HEAD2')

    def _update_notes_editor_height(self):
        if not hasattr(self, 'notes'):
            return
        doc = self.notes.document()
        viewport_width = max(0, self.notes.viewport().width())
        if viewport_width > 0:
            doc.setTextWidth(viewport_width)
        doc_layout = doc.documentLayout()
        doc_height = float(doc_layout.documentSize().height()) if doc_layout is not None else 0.0
        line_height = max(16, self.notes.fontMetrics().lineSpacing())
        minimum_doc_height = float(line_height + 8)
        content_height = max(minimum_doc_height, doc_height)
        frame = self.notes.frameWidth() * 2
        target = max(30, min(220, int(round(content_height)) + frame + 4))
        self.notes.setFixedHeight(target)

    def _style_general_editor(self, editor: QWidget):
        pass

    def _make_arrow_button(self, icon_name: str, tooltip: str) -> QPushButton:
        icon_path = TOOL_ICONS_DIR / icon_name
        return make_arrow_button(icon_path, tooltip)

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
        return known_components_from_tools(
            tools,
            translate=self._t,
            localized_cutting_type=self._localized_cutting_type,
        )

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
        return component_dropdown_values(self.parts_table.row_dicts())

    def _component_display_for_key(self, key: str) -> str:
        return component_display_for_key(key, self.parts_table.row_dicts())

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
        self._configure_combo_popup(combo, max_rows=8, row_height=44)

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

        target_rows = [
            row
            for row in self._group_target_rows
            if 0 <= row < self.parts_table.rowCount()
        ]
        if not target_rows:
            target_rows = self._selected_component_rows()

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
        tool_id = self._tool_id_display_value(self.tool_id.text())
        tool_type = self.tool_type.currentText().strip()
        self.editor_header_title.setText(description or self._t('tool_editor.header.new_tool', 'New tool'))
        self.editor_header_id.setText(tool_id)
        self.editor_type_badge.setText(tool_type)

    def _normalize_tool_id_input(self, text: str):
        digits = self._tool_id_editor_value(text)
        if text == digits:
            return
        self.tool_id.blockSignals(True)
        self.tool_id.setText(digits)
        self.tool_id.blockSignals(False)
        self.tool_id.setCursorPosition(len(digits))

    def _normalize_decimal_comma_input(self, editor: QLineEdit, text: str):
        if ',' not in text:
            return
        cursor_pos = editor.cursorPosition()
        normalized = text.replace(',', '.')
        editor.blockSignals(True)
        editor.setText(normalized)
        editor.blockSignals(False)
        editor.setCursorPosition(min(len(normalized), cursor_pos))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_general_fields()
        self._update_notes_editor_height()
        self._update_transform_row_sizes()
        self._ensure_on_screen()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._ensure_on_screen()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._update_notes_editor_height)
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
        return empty_measurement_editor_state()

    @staticmethod
    def _normalize_xyz_text(value) -> str:
        return normalize_xyz_text(value)

    @staticmethod
    def _normalize_float_value(value, default: float = 0.0) -> float:
        return normalize_float_value(value, default)

    @staticmethod
    def _normalize_distance_space(part_name, part_index, point_space) -> str:
        return normalize_distance_space(part_name, part_index, point_space)

    def _normalize_measurement_editor_state(self, tool_data):
        return normalize_measurement_editor_state(tool_data)

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
        self._part_transforms[index] = compact_transform_dict(
            normalize_transform_dict(transform)
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

    def _saved_transform_for_index(self, index: int) -> dict:
        return normalize_transform_dict(self._saved_part_transforms.get(index, {}))

    def _display_transform_for_index(self, index: int, transform: dict) -> dict:
        _ = index  # keep index arg for future per-part display modes
        return normalize_transform_dict(transform)

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
            compact = compact_transform_dict(normalize_transform_dict(raw))
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
                self._part_transforms[idx] = compact_transform_dict(baseline)
            self.models_preview.set_part_transforms(
                all_part_transforms_payload(self._part_transforms, self.model_table.rowCount())
            )
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
        t = normalize_transform_dict(self._part_transforms.get(index, {}))
        if self._current_transform_mode == 'translate':
            t['x'] = vx
            t['y'] = vy
            t['z'] = vz
        else:
            t['rx'] = vx
            t['ry'] = vy
            t['rz'] = vz
        self._part_transforms[index] = compact_transform_dict(t)
        self.models_preview.set_part_transforms(
            all_part_transforms_payload(self._part_transforms, self.model_table.rowCount())
        )

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
            self._configure_combo_popup(combo, max_rows=8, row_height=44)
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

    def _load_measurement_overlays(self, overlays):
        # Compatibility-sensitive: parser preserves legacy overlay shape but
        # centralizes migration/default rules in one support module.
        self._measurement_editor_state = parse_measurement_overlays(overlays)
        self._update_measurement_summary_label()

    def _measurement_overlays_from_tables(self):
        return measurement_overlays_from_state(
            self._measurement_editor_state,
            translate=lambda key, default: self._t(key, default),
        )

    # -------------------------
    # EXISTING HELPERS
    # -------------------------
    def _update_cutting_label(self):
        raw_value = (self.cutting_type.currentData() or self.cutting_type.currentText() or 'Insert').strip() or 'Insert'
        localized = self._localized_cutting_type(raw_value)
        self.cutting_code_label.setText(self._t('tool_library.field.cutting_code', '{cutting_type} code', cutting_type=localized))

    @staticmethod
    def _is_turning_drill_tool_type(raw_tool_type: str) -> bool:
        return is_turning_drill_tool_type(raw_tool_type)

    @staticmethod
    def _is_mill_tool_type(raw_tool_type: str) -> bool:
        return is_mill_tool_type(raw_tool_type, MILLING_TOOL_TYPES)

    def _update_tool_type_fields(self):
        field_state = build_tool_type_field_state(
            selected_type=(self.tool_type.currentData() or self.tool_type.currentText() or 'O.D Turning').strip() or 'O.D Turning',
            cutting_type=(self.cutting_type.currentData() or self.cutting_type.currentText() or 'Insert').strip() or 'Insert',
            selected_head=self._get_tool_head_value(),
            turning_tool_types=TURNING_TOOL_TYPES,
            milling_tool_types=MILLING_TOOL_TYPES,
        )

        layout_update = build_tool_type_layout_update(
            field_state,
            turning_drill_geometry_mode=self._turning_drill_geometry_mode,
            drill_nose_angle_text=self.drill_nose_angle.text(),
            nose_corner_radius_text=self.nose_corner_radius.text(),
        )
        if layout_update.copy_drill_angle_to_corner is not None:
            self.nose_corner_radius.setText(layout_update.copy_drill_angle_to_corner)
        if layout_update.copy_corner_angle_to_drill is not None:
            self.drill_nose_angle.setText(layout_update.copy_corner_angle_to_drill)
        self._turning_drill_geometry_mode = layout_update.next_turning_drill_geometry_mode
        self.corner_or_nose_label.setText(
            self._t(layout_update.corner_label_key, layout_update.corner_label_fallback)
        )

        self.corner_or_nose_field.setVisible(field_state.show_corner_or_nose)
        self.drill_field.setVisible(field_state.show_drill_field)
        self.mill_field.setVisible(field_state.show_mill_field)
        self.radius_field.setVisible(field_state.show_radius)
        self.b_axis_field.setVisible(field_state.show_b_axis)

        self._update_spindle_orientation_visibility()
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
        self._payload_adapter.load_into_dialog(self, self.tool)
        QTimer.singleShot(0, self._update_notes_editor_height)
        if self._assembly_transform_enabled:
            QTimer.singleShot(0, lambda: self._request_preview_transform_snapshot(refresh_selection=True))

    def get_tool_data(self):
        return self._payload_adapter.collect_from_dialog(self)
