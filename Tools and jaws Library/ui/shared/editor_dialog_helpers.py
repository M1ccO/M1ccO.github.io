"""Shared editor-dialog utilities used by tool and jaw editor dialogs.

Provides ``EditorDialogMixin`` -- a mixin class that encapsulates the common
dialog-chrome and measurement-management logic shared between
``AddEditToolDialog`` and ``AddEditJawDialog``.

Host requirements -- the dialog mixing this in must provide:

  Attributes:
    _clamping_screen_bounds          bool
    _measurement_editor_state        dict
    _translate                       Callable[[str, str | None], str]

  Methods:
    _t(key, default, **kwargs) -> str
    _model_table_to_parts()   -> list[dict]
    _refresh_models_preview()
"""

import json

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QWidget,
)

from config import SHARED_UI_PREFERENCES_PATH
from shared.ui.helpers.editor_helpers import (
    build_editor_field_card,
    build_editor_field_group,
    focus_editor_widget,
)
from ui.measurement_editor_dialog import MeasurementEditorDialog
from ui.tool_editor_support.measurement_rules import (
    empty_measurement_editor_state,
    measurement_overlays_from_state,
    normalize_measurement_editor_state,
    parse_measurement_overlays,
)


class EditorDialogMixin:
    """Mixin providing common dialog chrome and measurement helpers."""

    # ------------------------------------------------------------------
    # Field-building helpers
    # ------------------------------------------------------------------
    def _build_field_group(self, fields: list) -> QFrame:
        return build_editor_field_group(fields)

    def _focus_editor(self, widget: QWidget):
        focus_editor_widget(widget)

    # ------------------------------------------------------------------
    # Screen-clamping
    # ------------------------------------------------------------------
    def _ensure_on_screen(self):
        if self._clamping_screen_bounds:
            return
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or self.screen()
        if screen is None:
            return
        self._clamping_screen_bounds = True
        try:
            available = screen.availableGeometry()
            geom = self.frameGeometry()

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

    def _install_local_event_filters(self) -> None:
        """Install dialog-local event filter scope for this dialog tree."""
        self.installEventFilter(self)
        for widget in self.findChildren(QWidget):
            widget.installEventFilter(self)

    # ------------------------------------------------------------------
    # Assembly transform preference
    # ------------------------------------------------------------------
    def _is_assembly_transform_enabled(self) -> bool:
        try:
            with open(SHARED_UI_PREFERENCES_PATH, 'r', encoding='utf-8') as f:
                prefs = json.load(f)
            return bool(prefs.get('enable_assembly_transform', False))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Measurement helpers
    # ------------------------------------------------------------------
    def _empty_measurement_editor_state(self):
        return empty_measurement_editor_state()

    def _normalize_measurement_editor_state(self, data):
        return normalize_measurement_editor_state(data)

    def _load_measurement_overlays(self, overlays):
        self._measurement_editor_state = parse_measurement_overlays(overlays)
        self._update_measurement_summary_label()

    def _measurement_overlays_from_tables(self):
        return measurement_overlays_from_state(
            self._measurement_editor_state,
            translate=lambda key, default: self._t(key, default),
        )

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

    # ------------------------------------------------------------------
    # Shared init state  (call from __init__ after setting _translate)
    # ------------------------------------------------------------------
    def _init_editor_state(self):
        """Initialise the common editor state attributes shared by both dialogs."""
        from ui.shared.preview_controller import EditorPreviewController

        self._assembly_transform_enabled = self._is_assembly_transform_enabled()
        self._part_transforms: dict[int, dict] = {}
        self._saved_part_transforms: dict[int, dict] = {}
        self._measurement_editor_state = self._empty_measurement_editor_state()
        self._current_transform_mode = 'translate'
        self._fine_transform_enabled = False
        self._selected_part_index = -1
        self._selected_part_indices: list[int] = []
        self._suspend_preview_refresh = False
        self._clamping_screen_bounds = False
        self._preview_controller = EditorPreviewController(self)

    # ------------------------------------------------------------------
    # Combo helper
    # ------------------------------------------------------------------
    @staticmethod
    def _set_combo_by_data(combo, value: str):
        target = (value or '').strip()
        for idx in range(combo.count()):
            if (combo.itemData(idx) or '').strip() == target:
                combo.setCurrentIndex(idx)
                return

    # ------------------------------------------------------------------
    # Preview-controller delegates
    # ------------------------------------------------------------------
    def _refresh_models_preview(self):
        self._preview_controller.refresh_models_preview()

    def _on_viewer_transform_changed(self, index: int, transform: dict):
        self._preview_controller.on_viewer_transform_changed(index, transform)

    def _on_viewer_part_selected(self, index: int):
        self._preview_controller.on_viewer_part_selected(index)

    def _on_viewer_part_selection_changed(self, indices: list[int]):
        self._preview_controller.on_viewer_part_selection_changed(indices)

    def _sync_model_table_selection(self):
        self._preview_controller.sync_model_table_selection()

    def _saved_transform_for_index(self, index: int) -> dict:
        return self._preview_controller.saved_transform_for_index(index)

    def _apply_preview_transforms_snapshot(self, snapshot, *, refresh_selection: bool = False) -> bool:
        return self._preview_controller.apply_preview_transforms_snapshot(snapshot, refresh_selection=refresh_selection)

    def _request_preview_transform_snapshot(self, *, refresh_selection: bool = False):
        self._preview_controller.request_preview_transform_snapshot(refresh_selection=refresh_selection)

    def _sync_preview_transform_snapshot_for_save(self, timeout_ms: int = 350):
        self._preview_controller.sync_preview_transform_snapshot_for_save(timeout_ms)

    def _refresh_transform_selection_state(self):
        self._preview_controller.refresh_transform_selection_state()

    def _update_transform_fields(self, t: dict, index: int | None = None):
        self._preview_controller.update_transform_fields(t)

    def _update_transform_row_sizes(self):
        self._preview_controller.update_transform_row_sizes()

    def _on_mode_toggle_clicked(self):
        self._preview_controller.on_mode_toggle_clicked()

    def _set_gizmo_mode(self, mode: str):
        self._preview_controller.set_gizmo_mode(mode)

    def _update_mode_toggle_button_appearance(self):
        self._preview_controller.update_mode_toggle_button_appearance()

    def _update_fine_transform_button_appearance(self):
        self._preview_controller.update_fine_transform_button_appearance()

    def _on_fine_transform_toggled(self, checked: bool):
        self._preview_controller.on_fine_transform_toggled(checked)

    def _reset_current_part_transform(self, target: str = 'origin'):
        self._preview_controller.reset_current_part_transform(target)

    def _apply_manual_transform(self):
        self._preview_controller.apply_manual_transform()

    def _on_model_table_selection_changed(self):
        self._preview_controller.on_model_table_selection_changed()
        self._refresh_models_preview()

