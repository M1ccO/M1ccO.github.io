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
)

# NOTE: FIXTURE_MODELS_ROOT_DEFAULT will be added to config.py by the parent task;
# until then this import will fail at runtime.
from config import FIXTURE_MODELS_ROOT_DEFAULT, SHARED_UI_PREFERENCES_PATH, TOOL_ICONS_DIR, TOOL_MODELS_ROOT_DEFAULT
from shared.ui.helpers.editor_helpers import (
    apply_secondary_button_theme,
    build_editor_field_card,
    create_dialog_buttons,
    setup_editor_dialog,
)
from shared.data.model_paths import format_model_path_for_display, read_model_roots
from ui.fixture_editor_support import build_models_tab
from ui.shared.editor_dialog_helpers import EditorDialogMixin
from ui.shared.model_table_helpers import ModelTableMixin
from ui.tool_editor_support.transform_rules import (
    compact_transform_dict,
    normalize_transform_dict,
)
from ui.widgets.common import apply_shared_dropdown_style, clear_focused_dropdown_on_outside_click


class AddEditFixtureDialog(QDialog, EditorDialogMixin, ModelTableMixin):
    # Fixtures use a free-text `fixture_type` (user-defined) instead of a
    # fixed list. `fixture_kind` is constrained to 'Part' or 'Assembly'.
    FIXTURE_KINDS = ['Part', 'Assembly']

    def __init__(
        self,
        parent=None,
        fixture=None,
        translate: Callable[[str, str | None], str] | None = None,
        batch_label: str | None = None,
        group_edit_mode: bool = False,
        group_count: int | None = None,
    ):
        super().__init__(parent)
        self.fixture = fixture or {}
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self._batch_label = (batch_label or '').strip()
        self._group_edit_mode = bool(group_edit_mode)
        self._group_count = int(group_count or 0)
        self._general_field_columns = None

        self._init_editor_state()

        self.setWindowTitle(self._dialog_title())
        self.resize(1120, 760)
        self.setMinimumSize(900, 660)
        self.setModal(True)
        setup_editor_dialog(self)
        self._build_ui()
        self._install_local_event_filters()
        self._load_fixture()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _dialog_title(self) -> str:
        if self._group_edit_mode:
            if self._group_count > 1:
                return self._t(
                    'fixture_editor.window_title.group',
                    'Group Edit ({count} items)',
                    count=self._group_count,
                )
            return self._t('fixture_editor.window_title.group', 'Group Edit')
        fixture_id = self.fixture.get('fixture_id', '').strip()
        if fixture_id:
            base = self._t('fixture_editor.window_title.edit', 'Edit Fixture - {fixture_id}', fixture_id=fixture_id)
        else:
            base = self._t('fixture_editor.window_title.add', 'Add Fixture')
        if self._batch_label:
            return f"{base} ({self._batch_label})"
        return base

    def _localized_fixture_kind(self, raw: str) -> str:
        normalized = (raw or '').strip().lower().replace(' ', '_')
        return self._t(f'fixture_library.fixture_kind.{normalized}', raw)

    def _build_ui(self):
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_general_tab(), self._t('fixture_editor.tab.general', 'General'))
        build_models_tab(self, self.tabs)

        self._dialog_buttons = create_dialog_buttons(
            self,
            save_text=self._t('fixture_editor.action.save_fixture', 'SAVE FIXTURE'),
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
        self.header_title = QLabel(self._t('fixture_editor.header.new_fixture', 'New fixture'))
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

        self.fixture_id = QLineEdit()
        # fixture_type is a free-text, user-defined value.
        self.fixture_type = QLineEdit()
        self.fixture_type.setPlaceholderText(
            self._t('fixture_editor.placeholder.fixture_type', 'e.g. Vise, Collet, Custom...')
        )
        self.fixture_kind = QComboBox()
        for raw_kind in self.FIXTURE_KINDS:
            self.fixture_kind.addItem(self._localized_fixture_kind(raw_kind), raw_kind)
        self.last_modified = QLineEdit()
        self.notes = QLineEdit()

        self._style_combo(self.fixture_kind)
        self.fixture_type.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.fixture_type.setMinimumWidth(180)
        self.fixture_kind.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.fixture_kind.setMinimumWidth(180)

        group1 = self._build_field_group([
            self._build_edit_field(self._t('fixture_library.field.fixture_id', 'Fixture ID'), self.fixture_id),
            self._build_edit_field(self._t('fixture_library.field.fixture_type', 'Fixture type'), self.fixture_type),
            self._build_edit_field(self._t('fixture_library.field.fixture_kind', 'Fixture kind'), self.fixture_kind),
        ])
        self._last_modified_field = self._build_edit_field(self._t('fixture_library.field.last_modified', 'Last modified'), self.last_modified)
        group3 = self._build_field_group([
            self._last_modified_field,
            self._build_edit_field(self._t('fixture_library.field.notes', 'Notes'), self.notes),
        ])

        form_layout.addWidget(group1)
        form_layout.addWidget(group3)
        general_content_layout.addWidget(form_frame)
        general_content_layout.addStretch(1)

        self.fixture_id.textChanged.connect(self._update_header)
        self.fixture_type.textChanged.connect(self._update_header)
        self._update_header()
        return tab

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
        fixture_id = self.fixture_id.text().strip()
        self.header_title.setText(
            self._t('fixture_editor.header.new_fixture', 'New fixture')
            if not fixture_id
            else self._t('fixture_editor.header.fixture_with_id', 'Fixture {fixture_id}', fixture_id=fixture_id)
        )
        self.header_id.setText(fixture_id)
        self.type_badge.setText(self.fixture_type.text())

    def _load_fixture(self):
        if not self.fixture:
            self._update_measurement_summary_label()
            return
        self.fixture_id.setText(self.fixture.get('fixture_id', ''))
        self.fixture_type.setText(self.fixture.get('fixture_type', ''))
        self._set_combo_by_data(self.fixture_kind, self.fixture.get('fixture_kind', 'Part'))
        self.last_modified.setText(self.fixture.get('last_modified', ''))
        self.notes.setText(self.fixture.get('notes', ''))

        raw_models = self.fixture.get('stl_path', '')
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

        self._load_measurement_overlays(self.fixture.get('measurement_overlays', []))

        selected_parts = []
        raw_selected_parts = self.fixture.get('preview_selected_parts', [])
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
                one = int(self.fixture.get('preview_selected_part', -1) or -1)
            except Exception:
                one = -1
            if one >= 0:
                selected_parts = [one]
        self._selected_part_indices = selected_parts
        self._selected_part_index = selected_parts[-1] if selected_parts else -1

        mode = str(self.fixture.get('preview_transform_mode', 'translate') or 'translate').strip().lower()
        self._current_transform_mode = mode if mode in {'translate', 'rotate'} else 'translate'
        self._fine_transform_enabled = bool(self.fixture.get('preview_fine_transform', False))

        self._refresh_models_preview()
        self._update_mode_toggle_button_appearance()
        self._update_fine_transform_button_appearance()
        self._refresh_transform_selection_state()
        if self._assembly_transform_enabled and self._selected_part_indices:
            self.models_preview.select_parts(self._selected_part_indices)
        self._update_header()

    # ------------------------------------------------------------------
    # Model-table helpers  (provided by ModelTableMixin)
    # ------------------------------------------------------------------
    def _fixtures_models_root(self):
        _, fixtures_models_root = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            FIXTURE_MODELS_ROOT_DEFAULT,
        )
        fixtures_models_root.mkdir(parents=True, exist_ok=True)
        return fixtures_models_root

    _models_root = _fixtures_models_root

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_transform_row_sizes()
        self._ensure_on_screen()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_transform_row_sizes()
        self._ensure_on_screen()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._ensure_on_screen()

    def get_fixture_data(self):
        self._sync_preview_transform_snapshot_for_save()
        parts = self._model_table_to_parts()
        fixture = {
            'fixture_id': self.fixture_id.text().strip(),
            'fixture_type': self.fixture_type.text().strip(),
            'fixture_kind': self.fixture_kind.currentData() or self.fixture_kind.currentText(),
            'clamping_diameter_text': '',
            'clamping_length': '',
            'used_in_work': '',
            'turning_washer': '',
            'last_modified': self.last_modified.text().strip(),
            'notes': self.notes.text().strip(),
            'stl_path': json.dumps(parts) if parts else '',
            'measurement_overlays': self._measurement_overlays_from_tables(),
            'preview_selected_part': self._selected_part_index,
            'preview_selected_parts': [idx for idx in self._selected_part_indices if isinstance(idx, int) and idx >= 0],
            'preview_transform_mode': self._current_transform_mode,
            'preview_fine_transform': bool(self._fine_transform_enabled),
        }

        if not fixture['fixture_id'] and not self._group_edit_mode:
            raise ValueError(self._t('fixture_editor.error.fixture_id_required', 'Fixture ID is required.'))
        if fixture['fixture_kind'] not in self.FIXTURE_KINDS:
            raise ValueError(self._t('fixture_editor.error.fixture_kind_invalid', 'Fixture kind is invalid.'))
        return fixture

    def accept(self):
        try:
            self.get_fixture_data()
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))
            return
        super().accept()

