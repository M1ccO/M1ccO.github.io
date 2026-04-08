"""Axis and rotation helper functions shared by the measurement editor."""

from __future__ import annotations

import math

from .coordinates import fmt_coord, xyz_to_tuple


def axis_xyz_text(axis: str) -> str:
    return {
        "x": "1, 0, 0",
        "y": "0, 1, 0",
        "z": "0, 0, 1",
    }.get(str(axis or "").strip().lower(), "0, 0, 1")


def axis_from_xyz(value, default: str = "z") -> str:
    x, y, z = xyz_to_tuple(value)
    magnitudes = {
        "x": abs(x),
        "y": abs(y),
        "z": abs(z),
    }
    axis, magnitude = max(magnitudes.items(), key=lambda item: item[1])
    return axis if magnitude > 1e-6 else default


def normalize_axis_xyz_text(value, fallback: str = "0, 0, 1") -> str:
    x, y, z = xyz_to_tuple(value)
    length = (x * x + y * y + z * z) ** 0.5
    if length <= 1e-8:
        x, y, z = xyz_to_tuple(fallback)
        length = (x * x + y * y + z * z) ** 0.5
    if length <= 1e-8:
        x, y, z = 0.0, 0.0, 1.0
        length = 1.0
    return f"{fmt_coord(x / length)}, {fmt_coord(y / length)}, {fmt_coord(z / length)}"


def diameter_axis_mode_from_xyz(value, default: str = "z") -> str:
    x, y, z = xyz_to_tuple(value)
    length = (x * x + y * y + z * z) ** 0.5
    if length <= 1e-8:
        return default
    nx = x / length
    ny = y / length
    nz = z / length
    tol = 1e-3
    if abs(abs(nx) - 1.0) <= tol and abs(ny) <= tol and abs(nz) <= tol:
        return "x"
    if abs(abs(ny) - 1.0) <= tol and abs(nx) <= tol and abs(nz) <= tol:
        return "y"
    if abs(abs(nz) - 1.0) <= tol and abs(nx) <= tol and abs(ny) <= tol:
        return "z"
    return "direct"


def normalize_diameter_axis_mode(mode: str, axis_xyz, default: str = "z") -> str:
    normalized = str(mode or "").strip().lower()
    if normalized in {"x", "y", "z", "direct"}:
        return normalized
    return diameter_axis_mode_from_xyz(axis_xyz, default=default)


def rotation_deg_to_axis_xyz_text(
    rx_deg: float,
    ry_deg: float,
    rz_deg: float,
    fallback: str = "0, 0, 1",
) -> str:
    rx = math.radians(float(rx_deg))
    ry = math.radians(float(ry_deg))
    rz = math.radians(float(rz_deg))
    cx = math.cos(rx)
    sx = math.sin(rx)
    cy = math.cos(ry)
    sy = math.sin(ry)
    cz = math.cos(rz)
    sz = math.sin(rz)
    vx = (cz * sy * cx) + (sz * sx)
    vy = (sz * sy * cx) - (cz * sx)
    vz = cy * cx
    return normalize_axis_xyz_text(f"{vx}, {vy}, {vz}", fallback=fallback)


def axis_xyz_to_rotation_deg_tuple(axis_xyz) -> tuple[float, float, float]:
    x, y, z = xyz_to_tuple(axis_xyz)
    length = (x * x + y * y + z * z) ** 0.5
    if length <= 1e-8:
        return 0.0, 0.0, 0.0
    vx = x / length
    vy = y / length
    vz = z / length
    sx = max(-1.0, min(1.0, -vy))
    rx = math.asin(sx)
    cx = math.cos(rx)
    if abs(cx) <= 1e-8:
        ry = 0.0
    else:
        ry = math.atan2(vx, vz)
    rz = 0.0
    return math.degrees(rx), math.degrees(ry), math.degrees(rz)


__all__ = [
    "axis_xyz_text",
    "axis_from_xyz",
    "normalize_axis_xyz_text",
    "diameter_axis_mode_from_xyz",
    "normalize_diameter_axis_mode",
    "rotation_deg_to_axis_xyz_text",
    "axis_xyz_to_rotation_deg_tuple",
]
