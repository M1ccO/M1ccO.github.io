from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from config import ENABLE_TOOL_LIBRARY_PRELOAD

_TRACE_ENABLED = str(os.environ.get("NTX_TOOL_LIBRARY_LAUNCH_TRACE", "1")).strip().lower() not in {"0", "false", "no", "off"}
_BYPASS_BACKGROUND_PRELOAD = str(
    os.environ.get("NTX_DIAG_BYPASS_BACKGROUND_TOOL_LIBRARY_PRELOAD", "0")
).strip().lower() in {"1", "true", "yes", "on"}
_ENABLE_HIDDEN_AUTO_LAUNCH = str(
    os.environ.get("NTX_ENABLE_HIDDEN_TOOL_LIBRARY_AUTO_LAUNCH", "1")
).strip().lower() in {"1", "true", "yes", "on"}
_BYPASS_PRELOAD_WHEN_EMBEDDED = str(
    os.environ.get("NTX_BYPASS_PRELOAD_IN_EMBEDDED_MODE", "0")
).strip().lower() in {"1", "true", "yes", "on"}


def _write_preload_trace(event: str, **fields) -> None:
    if not _TRACE_ENABLED:
        return
    try:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "pid": os.getpid(),
        }
        payload.update({k: v for k, v in fields.items() if v not in (None, "")})
        path = Path(__file__).resolve().parents[2] / "temp" / "tool_library_launch_trace.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _is_visible_work_editor(widget) -> bool:
    return bool(widget is not None and widget.isVisible() and widget.property("workEditorDialog"))


def _build_silent_preload_payload(window) -> dict:
    payload = {"show": False}

    draw_service = getattr(window, "draw_service", None)
    if draw_service is not None:
        tools_db_path = str(getattr(draw_service, "tool_db_path", "") or "").strip()
        jaws_db_path = str(getattr(draw_service, "jaw_db_path", "") or "").strip()
        fixtures_db_path = str(
            getattr(draw_service, "fixture_db_path", getattr(draw_service, "jaw_db_path", "")) or ""
        ).strip()
        if tools_db_path:
            payload["tools_db_path"] = tools_db_path
        if jaws_db_path:
            payload["jaws_db_path"] = jaws_db_path
        if fixtures_db_path:
            payload["fixtures_db_path"] = fixtures_db_path

    work_service = getattr(window, "work_service", None)
    get_machine_profile_key = getattr(work_service, "get_machine_profile_key", None)
    if callable(get_machine_profile_key):
        machine_profile_key = str(get_machine_profile_key() or "").strip().lower()
        if machine_profile_key:
            payload["machine_profile_key"] = machine_profile_key

    return payload


def initialize_preload_state(window) -> None:
    window._tool_library_preload_completed = not bool(ENABLE_TOOL_LIBRARY_PRELOAD)
    window._tool_library_preload_retries = 0
    window._tool_library_preload_max_retries = 24
    window._tool_library_preload_scheduled = False
    window._tool_library_preload_pause_count = 0
    window._tool_library_preload_launch_started = False


def pause_tool_library_preload(window) -> None:
    if not ENABLE_TOOL_LIBRARY_PRELOAD:
        return
    window._tool_library_preload_pause_count = max(0, int(getattr(window, "_tool_library_preload_pause_count", 0))) + 1


def resume_tool_library_preload(window, schedule_delay_ms: int = 700) -> None:
    if not ENABLE_TOOL_LIBRARY_PRELOAD:
        return
    pause_count = max(0, int(getattr(window, "_tool_library_preload_pause_count", 0)))
    if pause_count <= 0:
        return
    window._tool_library_preload_pause_count = pause_count - 1
    if window._tool_library_preload_pause_count == 0 and not getattr(window, "_tool_library_preload_completed", False):
        if not getattr(window, "_tool_library_preload_scheduled", False):
            window._tool_library_preload_scheduled = True
            QTimer.singleShot(max(0, int(schedule_delay_ms)), lambda: retry_tool_library_preload(window))


def preload_tool_library_background(window) -> None:
    if not ENABLE_TOOL_LIBRARY_PRELOAD:
        _write_preload_trace("preload.background.disabled")
        window._tool_library_preload_completed = True
        return
    if _BYPASS_BACKGROUND_PRELOAD:
        _write_preload_trace("preload.background.bypassed")
        return
    if window._tool_library_preload_completed:
        _write_preload_trace("preload.background.skip_completed")
        return
    if int(getattr(window, "_tool_library_preload_pause_count", 0)) > 0:
        _write_preload_trace("preload.background.paused", pause_count=int(getattr(window, "_tool_library_preload_pause_count", 0)))
        if not window._tool_library_preload_scheduled:
            window._tool_library_preload_scheduled = True
            QTimer.singleShot(700, lambda: retry_tool_library_preload(window))
        return

    app = QApplication.instance()
    active_modal = app.activeModalWidget() if app is not None else None
    work_editor_visible = False
    if app is not None:
        for top in app.topLevelWidgets():
            if _is_visible_work_editor(top):
                work_editor_visible = True
                break

    if (
        active_modal is not None
        or work_editor_visible
        or not window.isVisible()
        or window.isMinimized()
    ):
        _write_preload_trace(
            "preload.background.defer",
            modal=bool(active_modal is not None),
            work_editor_visible=bool(work_editor_visible),
            window_visible=bool(window.isVisible()),
            window_minimized=bool(window.isMinimized()),
        )
        if window._tool_library_preload_retries < window._tool_library_preload_max_retries:
            window._tool_library_preload_retries += 1
            if not window._tool_library_preload_scheduled:
                window._tool_library_preload_scheduled = True
                QTimer.singleShot(700, lambda: retry_tool_library_preload(window))
        return

    if window._send_to_tool_library(_build_silent_preload_payload(window)):
        _write_preload_trace("preload.background.ipc_success")
        window._tool_library_preload_completed = True
        window._tool_library_preload_launch_started = False
        return

    launch_started = bool(getattr(window, "_tool_library_preload_launch_started", False))
    ready_check = getattr(window, "_is_tool_library_ready", None)
    is_ready = False
    if callable(ready_check):
        try:
            is_ready = bool(ready_check())
        except Exception:
            is_ready = False

    if launch_started or is_ready:
        _write_preload_trace("preload.background.wait_ready", launch_started=bool(launch_started), is_ready=bool(is_ready))
        if window._tool_library_preload_retries < window._tool_library_preload_max_retries:
            window._tool_library_preload_retries += 1
            if not window._tool_library_preload_scheduled:
                window._tool_library_preload_scheduled = True
                QTimer.singleShot(350, lambda: retry_tool_library_preload(window))
        return

    if not _ENABLE_HIDDEN_AUTO_LAUNCH:
        _write_preload_trace("preload.background.hidden_auto_launch.disabled")
        window._tool_library_preload_completed = True
        return

    if _BYPASS_PRELOAD_WHEN_EMBEDDED:
        _write_preload_trace("preload.background.bypassed_for_embedded")
        window._tool_library_preload_completed = True
        return

    if window._launch_tool_library(["--hidden"]):
        _write_preload_trace("preload.background.launch_started")
        window._tool_library_preload_launch_started = True
        if not window._tool_library_preload_scheduled:
            window._tool_library_preload_scheduled = True
            QTimer.singleShot(350, lambda: retry_tool_library_preload(window))


def retry_tool_library_preload(window) -> None:
    if not ENABLE_TOOL_LIBRARY_PRELOAD:
        return
    window._tool_library_preload_scheduled = False
    preload_tool_library_background(window)