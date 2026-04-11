from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolTypeFieldState:
    selected_type: str
    cutting_type: str
    selected_head: str
    turning_drill_type: bool
    mill_tool_type: bool
    turning_tool_type: bool
    is_chamfer: bool
    is_center_drill_tool: bool
    uses_pitch_label: bool
    geometry_uses_nose_angle: bool
    is_drill_cutting: bool
    show_corner_or_nose: bool
    show_drill_field: bool
    show_mill_field: bool
    show_radius: bool
    show_b_axis: bool
    corner_label_kind: str


def is_turning_drill_tool_type(raw_tool_type: str) -> bool:
    normalized = (raw_tool_type or "").strip().lower()
    return normalized in {"turn drill", "turn spot drill"}


def is_mill_tool_type(raw_tool_type: str, milling_tool_types: tuple[str, ...] | list[str]) -> bool:
    return (raw_tool_type or "").strip() in set(milling_tool_types)


def build_tool_type_field_state(
    *,
    selected_type: str,
    cutting_type: str,
    selected_head: str,
    turning_tool_types: tuple[str, ...] | list[str],
    milling_tool_types: tuple[str, ...] | list[str],
) -> ToolTypeFieldState:
    selected_type = (selected_type or "O.D Turning").strip() or "O.D Turning"
    cutting_type = (cutting_type or "Insert").strip() or "Insert"
    selected_head = (selected_head or "HEAD1").strip().upper() or "HEAD1"

    turning_drill_type = is_turning_drill_tool_type(selected_type)
    mill_tool_type = is_mill_tool_type(selected_type, milling_tool_types)
    turning_tool_type = selected_type in set(turning_tool_types)
    is_chamfer = selected_type == "Chamfer"
    is_center_drill_tool = selected_type == "Spot Drill"
    uses_pitch_label = selected_type == "Tapping"
    geometry_uses_nose_angle = is_chamfer or is_center_drill_tool
    is_drill_cutting = cutting_type in {"Drill", "Center drill"}

    if turning_drill_type:
        corner_label_kind = "nose_angle"
    elif uses_pitch_label:
        corner_label_kind = "pitch"
    elif turning_tool_type:
        corner_label_kind = "nose_radius"
    elif geometry_uses_nose_angle:
        corner_label_kind = "nose_angle"
    elif mill_tool_type:
        corner_label_kind = "corner_radius"
    else:
        corner_label_kind = "nose_corner_radius"

    show_corner_or_nose = geometry_uses_nose_angle or not (is_drill_cutting and not turning_drill_type)
    show_drill_field = (is_drill_cutting and not turning_drill_type) and not geometry_uses_nose_angle
    show_mill_field = mill_tool_type and not is_center_drill_tool and (not is_drill_cutting or geometry_uses_nose_angle)
    show_radius = (not turning_tool_type) or turning_drill_type
    show_b_axis = turning_tool_type and not turning_drill_type and selected_head == "HEAD1"

    return ToolTypeFieldState(
        selected_type=selected_type,
        cutting_type=cutting_type,
        selected_head=selected_head,
        turning_drill_type=turning_drill_type,
        mill_tool_type=mill_tool_type,
        turning_tool_type=turning_tool_type,
        is_chamfer=is_chamfer,
        is_center_drill_tool=is_center_drill_tool,
        uses_pitch_label=uses_pitch_label,
        geometry_uses_nose_angle=geometry_uses_nose_angle,
        is_drill_cutting=is_drill_cutting,
        show_corner_or_nose=show_corner_or_nose,
        show_drill_field=show_drill_field,
        show_mill_field=show_mill_field,
        show_radius=show_radius,
        show_b_axis=show_b_axis,
        corner_label_kind=corner_label_kind,
    )
