from typing import Callable
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
    QTableWidgetItem, QHeaderView, QTreeWidget, QTreeWidgetItem
)
from config import (
    MILLING_TOOL_TYPES,
    TURNING_TOOL_TYPES,
    JAW_MODELS_ROOT_DEFAULT,
    SHARED_UI_PREFERENCES_PATH,
    TOOL_ICONS_DIR,
    TOOL_MODELS_ROOT_DEFAULT,
)
from shared.data.model_paths import format_model_path_for_display, read_model_roots
from ui.widgets.parts_table import PartsTable
from ui.widgets.common import clear_focused_dropdown_on_outside_click, apply_shared_dropdown_style
from ui.shared.editor_dialog_helpers import EditorDialogMixin
from ui.shared.model_table_helpers import ModelTableMixin
from ui.tool_editor_support.components_tab import build_components_tab, build_spare_parts_tab
from ui.tool_editor_support.general_tab import build_general_tab
from ui.tool_editor_support.models_tab import build_models_tab
from ui.tool_editor_support import (
    ToolEditorPayloadCodec,
    build_tool_type_field_state,
    component_display_for_key,
    component_dropdown_values,
    is_mill_tool_type,
    is_turning_drill_tool_type,
    known_components_from_tools,
    compact_transform_dict,
    normalize_transform_dict,
)
from ui.tool_editor_support.component_picker_dialog import ComponentPickerDialog
from ui.tool_editor_support.component_linking_dialog import ComponentLinkingDialog
from ui.tool_editor_support.detail_layout_rules import build_tool_type_layout_update
from ui.tool_editor_support.measurement_rules import (
    normalize_distance_space,
    normalize_float_value,
    normalize_xyz_text,
)
from ui.tool_editor_support.spare_parts_table_coordinator import SparePartsTableCoordinator
from shared.ui.helpers.editor_helpers import (
    setup_editor_dialog,
    apply_host_visual_style,
    create_dialog_buttons,
    apply_secondary_button_theme,
    make_arrow_button,
    build_editor_field_card,
    build_picker_row,
)
from shared.ui.editor_launch_debug import editor_launch_diag_enabled, editor_launch_debug, editor_launch_id


class AddEditToolDialog(QDialog, EditorDialogMixin, ModelTableMixin):

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
        self.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.setWindowTitle(self._dialog_title())
        self.resize(1120, 760)
        self.setMinimumSize(900, 660)
        self.setModal(True)

        self.setUpdatesEnabled(False)
        try:
            setup_editor_dialog(self)
            if editor_launch_diag_enabled("BYPASS_HOST_STYLE"):
                editor_launch_debug("dialog.tool.host_style_bypassed", launch_id=editor_launch_id(self))
            else:
                from shared.ui.helpers.editor_helpers import apply_host_visual_style
                apply_host_visual_style(self, parent)

            self._init_editor_state()
            self._group_target_rows: list[int] = []
            self._general_field_columns = None
            self._turning_drill_geometry_mode = False
            self._spindle_orientation_mode = 'main'
            self._spare_parts_coordinator = None
            self._payload_codec = ToolEditorPayloadCodec(
                translate=self._t,
                localized_cutting_type=self._localized_cutting_type,
                tool_id_editor_value=self._tool_id_editor_value,
                tool_id_storage_value=self._tool_id_storage_value,
                turning_tool_types=TURNING_TOOL_TYPES,
                milling_tool_types=MILLING_TOOL_TYPES,
            )
            self._build_ui()
            self._install_local_event_filters()
            self._init_spare_parts_coordinator()
            self._load_tool()
            self._update_cutting_label()
            self._update_tool_type_fields()
            self._update_notes_editor_height()
            self._update_transform_row_sizes()
            for _child in self.findChildren(QWidget):
                _child.style().unpolish(_child)
                _child.style().polish(_child)
                _child.ensurePolished()
            self.layout().activate()
        finally:
            self.setUpdatesEnabled(True)
            self.setAttribute(Qt.WA_DontShowOnScreen, False)

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

    def _init_spare_parts_coordinator(self):
        """Initialize the spare parts table coordinator after UI is built."""
        if hasattr(self, 'spare_parts_table'):
            self._spare_parts_coordinator = SparePartsTableCoordinator(
                table=self.spare_parts_table,
                component_dropdown_values=self._component_dropdown_values,
                component_display_for_key=self._component_display_for_key,
                refresh_on_structure_change=lambda: self._refresh_measurement_part_dropdowns(),
            )

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            focused = QApplication.focusWidget()
            if focused is self.group_name_edit:
                self._apply_group_name()
                return True  # fully consume â€” prevent dialog default button from firing
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
        if self._spare_parts_coordinator:
            self._spare_parts_coordinator.schedule_refresh()

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
        if self._spare_parts_coordinator:
            self._spare_parts_coordinator.schedule_refresh()

    def _pick_spare_part(self):
        entry = self._open_component_picker(
            self._t('tool_editor.component.select_additional', 'Select additional part'),
            ('support',),
        )
        if not entry:
            return
        if self._spare_parts_coordinator:
            self._spare_parts_coordinator.add_spare_part_row(
                {
                    'name': entry.get('name', self._t('tool_library.field.part', 'Part')),
                    'code': entry.get('code', ''),
                    'link': entry.get('link', ''),
                    'component_key': '',
                    'group': '',
                }
            )

    # Backward-compatible hooks used by ToolEditorPayloadCodec.
    def _add_spare_part_row(self, part: dict | None = None):
        if self._spare_parts_coordinator:
            self._spare_parts_coordinator.add_spare_part_row(part or {})
            return
        payload = part or {}
        self.spare_parts_table.add_row_dict(
            {
                'name': (payload.get('name') or '').strip(),
                'code': (payload.get('code') or '').strip(),
                'link': (payload.get('link') or '').strip(),
                'linked_component': '',
                'group': (payload.get('group') or '').strip(),
            }
        )

    def _refresh_spare_component_dropdowns(self):
        if self._spare_parts_coordinator:
            self._spare_parts_coordinator.schedule_refresh()

    def _get_spare_component_key(self, row: int) -> str:
        if self._spare_parts_coordinator:
            return self._spare_parts_coordinator.get_component_key(row)
        return str(
            self.spare_parts_table.cell_user_data(row, 'linked_component', Qt.UserRole, '') or ''
        ).strip()

    def _component_dropdown_values(self):
        return component_dropdown_values(self.parts_table.row_dicts())

    def _component_display_for_key(self, key: str) -> str:
        return component_display_for_key(key, self.parts_table.row_dicts())

    def _remove_component_row(self):
        self.parts_table.remove_selected_row()
        if self._spare_parts_coordinator:
            self._spare_parts_coordinator.schedule_refresh()

    def _move_component_row(self, delta: int):
        self.parts_table.move_selected_row(delta)
        if self._spare_parts_coordinator:
            self._spare_parts_coordinator.schedule_refresh()

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

        dlg = ComponentLinkingDialog(
            options,
            preselected_key=self._selected_component_ref(),
            parent=self,
            translate=self._t,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        component_ref = dlg.selected_component_key()
        if not component_ref:
            return

        for row in selected_rows:
            if self._spare_parts_coordinator:
                self._spare_parts_coordinator.set_component_key(row, component_ref)
        if self._spare_parts_coordinator:
            self._spare_parts_coordinator.schedule_refresh()

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
        if self._spare_parts_coordinator:
            self._spare_parts_coordinator.schedule_refresh()

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
        editor_launch_debug(
            "dialog.tool.show_event",
            launch_id=editor_launch_id(self),
            visible=self.isVisible(),
            active=self.isActiveWindow(),
            title=self.windowTitle(),
        )
        self._ensure_on_screen()

    def paintEvent(self, event):
        first_paint = not bool(getattr(self, "_editor_launch_first_paint_logged", False))
        super().paintEvent(event)
        if first_paint:
            self._editor_launch_first_paint_logged = True
            editor_launch_debug(
                "dialog.tool.first_paint",
                launch_id=editor_launch_id(self),
                visible=self.isVisible(),
                active=self.isActiveWindow(),
                title=self.windowTitle(),
            )

    # -------------------------
    # MODEL TAB HELPERS  (provided by ModelTableMixin)
    # -------------------------
    def _tools_models_root(self):
        tools_models_root, _ = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            JAW_MODELS_ROOT_DEFAULT,
        )
        tools_models_root.mkdir(parents=True, exist_ok=True)
        return tools_models_root

    _models_root = _tools_models_root

    def _on_model_list_structure_changed(self):
        self._refresh_measurement_part_dropdowns()

    @staticmethod
    def _normalize_xyz_text(value) -> str:
        return normalize_xyz_text(value)

    @staticmethod
    def _normalize_float_value(value, default: float = 0.0) -> float:
        return normalize_float_value(value, default)

    @staticmethod
    def _normalize_distance_space(part_name, part_index, point_space) -> str:
        return normalize_distance_space(part_name, part_index, point_space)

    def _display_transform_for_index(self, index: int, transform: dict) -> dict:
        _ = index
        return normalize_transform_dict(transform)

    @staticmethod
    def _normalized_transform_dict(transform: dict) -> dict:
        return normalize_transform_dict(transform)

    @staticmethod
    def _compact_transform_dict(transform: dict) -> dict:
        return compact_transform_dict(transform)

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
        self._payload_codec.load_into_dialog(self, self.tool)

    def get_tool_data(self):
        return self._payload_codec.collect_from_dialog(self)

    def accept(self):
        self._accepted_tool_data = self.get_tool_data()
        super().accept()

    def get_accepted_tool_data(self) -> dict:
        """Return the data captured at accept() time — safe to call after dialog closes."""
        return dict(getattr(self, '_accepted_tool_data', {}))

