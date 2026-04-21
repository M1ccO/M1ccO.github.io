from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QMessageBox
from shared.ui.transition_shell import (
    SENDER_TRANSITION_COMPLETE_COMMAND,
    cancel_sender_transition,
    complete_sender_transition,
    prepare_sender_transition,
)

_log = logging.getLogger(__name__)


def handoff_to_setup_manager(
    window,
    *,
    setup_manager_server_name: str,
    source_dir: Path,
    callback_server_name: str = "",
) -> None:
    import ctypes
    import ctypes.wintypes

    x, y, width, height = window._current_window_rect()
    prepare_sender_transition(window, geometry=(x, y, width, height))
    geometry = f"{x},{y},{width},{height}"
    _log.debug("handoff_to_setup_manager: opacity=%.2f geometry=%s", window.windowOpacity(), geometry)

    try:
        ctypes.windll.user32.AllowSetForegroundWindow(ctypes.wintypes.DWORD(-1))
    except Exception:
        pass

    # Cancel any in-flight fade-in timer so Library doesn't re-appear.
    _pending = getattr(window, "_pending_fade_in_timer", None)
    if _pending is not None:
        try:
            _pending.stop()
        except Exception:
            pass
        window._pending_fade_in_timer = None
    # Also stop any running fade animation.
    _fade_anim = getattr(window, "_fade_anim", None)
    if _fade_anim is not None:
        try:
            _fade_anim.stop()
        except Exception:
            pass
        window._fade_anim = None

    window.setWindowOpacity(1.0)

    payload = _show_request_payload(
        geometry=geometry,
        callback_server_name=callback_server_name,
    )

    _log.debug("handoff_to_setup_manager: sending IPC to server=%r", setup_manager_server_name)
    sent = _send_show_request(
        setup_manager_server_name=setup_manager_server_name,
        payload=payload,
    )
    _log.debug("handoff_to_setup_manager: IPC sent=%s", sent)
    if sent:
        if not callback_server_name:
            QTimer.singleShot(120, lambda: complete_setup_manager_handoff(window))
        return

    launched = _launch_setup_manager(geometry=geometry, source_dir=source_dir)
    _log.debug("handoff_to_setup_manager: launch=%s", launched)
    if launched:
        _send_show_request_with_retry(
            setup_manager_server_name=setup_manager_server_name,
            payload=payload,
            on_failed=lambda: _handle_setup_manager_start_timeout(window),
        )
        if not callback_server_name:
            QTimer.singleShot(300, lambda: complete_setup_manager_handoff(window))
        return

    cancel_sender_transition(window)
    QMessageBox.warning(
        window,
        "Setup Manager unavailable",
        "Could not locate a launchable Setup Manager instance.",
    )


def complete_setup_manager_handoff(window) -> None:
    complete_sender_transition(window)


def _handle_setup_manager_start_timeout(window) -> None:
    cancel_sender_transition(window)
    QMessageBox.warning(
        window,
        "Setup Manager unavailable",
        "Setup Manager started but did not become ready in time. Please try again.",
    )


def _show_request_payload(*, geometry: str, callback_server_name: str) -> dict:
    payload = {
        "command": "show",
        "geometry": geometry,
    }
    callback_server_name = str(callback_server_name or "").strip()
    if callback_server_name:
        payload["handoff_hide_callback_server"] = callback_server_name
    return payload


def _send_show_request(*, setup_manager_server_name: str, payload: dict) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(setup_manager_server_name)
    if not socket.waitForConnected(300):
        return False
    try:
        socket.write(json.dumps(payload).encode("utf-8"))
        socket.flush()
        socket.waitForBytesWritten(300)
        return True
    except Exception:
        return False
    finally:
        try:
            socket.disconnectFromServer()
        except Exception:
            pass


def _send_show_request_with_retry(
    *,
    setup_manager_server_name: str,
    payload: dict,
    attempts: int = 36,
    delay_ms: int = 300,
    max_delay_ms: int = 1600,
    on_failed=None,
) -> None:
    if _send_show_request(setup_manager_server_name=setup_manager_server_name, payload=payload):
        return
    if attempts <= 1:
        if callable(on_failed):
            on_failed()
        return
    QTimer.singleShot(
        delay_ms,
        lambda: _send_show_request_with_retry(
            setup_manager_server_name=setup_manager_server_name,
            payload=payload,
            attempts=attempts - 1,
            delay_ms=min(max_delay_ms, int(delay_ms * 1.25)),
            max_delay_ms=max_delay_ms,
            on_failed=on_failed,
        ),
    )


def _launch_setup_manager(*, geometry: str, source_dir: Path) -> bool:
    setup_roots = [
        source_dir.parent / "Setup Manager",
        Path(sys.executable).resolve().parent.parent / "Setup Manager",
    ]
    for setup_root in setup_roots:
        setup_manager_main = setup_root / "main.py"
        if setup_manager_main.exists():
            try:
                launched = QProcess.startDetached(
                    str(Path(sys.executable)),
                    [str(setup_manager_main), "--geometry", geometry],
                    str(setup_root),
                )
            except Exception:
                launched = False
            if launched:
                return True

        setup_manager_exe = setup_root / "Setup Manager.exe"
        if not setup_manager_exe.exists():
            continue
        try:
            launched = QProcess.startDetached(
                str(setup_manager_exe),
                ["--geometry", geometry],
                str(setup_root),
            )
        except Exception:
            launched = False
        if launched:
            return True
    return False
