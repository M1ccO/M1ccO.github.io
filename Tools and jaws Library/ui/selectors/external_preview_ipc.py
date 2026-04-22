from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QMessageBox

from config import SOURCE_DIR, TOOL_LIBRARY_SERVER_NAME
from ..fixture_preview_rules import (
    fixture_preview_has_model_payload,
    fixture_preview_measurement_overlays,
    fixture_preview_parts_payload,
    fixture_preview_stl_path,
    fixture_preview_transform_signature,
)
from ..jaw_page_support.preview_rules import (
    jaw_preview_has_model_payload,
    jaw_preview_measurement_overlays,
    jaw_preview_parts_payload,
    jaw_preview_stl_path,
    jaw_preview_transform_signature,
)


_OPEN_COMMAND = "open_selector_preview"
_CLOSE_COMMAND = "close_selector_preview"


def _rect_payload(rect) -> list[int] | None:
    if rect is None:
        return None
    try:
        width = int(rect.width())
        height = int(rect.height())
        x = int(rect.x())
        y = int(rect.y())
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return [x, y, width, height]


def _host_geometry_payload(page) -> dict:
    window_fn = getattr(page, "window", None)
    if not callable(window_fn):
        return {}
    try:
        host_window = window_fn()
    except Exception:
        return {}
    if host_window is None:
        return {}

    frame_rect = None
    geometry_rect = None
    try:
        frame_rect = host_window.frameGeometry()
    except Exception:
        frame_rect = None
    try:
        geometry_rect = host_window.geometry()
    except Exception:
        geometry_rect = None

    payload = {}
    frame_payload = _rect_payload(frame_rect)
    geometry_payload = _rect_payload(geometry_rect)
    if frame_payload is not None:
        payload["host_frame_geometry"] = frame_payload
    if geometry_payload is not None:
        payload["host_content_geometry"] = geometry_payload
    return payload


def _set_preview_button_checked(page, checked: bool) -> None:
    button = getattr(page, "preview_window_btn", None)
    if button is None:
        return
    block_signals = getattr(button, "blockSignals", None)
    if callable(block_signals):
        block_signals(True)
    button.setChecked(checked)
    if callable(block_signals):
        block_signals(False)


def _send_selector_preview_request(payload: dict) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(TOOL_LIBRARY_SERVER_NAME)
    if not socket.waitForConnected(350):
        return False
    try:
        socket.write(json.dumps(payload).encode("utf-8"))
        socket.flush()
        socket.waitForBytesWritten(700)
        return True
    except Exception:
        return False
    finally:
        try:
            socket.disconnectFromServer()
        except Exception:
            pass


def _launch_hidden_tool_library() -> bool:
    exe_candidates = [
        SOURCE_DIR / "Tools and jaws Library.exe",
        SOURCE_DIR / "dist" / "Tools and jaws Library" / "Tools and jaws Library.exe",
    ]
    for candidate in exe_candidates:
        if not candidate.exists():
            continue
        try:
            launched = QProcess.startDetached(str(candidate), ["--hidden"], str(candidate.parent))
        except Exception:
            launched = False
        if launched:
            return True

    main_path = SOURCE_DIR / "main.py"
    if not main_path.exists():
        return False

    python_candidates: list[Path] = []
    current_executable = Path(sys.executable)
    if current_executable.name.lower().startswith("python") and current_executable.exists():
        python_candidates.append(current_executable)
    venv_dir = SOURCE_DIR.parent / ".venv" / "Scripts"
    for name in ("pythonw.exe", "python.exe"):
        candidate = venv_dir / name
        if candidate.exists() and candidate not in python_candidates:
            python_candidates.append(candidate)

    for python_executable in python_candidates:
        try:
            launched = QProcess.startDetached(
                str(python_executable),
                [str(main_path), "--hidden"],
                str(SOURCE_DIR),
            )
        except Exception:
            launched = False
        if launched:
            return True
    return False


def _show_preview_host_unavailable(page) -> None:
    QMessageBox.information(
        page,
        page._t("tool_library.preview.window_title", "3D Preview"),
        page._t(
            "selector.preview.host_unavailable",
            "3D Preview is unavailable because the Tool Library preview host is not running.",
        ),
    )


def _schedule_preview_retry(page, payload: dict, *, attempts: int, delay_ms: int, show_errors: bool) -> None:
    def _retry() -> None:
        button = getattr(page, "preview_window_btn", None)
        if button is None or not button.isChecked():
            return
        if _send_selector_preview_request(payload):
            return
        if attempts <= 1:
            _set_preview_button_checked(page, False)
            if show_errors:
                _show_preview_host_unavailable(page)
            return
        _schedule_preview_retry(
            page,
            payload,
            attempts=attempts - 1,
            delay_ms=min(1000, int(delay_ms * 1.25)),
            show_errors=show_errors,
        )

    QTimer.singleShot(max(0, int(delay_ms)), _retry)


def _open_external_preview(page, preview_payload: dict | None, *, show_errors: bool) -> bool:
    if not isinstance(preview_payload, dict):
        _send_selector_preview_request({"command": _CLOSE_COMMAND})
        return False

    request = {"command": _OPEN_COMMAND, "preview": preview_payload}
    if _send_selector_preview_request(request):
        return True

    if _launch_hidden_tool_library():
        _schedule_preview_retry(page, request, attempts=14, delay_ms=150, show_errors=show_errors)
        return True

    if show_errors:
        _show_preview_host_unavailable(page)
    return False


def _close_external_preview() -> None:
    _send_selector_preview_request({"command": _CLOSE_COMMAND})


def _normalize_parts_payload(raw) -> list[dict]:
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [dict(item) for item in parsed if isinstance(item, dict)]


def _normalize_overlays(raw) -> list[dict]:
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [dict(item) for item in parsed if isinstance(item, dict)]


def _transform_payload(item: dict | None) -> dict:
    item = item if isinstance(item, dict) else {}
    return {
        "alignment_plane": str(item.get("preview_plane") or "XZ").strip().upper(),
        "rot_x": int(item.get("preview_rot_x", 0) or 0),
        "rot_y": int(item.get("preview_rot_y", 0) or 0),
        "rot_z": int(item.get("preview_rot_z", 0) or 0),
        "transform_mode": str(item.get("preview_transform_mode") or "translate").strip().lower(),
        "fine_transform": bool(item.get("preview_fine_transform", False)),
        "selected_part": int(item.get("preview_selected_part", -1) or -1),
        "selected_parts": [
            int(index)
            for index in (item.get("preview_selected_parts", []) or [])
            if str(index).strip().lstrip("-").isdigit()
        ],
    }


def _tool_preview_payload(page) -> dict | None:
    tool = page._get_selected_tool()
    if not isinstance(tool, dict):
        return None
    stl_path = tool.get("stl_path")
    parts = _normalize_parts_payload(stl_path)
    text_path = "" if parts else str(stl_path or "").strip()
    if not parts and not text_path:
        return None
    tool_id = str(tool.get("id") or "").strip()
    label = str(tool.get("description") or "").strip() or tool_id or "3D Preview"
    overlays = _normalize_overlays(tool.get("measurement_overlays", []))
    return {
        "kind": "tool",
        "item_id": tool_id,
        "title": page._t("tool_library.preview.window_title_tool", "3D Preview - {tool_id}", tool_id=tool_id).rstrip(" -"),
        "label": label,
        "stl_path": text_path,
        "parts": parts,
        "measurement_overlays": overlays,
        "measurements_enabled": bool(getattr(page, "_detached_measurements_enabled", True)),
        "model_key": json.dumps([tool_id, text_path, parts, overlays], ensure_ascii=False, sort_keys=True, default=str),
        "transform": {},
        **_host_geometry_payload(page),
    }


def _jaw_preview_payload(page) -> dict | None:
    current_jaw_id = str(getattr(page, "current_jaw_id", "") or "").strip()
    if not current_jaw_id:
        return None
    jaw = page.jaw_service.get_jaw(current_jaw_id)
    if not isinstance(jaw, dict) or not jaw_preview_has_model_payload(jaw):
        return None
    parts = jaw_preview_parts_payload(jaw)
    jaw_id = str(jaw.get("jaw_id") or current_jaw_id).strip()
    return {
        "kind": "jaw",
        "item_id": jaw_id,
        "title": page._t("tool_library.preview.window_title_tool", "3D Preview - {tool_id}", tool_id=jaw_id).rstrip(" -"),
        "label": jaw_id or "3D Preview",
        "stl_path": "" if parts else jaw_preview_stl_path(jaw),
        "parts": parts,
        "measurement_overlays": jaw_preview_measurement_overlays(jaw),
        "measurements_enabled": bool(getattr(page, "_detached_measurements_enabled", True)),
        "model_key": json.dumps([jaw_id, jaw_preview_stl_path(jaw), parts, jaw_preview_transform_signature(jaw)], ensure_ascii=False, sort_keys=True, default=str),
        "transform": _transform_payload(jaw),
        **_host_geometry_payload(page),
    }


def _fixture_preview_payload(page) -> dict | None:
    fixture = page._get_selected_fixture()
    if not isinstance(fixture, dict) or not fixture_preview_has_model_payload(fixture):
        return None
    parts = fixture_preview_parts_payload(fixture)
    fixture_id = str(fixture.get("fixture_id") or "").strip()
    return {
        "kind": "fixture",
        "item_id": fixture_id,
        "title": page._t("tool_library.preview.window_title_tool", "3D Preview - {tool_id}", tool_id=fixture_id).rstrip(" -"),
        "label": fixture_id or "3D Preview",
        "stl_path": "" if parts else fixture_preview_stl_path(fixture),
        "parts": parts,
        "measurement_overlays": fixture_preview_measurement_overlays(fixture),
        "measurements_enabled": bool(getattr(page, "_detached_measurements_enabled", True)),
        "model_key": json.dumps([fixture_id, fixture_preview_stl_path(fixture), parts, fixture_preview_transform_signature(fixture)], ensure_ascii=False, sort_keys=True, default=str),
        "transform": _transform_payload(fixture),
        **_host_geometry_payload(page),
    }


def sync_embedded_tool_selector_preview(page, *, show_errors: bool = False) -> bool:
    button = getattr(page, "preview_window_btn", None)
    if button is None or not button.isChecked():
        return False
    payload = _tool_preview_payload(page)
    if payload is None:
        _close_external_preview()
        if show_errors:
            QMessageBox.information(
                page,
                page._t("tool_library.preview.window_title", "3D Preview"),
                page._t("tool_library.preview.none_assigned_selected", "The selected tool has no 3D model assigned."),
            )
        return False
    return _open_external_preview(page, payload, show_errors=show_errors)


def sync_embedded_jaw_selector_preview(page, *, show_errors: bool = False) -> bool:
    button = getattr(page, "preview_window_btn", None)
    if button is None or not button.isChecked():
        return False
    payload = _jaw_preview_payload(page)
    if payload is None:
        _close_external_preview()
        if show_errors:
            QMessageBox.information(
                page,
                page._t("tool_library.preview.window_title", "3D Preview"),
                page._t("tool_library.preview.none_assigned_selected", "The selected item has no 3D model assigned."),
            )
        return False
    return _open_external_preview(page, payload, show_errors=show_errors)


def sync_embedded_fixture_selector_preview(page, *, show_errors: bool = False) -> bool:
    button = getattr(page, "preview_window_btn", None)
    if button is None or not button.isChecked():
        return False
    payload = _fixture_preview_payload(page)
    if payload is None:
        _close_external_preview()
        if show_errors:
            QMessageBox.information(
                page,
                page._t("tool_library.preview.window_title", "3D Preview"),
                page._t("tool_library.preview.none_assigned_selected", "The selected item has no 3D model assigned."),
            )
        return False
    return _open_external_preview(page, payload, show_errors=show_errors)


def toggle_embedded_tool_selector_preview_window(page) -> None:
    button = getattr(page, "preview_window_btn", None)
    if button is None:
        return
    if button.isChecked():
        if not sync_embedded_tool_selector_preview(page, show_errors=True):
            _set_preview_button_checked(page, False)
        return
    _close_external_preview()


def toggle_embedded_jaw_selector_preview_window(page) -> None:
    button = getattr(page, "preview_window_btn", None)
    if button is None:
        return
    if button.isChecked():
        if not sync_embedded_jaw_selector_preview(page, show_errors=True):
            _set_preview_button_checked(page, False)
        return
    _close_external_preview()


def toggle_embedded_fixture_selector_preview_window(page) -> None:
    button = getattr(page, "preview_window_btn", None)
    if button is None:
        return
    if button.isChecked():
        if not sync_embedded_fixture_selector_preview(page, show_errors=True):
            _set_preview_button_checked(page, False)
        return
    _close_external_preview()


__all__ = [
    "sync_embedded_fixture_selector_preview",
    "sync_embedded_jaw_selector_preview",
    "sync_embedded_tool_selector_preview",
    "toggle_embedded_fixture_selector_preview_window",
    "toggle_embedded_jaw_selector_preview_window",
    "toggle_embedded_tool_selector_preview_window",
]