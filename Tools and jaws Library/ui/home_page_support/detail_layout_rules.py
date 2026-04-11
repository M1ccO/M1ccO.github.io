"""Rules for HomePage detail-grid layout by tool/cutting type.

The page owns widget creation; this module only decides which row structure
should be used and invokes the provided row-builder callbacks.
"""

from __future__ import annotations

from typing import Callable, Iterable


def apply_tool_detail_layout_rules(
    *,
    tool: dict,
    tool_head: str,
    raw_tool_type: str,
    raw_cutting_type: str,
    turning_drill_type: bool,
    angle_value: str,
    milling_tool_types: Iterable[str],
    turning_tool_types: Iterable[str],
    add_two_box_row: Callable[[int, str, str, str, str], None],
    add_three_box_row: Callable[[int, str, str, str, str, str, str], None],
    add_fallback_pair_row: Callable[[str, str, str, str], None],
    translate: Callable[..., str],
) -> int:
    """Apply row rules to the details grid and return the notes row index."""
    is_milling = raw_tool_type in set(milling_tool_types)
    is_drill_cutting = raw_cutting_type in {"Drill", "Center drill"}
    stripped_tool_type = (raw_tool_type or "").strip()
    is_drill_tool = stripped_tool_type == "Drill"
    is_chamfer = stripped_tool_type == "Chamfer"
    is_center_drill_tool = stripped_tool_type == "Spot Drill"
    uses_pitch_label = stripped_tool_type == "Tapping"
    is_turning_tool = raw_tool_type in set(turning_tool_types)
    show_b_axis = is_turning_tool and not turning_drill_type and tool_head == "HEAD1"
    is_head2_turning_non_drill = tool_head == "HEAD2" and is_turning_tool and not turning_drill_type

    if is_head2_turning_non_drill:
        add_three_box_row(
            0,
            translate("tool_library.field.geom_x", "Geom X"),
            str(tool.get("geom_x", "")),
            translate("tool_library.field.geom_z", "Geom Z"),
            str(tool.get("geom_z", "")),
            translate("tool_library.field.nose_radius", "Nose radius"),
            str(tool.get("nose_corner_radius", "")),
        )
    else:
        add_two_box_row(
            0,
            translate("tool_library.field.geom_x", "Geom X"),
            str(tool.get("geom_x", "")),
            translate("tool_library.field.geom_z", "Geom Z"),
            str(tool.get("geom_z", "")),
        )

    if turning_drill_type:
        add_two_box_row(
            1,
            translate("tool_library.field.radius", "Radius"),
            str(tool.get("radius", "")),
            translate("tool_library.field.nose_angle", "Nose angle"),
            angle_value,
        )
        return 2

    if is_turning_tool:
        if show_b_axis:
            add_two_box_row(
                1,
                translate("tool_library.field.b_axis_angle", "B-axis angle"),
                str(tool.get("b_axis_angle", "0")),
                translate("tool_library.field.nose_radius", "Nose radius"),
                str(tool.get("nose_corner_radius", "")),
            )
            return 2
        return 1

    if is_chamfer:
        add_three_box_row(
            1,
            translate("tool_library.field.radius", "Radius"),
            str(tool.get("radius", "")),
            translate("tool_library.field.nose_angle", "Nose angle"),
            angle_value,
            translate("tool_library.field.number_of_flutes", "Number of flutes"),
            str(tool.get("mill_cutting_edges", "")),
        )
        return 2

    if is_center_drill_tool or is_drill_tool:
        add_two_box_row(
            1,
            translate("tool_library.field.radius", "Radius"),
            str(tool.get("radius", "")),
            translate("tool_library.field.nose_angle", "Nose angle"),
            angle_value,
        )
        return 2

    if is_milling and not is_drill_cutting:
        add_three_box_row(
            1,
            translate("tool_library.field.radius", "Radius"),
            str(tool.get("radius", "")),
            translate("tool_library.field.number_of_flutes", "Number of flutes"),
            str(tool.get("mill_cutting_edges", "")),
            translate("tool_library.field.pitch", "Pitch")
            if uses_pitch_label
            else translate("tool_library.field.corner_radius", "Corner radius"),
            str(tool.get("nose_corner_radius", "")),
        )
        return 2

    if is_drill_cutting:
        add_fallback_pair_row(
            translate("tool_library.field.radius", "Radius"),
            str(tool.get("radius", "")),
            translate("tool_library.field.nose_angle", "Nose angle"),
            angle_value,
        )
    else:
        add_fallback_pair_row(
            translate("tool_library.field.radius", "Radius"),
            str(tool.get("radius", "")),
            translate("tool_library.field.nose_corner_radius", "Nose R / Corner R"),
            str(tool.get("nose_corner_radius", "")),
        )
    return 2

