"""Preview normalization and transform rules for Jaw Page."""

from __future__ import annotations

import json


def jaw_preview_stl_path(jaw: dict) -> str:
    return (jaw.get("stl_path", "") or "").strip()


def jaw_preview_label(jaw: dict, translate) -> str:
    return jaw.get("jaw_id", translate("jaw_library.preview.jaw_label", "Jaw"))


def jaw_preview_parts_payload(jaw: dict) -> list[dict]:
    raw = jaw.get("stl_path", "")
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


def jaw_preview_measurement_overlays(jaw: dict) -> list[dict]:
    raw = jaw.get("measurement_overlays", [])
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


def jaw_preview_has_model_payload(jaw: dict) -> bool:
    if jaw_preview_parts_payload(jaw):
        return True
    return bool(jaw_preview_stl_path(jaw))
