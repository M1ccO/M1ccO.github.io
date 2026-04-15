"""Fixture editor wrapper for the shared 3D models tab builder."""

from typing import Any

from PySide6.QtWidgets import QTabWidget, QWidget

from ui.shared.editor_models_tab import ModelsTabConfig, build_editor_models_tab


def build_models_tab(dialog: Any, root_tabs: QTabWidget) -> QWidget:
    return build_editor_models_tab(
        dialog,
        root_tabs,
        config=ModelsTabConfig(
            move_button_fallback_text='MOVE',
            reset_button_fallback_text='RESET',
        ),
    )
