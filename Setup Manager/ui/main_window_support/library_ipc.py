from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import logging
import os
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtNetwork import QLocalSocket


LOGGER = logging.getLogger(__name__)
_TRACE_ENABLED = str(os.environ.get("NTX_TOOL_LIBRARY_LAUNCH_TRACE", "1")).strip().lower() not in {"0", "false", "no", "off"}
_BYPASS_LAUNCH = str(os.environ.get("NTX_DIAG_BYPASS_TOOL_LIBRARY_LAUNCH", "0")).strip().lower() in {"1", "true", "yes", "on"}
_ENABLE_HIDDEN_AUTO_LAUNCH = str(
    os.environ.get("NTX_ENABLE_HIDDEN_TOOL_LIBRARY_AUTO_LAUNCH", "1")
).strip().lower() in {"1", "true", "yes", "on"}


def _trace_path() -> Path:
    return Path(__file__).resolve().parents[2] / "temp" / "tool_library_launch_trace.log"


def _write_launch_trace(event: str, **fields) -> None:
    if not _TRACE_ENABLED:
        return
    try:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "pid": os.getpid(),
        }
        payload.update({k: v for k, v in fields.items() if v not in (None, "")})
        path = _trace_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _caller_hint() -> str:
    try:
        frames = traceback.extract_stack(limit=10)
        for frame in reversed(frames[:-1]):
            file_lower = frame.filename.replace("\\", "/").lower()
            if file_lower.endswith("library_ipc.py"):
                continue
            return f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
    except Exception:
        pass
    return ""


def allow_set_foreground() -> None:
    """Grant any process permission to call SetForegroundWindow (Windows)."""
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(ctypes.wintypes.DWORD(-1))
    except Exception:
        pass


def send_to_tool_library(server_name: str, payload: dict, retries: int = 3, timeout_ms: int = 1500) -> bool:
    """Send an IPC payload to a running Tool Library instance."""
    _write_launch_trace(
        "ipc.send.begin",
        server=str(server_name or ""),
        retries=int(retries),
        caller=_caller_hint(),
        command=str((payload or {}).get("command") or ""),
        selector_mode=str((payload or {}).get("selector_mode") or ""),
        show=str((payload or {}).get("show") or ""),
    )
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
                _write_launch_trace("ipc.send.success", server=str(server_name or ""), caller=_caller_hint())
                return True
        except Exception:
            pass
        finally:
            try:
                sock.disconnectFromServer()
            except Exception:
                pass
    _write_launch_trace("ipc.send.failed", server=str(server_name or ""), caller=_caller_hint())
    return False


def is_tool_library_ready(server_name: str, ready_path: Path | None = None, timeout_ms: int = 200) -> bool:
    """Return True when Tool Library appears ready to accept IPC payloads."""
    if ready_path is not None:
        try:
            if ready_path.exists() and ready_path.read_text(encoding="utf-8").strip().lower() == "ready":
                return True
        except Exception:
            pass

    sock = QLocalSocket()
    sock.connectToServer(server_name)
    try:
        if sock.waitForConnected(timeout_ms):
            return True
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
    ready_path: Path | None = None,
) -> bool:
    """Start the Tool Library process. Returns True on success."""
    args = list(extra_args or [])
    hidden_launch = any(str(arg).strip().lower() == "--hidden" for arg in args)
    _write_launch_trace(
        "launch.request",
        caller=_caller_hint(),
        main_path=str(tool_library_main_path),
        project_dir=str(project_dir),
        args=" ".join(str(a) for a in args),
        hidden_launch=bool(hidden_launch),
        enable_hidden_auto_launch=bool(_ENABLE_HIDDEN_AUTO_LAUNCH),
        bypass=bool(_BYPASS_LAUNCH),
    )

    if hidden_launch and not _ENABLE_HIDDEN_AUTO_LAUNCH:
        _write_launch_trace(
            "launch.hidden_auto_launch.disabled",
            caller=_caller_hint(),
            args=" ".join(str(a) for a in args),
        )
        return False

    if _BYPASS_LAUNCH:
        _write_launch_trace("launch.bypassed", caller=_caller_hint())
        return False

    if ready_path is not None:
        try:
            ready_path.unlink(missing_ok=True)
        except Exception:
            pass

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
                LOGGER.info("Tool Library launch detached via interpreter: %s", candidate)
                _write_launch_trace(
                    "launch.detached.interpreter",
                    caller=_caller_hint(),
                    candidate=str(candidate),
                    cmd_args=" ".join(str(a) for a in cmd_args),
                    cwd=str(project_dir),
                )
                return True

    for exe_path in exe_candidates:
        if _is_safe_exe_target(exe_path):
            if QProcess.startDetached(str(exe_path), args, str(exe_path.parent)):
                LOGGER.info("Tool Library launch detached via executable: %s", exe_path)
                _write_launch_trace(
                    "launch.detached.executable",
                    caller=_caller_hint(),
                    candidate=str(exe_path),
                    cmd_args=" ".join(str(a) for a in args),
                    cwd=str(exe_path.parent),
                )
                return True
    LOGGER.warning("Tool Library launch failed: no launchable target resolved")
    _write_launch_trace("launch.failed", caller=_caller_hint())
    return False


def send_request_with_retry(
    send_func,
    payload: dict,
    attempts: int = 36,
    delay_ms: int = 300,
    on_success=None,
    on_failed=None,
    ready_check=None,
    max_delay_ms: int = 1600,
) -> None:
    """Retry IPC shortly after launch so module/filter payload is applied."""

    ready = True
    if callable(ready_check):
        try:
            ready = bool(ready_check())
        except Exception:
            ready = True

    # Even if readiness probe says "not ready", try IPC anyway to avoid
    # false-negative probes when runtime paths differ between launch modes.
    if send_func(payload):
        if callable(on_success):
            on_success()
        return

    if not ready:
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
                min(max_delay_ms, int(delay_ms * 1.25)),
                on_success=on_success,
                on_failed=on_failed,
                ready_check=ready_check,
                max_delay_ms=max_delay_ms,
            ),
        )
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
            min(max_delay_ms, int(delay_ms * 1.25)),
            on_success=on_success,
            on_failed=on_failed,
            ready_check=ready_check,
            max_delay_ms=max_delay_ms,
        ),
    )
