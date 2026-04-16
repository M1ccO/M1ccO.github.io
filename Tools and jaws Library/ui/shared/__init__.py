"""Shared UI builders used by multiple Tool/Jaw pages."""

from .selector_panel_builders import (
    apply_selector_icon_button,
    build_selector_card_shell,
    build_selector_actions_row,
    build_selector_info_header,
    build_selector_hint_label,
    build_selector_toggle_button,
)

# Optional editor-centric imports. Keep selector imports usable even when this
# package is loaded via namespace-safe embedded-selector paths.
try:
    from .editor_dialog_helpers import EditorDialogMixin
except Exception:  # pragma: no cover - optional import surface
    EditorDialogMixin = None

try:
    from .editor_protocol import EditorModelsHost
except Exception:  # pragma: no cover - optional import surface
    EditorModelsHost = None

try:
    from .model_table_helpers import ModelTableMixin
except Exception:  # pragma: no cover - optional import surface
    ModelTableMixin = None

try:
    from .preview_controller import EditorPreviewController
except Exception:  # pragma: no cover - optional import surface
    EditorPreviewController = None

__all__ = [
    "apply_selector_icon_button",
    "build_selector_card_shell",
    "build_selector_actions_row",
    "build_selector_info_header",
    "build_selector_hint_label",
    "build_selector_toggle_button",
    "EditorDialogMixin",
    "EditorModelsHost",
    "EditorPreviewController",
    "ModelTableMixin",
]
