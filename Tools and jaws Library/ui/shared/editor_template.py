"""Minimal template for a new library editor dialog with 3D models tab.

Copy this file into your new library's ``ui/`` folder and customise:
  1. Rename the class (e.g. ``AddEditFixtureDialog``).
  2. Add your own general/detail tabs before ``build_models_tab``.
  3. Implement ``_model_table_to_parts`` to serialise your data model.
  4. Override any host-protocol signal handlers you need custom behaviour for
     (``_add_model_row``, ``_remove_model_row``, ``_open_measurement_editor``,
     ``_on_model_table_changed``, etc.).
  5. Adjust ``ModelsTabConfig`` fields to customise button text / sizing.

The class satisfies ``EditorModelsHost`` (structural protocol) so all shared
3D-tab and preview-controller behaviour works out of the box.
"""

import json
from typing import Any, Callable

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLineEdit,
    QSizePolicy,
    QTabWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import SHARED_UI_PREFERENCES_PATH, TOOL_ICONS_DIR, TOOL_MODELS_ROOT_DEFAULT, JAW_MODELS_ROOT_DEFAULT
from shared.editor_helpers import (
    apply_secondary_button_theme,
    create_dialog_buttons,
    setup_editor_dialog,
)
from shared.model_paths import format_model_path_for_display, read_model_roots
from ui.shared.editor_models_tab import ModelsTabConfig, build_editor_models_tab
from ui.shared.preview_controller import EditorPreviewController
from ui.measurement_editor_dialog import MeasurementEditorDialog
from ui.tool_editor_support.measurement_rules import (
    empty_measurement_editor_state,
    measurement_overlays_from_state,
    normalize_measurement_editor_state,
    parse_measurement_overlays,
)


class AddEditItemDialog(QDialog):
    """Template editor with a 3D models tab powered by the shared modules."""

    def __init__(
        self,
        parent=None,
        item: dict | None = None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self.item = item or {}
        self._translate = translate or (lambda _key, default=None, **_kw: default or '')

        # -- Host-protocol state (required by EditorPreviewController) -------
        self._assembly_transform_enabled = self._is_assembly_transform_enabled()
        self._part_transforms: dict[int, dict] = {}
        self._saved_part_transforms: dict[int, dict] = {}
        self._measurement_editor_state = empty_measurement_editor_state()
        self._current_transform_mode = 'translate'
        self._fine_transform_enabled = False
        self._selected_part_index = -1
        self._selected_part_indices: list[int] = []
        self._suspend_preview_refresh = False
        self._clamping_screen_bounds = False

        # -- Shared controller -----------------------------------------------
        self._preview_controller = EditorPreviewController(self)

        # -- Dialog chrome ---------------------------------------------------
        self.setWindowTitle(self._t('editor.window_title', 'Edit Item'))
        self.resize(1120, 760)
        self.setMinimumSize(900, 660)
        self.setModal(True)
        setup_editor_dialog(self)
        self._build_ui()
        self._load_item()

    # -----------------------------------------------------------------
    # Localisation helper
    # -----------------------------------------------------------------
    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    # -----------------------------------------------------------------
    # Assembly-transform preference
    # -----------------------------------------------------------------
    @staticmethod
    def _is_assembly_transform_enabled() -> bool:
        try:
            with open(SHARED_UI_PREFERENCES_PATH, 'r') as f:
                prefs = json.load(f)
            return bool(prefs.get('enable_assembly_transform', False))
        except Exception:
            return False

    # -----------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.setObjectName('itemEditorTabs')
        root.addWidget(self.tabs, 1)

        # TODO: add your own general/detail tabs here
        # build_general_tab(self, self.tabs)

        # 3D models tab — fully handled by shared builder + controller
        build_editor_models_tab(
            self,
            self.tabs,
            config=ModelsTabConfig(
                move_button_fallback_text='MOVE',
                reset_button_fallback_text='RESET',
            ),
        )

        self._dialog_buttons = create_dialog_buttons(
            self,
            save_text=self._t('editor.action.save', 'SAVE'),
            cancel_text=self._t('common.cancel', 'Cancel').upper(),
            on_save=self.accept,
            on_cancel=self.reject,
        )
        self._save_btn = self._dialog_buttons.button(QDialogButtonBox.Save)
        root.addWidget(self._dialog_buttons)
        apply_secondary_button_theme(self, self._save_btn)

    # -----------------------------------------------------------------
    # Host-protocol: methods you MUST implement
    # -----------------------------------------------------------------
    def _model_table_to_parts(self) -> list[dict]:
        """Serialise the model table rows into part dicts for the preview."""
        result = []
        for row in range(self.model_table.rowCount()):
            name_item = self.model_table.item(row, 0)
            file_item = self.model_table.item(row, 1)
            name = name_item.text().strip() if name_item else ''
            stl_file = self._stored_model_path(file_item)
            color = self._get_model_row_color(row)
            if name or stl_file:
                part = {'name': name, 'file': stl_file, 'color': color or '#9ea7b3'}
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

    def _add_model_row(self, checked=False, values=None):
        if isinstance(checked, dict) and values is None:
            values = checked
        if values is None:
            models_root, _ = read_model_roots(
                SHARED_UI_PREFERENCES_PATH, TOOL_MODELS_ROOT_DEFAULT, JAW_MODELS_ROOT_DEFAULT,
            )
            models_root.mkdir(parents=True, exist_ok=True)
            file_path, _ = QFileDialog.getOpenFileName(
                self, self._t('editor.dialog.select_stl', 'Select STL model'),
                str(models_root), 'STL Files (*.stl)',
            )
            if not file_path:
                return
            import os
            base = os.path.splitext(os.path.basename(file_path))[0]
            values = {'name': base.replace('_', ' ').title(), 'file': file_path, 'color': ''}
        row = self.model_table.rowCount()
        self.model_table.insertRow(row)
        self.model_table.setItem(row, 0, QTableWidgetItem(values.get('name', '')))
        file_item = QTableWidgetItem(
            format_model_path_for_display(
                values.get('file', ''),
                *read_model_roots(SHARED_UI_PREFERENCES_PATH, TOOL_MODELS_ROOT_DEFAULT, JAW_MODELS_ROOT_DEFAULT),
            )
        )
        file_item.setData(Qt.UserRole, values.get('file', ''))
        self.model_table.setItem(row, 1, file_item)
        self.model_table.setCurrentCell(row, 0)
        self._refresh_models_preview()

    def _remove_model_row(self):
        row = self.model_table.currentRow()
        if row >= 0:
            self.model_table.removeRow(row)
            self._refresh_models_preview()

    def _move_model_row(self, delta: int):
        row = self.model_table.currentRow()
        if row < 0:
            return
        target = row + int(delta)
        if target < 0 or target >= self.model_table.rowCount():
            return
        # Minimal move — swap the two rows
        for col in range(self.model_table.columnCount()):
            item_a = self.model_table.takeItem(row, col)
            item_b = self.model_table.takeItem(target, col)
            self.model_table.setItem(row, col, item_b)
            self.model_table.setItem(target, col, item_a)
        self.model_table.setCurrentCell(target, 0)
        self._refresh_models_preview()

    def _on_model_table_changed(self, item):
        if item.column() == 1:
            item.setData(Qt.UserRole, item.text().strip())
        self._refresh_models_preview()

    def _open_measurement_editor(self):
        dialog = MeasurementEditorDialog(
            tool_data=normalize_measurement_editor_state(self._measurement_editor_state),
            parts=self._model_table_to_parts(),
            parent=self,
            translate=self._translate,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        self._measurement_editor_state = normalize_measurement_editor_state(dialog.get_measurements())
        self._update_measurement_summary_label()
        self._refresh_models_preview()

    def _update_measurement_summary_label(self):
        if not hasattr(self, 'measurement_summary_label'):
            return
        total = sum(len(items) for items in self._measurement_editor_state.values())
        if total <= 0:
            self.measurement_summary_label.setText(
                self._t('tool_editor.measurements.none', 'No measurements configured')
            )
        else:
            self.measurement_summary_label.setText(
                self._t('tool_editor.measurements.count', '{count} measurements configured', count=total)
            )

    # -----------------------------------------------------------------
    # Host-protocol delegates (one-liners → controller)
    # -----------------------------------------------------------------
    def _refresh_models_preview(self):
        self._preview_controller.refresh_models_preview()

    def _on_viewer_transform_changed(self, index, transform):
        self._preview_controller.on_viewer_transform_changed(index, transform)

    def _on_viewer_part_selected(self, index):
        self._preview_controller.on_viewer_part_selected(index)

    def _on_viewer_part_selection_changed(self, indices):
        self._preview_controller.on_viewer_part_selection_changed(indices)

    def _sync_model_table_selection(self):
        self._preview_controller.sync_model_table_selection()

    def _saved_transform_for_index(self, index):
        return self._preview_controller.saved_transform_for_index(index)

    def _apply_preview_transforms_snapshot(self, snapshot, *, refresh_selection=False):
        return self._preview_controller.apply_preview_transforms_snapshot(snapshot, refresh_selection=refresh_selection)

    def _request_preview_transform_snapshot(self, *, refresh_selection=False):
        self._preview_controller.request_preview_transform_snapshot(refresh_selection=refresh_selection)

    def _sync_preview_transform_snapshot_for_save(self, timeout_ms=350):
        self._preview_controller.sync_preview_transform_snapshot_for_save(timeout_ms)

    def _refresh_transform_selection_state(self):
        self._preview_controller.refresh_transform_selection_state()

    def _update_transform_fields(self, transform):
        self._preview_controller.update_transform_fields(transform)

    def _update_transform_row_sizes(self):
        self._preview_controller.update_transform_row_sizes()

    def _on_mode_toggle_clicked(self):
        self._preview_controller.on_mode_toggle_clicked()

    def _set_gizmo_mode(self, mode):
        self._preview_controller.set_gizmo_mode(mode)

    def _update_mode_toggle_button_appearance(self):
        self._preview_controller.update_mode_toggle_button_appearance()

    def _update_fine_transform_button_appearance(self):
        self._preview_controller.update_fine_transform_button_appearance()

    def _on_fine_transform_toggled(self, checked):
        self._preview_controller.on_fine_transform_toggled(checked)

    def _reset_current_part_transform(self, target='origin'):
        self._preview_controller.reset_current_part_transform(target)

    def _apply_manual_transform(self):
        self._preview_controller.apply_manual_transform()

    def _on_model_table_selection_changed(self):
        self._preview_controller.on_model_table_selection_changed()

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------
    @staticmethod
    def _stored_model_path(item) -> str:
        if item is None:
            return ''
        raw = item.data(Qt.UserRole)
        return str(raw).strip() if raw is not None else item.text().strip()

    def _get_model_row_color(self, row: int) -> str:
        from PySide6.QtWidgets import QPushButton
        widget = self.model_table.cellWidget(row, 2)
        if isinstance(widget, QPushButton):
            return widget.property('colorHex') or '#9ea7b3'
        if isinstance(widget, QWidget):
            btn = widget.findChild(QPushButton)
            if btn is not None:
                return btn.property('colorHex') or '#9ea7b3'
        item = self.model_table.item(row, 2)
        return item.text().strip() if item else '#9ea7b3'

    def _load_item(self):
        """Load existing item data into the dialog. Customise for your model."""
        pass

    def get_item_data(self) -> dict:
        """Collect all dialog data into a dict for saving. Customise for your model."""
        self._preview_controller.sync_preview_transform_snapshot_for_save()
        parts = self._model_table_to_parts()
        return {
            'stl_path': json.dumps(parts) if parts else '',
            'measurement_overlays': measurement_overlays_from_state(
                self._measurement_editor_state,
                translate=lambda key, default: self._t(key, default),
            ),
        }
