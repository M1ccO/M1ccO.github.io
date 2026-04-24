import json
from typing import Callable

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QTextEdit,
)

from config import JAW_MODELS_ROOT_DEFAULT, SHARED_UI_PREFERENCES_PATH, TOOL_ICONS_DIR, TOOL_MODELS_ROOT_DEFAULT
from shared.ui.helpers.editor_helpers import (
    apply_host_visual_style,
    apply_secondary_button_theme,
    build_editor_field_card,
    create_dialog_buttons,
    setup_editor_dialog,
)
from shared.ui.editor_launch_debug import editor_launch_diag_enabled, editor_launch_debug, editor_launch_id
from shared.data.model_paths import format_model_path_for_display, read_model_roots
from ui.jaw_editor_support import build_models_tab
from ui.jaw_page_support.preview_rules import apply_jaw_preview_transform
from ui.shared.editor_dialog_helpers import EditorDialogMixin
from ui.shared.model_table_helpers import ModelTableMixin
from ui.tool_editor_support.transform_rules import (
    compact_transform_dict,
    normalize_transform_dict,
)
from ui.widgets.common import apply_shared_dropdown_style, clear_focused_dropdown_on_outside_click


class AddEditJawDialog(QDialog, EditorDialogMixin, ModelTableMixin):
    JAW_TYPES = ['Soft jaws', 'Hard jaws', 'Spiked jaws', 'Special jaws']
    SPINDLE_SIDES = ['Main spindle', 'Sub spindle', 'Both']

    def __init__(
        self,
        parent=None,
        jaw=None,
        translate: Callable[[str, str | None], str] | None = None,
        batch_label: str | None = None,
        group_edit_mode: bool = False,
        group_count: int | None = None,
    ):
        super().__init__(parent)
        self.jaw = jaw or {}
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self._batch_label = (batch_label or '').strip()
        self._group_edit_mode = bool(group_edit_mode)
        self._group_count = int(group_count or 0)
        self._general_field_columns = None
        self.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.setWindowTitle(self._dialog_title())
        self.resize(1120, 760)
        self.setMinimumSize(900, 660)
        self.setModal(True)

        self.setUpdatesEnabled(False)
        try:
            if editor_launch_diag_enabled("BYPASS_HOST_STYLE"):
                editor_launch_debug("dialog.jaw.host_style_bypassed", launch_id=editor_launch_id(self))
            else:
                # Adopt host style early so background is themed on first paint.
                from shared.ui.helpers.editor_helpers import apply_host_visual_style
                apply_host_visual_style(self, parent)

            self._init_editor_state()

            setup_editor_dialog(self)
            self._build_ui()
            self._install_local_event_filters()
            self._load_jaw()
            self._update_transform_row_sizes()
            if hasattr(self, 'notes'):
                if isinstance(self.notes, QTextEdit):
                    self._update_notes_editor_height()

            # DEEP POLISH: Ensure all child widgets have the correct stylesheet/palette applied 
            # before the window is ever shown, preventing the white flash.
            for widget in self.findChildren(QWidget):
                widget.ensurePolished()
        finally:
            self.setUpdatesEnabled(True)
            self.setAttribute(Qt.WA_DontShowOnScreen, False)


    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _dialog_title(self) -> str:
        if self._group_edit_mode:
            if self._group_count > 1:
                return self._t(
                    'jaw_editor.window_title.group',
                    'Group Edit ({count} items)',
                    count=self._group_count,
                )
            return self._t('jaw_editor.window_title.group', 'Group Edit')
        jaw_id = self.jaw.get('jaw_id', '').strip()
        if jaw_id:
            base = self._t('jaw_editor.window_title.edit', 'Edit Jaw - {jaw_id}', jaw_id=jaw_id)
        else:
            base = self._t('jaw_editor.window_title.add', 'Add Jaw')
        if self._batch_label:
            return f"{base} ({self._batch_label})"
        return base

    def _localized_jaw_type(self, raw: str) -> str:
        normalized = (raw or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.jaw_type.{normalized}', raw)

    def _localized_spindle_side(self, raw: str) -> str:
        normalized = (raw or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.spindle_side.{normalized}', raw)

    def _build_ui(self):
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_general_tab(), self._t('jaw_editor.tab.general', 'General'))
        build_models_tab(self, self.tabs)

        self._dialog_buttons = create_dialog_buttons(
            self,
            save_text=self._t('jaw_editor.action.save_jaw', 'SAVE JAW'),
            cancel_text=self._t('common.cancel', 'Cancel').upper(),
            on_save=self.accept,
            on_cancel=self.reject,
        )
        self._save_btn = self._dialog_buttons.button(QDialogButtonBox.Save)
        root.addWidget(self._dialog_buttons)
        apply_secondary_button_theme(self, self._save_btn)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            clear_focused_dropdown_on_outside_click(obj, self)
        if obj is getattr(self, '_reset_transform_btn', None):
            if event.type() == QEvent.MouseButtonPress and hasattr(event, 'button') and event.button() == Qt.RightButton:
                self._reset_current_part_transform(target='saved')
                return True
        return super().eventFilter(obj, event)

    def _build_general_tab(self):
        tab = QWidget()
        tab.setProperty('editorPageSurface', True)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        self.general_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(scroll, 1)

        general_content = QWidget()
        general_content.setProperty('editorFieldsViewport', True)
        general_content.setProperty('editorPageSurface', True)
        general_content_layout = QVBoxLayout(general_content)
        general_content_layout.setContentsMargins(0, 0, 0, 0)
        general_content_layout.setSpacing(0)
        scroll.setWidget(general_content)

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
        self.header_title = QLabel(self._t('jaw_editor.header.new_jaw', 'New jaw'))
        self.header_title.setProperty('detailHeroTitle', True)
        self.header_title.setWordWrap(True)
        self.header_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.header_id = QLabel('')
        self.header_id.setProperty('detailHeroTitle', True)
        self.header_id.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title_row.addWidget(self.header_title, 1)
        title_row.addWidget(self.header_id, 0, Qt.AlignRight)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        self.type_badge = QLabel('')
        self.type_badge.setProperty('toolBadge', True)
        meta_row.addWidget(self.type_badge, 0, Qt.AlignLeft)
        meta_row.addStretch(1)

        header_layout.addLayout(title_row)
        header_layout.addLayout(meta_row)
        form_layout.addWidget(header)

        self.jaw_id = QLineEdit()
        self.jaw_type = QComboBox()
        for raw_type in self.JAW_TYPES:
            self.jaw_type.addItem(self._localized_jaw_type(raw_type), raw_type)
        self.spindle_side = QComboBox()
        for raw_side in self.SPINDLE_SIDES:
            self.spindle_side.addItem(self._localized_spindle_side(raw_side), raw_side)
        self.clamping_diameter_text = QLineEdit()
        self.clamping_length = QLineEdit()
        self.turning_washer = QLineEdit()
        self.last_modified = QLineEdit()
        self.notes = QLineEdit()

        self.clamping_diameter_text.setPlaceholderText(self._t('jaw_editor.placeholder.clamping_diameter', '52.40 mm or 50-58 mm'))
        self.clamping_length.setPlaceholderText(self._t('jaw_editor.placeholder.clamping_length', 'e.g. 24.0 mm'))

        self._style_combo(self.jaw_type)
        self._style_combo(self.spindle_side)
        self.jaw_type.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.jaw_type.setMinimumWidth(180)
        self.spindle_side.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.spindle_side.setMinimumWidth(180)

        group1 = self._build_field_group([
            self._build_edit_field(self._t('jaw_library.field.jaw_id', 'Jaw ID'), self.jaw_id),
            self._build_edit_field(self._t('jaw_library.field.jaw_type', 'Jaw type'), self.jaw_type),
            self._build_edit_field(self._t('jaw_library.field.spindle_side', 'Spindle side'), self.spindle_side),
        ])
        group2 = self._build_field_group([
            self._build_edit_field(self._t('jaw_library.field.clamping_diameter', 'Clamping diameter'), self.clamping_diameter_text),
            self._build_edit_field(self._t('jaw_library.field.clamping_length', 'Clamping length'), self.clamping_length),
            self._build_edit_field(self._t('jaw_library.field.turning_ring', 'Turning ring'), self.turning_washer),
        ])
        self._last_modified_field = self._build_edit_field(self._t('jaw_library.field.last_modified', 'Last modified'), self.last_modified)
        group3 = self._build_field_group([
            self._last_modified_field,
            self._build_edit_field(self._t('jaw_library.field.notes', 'Notes'), self.notes),
        ])

        form_layout.addWidget(group1)
        form_layout.addWidget(group2)
        form_layout.addWidget(group3)
        general_content_layout.addWidget(form_frame)
        general_content_layout.addStretch(1)

        self.jaw_id.textChanged.connect(self._update_header)
        self.jaw_type.currentTextChanged.connect(self._update_header)
        self.jaw_type.currentTextChanged.connect(self._update_spiked_fields)
        self._update_header()
        self._update_spiked_fields()
        return tab

    def _update_spiked_fields(self):
        is_spiked = (self.jaw_type.currentData() or '') == 'Spiked jaws'
        self._last_modified_field.setVisible(not is_spiked)

    def _build_edit_field(self, title: str, editor: QWidget) -> QFrame:
        return build_editor_field_card(
            title,
            editor,
            label_min_width=200,
            label_max_width=200,
            label_word_wrap=True,
            label_top_align=True,
            focus_handler=self._focus_editor,
        )

    def _style_combo(self, combo: QComboBox):
        apply_shared_dropdown_style(combo)

    def _update_header(self):
        jaw_id = self.jaw_id.text().strip()
        self.header_title.setText(
            self._t('jaw_editor.header.new_jaw', 'New jaw')
            if not jaw_id
            else self._t('jaw_editor.header.jaw_with_id', 'Jaw {jaw_id}', jaw_id=jaw_id)
        )
        self.header_id.setText(jaw_id)
        self.type_badge.setText(self.jaw_type.currentText())

    def _load_jaw(self):
        self._preview_orientation_applied = False
        if not self.jaw:
            self._update_measurement_summary_label()
            return
        self.jaw_id.setText(self.jaw.get('jaw_id', ''))
        self._set_combo_by_data(self.jaw_type, self.jaw.get('jaw_type', 'Soft jaws'))
        self._set_combo_by_data(self.spindle_side, self.jaw.get('spindle_side', 'Main spindle'))
        self.clamping_diameter_text.setText(self.jaw.get('clamping_diameter_text', ''))
        self.clamping_length.setText(self.jaw.get('clamping_length', ''))
        self.turning_washer.setText(self.jaw.get('turning_washer', ''))
        self.last_modified.setText(self.jaw.get('last_modified', ''))
        self.notes.setText(self.jaw.get('notes', ''))

        raw_models = self.jaw.get('stl_path', '')
        model_parts = []
        if isinstance(raw_models, list):
            model_parts = raw_models
        elif isinstance(raw_models, str) and raw_models.strip():
            try:
                parsed = json.loads(raw_models)
                if isinstance(parsed, list):
                    model_parts = parsed
                elif isinstance(parsed, str):
                    model_parts = [{'name': self._t('tool_editor.model.default_name', 'Model'), 'file': parsed, 'color': '#9ea7b3'}]
            except Exception:
                model_parts = [{'name': self._t('tool_editor.model.default_name', 'Model'), 'file': raw_models, 'color': '#9ea7b3'}]

        self._suspend_preview_refresh = True
        try:
            for part in model_parts:
                if not isinstance(part, dict):
                    continue
                self._add_model_row(
                    {
                        'name': str(part.get('name', '') or ''),
                        'file': str(part.get('file', '') or ''),
                        'color': str(part.get('color', '') or ''),
                    }
                )
        finally:
            self._suspend_preview_refresh = False

        self._part_transforms = {}
        self._saved_part_transforms = {}
        for index, part in enumerate(model_parts):
            if not isinstance(part, dict):
                continue
            transform = {
                'x': part.get('offset_x', 0),
                'y': part.get('offset_y', 0),
                'z': part.get('offset_z', 0),
                'rx': part.get('rot_x', 0),
                'ry': part.get('rot_y', 0),
                'rz': part.get('rot_z', 0),
            }
            compact = compact_transform_dict(normalize_transform_dict(transform))
            if compact:
                self._part_transforms[index] = dict(compact)
                self._saved_part_transforms[index] = dict(compact)

        self._load_measurement_overlays(self.jaw.get('measurement_overlays', []))

        selected_parts = []
        raw_selected_parts = self.jaw.get('preview_selected_parts', [])
        if isinstance(raw_selected_parts, str):
            try:
                raw_selected_parts = json.loads(raw_selected_parts)
            except Exception:
                raw_selected_parts = []
        if isinstance(raw_selected_parts, list):
            for value in raw_selected_parts:
                try:
                    idx = int(value)
                except Exception:
                    continue
                if idx >= 0:
                    selected_parts.append(idx)
        if not selected_parts:
            try:
                one = int(self.jaw.get('preview_selected_part', -1) or -1)
            except Exception:
                one = -1
            if one >= 0:
                selected_parts = [one]
        self._selected_part_indices = selected_parts
        self._selected_part_index = selected_parts[-1] if selected_parts else -1

        mode = str(self.jaw.get('preview_transform_mode', 'translate') or 'translate').strip().lower()
        self._current_transform_mode = mode if mode in {'translate', 'rotate'} else 'translate'
        self._fine_transform_enabled = bool(self.jaw.get('preview_fine_transform', False))

        self._refresh_models_preview()
        self._update_mode_toggle_button_appearance()
        self._update_fine_transform_button_appearance()
        self._refresh_transform_selection_state()
        if self._assembly_transform_enabled and self._selected_part_indices:
            self.models_preview.select_parts(self._selected_part_indices)
        self._update_header()

    def _refresh_models_preview(self):
        self._preview_controller.refresh_models_preview()
        if self.jaw and hasattr(self.models_preview, 'set_alignment_plane') and not getattr(self, '_preview_orientation_applied', False):
            apply_jaw_preview_transform(self.models_preview, self.jaw)
            self._preview_orientation_applied = True

    # ------------------------------------------------------------------
    # Model-table helpers  (provided by ModelTableMixin)
    # ------------------------------------------------------------------
    def _jaws_models_root(self):
        _, jaws_models_root = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            JAW_MODELS_ROOT_DEFAULT,
        )
        jaws_models_root.mkdir(parents=True, exist_ok=True)
        return jaws_models_root

    _models_root = _jaws_models_root

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ensure_on_screen()

    def showEvent(self, event):
        super().showEvent(event)
        editor_launch_debug(
            "dialog.jaw.show_event",
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
                "dialog.jaw.first_paint",
                launch_id=editor_launch_id(self),
                visible=self.isVisible(),
                active=self.isActiveWindow(),
                title=self.windowTitle(),
            )

    def moveEvent(self, event):
        super().moveEvent(event)
        self._ensure_on_screen()

    def get_jaw_data(self):
        self._sync_preview_transform_snapshot_for_save()
        parts = self._model_table_to_parts()

        preview = getattr(self, 'models_preview', None)
        preview_plane = 'XZ'
        preview_rot_x = preview_rot_y = preview_rot_z = 0
        if preview is not None and hasattr(preview, '_alignment_plane'):
            preview_plane = preview._alignment_plane or 'XZ'
            rot = getattr(preview, '_rotation_deg', {})
            preview_rot_x = int(rot.get('x', 0) or 0)
            preview_rot_y = int(rot.get('y', 0) or 0)
            preview_rot_z = int(rot.get('z', 0) or 0)
        elif self.jaw:
            preview_plane = (self.jaw.get('preview_plane', '') or 'XZ').strip()
            preview_rot_x = int(self.jaw.get('preview_rot_x', 0) or 0)
            preview_rot_y = int(self.jaw.get('preview_rot_y', 0) or 0)
            preview_rot_z = int(self.jaw.get('preview_rot_z', 0) or 0)

        jaw = {
            'jaw_id': self.jaw_id.text().strip(),
            'jaw_type': self.jaw_type.currentData() or self.jaw_type.currentText(),
            'spindle_side': self.spindle_side.currentData() or self.spindle_side.currentText(),
            'clamping_diameter_text': self.clamping_diameter_text.text().strip(),
            'clamping_length': self.clamping_length.text().strip(),
            'used_in_work': '',
            'turning_washer': self.turning_washer.text().strip(),
            'last_modified': self.last_modified.text().strip(),
            'notes': self.notes.text().strip(),
            'stl_path': json.dumps(parts) if parts else '',
            'measurement_overlays': self._measurement_overlays_from_tables(),
            'preview_plane': preview_plane,
            'preview_rot_x': preview_rot_x,
            'preview_rot_y': preview_rot_y,
            'preview_rot_z': preview_rot_z,
            'preview_selected_part': self._selected_part_index,
            'preview_selected_parts': [idx for idx in self._selected_part_indices if isinstance(idx, int) and idx >= 0],
            'preview_transform_mode': self._current_transform_mode,
            'preview_fine_transform': bool(self._fine_transform_enabled),
        }

        if not jaw['jaw_id'] and not self._group_edit_mode:
            raise ValueError(self._t('jaw_editor.error.jaw_id_required', 'Jaw ID is required.'))
        if jaw['jaw_type'] not in self.JAW_TYPES:
            raise ValueError(self._t('jaw_editor.error.jaw_type_invalid', 'Jaw type is invalid.'))
        if jaw['spindle_side'] not in self.SPINDLE_SIDES:
            raise ValueError(self._t('jaw_editor.error.spindle_side_invalid', 'Spindle side is invalid.'))
        return jaw

    def accept(self):
        try:
            self._accepted_jaw_data = self.get_jaw_data()
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))
            return
        super().accept()

    def get_accepted_jaw_data(self) -> dict:
        """Return the data captured at accept() time — safe to call after dialog closes."""
        return dict(getattr(self, '_accepted_jaw_data', {}))

