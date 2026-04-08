"""Distance editing helper functions extracted from the dialog controller."""

from __future__ import annotations

from ..utils.coordinates import float_or_default, fmt_coord, xyz_to_tuple


def distance_value_mode(is_custom_checked: bool) -> str:
    return "custom" if is_custom_checked else "measured"


def normalize_distance_adjust_mode(mode: str) -> str:
    return "point" if mode == "point" else "offset"


def toggle_distance_adjust_mode(mode: str) -> str:
    return "offset" if mode == "point" else "point"


def normalize_distance_nudge_point(point: str) -> str:
    return "end" if point == "end" else "start"


def distance_adjust_target_key(mode: str, point: str) -> str:
    return f"{point}_xyz" if mode == "point" else "offset_xyz"


def normalize_distance_axis(axis: str) -> str:
    normalized = str(axis or "").strip().lower()
    if normalized in {"direct", "x", "y", "z"}:
        return normalized
    return "z"


def distance_axis_sign(model: dict, axis: str) -> float:
    sx, sy, sz = xyz_to_tuple(model.get("start_xyz", "0, 0, 0"))
    ex, ey, ez = xyz_to_tuple(model.get("end_xyz", "0, 0, 0"))
    if axis == "x":
        value = ex - sx
    elif axis == "y":
        value = ey - sy
    else:
        value = ez - sz
    return 1.0 if value >= 0 else -1.0


def distance_effective_point_xyz_text(model: dict, point: str) -> str:
    point_key = "end_xyz" if point == "end" else "start_xyz"
    shift_key = "end_shift" if point == "end" else "start_shift"
    x, y, z = xyz_to_tuple(model.get(point_key, "0, 0, 0"))
    shift = float_or_default(model.get(shift_key, 0.0), 0.0)
    axis = str(model.get("distance_axis", "z")).strip().lower()

    if axis == "direct":
        sx, sy, sz = xyz_to_tuple(model.get("start_xyz", "0, 0, 0"))
        ex, ey, ez = xyz_to_tuple(model.get("end_xyz", "0, 0, 0"))
        dx = ex - sx
        dy = ey - sy
        dz = ez - sz
        length = (dx * dx + dy * dy + dz * dz) ** 0.5
        if length > 1e-8:
            ux = dx / length
            uy = dy / length
            uz = dz / length
            x += ux * shift
            y += uy * shift
            z += uz * shift
    elif axis == "x":
        x += distance_axis_sign(model, "x") * shift
    elif axis == "y":
        y += distance_axis_sign(model, "y") * shift
    else:
        z += distance_axis_sign(model, "z") * shift

    return f"{fmt_coord(x)}, {fmt_coord(y)}, {fmt_coord(z)}"


def distance_measured_value_text(model: dict, axis: str) -> str:
    start_text = str(model.get("start_xyz") or "").strip()
    end_text = str(model.get("end_xyz") or "").strip()
    if not start_text or not end_text:
        return ""

    sx, sy, sz = xyz_to_tuple(start_text)
    ex, ey, ez = xyz_to_tuple(end_text)
    if axis == "x":
        value = abs(ex - sx)
    elif axis == "y":
        value = abs(ey - sy)
    elif axis == "z":
        value = abs(ez - sz)
    else:
        dx = ex - sx
        dy = ey - sy
        dz = ez - sz
        value = (dx * dx + dy * dy + dz * dz) ** 0.5
    return f"{value:.3f} mm"


__all__ = [
    "distance_value_mode",
    "normalize_distance_adjust_mode",
    "toggle_distance_adjust_mode",
    "normalize_distance_nudge_point",
    "distance_adjust_target_key",
    "normalize_distance_axis",
    "distance_axis_sign",
    "distance_effective_point_xyz_text",
    "distance_measured_value_text",
]
