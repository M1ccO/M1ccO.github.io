"""Angle measurement normalization helpers."""

from __future__ import annotations

from collections.abc import Callable

from ..utils.coordinates import xyz_to_text


def normalize_angle_measurement(
    meas: dict | None,
    *,
    ensure_uid: Callable[[dict | None], str],
    translate: Callable[[str, str | None], str],
) -> dict:
    data = dict(meas or {})
    uid = ensure_uid(data)
    return {
        "name": str(data.get("name", "")).strip()
        or translate("tool_editor.measurements.new_angle", "New Angle"),
        "part": str(data.get("part", "")).strip(),
        "center_xyz": xyz_to_text(data.get("center_xyz", "0, 0, 0")),
        "start_xyz": xyz_to_text(data.get("start_xyz", "1, 0, 0")),
        "end_xyz": xyz_to_text(data.get("end_xyz", "0, 1, 0")),
        "type": "angle",
        "_uid": uid,
    }


__all__ = ["normalize_angle_measurement"]
