from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QMessageBox

_log = logging.getLogger(__name__)


def handoff_to_setup_manager(window, *, setup_manager_server_name: str, source_dir: Path) -> None:
    import ctypes
    import ctypes.wintypes

    x, y, width, height = window._current_window_rect()
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

    _log.debug("handoff_to_setup_manager: sending IPC to server=%r", setup_manager_server_name)
    sent = _send_show_request(
        setup_manager_server_name=setup_manager_server_name,
        geometry=geometry,
    )
    _log.debug("handoff_to_setup_manager: IPC sent=%s", sent)
    if sent:
        QTimer.singleShot(120, lambda: _complete_handoff(window))
        return

    launched = _launch_setup_manager(geometry=geometry, source_dir=source_dir)
    _log.debug("handoff_to_setup_manager: launch=%s", launched)
    if launched:
        # Cold-launch path: keep the Library visible just long enough for the
        # target process to surface its first window before we hide.
        QTimer.singleShot(300, lambda: _complete_handoff(window))
        return

    QMessageBox.warning(
        window,
        "Setup Manager unavailable",
        "Could not locate a launchable Setup Manager instance.",
    )


def _complete_handoff(window) -> None:
    window.hide()
    window.setWindowOpacity(1.0)


def _send_show_request(*, setup_manager_server_name: str, geometry: str) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(setup_manager_server_name)
    if not socket.waitForConnected(300):
        return False
    try:
        socket.write(
            json.dumps(
                {
                    "command": "show",
                    "geometry": geometry,
                }
            ).encode("utf-8")
        )
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
