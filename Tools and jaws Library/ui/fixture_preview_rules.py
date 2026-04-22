"""Shared fixture preview normalization and transform rules."""

from __future__ import annotations

import json


def fixture_preview_stl_path(fixture: dict) -> str:
    return (fixture.get("stl_path", "") or "").strip()


def fixture_preview_label(fixture: dict, translate) -> str:
    return fixture.get("fixture_id", translate("jaw_library.preview.jaw_label", "Fixture"))


def fixture_preview_parts_payload(fixture: dict) -> list[dict]:
    raw = fixture.get("stl_path", "")
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


def fixture_preview_measurement_overlays(fixture: dict) -> list[dict]:
    raw = fixture.get("measurement_overlays", [])
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


def fixture_preview_has_model_payload(fixture: dict) -> bool:
    if fixture_preview_parts_payload(fixture):
        return True
    return bool(fixture_preview_stl_path(fixture))


def fixture_preview_plane(fixture: dict) -> str:
    plane = str(fixture.get("preview_plane") or "XZ").strip().upper()
    return plane if plane in {"XZ", "XY", "YZ"} else "XZ"


def fixture_preview_rotation(fixture: dict) -> tuple[int, int, int]:
    return (
        int(fixture.get("preview_rot_x", 0) or 0),
        int(fixture.get("preview_rot_y", 0) or 0),
        int(fixture.get("preview_rot_z", 0) or 0),
    )


def fixture_preview_transform_signature(fixture: dict) -> tuple:
    selected_parts = fixture.get("preview_selected_parts", []) or []
    normalized_selected_parts = []
    if isinstance(selected_parts, list):
        for idx in selected_parts:
            try:
                normalized_selected_parts.append(int(idx))
            except Exception:
                continue
    return (
        fixture_preview_plane(fixture),
        *fixture_preview_rotation(fixture),
        str(fixture.get("preview_transform_mode", "translate") or "translate").strip().lower(),
        bool(fixture.get("preview_fine_transform", False)),
        int(fixture.get("preview_selected_part", -1) or -1),
        tuple(normalized_selected_parts),
    )


def apply_fixture_preview_transform(viewer, fixture: dict) -> None:
    plane = fixture_preview_plane(fixture)
    rot_x, rot_y, rot_z = fixture_preview_rotation(fixture)

    viewer.set_alignment_plane(plane)
    viewer.reset_model_rotation()
    if rot_x:
        viewer.rotate_model("x", rot_x)
    if rot_y:
        viewer.rotate_model("y", rot_y)
    if rot_z:
        viewer.rotate_model("z", rot_z)

    viewer.set_transform_mode(str(fixture.get("preview_transform_mode", "translate") or "translate").strip().lower())
    viewer.set_fine_transform_enabled(bool(fixture.get("preview_fine_transform", False)))

    selected_parts = fixture.get("preview_selected_parts", []) or []
    if isinstance(selected_parts, list):
        normalized_selected_parts = []
        for idx in selected_parts:
            try:
                normalized_selected_parts.append(int(idx))
            except Exception:
                continue
        if normalized_selected_parts:
            viewer.select_parts(normalized_selected_parts)
            return

    viewer.select_part(int(fixture.get("preview_selected_part", -1) or -1))