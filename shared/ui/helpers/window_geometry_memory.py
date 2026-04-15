from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication


_WINDOW_MEMORY_KEY = "window_memory"
_DETACHED_PREVIEW_POLICY_KEY = "detached_preview_policy"
_SUPPORTED_PREVIEW_MODES = {"follow_last", "left", "right", "embedded", "current"}


def _load_preferences(path: Path) -> dict:
    prefs_path = Path(path)
    if not prefs_path.exists():
        return {}
    try:
        payload = json.loads(prefs_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _save_preferences(path: Path, payload: dict) -> None:
    prefs_path = Path(path)
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    prefs_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _clamp_to_available_screen(rect: QRect) -> QRect:
    probe = QPoint(rect.x() + 20, rect.y() + 20)
    screen = QGuiApplication.screenAt(probe) or QGuiApplication.primaryScreen()
    if screen is None:
        return rect

    avail = screen.availableGeometry()
    width = max(360, min(rect.width(), avail.width()))
    height = max(260, min(rect.height(), avail.height()))
    x = max(avail.left(), min(rect.x(), avail.right() - width + 1))
    y = max(avail.top(), min(rect.y(), avail.bottom() - height + 1))
    return QRect(x, y, width, height)


def restore_window_geometry(window, preferences_path: Path, geometry_key: str) -> bool:
    prefs = _load_preferences(preferences_path)
    memory = prefs.get(_WINDOW_MEMORY_KEY)
    if not isinstance(memory, dict):
        return False

    stored = memory.get(str(geometry_key).strip())
    if not isinstance(stored, dict):
        return False

    try:
        rect = QRect(
            int(stored.get("x", 0)),
            int(stored.get("y", 0)),
            int(stored.get("w", 0)),
            int(stored.get("h", 0)),
        )
    except Exception:
        return False

    if rect.width() <= 0 or rect.height() <= 0:
        return False

    clamped = _clamp_to_available_screen(rect)
    window.setGeometry(clamped)
    return True


def save_window_geometry(window, preferences_path: Path, geometry_key: str) -> None:
    frame = window.frameGeometry()
    payload = {
        "x": int(frame.x()),
        "y": int(frame.y()),
        "w": int(frame.width()),
        "h": int(frame.height()),
    }

    prefs = _load_preferences(preferences_path)
    memory = prefs.get(_WINDOW_MEMORY_KEY)
    if not isinstance(memory, dict):
        memory = {}
    memory[str(geometry_key).strip()] = payload
    prefs[_WINDOW_MEMORY_KEY] = memory
    _save_preferences(preferences_path, prefs)


def get_detached_preview_open_mode(preferences_path: Path) -> str:
    prefs = _load_preferences(preferences_path)
    policy = prefs.get(_DETACHED_PREVIEW_POLICY_KEY)
    if not isinstance(policy, dict):
        return "follow_last"

    mode = str(policy.get("mode") or "follow_last").strip().lower()
    # Support legacy 'current' mode by converting to 'embedded'
    if mode == "current":
        mode = "embedded"
    if mode not in _SUPPORTED_PREVIEW_MODES:
        return "follow_last"
    return mode


def place_dialog_near_host(dialog, host_window, *, side: str = "right") -> None:
    if dialog is None or host_window is None:
        return

    host_frame = host_window.frameGeometry()
    host_geom = host_window.geometry()
    if host_frame.width() <= 0 or host_frame.height() <= 0:
        return

    width = min(max(520, int(host_frame.width() * 0.37)), 700)
    # Height: from content top to frame bottom
    height = host_frame.bottom() - host_geom.top()

    if str(side).strip().lower() == "left":
        x = host_frame.left() - width - 1
    else:
        x = host_frame.right() + 1
    y = host_geom.top()  # Start at content area top

    # Clamp position to screen bounds, preserving exact height
    probe = QPoint(x + 20, y + 20)
    screen = QGuiApplication.screenAt(probe) or QGuiApplication.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        x = max(avail.left(), min(x, avail.right() - width + 1))
        y = max(avail.top(), min(y, avail.bottom() - height + 1))
    
    dialog.setGeometry(x, y, width, height)
