from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtNetwork import QLocalSocket


def allow_set_foreground() -> None:
    """Grant any process permission to call SetForegroundWindow (Windows)."""
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(ctypes.wintypes.DWORD(-1))
    except Exception:
        pass


def send_to_tool_library(server_name: str, payload: dict, retries: int = 3, timeout_ms: int = 1500) -> bool:
    """Send an IPC payload to a running Tool Library instance."""
    for _ in range(retries):
        sock = QLocalSocket()
        sock.connectToServer(server_name)
        if not sock.waitForConnected(timeout_ms):
            try:
                sock.disconnectFromServer()
            except Exception:
                pass
            continue
        try:
            sock.write(json.dumps(payload).encode("utf-8"))
            sock.flush()
            if sock.waitForBytesWritten(timeout_ms):
                return True
        except Exception:
            pass
        finally:
            try:
                sock.disconnectFromServer()
            except Exception:
                pass
    return False


def launch_tool_library(
    tool_library_main_path: Path,
    exe_candidates: list[Path],
    project_dir: Path,
    extra_args: list | None = None,
) -> bool:
    """Start the Tool Library process. Returns True on success."""
    args = list(extra_args or [])

    def _is_safe_exe_target(exe_path: Path) -> bool:
        try:
            resolved = exe_path.resolve()
            current = Path(sys.executable).resolve()
        except Exception:
            return False
        if not resolved.exists() or resolved == current:
            return False
        return "tool library" in resolved.name.lower()

    if tool_library_main_path.exists() and not getattr(sys, "frozen", False):
        candidates = []
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        if pythonw.exists():
            candidates.append(str(pythonw))
        candidates.append(str(Path(sys.executable)))
        py_cmd = shutil.which("python")
        if py_cmd:
            candidates.append(py_cmd)
        py_launcher = shutil.which("py")
        if py_launcher:
            candidates.append(py_launcher)

        for candidate in candidates:
            cmd_args = [str(tool_library_main_path)] + args
            candidate_name = Path(candidate).name.lower()
            if candidate_name in {"py.exe", "py"}:
                cmd_args = ["-3", str(tool_library_main_path)] + args
            if QProcess.startDetached(candidate, cmd_args, str(project_dir)):
                return True

    for exe_path in exe_candidates:
        if _is_safe_exe_target(exe_path):
            if QProcess.startDetached(str(exe_path), args, str(exe_path.parent)):
                return True
    return False


def send_request_with_retry(
    send_func,
    payload: dict,
    attempts: int = 36,
    delay_ms: int = 300,
    on_success=None,
    on_failed=None,
) -> None:
    """Retry IPC shortly after launch so module/filter payload is applied."""
    if send_func(payload):
        if callable(on_success):
            on_success()
        return
    if attempts <= 1:
        if callable(on_failed):
            on_failed()
        return
    QTimer.singleShot(
        delay_ms,
        lambda: send_request_with_retry(
            send_func,
            payload,
            attempts - 1,
            delay_ms,
            on_success=on_success,
            on_failed=on_failed,
        ),
    )
