"""Diameter measurement normalization helpers."""

from __future__ import annotations

import math
from collections.abc import Callable

from ..utils.axis_math import (
    axis_xyz_text,
    normalize_axis_xyz_text,
    normalize_diameter_axis_mode,
)
from ..utils.coordinates import float_or_default, xyz_to_text_optional


def normalize_diameter_measurement(
    meas: dict | None,
    *,
    ensure_uid: Callable[[dict | None], str],
    translate: Callable[[str, str | None], str],
) -> dict:
    data = dict(meas or {})
    uid = ensure_uid(data)

    edge_text = xyz_to_text_optional(data.get("edge_xyz", ""))
    diameter_text = str(data.get("diameter", "")).strip()
    if diameter_text:
        try:
            diameter_num = float(diameter_text.replace(",", "."))
        except Exception:
            diameter_num = None
        if not (isinstance(diameter_num, float) and math.isfinite(diameter_num)):
            diameter_text = ""
        else:
            diameter_text = f"{diameter_num:.6g}"

    mode = str(data.get("diameter_mode", "")).strip().lower()
    if mode not in {"measured", "manual"}:
        mode = "manual" if diameter_text else ("measured" if edge_text else "manual")

    try:
        part_index = int(data.get("part_index", -1) or -1)
    except Exception:
        part_index = -1

    axis_mode = normalize_diameter_axis_mode(
        str(data.get("diameter_axis_mode", "")).strip().lower(),
        data.get("axis_xyz", "0, 0, 1"),
        default="z",
    )
    axis_xyz = (
        axis_xyz_text(axis_mode)
        if axis_mode in {"x", "y", "z"}
        else normalize_axis_xyz_text(data.get("axis_xyz", "0, 0, 1"))
    )
    visual_offset_mm = float_or_default(data.get("diameter_visual_offset_mm", 1.0), 1.0)

    return {
        "name": str(data.get("name", "")).strip()
        or translate("tool_editor.measurements.new_diameter", "New Diameter"),
        "part": str(data.get("part", "")).strip(),
        "part_index": part_index,
        "center_xyz": xyz_to_text_optional(data.get("center_xyz", "")),
        "edge_xyz": edge_text,
        "axis_xyz": axis_xyz,
        "diameter_axis_mode": axis_mode,
        "offset_xyz": xyz_to_text_optional(data.get("offset_xyz", "")),
        "diameter_visual_offset_mm": visual_offset_mm,
        "diameter_mode": mode,
        "diameter": diameter_text,
        "type": "diameter_ring",
        "_uid": uid,
    }


def compose_diameter_commit_payload(
    *,
    model: dict,
    name_text: str,
    axis_value: str,
    diameter_mode: str,
    diameter_text: str,
    visual_offset_mm: float,
    uid: str,
    translate: Callable[[str, str | None], str],
) -> dict:
    axis_mode = normalize_diameter_axis_mode(
        axis_value,
        model.get("axis_xyz", "0, 0, 1"),
        default="z",
    )
    axis_xyz = (
        axis_xyz_text(axis_mode)
        if axis_mode in {"x", "y", "z"}
        else normalize_axis_xyz_text(model.get("axis_xyz", "0, 0, 1"))
    )

    try:
        part_index = int(model.get("part_index", -1) or -1)
    except Exception:
        part_index = -1

    return {
        "name": name_text or translate("tool_editor.measurements.new_diameter", "New Diameter"),
        "part": str(model.get("part", "")).strip(),
        "part_index": part_index,
        "center_xyz": str(model.get("center_xyz", "")).strip(),
        "edge_xyz": str(model.get("edge_xyz", "")).strip(),
        "axis_xyz": axis_xyz,
        "diameter_axis_mode": axis_mode,
        "offset_xyz": str(model.get("offset_xyz", "")).strip(),
        "diameter_visual_offset_mm": float(visual_offset_mm),
        "diameter_mode": diameter_mode,
        "diameter": diameter_text,
        "type": "diameter_ring",
        "_uid": uid,
    }


__all__ = [
    "normalize_diameter_measurement",
    "compose_diameter_commit_payload",
]
