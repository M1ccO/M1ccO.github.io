from __future__ import annotations

import os

from PySide6.QtCore import QTimer
from config import SETUP_MANAGER_SERVER_NAME
from PySide6.QtWidgets import QMessageBox
from shared.ui.transition_shell import cancel_sender_transition, complete_sender_transition, prepare_sender_transition

from .library_ipc import allow_set_foreground


_NO_MATCH_ID = "__NO_MATCH_LINKED_ITEMS__"
_HANDOFF_FALLBACK_TIMEOUT_MS = max(
    0,
    int(str(os.environ.get("NTX_LIBRARY_HANDOFF_FALLBACK_TIMEOUT_MS", "4500")).strip() or "4500"),
)
_FAST_IPC_TIMEOUT_MS = max(
    80,
    int(str(os.environ.get("NTX_LIBRARY_OPEN_FAST_IPC_TIMEOUT_MS", "220")).strip() or "220"),
)


def complete_tool_library_handoff(window) -> None:
    _clear_handoff_fallback_timer(window)
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
    _clear_handoff_fallback_timer(window)
    cancel_sender_transition(window)
    _show_library_start_timeout(window)


def _clear_handoff_fallback_timer(window) -> None:
    timer = getattr(window, "_library_handoff_fallback_timer", None)
    if timer is None:
        return
    try:
        timer.stop()
    except Exception:
        pass
    try:
        timer.deleteLater()
    except Exception:
        pass
    window._library_handoff_fallback_timer = None


def _start_handoff_fallback_timer(window) -> None:
    _clear_handoff_fallback_timer(window)
    if _HANDOFF_FALLBACK_TIMEOUT_MS <= 0:
        return

    timer = QTimer(window)
    timer.setSingleShot(True)
    timer.setInterval(int(_HANDOFF_FALLBACK_TIMEOUT_MS))

    def _fallback_recover() -> None:
        window._library_handoff_fallback_timer = None
        # If the sender transition never gets completed from IPC callback,
        # restore SM surface so the app never stays in a frozen transition shell.
        cancel_sender_transition(window)

    timer.timeout.connect(_fallback_recover)
    window._library_handoff_fallback_timer = timer
    timer.start()


def _begin_library_sender_transition(window, geometry_rect: tuple[int, int, int, int]) -> str:
    prepare_sender_transition(window, geometry=geometry_rect)
    _start_handoff_fallback_timer(window)
    x, y, width, height = geometry_rect
    return f"{x},{y},{width},{height}"


def _dispatch_open_payload(window, *, payload: dict, launch_args: list[str]) -> bool:
    # Fast first attempt to avoid long UI-thread blocking when IPC socket is stale.
    if window._send_to_tool_library(payload, retries=1, timeout_ms=_FAST_IPC_TIMEOUT_MS):
        return True

    is_ready_fn = getattr(window, "_is_tool_library_ready", None)
    is_ready = False
    if callable(is_ready_fn):
        try:
            is_ready = bool(is_ready_fn())
        except Exception:
            is_ready = False
    if is_ready:
        window._send_request_with_retry(
            payload,
            on_success=lambda: None,
            on_failed=lambda: _cancel_transition_and_show_start_timeout(window),
        )
        return True

    if window._launch_tool_library(launch_args):
        window._send_request_with_retry(
            payload,
            on_success=lambda: None,
            on_failed=lambda: _cancel_transition_and_show_start_timeout(window),
        )
        return True
    return False


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
    if _dispatch_open_payload(window, payload=payload, launch_args=["--geometry", geometry]):
        return

    cancel_sender_transition(window)
    _clear_handoff_fallback_timer(window)
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

    if kind == "jaw":
        args = ["--geometry", geometry, "--open-jaw", item_id] if item_id else []
    else:
        args = ["--geometry", geometry, "--open-tool", item_id] if item_id else []
    if _dispatch_open_payload(window, payload=payload, launch_args=args):
        return
    cancel_sender_transition(window)
    _clear_handoff_fallback_timer(window)
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
    if _dispatch_open_payload(window, payload=payload, launch_args=args):
        return

    cancel_sender_transition(window)
    _clear_handoff_fallback_timer(window)
    _show_library_unavailable(window)
