from __future__ import annotations


def format_lookup(item_id, ref_lookup, *, translate) -> str:
    text = str(item_id or "").strip()
    if not text:
        return "-"
    ref = ref_lookup(text)
    if not ref:
        return translate(
            "setup_page.message.missing_from_master_db",
            "{item_id} (missing from master database)",
            item_id=text,
        )
    description = str(ref.get("description") or "").strip()
    return f"{text} - {description}" if description else text


def format_lookup_list(values, ref_lookup, *, translate) -> str:
    clean_values = [str(value).strip() for value in (values or []) if str(value).strip()]
    if not clean_values:
        return "-"
    return "\n".join(format_lookup(value, ref_lookup, translate=translate) for value in clean_values)


def collect_library_filter_ids(work) -> tuple[list[str], list[str]]:
    if not work:
        return [], []

    jaw_ids: list[str] = []
    for jaw_id in (work.get("main_jaw_id") or "", work.get("sub_jaw_id") or ""):
        sid = str(jaw_id).strip()
        if sid and sid not in jaw_ids:
            jaw_ids.append(sid)

    tool_ids: list[str] = []
    for tool_id in (work.get("head1_tool_ids") or []) + (work.get("head2_tool_ids") or []):
        sid = str(tool_id).strip()
        if sid and sid not in tool_ids:
            tool_ids.append(sid)
    return tool_ids, jaw_ids


def build_library_launch_context_payload(work=None) -> dict:
    tool_ids, jaw_ids = collect_library_filter_ids(work)
    return {
        "selected": bool(work),
        "work_id": (work.get("work_id") or "").strip() if work else "",
        "drawing_id": (work.get("drawing_id") or "").strip() if work else "",
        "drawing_path": (work.get("drawing_path") or "").strip() if work else "",
        "description": (work.get("description") or "").strip() if work else "",
        "tool_ids": tool_ids,
        "jaw_ids": jaw_ids,
        "has_tools": bool(tool_ids),
        "has_jaws": bool(jaw_ids),
        "has_data": bool(tool_ids or jaw_ids),
    }


def has_library_links(work=None) -> bool:
    tool_ids, jaw_ids = collect_library_filter_ids(work)
    return bool(tool_ids or jaw_ids)


def emit_library_launch_context(page, work=None) -> None:
    page.libraryLaunchContextChanged.emit(build_library_launch_context_payload(work))


def open_library_viewer_for_current_work(page) -> None:
    if not page.current_work_id:
        return
    work = page.work_service.get_work(page.current_work_id)
    if not work:
        return
    tool_ids, jaw_ids = collect_library_filter_ids(work)
    page.openLibraryMasterFilterRequested.emit(tool_ids, jaw_ids)
