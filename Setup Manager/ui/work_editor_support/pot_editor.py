from __future__ import annotations

from typing import Any

from shared.ui.tool_assignment_editing import open_tool_pot_editor_dialog

from .tool_actions import populate_default_pots


def _collect_sections(dialog: Any) -> list[dict]:
    sections: list[dict] = []
    for head_name in dialog._head_profiles.keys():
        groups: list[dict] = []
        for spindle in dialog._spindle_profiles.keys():
            rows: list[dict] = []
            ordered_list = (dialog._tool_column_lists.get(head_name) or {}).get(spindle)
            if ordered_list is None:
                continue
            for item in ordered_list._assignments_by_spindle.get(spindle, []):
                tool_id = str(item.get("tool_id") or "").strip()
                if not tool_id:
                    continue
                rows.append(
                    {
                        "assignment": item,
                        "label": ordered_list._tool_label(item),
                        "icon": ordered_list._tool_icon_for_spindle_resolver(
                            (ordered_list._tool_ref_for_assignment(item) or {}).get("tool_type", ""),
                            spindle,
                        ),
                        "flip_vertical": str(getattr(ordered_list, "_head_key", "") or "").strip().upper() == "HEAD2",
                        "pot": str(item.get("pot") or "").strip(),
                        "placeholder": dialog._t("work_editor.tools.pot_placeholder", "Pot #"),
                    }
                )
            groups.append(
                {
                    "title": dialog._spindle_label(spindle, spindle),
                    "rows": rows,
                }
            )
        sections.append(
            {
                "title": dialog._head_label(head_name, head_name),
                "groups": groups,
            }
        )
    return sections


def open_pot_editor_dialog(dialog: Any) -> None:
    populate_default_pots(dialog)
    changed = open_tool_pot_editor_dialog(
        dialog,
        sections=_collect_sections(dialog),
        translate=dialog._t,
        title=dialog._t("work_editor.tools.pot_editor_title", "Pot Editor"),
    )
    if not changed:
        return
    for ordered_list in dialog._all_tool_list_widgets:
        ordered_list._render_current_spindle()
