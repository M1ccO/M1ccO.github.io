"""Opt-in trace logging for the Library editor launch glitch investigation."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)
_START = time.monotonic()
_ENABLED_VALUES = {"1", "true", "yes", "on", "debug"}
_CURRENT_LAUNCH_ID = ""


def editor_launch_debug_enabled() -> bool:
    """Return whether editor launch debug tracing is enabled."""
    value = os.environ.get("NTX_EDITOR_GLITCH_DEBUG", "")
    return value.strip().lower() in _ENABLED_VALUES


def editor_launch_diag_enabled(name: str) -> bool:
    """Return whether an opt-in editor launch diagnostic bypass is enabled."""
    suffix = str(name or "").strip().upper()
    if not suffix:
        return False
    value = os.environ.get(f"NTX_EDITOR_DIAG_{suffix}", "")
    return value.strip().lower() in _ENABLED_VALUES


def editor_launch_debug_log_path() -> Path:
    """Return the trace file path used when editor launch debug is enabled."""
    configured = os.environ.get("NTX_EDITOR_GLITCH_LOG", "").strip()
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "ntx_editor_glitch.log"


def _safe_text(value: Any) -> str:
    try:
        text = str(value)
    except Exception:
        text = repr(value)
    return text.replace("\n", "\\n").replace("\r", "\\r")


def _window_summary(window: Any) -> dict[str, str]:
    if window is None:
        return {}
    summary: dict[str, str] = {"class": type(window).__name__}
    for key, attr in (
        ("object", "objectName"),
        ("title", "windowTitle"),
        ("visible", "isVisible"),
        ("active", "isActiveWindow"),
        ("opacity", "windowOpacity"),
    ):
        try:
            value = getattr(window, attr)()
        except Exception:
            continue
        summary[key] = _safe_text(value)
    return summary


def _active_window_summary() -> dict[str, str]:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return {}
    app = QApplication.instance()
    if app is None:
        return {}
    try:
        return _window_summary(app.activeWindow())
    except Exception:
        return {}


def editor_launch_debug(event: str, **fields: Any) -> None:
    """Write one timestamped editor launch trace event when enabled."""
    if not editor_launch_debug_enabled():
        return

    payload: dict[str, str] = {
        "wall": datetime.now().isoformat(timespec="milliseconds"),
        "t_ms": str(int((time.monotonic() - _START) * 1000)),
        "event": event,
    }

    active = _active_window_summary()
    for key, value in active.items():
        payload[f"active_{key}"] = value

    for key, value in fields.items():
        payload[key] = _safe_text(value)

    line = " ".join(f"{key}={value!r}" for key, value in payload.items())
    LOG.debug("editor_launch_trace %s", line)

    path = editor_launch_debug_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        LOG.exception("Failed to write editor launch trace to %s", path)


def attach_editor_launch_id(target: Any, launch_id: str) -> None:
    """Attach a correlation id to a Qt object without assuming its type."""
    try:
        setattr(target, "_editor_launch_debug_id", launch_id)
    except Exception:
        pass


def set_editor_launch_context(launch_id: str) -> None:
    """Set the current launch id for widgets constructed before attachment."""
    global _CURRENT_LAUNCH_ID
    _CURRENT_LAUNCH_ID = _safe_text(launch_id)


def clear_editor_launch_context(launch_id: str = "") -> None:
    """Clear the current launch id if it still matches the active context."""
    global _CURRENT_LAUNCH_ID
    if not launch_id or _CURRENT_LAUNCH_ID == _safe_text(launch_id):
        _CURRENT_LAUNCH_ID = ""


def editor_launch_id(target: Any) -> str:
    """Find the nearest attached editor launch debug id."""
    current = target
    while current is not None:
        value = getattr(current, "_editor_launch_debug_id", "")
        if value:
            return _safe_text(value)
        try:
            current = current.parent()
        except Exception:
            break
    return _CURRENT_LAUNCH_ID


def _win32_process_window_snapshot() -> list[dict[str, str]]:
    if os.name != "nt":
        return []

    user32 = getattr(ctypes.windll, "user32", None)
    if user32 is None:
        return []

    current_pid = os.getpid()
    entries: list[dict[str, str]] = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

    def _enum_callback(hwnd, _lparam):
        try:
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if int(pid.value) != int(current_pid):
                return True

            length = int(user32.GetWindowTextLengthW(hwnd))
            title_buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buf, len(title_buf))

            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_buf, len(class_buf))

            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))

            entries.append(
                {
                    "hwnd": hex(int(hwnd)),
                    "class": _safe_text(class_buf.value),
                    "title": _safe_text(title_buf.value),
                    "visible": _safe_text(bool(user32.IsWindowVisible(hwnd))),
                    "x": str(int(rect.left)),
                    "y": str(int(rect.top)),
                    "w": str(max(0, int(rect.right - rect.left))),
                    "h": str(max(0, int(rect.bottom - rect.top))),
                }
            )
        except Exception:
            return True
        return True

    try:
        user32.EnumWindows(WNDENUMPROC(_enum_callback), 0)
    except Exception:
        return []
    return entries


def start_editor_window_probe(host: Any, trigger: str, *, duration_ms: int = 900, interval_ms: int = 25) -> None:
    """Sample top-level Qt/native windows around a suspected glitch trigger."""
    if not editor_launch_diag_enabled("WINDOW_PROBE"):
        return

    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except Exception:
        return

    app = QApplication.instance()
    if app is None:
        return

    probe_id = f"{_safe_text(trigger)}-{int(time.monotonic() * 1000)}"
    total_ticks = max(1, int(max(1, duration_ms) / max(1, interval_ms)))
    state = {"tick": 0, "last_signature": ""}

    editor_launch_debug(
        "probe.start",
        probe_id=probe_id,
        trigger=trigger,
        duration_ms=duration_ms,
        interval_ms=interval_ms,
    )

    timer_parent = host if host is not None else app
    timer = QTimer(timer_parent)
    timer.setInterval(max(1, int(interval_ms)))

    probes = getattr(app, "_editor_glitch_probe_timers", None)
    if probes is None:
        probes = []
        setattr(app, "_editor_glitch_probe_timers", probes)
    probes.append(timer)

    def _snapshot() -> list[dict[str, str]]:
        return _win32_process_window_snapshot()

    def _tick() -> None:
        native_windows = _snapshot()
        signature = repr(native_windows)
        if signature != state["last_signature"]:
            state["last_signature"] = signature
            editor_launch_debug(
                "probe.snapshot",
                probe_id=probe_id,
                trigger=trigger,
                tick=state["tick"],
                native_windows=native_windows,
            )

        state["tick"] += 1
        if state["tick"] >= total_ticks:
            try:
                timer.stop()
            except Exception:
                pass
            try:
                probes.remove(timer)
            except Exception:
                pass
            editor_launch_debug("probe.end", probe_id=probe_id, trigger=trigger, ticks=state["tick"])
            try:
                timer.deleteLater()
            except Exception:
                pass

    timer.timeout.connect(_tick)
    _tick()
    if state["tick"] < total_ticks:
        timer.start()


def cleanup_hidden_orphan_top_levels(host: Any = None, *, reason: str = "") -> int:
    """Delete hidden orphan top-level Qt widgets that can leak native surfaces."""
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return 0

    app = QApplication.instance()
    if app is None:
        return 0

    keep_ids = {id(host)} if host is not None else set()
    try:
        active = app.activeWindow()
        if active is not None:
            keep_ids.add(id(active))
    except Exception:
        pass

    cleaned = 0
    cleaned_items: list[str] = []
    basic_widget_classes = {
        "QLabel",
        "QLineEdit",
        "QPushButton",
        "QToolButton",
        "QFrame",
        "QComboBox",
        "QProgressDialog",
    }
    keep_class_suffixes = (
        "MainWindow",
        "ToolSelectorDialog",
        "JawSelectorDialog",
        "FixtureSelectorDialog",
        "AddEditToolDialog",
        "AddEditJawDialog",
        "FixtureEditorDialog",
        "PreferencesDialog",
    )

    for widget in list(app.topLevelWidgets()):
        if widget is None or id(widget) in keep_ids:
            continue

        try:
            if widget.parentWidget() is not None:
                continue
            if widget.isVisible() or widget.isActiveWindow():
                continue

            class_name = type(widget).__name__
            if any(class_name.endswith(suffix) for suffix in keep_class_suffixes):
                continue

            title = str(widget.windowTitle() or "").strip()
            should_cleanup = (
                class_name in basic_widget_classes
                or title in {"", "python3", "pythonw3", "pythonw", "Loading"}
            )
            if not should_cleanup:
                continue

            cleaned += 1
            cleaned_items.append(f"{class_name}:{title or '<empty>'}")
            try:
                widget.close()
            except Exception:
                pass
            try:
                widget.deleteLater()
            except Exception:
                pass
        except Exception:
            continue

    if cleaned:
        editor_launch_debug(
            "cleanup.hidden_orphan_top_levels",
            reason=reason,
            cleaned=cleaned,
            widgets=cleaned_items,
        )
    return cleaned


__all__ = [
    "attach_editor_launch_id",
    "clear_editor_launch_context",
    "cleanup_hidden_orphan_top_levels",
    "editor_launch_diag_enabled",
    "editor_launch_debug",
    "editor_launch_debug_enabled",
    "editor_launch_debug_log_path",
    "editor_launch_id",
    "start_editor_window_probe",
    "set_editor_launch_context",
]
