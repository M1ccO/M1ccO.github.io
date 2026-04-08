"""Preview synchronization helpers for measurement editor overlays."""

from __future__ import annotations

import math

from ..utils.axis_math import (
    axis_xyz_text,
    normalize_axis_xyz_text,
    normalize_diameter_axis_mode,
)
from ..utils.coordinates import (
    float_or_default,
    normalize_distance_point_space,
    xyz_to_text,
    xyz_to_text_optional,
)


def compose_preview_overlays(
    *,
    distance_overlays: list[dict],
    diameter_overlays: list[dict],
    radius_overlays: list[dict],
    angle_overlays: list[dict],
    active_distance_uid: str = "",
    active_point: str = "",
) -> list[dict]:
    overlays: list[dict] = []

    active_uid = str(active_distance_uid or "").strip()
    active_point_value = str(active_point or "").strip().lower()

    for overlay in distance_overlays:
        item = dict(overlay or {})
        if active_uid and str(item.get("_uid") or "").strip() == active_uid:
            item["active_point"] = active_point_value
        else:
            item["active_point"] = ""
        overlays.append(item)

    overlays.extend(diameter_overlays or [])
    overlays.extend(radius_overlays or [])
    overlays.extend(angle_overlays or [])
    return overlays


def apply_distance_overlay_update(current: dict, overlay: dict) -> dict:
    incoming_start_part = str(overlay.get("start_part", current.get("start_part", "")))
    incoming_end_part = str(overlay.get("end_part", current.get("end_part", "")))
    try:
        incoming_start_part_index = int(
            overlay.get("start_part_index", current.get("start_part_index", -1)) or -1
        )
    except Exception:
        incoming_start_part_index = -1
    try:
        incoming_end_part_index = int(
            overlay.get("end_part_index", current.get("end_part_index", -1)) or -1
        )
    except Exception:
        incoming_end_part_index = -1

    updated = dict(current)
    updated.update(
        {
            "start_part": incoming_start_part,
            "start_part_index": incoming_start_part_index,
            "start_xyz": xyz_to_text(overlay.get("start_xyz", current.get("start_xyz", ""))),
            "start_space": normalize_distance_point_space(
                incoming_start_part,
                incoming_start_part_index,
                overlay.get("start_space", current.get("start_space", "")),
            ),
            "end_part": incoming_end_part,
            "end_part_index": incoming_end_part_index,
            "end_xyz": xyz_to_text(overlay.get("end_xyz", current.get("end_xyz", ""))),
            "end_space": normalize_distance_point_space(
                incoming_end_part,
                incoming_end_part_index,
                overlay.get("end_space", current.get("end_space", "")),
            ),
            "distance_axis": str(overlay.get("distance_axis", current.get("distance_axis", "z"))),
            "label_value_mode": str(
                overlay.get("label_value_mode", current.get("label_value_mode", "measured"))
            ),
            "label_custom_value": str(
                overlay.get("label_custom_value", current.get("label_custom_value", ""))
            ),
            "offset_xyz": xyz_to_text(overlay.get("offset_xyz", current.get("offset_xyz", ""))),
            "start_shift": str(overlay.get("start_shift", current.get("start_shift", "0"))),
            "end_shift": str(overlay.get("end_shift", current.get("end_shift", "0"))),
            "type": "distance",
        }
    )
    return updated


def apply_diameter_overlay_update(current: dict, overlay: dict) -> dict:
    incoming_axis_xyz = overlay.get("axis_xyz", current.get("axis_xyz", "0, 0, 1"))
    incoming_axis_mode = normalize_diameter_axis_mode(
        overlay.get("diameter_axis_mode", current.get("diameter_axis_mode", "")),
        incoming_axis_xyz,
        default="z",
    )
    normalized_axis_xyz = (
        axis_xyz_text(incoming_axis_mode)
        if incoming_axis_mode in {"x", "y", "z"}
        else normalize_axis_xyz_text(incoming_axis_xyz, fallback="0, 0, 1")
    )

    incoming_diameter_raw = str(overlay.get("diameter", current.get("diameter", ""))).strip()
    try:
        incoming_diameter_num = float(incoming_diameter_raw.replace(",", "."))
    except Exception:
        incoming_diameter_num = None
    incoming_diameter_text = (
        f"{incoming_diameter_num:.6g}"
        if isinstance(incoming_diameter_num, float) and math.isfinite(incoming_diameter_num)
        else ""
    )

    updated = dict(current)
    updated.update(
        {
            "part": str(overlay.get("part", current.get("part", ""))),
            "part_index": int(overlay.get("part_index", current.get("part_index", -1)) or -1),
            "center_xyz": xyz_to_text_optional(overlay.get("center_xyz", current.get("center_xyz", ""))),
            "edge_xyz": xyz_to_text_optional(overlay.get("edge_xyz", current.get("edge_xyz", ""))),
            "axis_xyz": normalized_axis_xyz,
            "diameter_axis_mode": incoming_axis_mode,
            "offset_xyz": xyz_to_text_optional(overlay.get("offset_xyz", current.get("offset_xyz", ""))),
            "diameter_visual_offset_mm": float_or_default(
                overlay.get("diameter_visual_offset_mm", current.get("diameter_visual_offset_mm", 1.0)),
                1.0,
            ),
            "diameter_mode": str(overlay.get("diameter_mode", current.get("diameter_mode", "manual"))),
            "diameter": incoming_diameter_text,
            "type": "diameter_ring",
        }
    )
    return updated


__all__ = [
    "compose_preview_overlays",
    "apply_distance_overlay_update",
    "apply_diameter_overlay_update",
]
