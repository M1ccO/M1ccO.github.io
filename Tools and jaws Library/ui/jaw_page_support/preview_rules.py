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


def jaw_preview_plane(jaw: dict) -> str:
    plane = str(jaw.get('preview_plane') or 'XZ').strip().upper()
    return plane if plane in {'XZ', 'XY', 'YZ'} else 'XZ'


def jaw_preview_rotation(jaw: dict) -> tuple[int, int, int]:
    return (
        int(jaw.get('preview_rot_x', 0) or 0),
        int(jaw.get('preview_rot_y', 0) or 0),
        int(jaw.get('preview_rot_z', 0) or 0),
    )


def jaw_preview_transform_signature(jaw: dict) -> tuple:
    selected_parts = jaw.get('preview_selected_parts', []) or []
    normalized_selected_parts = []
    if isinstance(selected_parts, list):
        for idx in selected_parts:
            try:
                normalized_selected_parts.append(int(idx))
            except Exception:
                continue
    return (
        jaw_preview_plane(jaw),
        *jaw_preview_rotation(jaw),
        str(jaw.get('preview_transform_mode', 'translate') or 'translate').strip().lower(),
        bool(jaw.get('preview_fine_transform', False)),
        int(jaw.get('preview_selected_part', -1) or -1),
        tuple(normalized_selected_parts),
    )


def apply_jaw_preview_transform(viewer, jaw: dict) -> None:
    plane = jaw_preview_plane(jaw)
    rot_x, rot_y, rot_z = jaw_preview_rotation(jaw)

    viewer.set_alignment_plane(plane)
    viewer.reset_model_rotation()
    if rot_x:
        viewer.rotate_model('x', rot_x)
    if rot_y:
        viewer.rotate_model('y', rot_y)
    if rot_z:
        viewer.rotate_model('z', rot_z)

    viewer.set_transform_mode(str(jaw.get('preview_transform_mode', 'translate') or 'translate').strip().lower())
    viewer.set_fine_transform_enabled(bool(jaw.get('preview_fine_transform', False)))

    selected_parts = jaw.get('preview_selected_parts', []) or []
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

    viewer.select_part(int(jaw.get('preview_selected_part', -1) or -1))
