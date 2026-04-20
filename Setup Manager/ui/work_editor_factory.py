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


def _bump_resolver_caches_on_work_editor_open() -> None:
    """Natural sync point: invalidate resolver caches before Work Editor opens.

    The user may have edited the Tool or Jaw Library in the separate
    library process. The shared resolver cannot see those writes, so
    every Work Editor open performs a coarse cache bump to guarantee
    fresh labels/metadata. Cheap (only drops in-memory dicts) and runs
    once per open.
    """
    try:
        from services.preload_manager import get_preload_manager
    except Exception:
        return
    try:
        get_preload_manager().bump_revisions()
    except Exception:
        # Non-fatal: stale cache is a display issue, not a crash cause.
        pass


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
    _bump_resolver_caches_on_work_editor_open()
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
