"""Distance measurement normalization helpers."""

from __future__ import annotations

from collections.abc import Callable

from ..utils.coordinates import (
    normalize_distance_point_space,
    xyz_to_text_optional,
)


def normalize_distance_measurement(
    meas: dict | None,
    *,
    ensure_uid: Callable[[dict | None], str],
    translate: Callable[[str, str | None], str],
) -> dict:
    data = dict(meas or {})
    uid = ensure_uid(data)

    axis = str(data.get("distance_axis", "z")).strip().lower()
    if axis not in {"direct", "x", "y", "z"}:
        axis = "z"

    value_mode = str(data.get("label_value_mode", "measured")).strip().lower()
    if value_mode not in {"measured", "custom"}:
        value_mode = "measured"

    start_part = str(data.get("start_part", "")).strip()
    end_part = str(data.get("end_part", "")).strip()

    try:
        start_part_index = int(data.get("start_part_index", -1) or -1)
    except Exception:
        start_part_index = -1
    try:
        end_part_index = int(data.get("end_part_index", -1) or -1)
    except Exception:
        end_part_index = -1

    return {
        "name": str(data.get("name", "")).strip()
        or translate("tool_editor.measurements.new_distance", "New Distance"),
        "start_part": start_part,
        "start_part_index": start_part_index,
        "start_xyz": xyz_to_text_optional(data.get("start_xyz", "")),
        "start_space": normalize_distance_point_space(
            start_part,
            start_part_index,
            data.get("start_space", ""),
        ),
        "end_part": end_part,
        "end_part_index": end_part_index,
        "end_xyz": xyz_to_text_optional(data.get("end_xyz", "")),
        "end_space": normalize_distance_point_space(
            end_part,
            end_part_index,
            data.get("end_space", ""),
        ),
        "distance_axis": axis,
        "label_value_mode": value_mode,
        "label_custom_value": str(data.get("label_custom_value", "")).strip(),
        "offset_xyz": xyz_to_text_optional(data.get("offset_xyz", "")),
        "start_shift": str(data.get("start_shift", "0")).strip() or "0",
        "end_shift": str(data.get("end_shift", "0")).strip() or "0",
        "type": "distance",
        "_uid": uid,
    }


def compose_distance_commit_payload(
    *,
    model: dict,
    name_text: str,
    distance_axis: str,
    label_value_mode: str,
    label_custom_value: str,
    uid: str,
    translate: Callable[[str, str | None], str],
) -> dict:
    start_part = str(model.get("start_part", "")).strip()
    end_part = str(model.get("end_part", "")).strip()

    try:
        start_part_index = int(model.get("start_part_index", -1) or -1)
    except Exception:
        start_part_index = -1
    try:
        end_part_index = int(model.get("end_part_index", -1) or -1)
    except Exception:
        end_part_index = -1

    return {
        "name": name_text or translate("tool_editor.measurements.new_distance", "New Distance"),
        "start_part": start_part,
        "start_part_index": start_part_index,
        "start_xyz": str(model.get("start_xyz", "")).strip(),
        "start_space": normalize_distance_point_space(
            start_part,
            start_part_index,
            model.get("start_space", ""),
        ),
        "end_part": end_part,
        "end_part_index": end_part_index,
        "end_xyz": str(model.get("end_xyz", "")).strip(),
        "end_space": normalize_distance_point_space(
            end_part,
            end_part_index,
            model.get("end_space", ""),
        ),
        "distance_axis": distance_axis,
        "label_value_mode": label_value_mode,
        "label_custom_value": label_custom_value,
        "offset_xyz": str(model.get("offset_xyz", "")).strip(),
        "start_shift": str(model.get("start_shift", "0")).strip(),
        "end_shift": str(model.get("end_shift", "0")).strip(),
        "type": "distance",
        "_uid": uid,
    }


__all__ = [
    "normalize_distance_measurement",
    "compose_distance_commit_payload",
]
