from .machining_center import apply_fixture_selection_to_operation

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
    list_tool_refs = getattr(draw_service, "list_tool_refs", None)
    if not callable(list_tool_refs):
        refs_by_head = {head_key: [] for head_key in head_keys}
        return refs_by_head, []

    refs_by_head: dict[str, list[dict]] = {}
    for head_key in head_keys:
        refs_by_head[head_key] = list_tool_refs(
            force_reload=True,
            head_filter=head_key,
            dedupe_by_id=False,
        )

    if not any(refs_by_head.values()):
        combined = list_tool_refs(force_reload=True, dedupe_by_id=False)
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


def merge_tool_refs_and_sync_lists(
    refs_by_head: dict[str, list[dict]],
    combined_refs: list[dict],
    *,
    head_key: str,
    selected_items: list[dict],
    tool_column_lists: dict[str, dict[str, object]],
) -> tuple[dict[str, list[dict]], list[dict]]:
    merged_by_head, merged_combined = merge_tool_refs(
        refs_by_head,
        combined_refs,
        head_key=head_key,
        selected_items=selected_items,
    )
    for head, columns in tool_column_lists.items():
        refs = merged_by_head.get(head, merged_combined) or []
        for ordered_list in columns.values():
            ordered_list._all_tools = refs
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


def merge_jaw_refs_and_sync_selectors(
    jaw_refs: list[dict],
    selected_items: list[dict],
    jaw_selectors: dict[str, object],
) -> tuple[list[dict], bool]:
    merged_refs, changed = merge_jaw_refs(jaw_refs, selected_items)
    if changed:
        for selector in jaw_selectors.values():
            selector.populate(merged_refs)
    return merged_refs, changed


def build_tool_selector_bucket(
    selected_items: list[dict],
    *,
    spindle: str,
    assignment_key_fn,
) -> list[dict]:
    """Normalize selector payload into a de-duplicated assignment bucket."""
    bucket: list[dict] = []
    seen_keys: set[str] = set()
    for item in selected_items:
        if not isinstance(item, dict):
            continue
        tool_id = str(item.get("tool_id") or item.get("id") or "").strip()
        if not tool_id:
            continue
        entry = {
            "tool_id": tool_id,
            "spindle": spindle,
            "comment": str(item.get("comment") or "").strip(),
            "pot": str(item.get("pot") or item.get("default_pot") or "").strip(),
            "override_id": str(item.get("override_id") or "").strip(),
            "override_description": str(item.get("override_description") or "").strip(),
        }
        tool_uid = parse_optional_int(item.get("tool_uid", item.get("uid")))
        if tool_uid is not None:
            entry["tool_uid"] = tool_uid
        description = str(item.get("description") or "").strip()
        if description:
            entry["description"] = description
        tool_type = str(item.get("tool_type") or "").strip()
        if tool_type:
            entry["tool_type"] = tool_type
        default_pot = str(item.get("default_pot") or "").strip()
        if default_pot:
            entry["default_pot"] = default_pot
        key = assignment_key_fn(entry)
        if not key or key in seen_keys:
            continue
        bucket.append(entry)
        seen_keys.add(key)
    return bucket


def jaw_selection_by_spindle(selected_items: list[dict], *, normalize_spindle_fn=normalize_selector_spindle) -> dict[str, str]:
    """Return spindle->jaw mapping when selector payload includes slot metadata."""
    selected_by_spindle: dict[str, str] = {}
    for item in selected_items:
        if not isinstance(item, dict):
            continue
        jaw_id = str(item.get("jaw_id") or item.get("id") or "").strip()
        if not jaw_id:
            continue
        item_spindle = normalize_spindle_fn(item.get("spindle") or item.get("slot") or "")
        if item_spindle in ("main", "sub"):
            selected_by_spindle[item_spindle] = jaw_id
    return selected_by_spindle


def unique_selected_jaw_ids(selected_items: list[dict]) -> list[str]:
    selected_jaws: list[str] = []
    for item in selected_items:
        if not isinstance(item, dict):
            continue
        jaw_id = str(item.get("jaw_id") or item.get("id") or "").strip()
        if jaw_id and jaw_id not in selected_jaws:
            selected_jaws.append(jaw_id)
    return selected_jaws


def apply_tool_selector_items_to_ordered_list(
    ordered_list,
    selected_items: list[dict],
    *,
    spindle: str,
) -> list[dict]:
    """Build and apply selector bucket for one ordered-list spindle target."""
    bucket = build_tool_selector_bucket(
        selected_items,
        spindle=spindle,
        assignment_key_fn=ordered_list._assignment_key,
    )
    ordered_list._assignments_by_spindle[spindle] = bucket
    return bucket


def apply_jaw_selector_items_to_selectors(
    jaw_selectors: dict[str, object],
    selected_items: list[dict],
    *,
    target_spindle: str,
    normalize_spindle_fn=normalize_selector_spindle,
) -> bool:
    """Apply selector jaw payload to main/sub selectors.

    Handles both explicit spindle-tagged payloads and legacy flat jaw lists.
    """
    selected_by_spindle = jaw_selection_by_spindle(
        selected_items,
        normalize_spindle_fn=normalize_spindle_fn,
    )
    main_selector = jaw_selectors.get("main")
    sub_selector = jaw_selectors.get("sub")

    if selected_by_spindle:
        if main_selector is not None:
            main_selector.set_value(selected_by_spindle.get("main", ""))
        if sub_selector is not None:
            sub_selector.set_value(selected_by_spindle.get("sub", ""))
        return True

    selected_jaws = unique_selected_jaw_ids(selected_items)
    if not selected_jaws:
        if main_selector is not None:
            main_selector.set_value("")
        if sub_selector is not None:
            sub_selector.set_value("")
        return True

    if len(selected_jaws) >= 2:
        if main_selector is not None:
            main_selector.set_value(selected_jaws[0])
        if sub_selector is not None:
            sub_selector.set_value(selected_jaws[1])
        return True

    target_selector = jaw_selectors.get(target_spindle, main_selector)
    if target_selector is not None:
        target_selector.set_value(selected_jaws[0])
    return True


def apply_fixture_selector_items_to_operations(dialog, *, request: dict, selected_items: list[dict]) -> bool:
    target_key = str(request.get('target_key') or '').strip()
    if not target_key:
        return False
    legacy_apply = getattr(dialog, '_apply_fixture_selection_to_operation', None)
    if not hasattr(dialog, '_mc_operations') and callable(legacy_apply):
        return bool(legacy_apply(target_key, selected_items))
    return bool(apply_fixture_selection_to_operation(dialog, target_key, selected_items))


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
        override_id = str(assignment.get("override_id") or "").strip()
        if override_id:
            merged["override_id"] = override_id
        override_description = str(assignment.get("override_description") or "").strip()
        if override_description:
            merged["override_description"] = override_description
        pot = str(assignment.get("pot") or "").strip()
        if pot:
            merged["pot"] = pot
            merged["default_pot"] = pot

        resolved = by_key.get(ordered_list._assignment_key(assignment), {})
        description = str(assignment.get("description") or "").strip()
        if description:
            merged["description"] = description
        tool_type = str(assignment.get("tool_type") or "").strip()
        if tool_type:
            merged["tool_type"] = tool_type
        default_pot = str(assignment.get("default_pot") or "").strip()
        if default_pot and "default_pot" not in merged:
            merged["default_pot"] = default_pot
        if resolved:
            description = str(resolved.get("description") or "").strip()
            if description and "description" not in merged:
                merged["description"] = description
            tool_type = str(resolved.get("tool_type") or "").strip()
            if tool_type and "tool_type" not in merged:
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
        ordered_entry = ordered_lists.get(head_key)
        for spindle_key in spindle_keys:
            ordered_list = ordered_entry
            if isinstance(ordered_entry, dict):
                ordered_list = ordered_entry.get(spindle_key)
            if ordered_list is None:
                continue
            buckets[f"{head_key}:{spindle_key}"] = selector_initial_tool_assignments(ordered_list, spindle_key)
    return buckets
