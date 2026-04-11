from __future__ import annotations

from dataclasses import dataclass

from .tool_type_rules import ToolTypeFieldState


@dataclass(frozen=True)
class ToolTypeLayoutUpdate:
    """Resolved layout decisions for tool-type-driven detail fields."""

    corner_label_key: str
    corner_label_fallback: str
    next_turning_drill_geometry_mode: bool
    copy_drill_angle_to_corner: str | None
    copy_corner_angle_to_drill: str | None


_CORNER_LABELS: dict[str, tuple[str, str]] = {
    "pitch": ("tool_library.field.pitch", "Pitch"),
    "nose_radius": ("tool_library.field.nose_radius", "Nose radius"),
    "nose_angle": ("tool_library.field.nose_angle", "Nose angle"),
    "corner_radius": ("tool_library.field.corner_radius", "Corner radius"),
}


def _resolve_corner_label(kind: str) -> tuple[str, str]:
    return _CORNER_LABELS.get(
        kind,
        ("tool_library.field.nose_corner_radius", "Nose R / Corner R"),
    )


def build_tool_type_layout_update(
    field_state: ToolTypeFieldState,
    *,
    turning_drill_geometry_mode: bool,
    drill_nose_angle_text: str,
    nose_corner_radius_text: str,
) -> ToolTypeLayoutUpdate:
    """Compute UI sync/label updates for tool-type transitions.

    This isolates the compatibility-sensitive text hand-off behavior when the
    editor switches in/out of turning-drill geometry mode.
    """
    copy_drill_angle_to_corner: str | None = None
    copy_corner_angle_to_drill: str | None = None

    if field_state.turning_drill_type:
        if not turning_drill_geometry_mode:
            normalized = (drill_nose_angle_text or "").strip()
            if normalized:
                copy_drill_angle_to_corner = normalized
        return ToolTypeLayoutUpdate(
            corner_label_key="tool_library.field.nose_angle",
            corner_label_fallback="Nose angle",
            next_turning_drill_geometry_mode=True,
            copy_drill_angle_to_corner=copy_drill_angle_to_corner,
            copy_corner_angle_to_drill=None,
        )

    if turning_drill_geometry_mode:
        normalized = (nose_corner_radius_text or "").strip()
        if normalized:
            copy_corner_angle_to_drill = normalized

    corner_label_key, corner_label_fallback = _resolve_corner_label(field_state.corner_label_kind)
    return ToolTypeLayoutUpdate(
        corner_label_key=corner_label_key,
        corner_label_fallback=corner_label_fallback,
        next_turning_drill_geometry_mode=False,
        copy_drill_angle_to_corner=None,
        copy_corner_angle_to_drill=copy_corner_angle_to_drill,
    )
