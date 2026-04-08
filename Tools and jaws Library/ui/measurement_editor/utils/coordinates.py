"""Coordinate parsing/formatting helpers shared by the measurement editor."""

from __future__ import annotations

import math


def xyz_to_tuple(value) -> tuple[float, float, float]:
    """Convert xyz value (list or string) into a float triplet."""

    def _finite(v, default: float = 0.0) -> float:
        try:
            num = float(v)
        except Exception:
            return default
        return num if math.isfinite(num) else default

    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return _finite(value[0]), _finite(value[1]), _finite(value[2])

    text = str(value or "").strip()
    if not text:
        return 0.0, 0.0, 0.0

    text = (
        text.replace("[", " ")
        .replace("]", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace(";", ",")
    )
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) < 3:
        return 0.0, 0.0, 0.0
    return _finite(parts[0]), _finite(parts[1]), _finite(parts[2])


def fmt_coord(value: float) -> str:
    try:
        numeric = float(value)
    except Exception:
        numeric = 0.0
    if not math.isfinite(numeric):
        numeric = 0.0
    return f"{numeric:.4g}"


def xyz_to_text(value) -> str:
    x, y, z = xyz_to_tuple(value)
    return f"{fmt_coord(x)}, {fmt_coord(y)}, {fmt_coord(z)}"


def xyz_to_text_optional(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return xyz_to_text(value)


def float_or_default(value, default: float) -> float:
    try:
        numeric = float(str(value).strip().replace(",", "."))
    except Exception:
        return float(default)
    return numeric if math.isfinite(numeric) else float(default)


def normalize_distance_point_space(part_name, part_index, point_space) -> str:
    has_part_ref = bool(str(part_name or "").strip())
    if not has_part_ref:
        try:
            has_part_ref = int(part_index) >= 0
        except Exception:
            has_part_ref = False
    normalized = str(point_space or "").strip().lower()
    if normalized not in {"local", "world"}:
        return "local" if has_part_ref else "world"
    if normalized == "world" and has_part_ref:
        return "local"
    return normalized


__all__ = [
    "xyz_to_tuple",
    "fmt_coord",
    "xyz_to_text",
    "xyz_to_text_optional",
    "float_or_default",
    "normalize_distance_point_space",
]
