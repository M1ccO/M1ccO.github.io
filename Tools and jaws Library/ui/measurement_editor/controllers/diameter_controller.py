"""Diameter editing helper functions extracted from the dialog controller."""

from __future__ import annotations

from ..utils.coordinates import float_or_default, xyz_to_tuple


def diameter_adjust_mode(is_geometry_checked: bool) -> str:
    return "geometry" if is_geometry_checked else "callout"


def normalize_diameter_adjust_mode(mode: str) -> str:
    return "geometry" if mode == "geometry" else "callout"


def toggle_diameter_adjust_mode(mode: str) -> str:
    return "callout" if mode == "geometry" else "geometry"


def diameter_geometry_target(axis_value: str, is_rotation_checked: bool) -> str:
    if is_rotation_checked and str(axis_value or "").strip().lower() == "direct":
        return "rotation"
    return "axis"


def normalize_diameter_geometry_target(target: str, axis_value: str) -> str:
    if target == "rotation" and str(axis_value or "").strip().lower() == "direct":
        return "rotation"
    return "axis"


def toggle_diameter_geometry_target(target: str, axis_value: str) -> str:
    next_target = "axis" if target == "rotation" else "rotation"
    return normalize_diameter_geometry_target(next_target, axis_value)


def diameter_adjust_target_key(mode: str, geometry_target: str) -> str:
    if mode == "geometry":
        return "axis_xyz" if geometry_target == "rotation" else "center_xyz"
    return "offset_xyz"


def diameter_visual_offset_mm(model: dict | None = None) -> float:
    data = model or {}
    return float_or_default(data.get("diameter_visual_offset_mm", 1.0), 1.0)


def diameter_measured_numeric(model: dict | None = None) -> float | None:
    data = model or {}
    center_text = str(data.get("center_xyz") or "").strip()
    edge_text = str(data.get("edge_xyz") or "").strip()
    if not center_text or not edge_text:
        return None

    cx, cy, cz = xyz_to_tuple(center_text)
    ex, ey, ez = xyz_to_tuple(edge_text)
    dx = ex - cx
    dy = ey - cy
    dz = ez - cz

    ax, ay, az = xyz_to_tuple(data.get("axis_xyz", "0, 0, 1"))
    axis_len = (ax * ax + ay * ay + az * az) ** 0.5
    if axis_len <= 1e-8:
        ax, ay, az = 0.0, 0.0, 1.0
        axis_len = 1.0

    ux = ax / axis_len
    uy = ay / axis_len
    uz = az / axis_len
    axial = (dx * ux) + (dy * uy) + (dz * uz)

    px = dx - (ux * axial)
    py = dy - (uy * axial)
    pz = dz - (uz * axial)
    radius = (px * px + py * py + pz * pz) ** 0.5
    return radius * 2 if radius > 1e-6 else None


def diameter_has_manual_value(model: dict | None = None) -> bool:
    data = model or {}
    try:
        return float(str(data.get("diameter", "")).strip().replace(",", ".")) > 1e-6
    except Exception:
        return False


def diameter_is_complete(model: dict | None, fallback_mode: str) -> bool:
    data = model or {}
    has_center = bool(str(data.get("center_xyz") or "").strip())
    if not has_center:
        return False

    mode = str(data.get("diameter_mode") or fallback_mode).strip().lower()
    if mode == "measured":
        return bool(str(data.get("edge_xyz") or "").strip())
    return diameter_has_manual_value(data)


__all__ = [
    "diameter_adjust_mode",
    "normalize_diameter_adjust_mode",
    "toggle_diameter_adjust_mode",
    "diameter_geometry_target",
    "normalize_diameter_geometry_target",
    "toggle_diameter_geometry_target",
    "diameter_adjust_target_key",
    "diameter_visual_offset_mm",
    "diameter_measured_numeric",
    "diameter_has_manual_value",
    "diameter_is_complete",
]
