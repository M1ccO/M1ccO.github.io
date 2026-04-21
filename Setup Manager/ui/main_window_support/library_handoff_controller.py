from __future__ import annotations

from config import SETUP_MANAGER_SERVER_NAME
from PySide6.QtWidgets import QMessageBox
from shared.ui.transition_shell import cancel_sender_transition, complete_sender_transition, prepare_sender_transition

from .library_ipc import allow_set_foreground


_NO_MATCH_ID = "__NO_MATCH_LINKED_ITEMS__"


def complete_tool_library_handoff(window) -> None:
    complete_sender_transition(window)


def _selected_module(module: str) -> str:
    if module == "fixtures":
        return "fixtures"
    if module == "jaws":
        return "jaws"
    return "tools"


def _show_library_start_timeout(window) -> None:
    QMessageBox.warning(
        window,
        window._t("setup_manager.library_unavailable.title", "Tool Library unavailable"),
        window._t(
            "setup_manager.library_unavailable.start_timeout",
            "Tool Library started but did not become ready in time. Please try again.",
        ),
    )


def _show_library_unavailable(window) -> None:
    QMessageBox.warning(
        window,
        window._t("setup_manager.library_unavailable.title", "Tool Library unavailable"),
        window._t(
            "setup_manager.library_unavailable.body",
            "Could not find a launchable Tool Library executable or source entry point.",
        ),
    )


def _library_payload(window, *, module: str, geometry: str, clear_master_filter: bool = False, safe_tools=None, safe_jaws=None) -> dict:
    payload = {
        "geometry": geometry,
        "show": True,
        "module": _selected_module(module),
        "tools_db_path": str(window.draw_service.tool_db_path),
        "jaws_db_path": str(window.draw_service.jaw_db_path),
        "fixtures_db_path": str(getattr(window.draw_service, "fixture_db_path", window.draw_service.jaw_db_path)),
    }
    profile_key = str(getattr(window.work_service, "get_machine_profile_key", lambda: "")() or "").strip().lower()
    if profile_key:
        payload["machine_profile_key"] = profile_key
    if clear_master_filter:
        payload["clear_master_filter"] = True
    if safe_tools is not None:
        payload["master_filter_tools"] = list(safe_tools)
    if safe_jaws is not None:
        payload["master_filter_jaws"] = list(safe_jaws)
    if safe_tools is not None or safe_jaws is not None:
        payload["master_filter_active"] = True
    return payload


def _cancel_transition_and_show_start_timeout(window) -> None:
    cancel_sender_transition(window)
    _show_library_start_timeout(window)


def _begin_library_sender_transition(window, geometry_rect: tuple[int, int, int, int]) -> str:
    prepare_sender_transition(window, geometry=geometry_rect)
    x, y, width, height = geometry_rect
    return f"{x},{y},{width},{height}"


def open_tool_library_module(window, module: str) -> None:
    geometry = _begin_library_sender_transition(window, window._current_window_rect())
    allow_set_foreground()

    payload = _library_payload(
        window,
        module=module,
        geometry=geometry,
        clear_master_filter=True,
    )
    payload["handoff_hide_callback_server"] = SETUP_MANAGER_SERVER_NAME
    if window._send_to_tool_library(payload):
        return

    if window._launch_tool_library(["--geometry", geometry]):
        window._send_request_with_retry(
            payload,
            on_success=lambda: None,
            on_failed=lambda: _cancel_transition_and_show_start_timeout(window),
        )
        return

    cancel_sender_transition(window)
    _show_library_unavailable(window)


def open_tool_library_deep_link(window, kind: str, item_id: str) -> None:
    geometry = _begin_library_sender_transition(window, window._current_window_rect())
    allow_set_foreground()
    module = "jaws" if kind == "jaw" else "tools"
    payload = _library_payload(
        window,
        module=module,
        geometry=geometry,
        clear_master_filter=True,
    )
    payload["kind"] = str(kind or "").strip()
    payload["item_id"] = str(item_id or "").strip()
    payload["handoff_hide_callback_server"] = SETUP_MANAGER_SERVER_NAME
    if window._send_to_tool_library(payload):
        return

    if kind == "jaw":
        args = ["--geometry", geometry, "--open-jaw", item_id] if item_id else []
    else:
        args = ["--geometry", geometry, "--open-tool", item_id] if item_id else []
    if window._launch_tool_library(args):
        window._send_request_with_retry(
            payload,
            on_success=lambda: None,
            on_failed=lambda: _cancel_transition_and_show_start_timeout(window),
        )
        return
    cancel_sender_transition(window)
    _show_library_unavailable(window)


def open_tool_library_with_master_filter(window, tool_ids, jaw_ids, module: str = "tools") -> None:
    raw_tools = [str(t).strip() for t in (tool_ids or []) if str(t).strip()]
    raw_jaws = [str(j).strip() for j in (jaw_ids or []) if str(j).strip()]
    safe_tools = list(raw_tools) if raw_tools else [_NO_MATCH_ID]
    safe_jaws = list(raw_jaws) if raw_jaws else [_NO_MATCH_ID]
    selected_module = _selected_module(module)

    if selected_module == "tools" and tool_ids is not None and not raw_tools:
        QMessageBox.information(
            window,
            window._t("setup_manager.viewer.title", "Viewer"),
            window._t("setup_manager.viewer.no_tools", "No tools selected for this work."),
        )
    if selected_module == "jaws" and jaw_ids is not None and not raw_jaws:
        QMessageBox.information(
            window,
            window._t("setup_manager.viewer.title", "Viewer"),
            window._t("setup_manager.viewer.no_jaws", "No jaws selected for this work."),
        )
    if selected_module == "fixtures" and jaw_ids is not None and not raw_jaws:
        QMessageBox.information(
            window,
            window._t("setup_manager.viewer.title", "Viewer"),
            window._t("setup_manager.viewer.no_fixtures", "No fixtures selected for this work."),
        )

    geometry = _begin_library_sender_transition(window, window._current_window_rect())
    allow_set_foreground()

    payload = _library_payload(
        window,
        module=selected_module,
        geometry=geometry,
        safe_tools=safe_tools,
        safe_jaws=safe_jaws,
    )
    payload["handoff_hide_callback_server"] = SETUP_MANAGER_SERVER_NAME
    if window._send_to_tool_library(payload):
        return

    args = [
        "--geometry",
        geometry,
        "--master-filter-tools",
        ",".join(safe_tools),
        "--master-filter-jaws",
        ",".join(safe_jaws),
        "--master-filter-active",
        "1",
    ]
    if window._launch_tool_library(args):
        window._send_request_with_retry(
            payload,
            on_success=lambda: None,
            on_failed=lambda: _cancel_transition_and_show_start_timeout(window),
        )
        return

    cancel_sender_transition(window)
    _show_library_unavailable(window)
