from __future__ import annotations

from ui.machine_family_runtime import secondary_library_label, secondary_library_module
from ui.work_editor_factory import create_work_editor_dialog


def page_machine_profile_key(page) -> str | None:
    work_service = getattr(page, "work_service", None)
    getter = getattr(work_service, "get_machine_profile_key", None)
    if callable(getter):
        return getter()
    return None


def create_page_work_editor_dialog(page, host_window, work=None, **overrides):
    machine_profile_key = overrides.pop("machine_profile_key", page_machine_profile_key(page))
    return create_work_editor_dialog(
        page.draw_service,
        work=work,
        parent=None,
        style_host=host_window,
        translate=page._t,
        drawings_enabled=page.drawings_enabled,
        machine_profile_key=machine_profile_key,
        **overrides,
    )


def page_secondary_library_module(page) -> str:
    return secondary_library_module(profile_key=page_machine_profile_key(page))


def page_secondary_library_label(page) -> str:
    return secondary_library_label(profile_key=page_machine_profile_key(page))
