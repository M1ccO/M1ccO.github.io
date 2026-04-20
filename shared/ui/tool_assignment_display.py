from __future__ import annotations

from typing import Mapping


def _text(value: object) -> str:
    return str(value or "").strip()


def library_label_fields(assignment: Mapping[str, object] | None) -> tuple[str, str]:
    if not isinstance(assignment, Mapping):
        return "", ""
    return _text(assignment.get("tool_id") or assignment.get("id")), _text(assignment.get("description"))


def effective_fields(
    assignment: Mapping[str, object] | None,
    *,
    library_tool_id: str = "",
    library_description: str = "",
) -> tuple[str, str, bool]:
    if not isinstance(assignment, Mapping):
        return "", "", False

    base_tool_id = _text(library_tool_id) or _text(assignment.get("tool_id") or assignment.get("id"))
    base_description = _text(library_description) or _text(assignment.get("description"))
    override_id = _text(assignment.get("override_id"))
    override_description = _text(assignment.get("override_description"))

    effective_tool_id = override_id or base_tool_id
    effective_description = override_description or base_description
    is_edited = bool(
        (override_id and override_id != base_tool_id)
        or (override_description and override_description != base_description)
    )
    return effective_tool_id, effective_description, is_edited


def compose_title(*, row_index: int | None = None, tool_id: str = "", description: str = "") -> str:
    prefix = ""
    if isinstance(row_index, int) and row_index >= 0:
        prefix = f"{row_index + 1}. "

    label = _text(tool_id)
    desc = _text(description)
    if desc:
        label = f"{label}  -  {desc}" if label else desc
    return f"{prefix}{label}".rstrip() if prefix or label else prefix.rstrip()


def build_badges(*, comment: str = "", pot: str = "", edited: bool = False, show_pot: bool = False) -> list[str]:
    badges: list[str] = []
    normalized_pot = _text(pot)
    if normalized_pot and show_pot:
        badges.append(f"P:{normalized_pot}")
    if _text(comment):
        badges.append("C")
    if edited:
        badges.append("E")
    return badges
