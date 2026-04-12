"""Shared preview-controller logic for editor dialogs."""

from typing import Any

from PySide6.QtCore import QItemSelectionModel


class EditorPreviewController:
    """Coordinates embedded 3D preview updates for editor dialogs.

    The dialog remains the source of truth for data/state. This controller keeps
    shared preview-loading behavior in one place across Tool/Jaw editors.
    """

    def __init__(self, dialog: Any):
        self._dialog = dialog

    @property
    def dialog(self) -> Any:
        return self._dialog

    def refresh_embedded_models_preview(
        self,
        parts: list[dict],
        *,
        transform_edit_enabled: bool,
        measurement_overlays: list[dict] | None = None,
        measurements_visible: bool = False,
        measurement_drag_enabled: bool = False,
    ) -> None:
        preview = getattr(self.dialog, 'models_preview', None)
        if preview is None:
            return

        if not parts:
            if hasattr(preview, 'clear'):
                preview.clear()
            return

        if hasattr(preview, 'load_parts'):
            preview.load_parts(parts)
        elif hasattr(preview, 'load_stl'):
            # Single-model fallback for older preview widgets.
            first_existing = next((p.get('file') for p in parts if p.get('file')), None)
            preview.load_stl(first_existing)

        overlays = list(measurement_overlays or [])
        if hasattr(preview, 'set_measurement_overlays'):
            preview.set_measurement_overlays(overlays)
        if hasattr(preview, 'set_measurements_visible'):
            preview.set_measurements_visible(bool(measurements_visible and overlays))
        if hasattr(preview, 'set_measurement_drag_enabled'):
            preview.set_measurement_drag_enabled(bool(measurement_drag_enabled and overlays))
        if transform_edit_enabled and hasattr(preview, 'set_transform_edit_enabled'):
            preview.set_transform_edit_enabled(True)

    def on_viewer_part_selected(self, index: int) -> None:
        self.dialog._selected_part_indices = [index] if index >= 0 else []
        self.dialog._selected_part_index = index
        self.dialog._refresh_transform_selection_state()
        self.sync_model_table_selection()
        self.dialog._request_preview_transform_snapshot(refresh_selection=True)

    def on_viewer_part_selection_changed(self, indices: list[int]) -> None:
        normalized = [idx for idx in indices if isinstance(idx, int) and idx >= 0]
        self.dialog._selected_part_indices = normalized
        self.dialog._selected_part_index = normalized[-1] if normalized else -1
        self.dialog._refresh_transform_selection_state()
        self.sync_model_table_selection()
        self.dialog._request_preview_transform_snapshot(refresh_selection=True)

    def sync_model_table_selection(self) -> None:
        model_table = getattr(self.dialog, 'model_table', None)
        if model_table is None:
            return
        selection_model = model_table.selectionModel()
        if selection_model is None:
            return

        selection_model.blockSignals(True)
        model_table.blockSignals(True)
        try:
            selection_model.clearSelection()
            for index in getattr(self.dialog, '_selected_part_indices', []):
                model_index = model_table.model().index(index, 0)
                if not model_index.isValid():
                    continue
                selection_model.select(
                    model_index,
                    QItemSelectionModel.Select | QItemSelectionModel.Rows,
                )

            selected_index = getattr(self.dialog, '_selected_part_index', -1)
            if selected_index >= 0:
                current_index = model_table.model().index(selected_index, 0)
                if current_index.isValid():
                    selection_model.setCurrentIndex(current_index, QItemSelectionModel.NoUpdate)
        finally:
            model_table.blockSignals(False)
            selection_model.blockSignals(False)


__all__ = ['EditorPreviewController']
