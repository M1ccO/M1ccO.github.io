from __future__ import annotations

import json

from PySide6.QtCore import QMimeData


SELECTOR_TOOL_MIME = "application/x-tool-library-tool-assignment"
SELECTOR_JAW_MIME = "application/x-tool-library-jaw-assignment"


def _decode_payload(mime: QMimeData, mime_type: str) -> list[dict]:
    if not mime.hasFormat(mime_type):
        return []
    try:
        payload = json.loads(bytes(mime.data(mime_type)).decode("utf-8"))
    except Exception:
        payload = []
    return payload if isinstance(payload, list) else []


def encode_selector_payload(mime: QMimeData, mime_type: str, payload: list[dict]) -> None:
    if payload:
        mime.setData(mime_type, json.dumps(payload).encode("utf-8"))


def decode_tool_payload(mime: QMimeData) -> list[dict]:
    return _decode_payload(mime, SELECTOR_TOOL_MIME)


def decode_jaw_payload(mime: QMimeData) -> list[dict]:
    return _decode_payload(mime, SELECTOR_JAW_MIME)


def tool_payload_keys(mime: QMimeData) -> list[tuple[str, str | None]]:
    keys: list[tuple[str, str | None]] = []
    for item in decode_tool_payload(mime):
        if not isinstance(item, dict):
            continue
        tool_id = str(item.get("tool_id") or item.get("id") or "").strip()
        tool_uid_raw = item.get("tool_uid", item.get("uid"))
        tool_uid = str(tool_uid_raw).strip() if tool_uid_raw is not None and str(tool_uid_raw).strip() else None
        if tool_id:
            key = (tool_id, tool_uid)
            if key not in keys:
                keys.append(key)
    return keys


def first_dropped_jaw(mime: QMimeData) -> dict | None:
    for item in decode_jaw_payload(mime):
        if not isinstance(item, dict):
            continue
        jaw_id = str(item.get("jaw_id") or item.get("id") or "").strip()
        if not jaw_id:
            continue
        return {
            "jaw_id": jaw_id,
            "jaw_type": str(item.get("jaw_type") or "").strip(),
        }
    return None


def jaw_payload_ids(mime: QMimeData) -> list[str]:
    jaw_ids: list[str] = []
    for item in decode_jaw_payload(mime):
        if not isinstance(item, dict):
            continue
        jaw_id = str(item.get("jaw_id") or item.get("id") or "").strip()
        if jaw_id and jaw_id not in jaw_ids:
            jaw_ids.append(jaw_id)
    return jaw_ids
