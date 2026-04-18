from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QWidget

from ui.machine_family_runtime import MACHINING_CENTER_FAMILY, resolve_machine_family
from ui.work_editor_dialog import WorkEditorDialog
from ui.work_editor_support.machining_center import build_machining_center_zeros_tab_ui
from ui.work_editor_support.tab_builders import build_zeros_tab_ui
from ui.work_editor_support.tools_tab_builder import build_tools_tab_ui

try:
    from shared.ui.helpers.editor_helpers import create_titled_section
except ModuleNotFoundError:
    from editor_helpers import create_titled_section

from ui.work_editor_dialog import (
    WorkEditorJawSelectorPanel,
    WorkEditorOrderedToolList,
    WorkEditorToolRemoveDropButton,
    _section_label,
)


class LatheWorkEditorDialog(WorkEditorDialog):
    """Lathe-family Work Editor shell."""

    machine_family = "lathe"
    _startup_prime_zeros_tab = True
    _startup_prime_tools_tab = True

    def _build_family_zeros_tab(self) -> None:
        build_zeros_tab_ui(
            self,
            jaw_selector_panel_cls=WorkEditorJawSelectorPanel,
            create_titled_section_fn=create_titled_section,
        )

    def _build_family_tools_tab(self) -> None:
        build_tools_tab_ui(
            self,
            ordered_tool_list_cls=WorkEditorOrderedToolList,
            remove_drop_button_cls=WorkEditorToolRemoveDropButton,
            section_label_factory=_section_label,
        )


class MachiningCenterWorkEditorDialog(WorkEditorDialog):
    """Machining-center Work Editor shell."""

    machine_family = MACHINING_CENTER_FAMILY
    _startup_prime_zeros_tab = True
    _startup_prime_tools_tab = True

    def _build_family_zeros_tab(self) -> None:
        build_machining_center_zeros_tab_ui(
            self,
            create_titled_section_fn=create_titled_section,
            work_coordinates=self.WORK_COORDINATES,
        )

    def _build_family_tools_tab(self) -> None:
        build_tools_tab_ui(
            self,
            ordered_tool_list_cls=WorkEditorOrderedToolList,
            remove_drop_button_cls=WorkEditorToolRemoveDropButton,
            section_label_factory=_section_label,
        )


def resolve_work_editor_dialog_class(machine_profile_key: str | None):
    family = resolve_machine_family(profile_key=machine_profile_key)
    if family == MACHINING_CENTER_FAMILY:
        return MachiningCenterWorkEditorDialog
    return LatheWorkEditorDialog


def create_work_editor_dialog(
    draw_service,
    *,
    work=None,
    parent=None,
    style_host: QWidget | None = None,
    translate: Callable[[str, str | None], str] | None = None,
    batch_label: str | None = None,
    group_edit_mode: bool = False,
    group_count: int | None = None,
    drawings_enabled: bool = True,
    machine_profile_key: str | None = None,
):
    dialog_cls = resolve_work_editor_dialog_class(machine_profile_key)
    return dialog_cls(
        draw_service,
        work=work,
        parent=parent,
        style_host=style_host,
        translate=translate,
        batch_label=batch_label,
        group_edit_mode=group_edit_mode,
        group_count=group_count,
        drawings_enabled=drawings_enabled,
        machine_profile_key=machine_profile_key,
    )
