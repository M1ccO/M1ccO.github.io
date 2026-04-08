"""Radius measurement normalization helpers."""

from __future__ import annotations

from collections.abc import Callable

from ..utils.coordinates import xyz_to_text


def normalize_radius_measurement(
    meas: dict | None,
    *,
    ensure_uid: Callable[[dict | None], str],
    translate: Callable[[str, str | None], str],
) -> dict:
    data = dict(meas or {})
    uid = ensure_uid(data)
    return {
        "name": str(data.get("name", "")).strip()
        or translate("tool_editor.measurements.new_radius", "New Radius"),
        "part": str(data.get("part", "")).strip(),
        "center_xyz": xyz_to_text(data.get("center_xyz", "0, 0, 0")),
        "axis_xyz": xyz_to_text(data.get("axis_xyz", "0, 1, 0")),
        "radius": str(data.get("radius", "5")).strip() or "5",
        "type": "radius",
        "_uid": uid,
    }


__all__ = ["normalize_radius_measurement"]
