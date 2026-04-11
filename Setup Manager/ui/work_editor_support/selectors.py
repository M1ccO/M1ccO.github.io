from __future__ import annotations


def normalize_selector_head(value: str | None, known_heads: tuple[str, ...] | list[str] | None = None) -> str:
    text = str(value or "").strip().upper()
    known = tuple(str(item).strip().upper() for item in (known_heads or ("HEAD1", "HEAD2")) if str(item).strip())
    if text in known:
        return text
    return known[0] if known else "HEAD1"


def normalize_selector_spindle(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if text in {"sub", "sp2", "sub spindle"}:
        return "sub"
    return "main"


def parse_optional_int(value) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except Exception:
        return None


def tool_ref_key(tool: dict | None) -> str:
    if not isinstance(tool, dict):
        return ""
    uid = tool.get("uid", tool.get("tool_uid"))
    if uid is not None and str(uid).strip():
        return f"uid:{uid}"
    tool_id = str(tool.get("id") or tool.get("tool_id") or "").strip()
    return f"id:{tool_id}" if tool_id else ""


def jaw_ref_key(jaw: dict | None) -> str:
    if not isinstance(jaw, dict):
        return ""
    return str(jaw.get("id") or jaw.get("jaw_id") or "").strip()


def load_external_tool_refs(draw_service, head_keys: list[str] | tuple[str, ...]) -> tuple[dict[str, list[dict]], list[dict]]:
    refs_by_head: dict[str, list[dict]] = {}
    for head_key in head_keys:
        refs_by_head[head_key] = draw_service.list_tool_refs(
            force_reload=True,
            head_filter=head_key,
            dedupe_by_id=False,
        )

    if not any(refs_by_head.values()):
        combined = draw_service.list_tool_refs(force_reload=True, dedupe_by_id=False)
        refs_by_head = {head_key: list(combined) for head_key in head_keys}
        return refs_by_head, list(combined)

    # Head-specific caches can overlap. We also keep a combined cache for
    # selector callbacks that may return tools for a different head than the
    # list currently on screen.
    combined: list[dict] = []
    seen: set[str] = set()
    for group in refs_by_head.values():
        for tool in group or []:
            if not isinstance(tool, dict):
                continue
            key = tool_ref_key(tool)
            if not key or key in seen:
                continue
            seen.add(key)
            combined.append(dict(tool))

    for head_key, refs in list(refs_by_head.items()):
        if not refs:
            refs_by_head[head_key] = list(combined)

    return refs_by_head, combined


def merge_tool_refs(
    refs_by_head: dict[str, list[dict]],
    combined_refs: list[dict],
    *,
    head_key: str,
    selected_items: list[dict],
) -> tuple[dict[str, list[dict]], list[dict]]:
    target_refs = [dict(tool) for tool in (refs_by_head.get(head_key) or []) if isinstance(tool, dict)]
    target_map = {tool_ref_key(tool): index for index, tool in enumerate(target_refs)}

    merged_combined = [dict(tool) for tool in (combined_refs or []) if isinstance(tool, dict)]
    combined_map = {tool_ref_key(tool): index for index, tool in enumerate(merged_combined)}

    for item in selected_items:
        if not isinstance(item, dict):
            continue
        tool_id = str(item.get("tool_id") or item.get("id") or "").strip()
        if not tool_id:
            continue
        ref = {
            "id": tool_id,
            "uid": parse_optional_int(item.get("tool_uid", item.get("uid"))),
            "description": str(item.get("description") or "").strip(),
            "tool_type": str(item.get("tool_type") or "").strip(),
            "default_pot": str(item.get("default_pot") or "").strip(),
        }
        key = tool_ref_key(ref)
        if not key:
            continue
        if key in target_map:
            target_refs[target_map[key]].update({k: v for k, v in ref.items() if v not in (None, "")})
        else:
            target_map[key] = len(target_refs)
            target_refs.append(ref)
        if key in combined_map:
            merged_combined[combined_map[key]].update({k: v for k, v in ref.items() if v not in (None, "")})
        else:
            combined_map[key] = len(merged_combined)
            merged_combined.append(ref)

    merged_by_head = dict(refs_by_head)
    merged_by_head[head_key] = target_refs
    return merged_by_head, merged_combined


def merge_jaw_refs(jaw_refs: list[dict], selected_items: list[dict]) -> tuple[list[dict], bool]:
    merged_refs = [dict(jaw) for jaw in (jaw_refs or []) if isinstance(jaw, dict)]
    jaw_map = {jaw_ref_key(jaw): index for index, jaw in enumerate(merged_refs)}
    changed = False
    for item in selected_items:
        if not isinstance(item, dict):
            continue
        jaw_id = str(item.get("jaw_id") or item.get("id") or "").strip()
        if not jaw_id:
            continue
        ref = {
            "id": jaw_id,
            "jaw_type": str(item.get("jaw_type") or "").strip(),
            "description": str(item.get("description") or "").strip(),
        }
        if jaw_id in jaw_map:
            merged_refs[jaw_map[jaw_id]].update({k: v for k, v in ref.items() if v})
        else:
            jaw_map[jaw_id] = len(merged_refs)
            merged_refs.append(ref)
        changed = True
    return merged_refs, changed


def selector_initial_tool_assignments(ordered_list, spindle: str) -> list[dict]:
    target_spindle = normalize_selector_spindle(spindle or "main")
    by_key: dict[str, dict] = {}
    for tool in ordered_list._all_tools or []:
        if not isinstance(tool, dict):
            continue
        tool_key = ordered_list._assignment_key(
            {
                "tool_id": str(tool.get("id") or "").strip(),
                "tool_uid": tool.get("uid"),
            }
        )
        if tool_key:
            by_key[tool_key] = dict(tool)

    initial: list[dict] = []
    for assignment in ordered_list._assignments_by_spindle.get(target_spindle, []):
        if not isinstance(assignment, dict):
            continue
        tool_id = str(assignment.get("tool_id") or "").strip()
        if not tool_id:
            continue

        merged: dict = {"tool_id": tool_id}
        if assignment.get("tool_uid") is not None:
            merged["tool_uid"] = assignment.get("tool_uid")
        comment = str(assignment.get("comment") or "").strip()
        if comment:
            merged["comment"] = comment
        pot = str(assignment.get("pot") or "").strip()
        if pot:
            merged["default_pot"] = pot

        resolved = by_key.get(ordered_list._assignment_key(assignment), {})
        if resolved:
            description = str(resolved.get("description") or "").strip()
            if description:
                merged["description"] = description
            tool_type = str(resolved.get("tool_type") or "").strip()
            if tool_type:
                merged["tool_type"] = tool_type
            if "default_pot" not in merged:
                default_pot = str(resolved.get("default_pot") or "").strip()
                if default_pot:
                    merged["default_pot"] = default_pot

        initial.append(merged)
    return initial


def selector_initial_tool_assignment_buckets(
    ordered_lists: dict[str, object],
    head_keys: list[str] | tuple[str, ...],
    spindle_keys: list[str] | tuple[str, ...],
) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {}
    for head_key in head_keys:
        ordered_list = ordered_lists.get(head_key)
        if ordered_list is None:
            continue
        for spindle_key in spindle_keys:
            buckets[f"{head_key}:{spindle_key}"] = selector_initial_tool_assignments(ordered_list, spindle_key)
    return buckets
