"""Explicit host protocol for the shared 3D models-tab / preview-controller layer.

Any editor dialog that uses ``build_editor_models_tab`` and
``EditorPreviewController`` must satisfy this protocol.  The protocol is
structural (duck-typed at runtime) — there is no need to inherit from it.
Type-checkers can verify conformance when the dialog is annotated as
``EditorModelsHost``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EditorModelsHost(Protocol):
    """Contract that an editor dialog must fulfil for the shared 3D tab.

    **State attributes** — initialised by the dialog's ``__init__``:

    ==========================================  ========================================
    Attribute                                   Purpose
    ==========================================  ========================================
    ``_assembly_transform_enabled``  (bool)     Toggle interactive part transforms
    ``_fine_transform_enabled``      (bool)     Fine-step mode flag
    ``_part_transforms``             (dict)     ``{row_index: transform_dict}``
    ``_saved_part_transforms``       (dict)     Baseline transforms for reset-to-saved
    ``_current_transform_mode``      (str)      ``'translate'`` or ``'rotate'``
    ``_selected_part_index``         (int)      Last-selected row (−1 = none)
    ``_selected_part_indices``       (list)     All currently-selected rows
    ``_suspend_preview_refresh``     (bool)     Temporarily suppress preview updates
    ==========================================  ========================================

    **UI widgets** — attached by ``build_editor_models_tab``:

    =====================  ============  ===========================================
    Widget                 Type          Created by
    =====================  ============  ===========================================
    ``model_table``        PartsTable    ``build_editor_models_tab``
    ``models_preview``     StlPreview    ``build_editor_models_tab``
    ``_transform_x/y/z``  QLineEdit     ``_build_transform_controls``
    ``_mode_toggle_btn``   QPushButton   ``_build_transform_controls``
    ``_fine_transform_btn``QPushButton   ``_build_transform_controls``
    ``_reset_transform_btn``QPushButton  ``_build_transform_controls``
    ``_transform_frame``   QFrame        ``_build_transform_controls``
    =====================  ============  ===========================================

    **Methods the host MUST implement** (not handled by the controller):
    """

    # -- state attributes ------------------------------------------------
    _assembly_transform_enabled: bool
    _fine_transform_enabled: bool
    _part_transforms: dict[int, dict]
    _saved_part_transforms: dict[int, dict]
    _current_transform_mode: str
    _selected_part_index: int
    _selected_part_indices: list[int]
    _suspend_preview_refresh: bool

    # -- widgets (created by build_editor_models_tab) --------------------
    model_table: Any
    models_preview: Any
    _transform_frame: Any
    _mode_toggle_btn: Any
    _fine_transform_btn: Any
    _reset_transform_btn: Any
    _transform_x: Any
    _transform_y: Any
    _transform_z: Any

    # -- methods the host must implement ---------------------------------
    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        """Translate a localisation key."""
        ...

    def _model_table_to_parts(self) -> list[dict]:
        """Serialise the model table into a list of part dicts for the preview."""
        ...

    def _add_model_row(self, *args, **kwargs) -> None:
        """Add a new row to the model table (triggered by button click)."""
        ...

    def _remove_model_row(self) -> None:
        """Remove the selected row from the model table."""
        ...

    def _move_model_row(self, delta: int) -> None:
        """Reorder the model table by *delta* rows."""
        ...

    def _open_measurement_editor(self) -> None:
        """Open the measurement-editor dialog."""
        ...

    def _update_measurement_summary_label(self) -> None:
        """Refresh the measurement-count label text."""
        ...

    def _on_model_table_changed(self, item: Any) -> None:
        """React when a cell in the model table is edited."""
        ...


__all__ = ['EditorModelsHost']
