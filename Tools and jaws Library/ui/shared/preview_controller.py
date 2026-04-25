"""Shared preview-controller logic for editor dialogs.

Centralises all 3D-preview lifecycle, transform management, gizmo mode
switching, and selection synchronisation so that editor dialogs (Tool, Jaw,
or any future library) only keep thin one-liner delegates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEventLoop, QItemSelectionModel, QSize, QTimer
from PySide6.QtGui import QIcon

from config import TOOL_ICONS_DIR
from ui.tool_editor_support.transform_rules import (
    all_part_transforms_payload,
    compact_transform_dict,
    normalize_transform_dict,
)

if TYPE_CHECKING:
    from ui.shared.editor_protocol import EditorModelsHost


class EditorPreviewController:
    """Coordinates embedded 3D preview updates for editor dialogs.

    The *dialog* (host) remains the owner of all persistent state such as
    ``_part_transforms`` and ``_selected_part_indices``.  This controller
    keeps shared behaviour in one place so every editor dialog can delegate
    to it with one-liners.
    """

    def __init__(self, dialog: EditorModelsHost | Any):
        self._dialog = dialog

    @property
    def dialog(self) -> Any:
        return self._dialog

    # ------------------------------------------------------------------
    # Preview loading
    # ------------------------------------------------------------------

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

    def refresh_models_preview(self) -> None:
        """High-level refresh: read parts from the host table, push to preview."""
        d = self.dialog
        if d._suspend_preview_refresh:
            return
        parts = d._model_table_to_parts()
        self.refresh_embedded_models_preview(
            parts,
            transform_edit_enabled=bool(d._assembly_transform_enabled),
            measurement_overlays=[],
            measurements_visible=False,
            measurement_drag_enabled=False,
        )

    # ------------------------------------------------------------------
    # Viewer → dialog selection sync
    # ------------------------------------------------------------------

    def on_viewer_part_selected(self, index: int) -> None:
        d = self.dialog
        d._selected_part_indices = [index] if index >= 0 else []
        d._selected_part_index = index
        self.refresh_transform_selection_state()
        self.sync_model_table_selection()
        self.request_preview_transform_snapshot(refresh_selection=True)

    def on_viewer_part_selection_changed(self, indices: list[int]) -> None:
        normalized = [idx for idx in indices if isinstance(idx, int) and idx >= 0]
        d = self.dialog
        d._selected_part_indices = normalized
        d._selected_part_index = normalized[-1] if normalized else -1
        self.refresh_transform_selection_state()
        self.sync_model_table_selection()
        self.request_preview_transform_snapshot(refresh_selection=True)

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

    def on_model_table_selection_changed(self) -> None:
        d = self.dialog
        if not d._assembly_transform_enabled:
            return
        model_table = getattr(d, 'model_table', None)
        if model_table is None:
            return
        selection_model = model_table.selectionModel()
        if selection_model is None:
            return
        rows = sorted(idx.row() for idx in selection_model.selectedRows())
        d._selected_part_indices = rows
        d._selected_part_index = rows[-1] if rows else -1
        self.refresh_transform_selection_state()
        preview = getattr(d, 'models_preview', None)
        if preview is not None:
            preview.select_parts(rows)

    # ------------------------------------------------------------------
    # Transform change from viewer
    # ------------------------------------------------------------------

    def on_viewer_transform_changed(self, index: int, transform: dict) -> None:
        d = self.dialog
        d._part_transforms[index] = compact_transform_dict(
            normalize_transform_dict(transform)
        )
        if index in d._selected_part_indices:
            self.refresh_transform_selection_state()

    # ------------------------------------------------------------------
    # Transform snapshot (read from preview widget)
    # ------------------------------------------------------------------

    def saved_transform_for_index(self, index: int) -> dict:
        return normalize_transform_dict(
            self.dialog._saved_part_transforms.get(index, {})
        )

    def apply_preview_transforms_snapshot(
        self, snapshot: Any, *, refresh_selection: bool = False
    ) -> bool:
        d = self.dialog
        if not isinstance(snapshot, list) or len(snapshot) <= 0:
            return False
        model_table = getattr(d, 'model_table', None)
        row_count = model_table.rowCount() if model_table is not None else 0
        if row_count <= 0:
            return False
        transformed: dict[int, dict] = {}
        upper = min(row_count, len(snapshot))
        for index in range(upper):
            raw = snapshot[index]
            if not isinstance(raw, dict):
                continue
            compact = compact_transform_dict(normalize_transform_dict(raw))
            if compact:
                transformed[index] = compact
        d._part_transforms = transformed
        if refresh_selection:
            self.refresh_transform_selection_state()
        return True

    def request_preview_transform_snapshot(
        self, *, refresh_selection: bool = False
    ) -> None:
        d = self.dialog
        if not d._assembly_transform_enabled:
            return
        preview = getattr(d, 'models_preview', None)
        if preview is None:
            return
        try:
            preview.get_part_transforms(
                lambda snapshot: self.apply_preview_transforms_snapshot(
                    snapshot, refresh_selection=refresh_selection,
                )
            )
        except Exception:
            return

    def sync_preview_transform_snapshot_for_save(
        self, timeout_ms: int = 350
    ) -> None:
        from shared.ui.runtime_trace import rtrace
        d = self.dialog
        if not d._assembly_transform_enabled:
            rtrace("snapshot_for_save.skip.no_assembly_transform")
            return
        preview = getattr(d, 'models_preview', None)
        if preview is None:
            rtrace("snapshot_for_save.skip.no_preview")
            return
        # Bypass placeholder preview (lazy Models tab never opened) — no live
        # transforms to sync. Avoid nested event loop entirely.
        preview_cls = type(preview).__name__
        if preview_cls == '_BypassedPreview':
            rtrace("snapshot_for_save.skip.bypassed_preview")
            return
        if not bool(getattr(d, '_models_tab_materialized', False)):
            rtrace("snapshot_for_save.skip.not_materialized")
            return
        result_holder: dict[str, Any] = {'snapshot': None, 'done': False, 'sync_done': False}

        def _on_snapshot(snapshot: Any) -> None:
            result_holder['snapshot'] = snapshot
            result_holder['done'] = True
            loop = result_holder.get('loop')
            if loop is not None:
                try:
                    loop.quit()
                except Exception:
                    pass

        try:
            preview.get_part_transforms(_on_snapshot)
        except Exception as exc:
            rtrace("snapshot_for_save.get_part_transforms.raised", err=str(exc))
            return

        # Synchronous callback path (cached transforms, WebEngine not ready) —
        # skip nested QEventLoop. Prevents dialog close events from being
        # processed mid-accept.
        if result_holder['done']:
            rtrace("snapshot_for_save.sync_callback", snapshot_len=len(result_holder['snapshot']) if isinstance(result_holder['snapshot'], list) else -1)
            self.apply_preview_transforms_snapshot(result_holder['snapshot'])
            return

        loop = QEventLoop(d)
        result_holder['loop'] = loop
        timer = QTimer(d)
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(max(100, int(timeout_ms)))
        rtrace("snapshot_for_save.enter_nested_loop", timeout_ms=timeout_ms)
        try:
            loop.exec()
        finally:
            timer.stop()
            result_holder['loop'] = None
        rtrace("snapshot_for_save.exit_nested_loop", done=result_holder['done'])
        if result_holder['done']:
            self.apply_preview_transforms_snapshot(result_holder['snapshot'])

    # ------------------------------------------------------------------
    # Transform selection state & fields
    # ------------------------------------------------------------------

    def refresh_transform_selection_state(self) -> None:
        d = self.dialog
        count = len(d._selected_part_indices)
        single_selected = count == 1 and d._selected_part_index >= 0

        for widget in (d._transform_x, d._transform_y, d._transform_z):
            widget.setEnabled(single_selected)

        preview = getattr(d, 'models_preview', None)

        if count == 0:
            if preview is not None:
                preview.set_selection_caption(None)
            d._transform_x.setText('0')
            d._transform_y.setText('0')
            d._transform_z.setText('0')
            d._reset_transform_btn.setEnabled(False)
            return

        d._reset_transform_btn.setEnabled(True)

        if single_selected:
            index = d._selected_part_index
            model_table = getattr(d, 'model_table', None)
            name_item = model_table.item(index, 0) if model_table else None
            name = name_item.text().strip() if name_item else f'Part {index + 1}'
            if preview is not None:
                preview.set_selection_caption(name or f'Part {index + 1}')
            self.update_transform_fields(d._part_transforms.get(index, {}))
            return

        if preview is not None:
            preview.set_selection_caption(
                d._t(
                    'tool_editor.preview.selection_count',
                    '{count} models selected',
                    count=count,
                )
            )
        self.update_transform_fields(
            d._part_transforms.get(d._selected_part_index, {})
        )

    def update_transform_fields(self, transform: dict) -> None:
        d = self.dialog
        view_t = normalize_transform_dict(transform)
        if d._current_transform_mode == 'translate':
            d._transform_x.setText(str(view_t.get('x', 0)))
            d._transform_y.setText(str(view_t.get('y', 0)))
            d._transform_z.setText(str(view_t.get('z', 0)))
        else:
            d._transform_x.setText(str(view_t.get('rx', 0)))
            d._transform_y.setText(str(view_t.get('ry', 0)))
            d._transform_z.setText(str(view_t.get('rz', 0)))

    # ------------------------------------------------------------------
    # Transform row / button sizing
    # ------------------------------------------------------------------

    def update_transform_row_sizes(self) -> None:
        d = self.dialog
        if not hasattr(d, '_transform_x'):
            return
        btn_w = 42
        edit_w = 80
        d._mode_toggle_btn.setFixedWidth(btn_w)
        d._fine_transform_btn.setFixedWidth(btn_w)
        d._reset_transform_btn.setFixedWidth(btn_w)
        d._mode_toggle_btn.setIconSize(QSize(18, 18))
        d._fine_transform_btn.setIconSize(QSize(18, 18))
        d._reset_transform_btn.setIconSize(QSize(18, 18))
        d._transform_x.setFixedWidth(edit_w)
        d._transform_y.setFixedWidth(edit_w)
        d._transform_z.setFixedWidth(edit_w)

    # ------------------------------------------------------------------
    # Gizmo mode (translate / rotate)
    # ------------------------------------------------------------------

    def on_mode_toggle_clicked(self) -> None:
        d = self.dialog
        self.set_gizmo_mode('translate' if d._mode_toggle_btn.isChecked() else 'rotate')

    def set_gizmo_mode(self, mode: str) -> None:
        d = self.dialog
        d._current_transform_mode = mode
        self.update_mode_toggle_button_appearance()
        preview = getattr(d, 'models_preview', None)
        if preview is not None:
            preview.set_transform_mode(mode)
        self.refresh_transform_selection_state()

    def update_mode_toggle_button_appearance(self) -> None:
        d = self.dialog
        if not hasattr(d, '_mode_toggle_btn'):
            return
        is_translate = d._current_transform_mode == 'translate'
        next_icon = 'rotate.svg' if is_translate else 'move.svg'
        next_tooltip = (
            d._t('tool_editor.transform.switch_to_rotate', 'Click to rotate')
            if is_translate else
            d._t('tool_editor.transform.switch_to_move', 'Click to move')
        )
        d._mode_toggle_btn.setChecked(is_translate)
        d._mode_toggle_btn.setText('')
        d._mode_toggle_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / next_icon)))
        d._mode_toggle_btn.setIconSize(QSize(18, 18))
        d._mode_toggle_btn.setToolTip(next_tooltip)
        self.update_transform_row_sizes()

    # ------------------------------------------------------------------
    # Fine transform toggle
    # ------------------------------------------------------------------

    def update_fine_transform_button_appearance(self) -> None:
        d = self.dialog
        if not hasattr(d, '_fine_transform_btn'):
            return
        icon_name = '1x.svg' if d._fine_transform_enabled else 'fine_tune.svg'
        tooltip = (
            d._t('tool_editor.transform.disable_fine', 'Click for 1x step')
            if d._fine_transform_enabled else
            d._t('tool_editor.transform.enable_fine', 'Click to fine tune')
        )
        d._fine_transform_btn.setText('')
        d._fine_transform_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
        d._fine_transform_btn.setIconSize(QSize(18, 18))
        d._fine_transform_btn.setToolTip(tooltip)
        self.update_transform_row_sizes()

    def on_fine_transform_toggled(self, checked: bool) -> None:
        d = self.dialog
        d._fine_transform_enabled = bool(checked)
        self.update_fine_transform_button_appearance()
        preview = getattr(d, 'models_preview', None)
        if preview is not None:
            preview.set_fine_transform_enabled(d._fine_transform_enabled)

    # ------------------------------------------------------------------
    # Reset / manual transform
    # ------------------------------------------------------------------

    def reset_current_part_transform(self, target: str = 'origin') -> None:
        d = self.dialog
        if d._selected_part_index < 0:
            return
        indices = d._selected_part_indices or [d._selected_part_index]
        if target == 'saved':
            for idx in indices:
                baseline = self.saved_transform_for_index(idx)
                d._part_transforms[idx] = compact_transform_dict(baseline)
            model_table = getattr(d, 'model_table', None)
            row_count = model_table.rowCount() if model_table else 0
            preview = getattr(d, 'models_preview', None)
            if preview is not None:
                preview.set_part_transforms(
                    all_part_transforms_payload(d._part_transforms, row_count)
                )
            self.refresh_transform_selection_state()
            return
        preview = getattr(d, 'models_preview', None)
        if preview is not None:
            preview.reset_selected_part_transform()

    def apply_manual_transform(self) -> None:
        d = self.dialog
        if len(d._selected_part_indices) != 1 or d._selected_part_index < 0:
            return
        try:
            vx = float(d._transform_x.text().replace(',', '.'))
            vy = float(d._transform_y.text().replace(',', '.'))
            vz = float(d._transform_z.text().replace(',', '.'))
        except ValueError:
            return
        index = d._selected_part_index
        t = normalize_transform_dict(d._part_transforms.get(index, {}))
        if d._current_transform_mode == 'translate':
            t['x'] = vx
            t['y'] = vy
            t['z'] = vz
        else:
            t['rx'] = vx
            t['ry'] = vy
            t['rz'] = vz
        d._part_transforms[index] = compact_transform_dict(t)
        model_table = getattr(d, 'model_table', None)
        row_count = model_table.rowCount() if model_table else 0
        preview = getattr(d, 'models_preview', None)
        if preview is not None:
            preview.set_part_transforms(
                all_part_transforms_payload(d._part_transforms, row_count)
            )


__all__ = ['EditorPreviewController']
