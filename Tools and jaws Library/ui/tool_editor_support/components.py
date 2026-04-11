from __future__ import annotations

import json
from typing import Callable


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value or "[]")
        except Exception:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def normalized_component_items(
    tool: dict,
    *,
    translate: Callable[[str, str | None], str],
    localized_cutting_type: Callable[[str], str],
) -> list[dict]:
    # Newer rows store normalized component_items, but older tools still persist
    # holder/cutting fields separately. This keeps both shapes loadable.
    component_items = _json_list(tool.get("component_items", []))
    if component_items:
        return [item for item in component_items if isinstance(item, dict)]

    cutting_type = (tool.get("cutting_type", "Insert") or "Insert").strip() or "Insert"
    return [
        {
            "role": "holder",
            "label": translate("tool_library.field.holder", "Holder"),
            "code": tool.get("holder_code", ""),
            "link": tool.get("holder_link", ""),
        },
        {
            "role": "holder",
            "label": translate("tool_library.field.add_element", "Add. Element"),
            "code": tool.get("holder_add_element", ""),
            "link": tool.get("holder_add_element_link", ""),
        },
        {
            "role": "cutting",
            "label": cutting_type,
            "code": tool.get("cutting_code", ""),
            "link": tool.get("cutting_link", ""),
        },
        {
            "role": "cutting",
            "label": translate(
                "tool_library.field.add_cutting",
                "Add. {cutting_type}",
                cutting_type=localized_cutting_type(cutting_type),
            ),
            "code": tool.get("cutting_add_element", ""),
            "link": tool.get("cutting_add_element_link", ""),
        },
    ]


def normalized_support_parts(tool: dict) -> list[dict]:
    raw_parts = tool.get("support_parts", [])
    support_parts = _json_list(raw_parts)
    normalized: list[dict] = []
    for part in support_parts:
        if isinstance(part, str):
            try:
                part = json.loads(part)
            except Exception:
                part = {"name": part, "code": "", "link": "", "component_key": "", "group": ""}
        if isinstance(part, dict):
            normalized.append(part)
    return normalized


def known_components_from_tools(
    tools: list[dict],
    *,
    translate: Callable[[str, str | None], str],
    localized_cutting_type: Callable[[str], str],
) -> list[dict]:
    entries: list[dict] = []

    def add_entry(kind: str, name: str, code: str, link: str, source: str) -> None:
        code = (code or "").strip()
        link = (link or "").strip()
        if not code:
            return
        entries.append(
            {
                "kind": kind,
                "name": (name or kind.title()).strip(),
                "code": code,
                "link": link,
                "source": source,
            }
        )

    for tool in tools:
        source = str(tool.get("id", "") or "").strip()
        component_items = normalized_component_items(
            tool,
            translate=translate,
            localized_cutting_type=localized_cutting_type,
        )
        if component_items:
            for item in component_items:
                role = (item.get("role") or "").strip().lower()
                if role not in {"holder", "cutting", "support"}:
                    continue
                add_entry(
                    role,
                    item.get("label", translate("tool_library.field.part", "Part")),
                    item.get("code", ""),
                    item.get("link", ""),
                    source,
                )

        for part in normalized_support_parts(tool):
            add_entry(
                "support",
                part.get("name", translate("tool_library.field.part", "Part")),
                part.get("code", ""),
                part.get("link", ""),
                source,
            )

    dedup: dict[tuple[str, str, str, str, str], dict] = {}
    for entry in entries:
        key = (
            entry.get("kind", ""),
            entry.get("name", ""),
            entry.get("code", ""),
            entry.get("link", ""),
            entry.get("source", ""),
        )
        if key not in dedup:
            dedup[key] = entry
    return list(dedup.values())


def component_dropdown_values(row_dicts: list[dict]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in row_dicts:
        role = (entry.get("role") or "component").strip().lower()
        label = (entry.get("label") or "").strip()
        code = (entry.get("code") or "").strip()
        if not code:
            continue
        key = f"{role}:{code}"
        if key in seen:
            continue
        seen.add(key)
        display = f"{label} ({code})" if label else code
        values.append((display, key))
    return values


def component_display_for_key(key: str, row_dicts: list[dict]) -> str:
    key = (key or "").strip()
    if not key:
        return "-"
    for entry in row_dicts:
        role = (entry.get("role") or "component").strip().lower()
        label = (entry.get("label") or "").strip()
        code = (entry.get("code") or "").strip()
        if code and f"{role}:{code}" == key:
            return f"{label} ({code})" if label else code
    return key.split(":", 1)[1] if ":" in key else key


def component_items_from_rows(
    row_dicts: list[dict],
    *,
    translate: Callable[[str, str | None], str],
    localized_cutting_type: Callable[[str], str],
) -> list[dict]:
    items: list[dict] = []
    for entry in row_dicts:
        role = (entry.get("role") or "support").strip().lower()
        if role not in {"holder", "cutting", "support"}:
            role = "support"
        code = (entry.get("code") or "").strip()
        if not code:
            continue
        label = (entry.get("label") or "").strip()
        if not label:
            if role == "holder":
                label = translate("tool_library.field.holder", "Holder")
            elif role == "cutting":
                label = localized_cutting_type("Insert")
            else:
                label = translate("tool_library.field.part", "Part")
        items.append(
            {
                "role": role,
                "label": label,
                "code": code,
                "link": (entry.get("link") or "").strip(),
                "group": (entry.get("group") or "").strip(),
                "component_key": f"{role}:{code}",
                "order": len(items),
            }
        )
    return items


def spare_parts_from_rows(rows: list[dict]) -> list[dict]:
    result: list[dict] = []
    for entry in rows:
        name = (entry.get("name") or "").strip()
        code = (entry.get("code") or "").strip()
        link = (entry.get("link") or "").strip()
        component_key = (entry.get("component_key") or "").strip()
        group = (entry.get("group") or "").strip()
        if not (name or code or link or component_key):
            continue
        result.append(
            {
                "name": name,
                "code": code,
                "link": link,
                "component_key": component_key,
                "group": group,
            }
        )
    return result
