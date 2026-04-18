from __future__ import annotations

import json

from machine_profiles import MachineProfile, is_machining_center, load_profile


def resolve_setup_card_profile(machine_profile_key: str | None) -> MachineProfile:
    return load_profile(machine_profile_key)


def _head_label(translate, head) -> str:
    return translate(head.label_key, head.label_default)


def _spindle_label(translate, spindle) -> str:
    return translate(spindle.label_key, spindle.label_default)


def _spindle_title(translate, profile: MachineProfile, spindle_key: str) -> str:
    spindle = profile.spindle(spindle_key)
    if spindle is not None:
        return translate(spindle.jaw_title_key, spindle.jaw_title_default)
    fallback_map = {
        "main": translate("work_editor.spindles.sp1_jaw", "Pääkara"),
        "sub": translate("work_editor.spindles.sp2_jaw", "Vastakara"),
    }
    return fallback_map.get(str(spindle_key or "").strip().lower(), str(spindle_key or "").strip())


def _mc_axis_label(profile: MachineProfile, axis: str) -> str:
    axis_key = str(axis or "").strip().lower()
    if axis_key in {"x", "y", "z"}:
        return axis_key.upper()
    if axis_key == "c" and int(getattr(profile, "axis_count", 3) or 3) >= 4:
        return str(getattr(profile, "fourth_axis_letter", "C") or "C").strip().upper()
    if axis_key == "b" and int(getattr(profile, "axis_count", 3) or 3) == 5:
        return str(getattr(profile, "fifth_axis_letter", "B") or "B").strip().upper()
    return axis_key.upper()


def _head_summary_section(printer, profile: MachineProfile, head: object, work: dict) -> dict:
    head_key = str(getattr(head, "key", "") or "").strip().upper()
    head_prefix = head_key.lower()
    lines = [
        printer._t(
            "print.setup_card.label.program",
            "Program: {value}",
            value=printer._safe(work.get("main_program")),
        ),
        printer._t(
            "print.setup_card.label.sub_program",
            "Sub program: {value}",
            value=printer._safe(work.get(f"{head_prefix}_sub_program")),
        ),
    ]
    for spindle in profile.spindles:
        coord = work.get(f"{head_prefix}_{spindle.key}_coord") or work.get(f"{head_prefix}_zero")
        axis_text_parts = []
        for axis in profile.zero_axes:
            value = printer._to_text(work.get(f"{head_prefix}_{spindle.key}_{axis}"))
            if value:
                axis_text_parts.append(f"{axis.upper()}{value}")
        if not axis_text_parts:
            continue
        zero_text = " | ".join(axis_text_parts)
        coord_text = printer._to_text(coord)
        if coord_text:
            zero_text = f"{coord_text} - {zero_text}"
        lines.append(
            printer._t(
                "print.setup_card.label.zero",
                "{spindle} zero: {text}",
                spindle=_spindle_label(printer._t, spindle),
                text=zero_text,
            )
        )
    return {
        "title": _head_label(printer._t, head),
        "lines": lines,
        "layout": "half",
        "colorize_axis_letters": True,
        "bold_value_after_colon": True,
    }


def _lathe_jaw_sections(printer, profile: MachineProfile, work: dict) -> list[dict]:
    sections: list[dict] = []
    spindle_order = [spindle.key for spindle in profile.spindles]
    if "main" not in spindle_order:
        spindle_order.insert(0, "main")
    if "sub" not in spindle_order and printer._to_text(work.get("sub_jaw_id")):
        spindle_order.append("sub")

    for spindle_key in spindle_order:
        jaw_id = work.get(f"{spindle_key}_jaw_id")
        if not printer._to_text(jaw_id) and spindle_key == "sub" and profile.spindle_count <= 1:
            continue
        spindle_title = _spindle_title(printer._t, profile, spindle_key)
        details = printer._jaw_details(jaw_id)
        jaw_lines = [
            printer._t(
                f"print.setup_card.label.{spindle_key}_jaw",
                "{spindle} leuka: {value}",
                spindle=spindle_title,
                value=printer._jaw_summary(jaw_id),
            )
        ]
        turning_washer = printer._to_text(details.get("turning_washer"))
        if turning_washer:
            jaw_lines.append(
                printer._t(
                    f"print.setup_card.label.{spindle_key}_turning_ring",
                    "{spindle} sorvausrengas: {value}",
                    spindle=spindle_title,
                    value=turning_washer,
                )
            )
        last_modified = printer._to_text(details.get("last_modified"))
        if last_modified:
            jaw_lines.append(
                printer._t(
                    f"print.setup_card.label.{spindle_key}_last_modified",
                    "{spindle} viimeksi muokattu: {value}",
                    spindle=spindle_title,
                    value=last_modified,
                )
            )
        stop_screws = printer._to_text(work.get(f"{spindle_key}_stop_screws"))
        if stop_screws:
            jaw_lines.append(
                printer._t(
                    f"print.setup_card.label.{spindle_key}_stop_screws",
                    "{spindle} stoppariruuvit: {value}",
                    spindle=spindle_title,
                    value=stop_screws,
                )
            )
        sections.append(
            {
                "title": printer._t(
                    f"print.setup_card.section.jaws_{spindle_key}",
                    "{spindle}n leuat",
                    spindle=spindle_title,
                ),
                "lines": jaw_lines,
                "layout": "half",
                "bold_value_after_colon": True,
            }
        )
    return sections


def _mc_operations(work: dict) -> list[dict]:
    operations = work.get("mc_operations") or []
    if isinstance(operations, str):
        try:
            operations = json.loads(operations)
        except Exception:
            operations = []
    if not isinstance(operations, list):
        return []
    return [item for item in operations if isinstance(item, dict)]


def _mc_operation_summary_sections(printer, profile: MachineProfile, work: dict) -> list[dict]:
    operations = _mc_operations(work)
    if not operations:
        return []

    operation_lines: list[str] = []
    fixture_lines: list[str] = []
    for op in operations:
        op_key = printer._to_text(op.get("op_key")) or printer._t("work_editor.tools.operation", "Operation")
        coord = printer._to_text(op.get("coord"))
        axis_values = op.get("axes") if isinstance(op.get("axes"), dict) else {}
        axis_parts = []
        for axis in profile.zero_axes:
            value = printer._to_text(axis_values.get(axis))
            if value:
                axis_parts.append(f"{_mc_axis_label(profile, axis)}{value}")
        location = coord
        if axis_parts:
            axis_text = " | ".join(axis_parts)
            location = f"{coord} - {axis_text}" if coord else axis_text
        operation_lines.append(
            printer._t(
                "print.setup_card.label.operation",
                "{op_key}: {value}",
                op_key=op_key,
                value=location or "-",
            )
        )
        sub_program = printer._to_text(op.get("sub_program"))
        if sub_program:
            operation_lines.append(
                printer._t(
                    "print.setup_card.label.operation_sub_program",
                    "{op_key} sub program: {value}",
                    op_key=op_key,
                    value=sub_program,
                )
            )

        fixture_items = [dict(item) for item in (op.get("fixture_items") or []) if isinstance(item, dict)]
        fixture_ids = [
            printer._to_text(item.get("fixture_id") or item.get("id"))
            for item in fixture_items
        ] or [printer._to_text(item) for item in (op.get("fixture_ids") or [])]
        fixture_ids = [item for item in fixture_ids if item]
        fixture_lines.append(
            printer._t(
                "print.setup_card.label.operation_fixtures",
                "{op_key} fixtures: {value}",
                op_key=op_key,
                value=", ".join(fixture_ids) if fixture_ids else printer._t("common.none", "None"),
            )
        )
        selected_part = printer._to_text(op.get("selected_fixture_part"))
        if selected_part:
            fixture_lines.append(
                printer._t(
                    "print.setup_card.label.operation_fixture_part",
                    "{op_key} selected part: {value}",
                    op_key=op_key,
                    value=selected_part,
                )
            )

    return [
        {
            "title": printer._t("print.setup_card.section.operations", "Operations"),
            "lines": operation_lines,
            "layout": "full",
            "colorize_axis_letters": True,
            "bold_value_after_colon": True,
        },
        {
            "title": printer._t("print.setup_card.section.fixtures", "Fixtures"),
            "lines": fixture_lines or [printer._t("common.none", "None")],
            "layout": "full",
            "bold_value_after_colon": True,
        },
    ]


def build_setup_card_sections(printer, work: dict, profile: MachineProfile) -> list[dict]:
    sections: list[dict] = []
    if is_machining_center(profile):
        sections.extend(_mc_operation_summary_sections(printer, profile, work))
    else:
        sections.extend(_head_summary_section(printer, profile, head, work) for head in profile.heads)
        sections.extend(_lathe_jaw_sections(printer, profile, work))

    notes_text = printer._to_text(work.get("notes"))
    if notes_text and notes_text not in {"-", "--"}:
        sections.append(
            {
                "title": printer._t("setup_page.section.notes", "Notes"),
                "lines": [notes_text],
                "layout": "full",
            }
        )
    robot_info = printer._to_text(work.get("robot_info"))
    if robot_info:
        sections.append(
            {
                "title": printer._t("print.setup_card.section.robot_notes", "Robot notes"),
                "lines": [robot_info],
                "layout": "full",
            }
        )
    return sections


def build_setup_card_tool_groups(printer, work: dict, profile: MachineProfile) -> list[dict]:
    if is_machining_center(profile):
        groups = []
        for op in _mc_operations(work):
            main_tools, sub_tools = printer._tool_lists_for_head(op.get("tool_assignments") or [])
            if main_tools or sub_tools:
                groups.append(
                    {
                        "label": printer._to_text(op.get("op_key")) or printer._t("work_editor.tools.operation", "Operation"),
                        "main": main_tools,
                        "sub": sub_tools,
                    }
                )
        return groups

    groups = []
    for head in profile.heads:
        head_prefix = str(head.key or "").strip().lower()
        main_tools, sub_tools = printer._tool_lists_for_head(work.get(f"{head_prefix}_tool_assignments") or [])
        if main_tools or sub_tools:
            groups.append(
                {
                    "label": _head_label(printer._t, head),
                    "main": main_tools,
                    "sub": sub_tools,
                }
            )
    return groups
