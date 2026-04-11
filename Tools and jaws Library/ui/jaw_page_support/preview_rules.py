"""Preview normalization and transform rules for Jaw Page."""

from __future__ import annotations


def jaw_preview_stl_path(jaw: dict) -> str:
    return (jaw.get("stl_path", "") or "").strip()


def jaw_preview_label(jaw: dict, translate) -> str:
    return jaw.get("jaw_id", translate("jaw_library.preview.jaw_label", "Jaw"))


def jaw_preview_alignment_plane(jaw: dict) -> str:
    plane = (jaw.get("preview_plane", "") or "XZ").strip()
    return plane if plane in ("XZ", "XY", "YZ") else "XZ"


def jaw_preview_rotation_steps(jaw: dict) -> list[tuple[str, int]]:
    rotations: list[tuple[str, int]] = []
    for axis, key in (("x", "preview_rot_x"), ("y", "preview_rot_y"), ("z", "preview_rot_z")):
        deg = int(jaw.get(key, 0) or 0) % 360
        if deg:
            rotations.append((axis, deg))
    return rotations

