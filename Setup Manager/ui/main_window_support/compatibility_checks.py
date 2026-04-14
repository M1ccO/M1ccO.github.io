from __future__ import annotations

import sqlite3
from pathlib import Path


def resolve_compatibility_target_path(database_path):
    target_path = Path(str(database_path or "").strip()).expanduser()
    if not str(target_path).strip():
        return None, {
            "kind": "empty",
            "message_key": "preferences.database.compatibility.empty_path",
            "default": "No Setup database path was provided.",
            "kwargs": {},
        }
    if not target_path.exists():
        return None, {
            "kind": "missing",
            "message_key": "preferences.database.compatibility.missing_path",
            "default": "The selected Setup database was not found:\n{path}",
            "kwargs": {"path": str(target_path)},
        }
    return target_path, None


def load_works_for_compatibility(database_path, row_to_work):
    """Load works rows from a Setup database and convert rows via *row_to_work*."""
    conn = sqlite3.connect(str(database_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM works ORDER BY work_id COLLATE NOCASE ASC").fetchall()
    finally:
        conn.close()
    return [row_to_work(row) for row in rows]


def build_compatibility_report(works, tool_refs, jaw_refs, translate):
    tool_ids = {str(item.get("id") or "").strip() for item in tool_refs if str(item.get("id") or "").strip()}
    tool_uids = {
        int(item.get("uid")): item
        for item in tool_refs
        if item.get("uid") is not None and str(item.get("uid")).strip()
    }
    jaw_ids = {str(item.get("id") or "").strip() for item in jaw_refs if str(item.get("id") or "").strip()}

    total_works = len(works)
    fully_resolved = 0
    works_with_issues = 0
    jaw_match_count = 0
    tool_uid_match_count = 0
    tool_id_fallback_count = 0
    missing_jaw_count = 0
    missing_tool_count = 0
    issue_lines = []

    for work in works:
        work_id = str(work.get("work_id") or "").strip() or "(no work ID)"
        local_missing = []

        for label, jaw_id in (
            (translate("work_editor.ref.main_jaw", "Main jaw"), str(work.get("main_jaw_id") or "").strip()),
            (translate("work_editor.ref.sub_jaw", "Sub jaw"), str(work.get("sub_jaw_id") or "").strip()),
        ):
            if not jaw_id:
                continue
            if jaw_id in jaw_ids:
                jaw_match_count += 1
            else:
                missing_jaw_count += 1
                local_missing.append(f"{label}: {jaw_id}")

        for head_label, assignments in (
            (translate("work_editor.ref.head1_tool", "Head 1 tool"), work.get("head1_tool_assignments") or []),
            (translate("work_editor.ref.head2_tool", "Head 2 tool"), work.get("head2_tool_assignments") or []),
        ):
            for assignment in assignments:
                tool_id = str((assignment or {}).get("tool_id") or "").strip()
                raw_uid = (assignment or {}).get("tool_uid")
                matched = False
                if raw_uid is not None and str(raw_uid).strip():
                    try:
                        if int(raw_uid) in tool_uids:
                            tool_uid_match_count += 1
                            matched = True
                    except Exception:
                        pass
                if not matched and tool_id and tool_id in tool_ids:
                    tool_id_fallback_count += 1
                    matched = True
                if not matched and tool_id:
                    missing_tool_count += 1
                    uid_text = f" [uid {raw_uid}]" if raw_uid is not None and str(raw_uid).strip() else ""
                    local_missing.append(f"{head_label}: {tool_id}{uid_text}")

        if local_missing:
            works_with_issues += 1
            issue_lines.append(f"{work_id}: " + "; ".join(local_missing))
        else:
            fully_resolved += 1

    summary = translate(
        "preferences.database.compatibility.summary",
        "Works checked: {total}\nFully resolved: {resolved}\nWorks with issues: {issues}\n\nJaw matches: {jaw_matches}\nTool matches by UID: {tool_uid_matches}\nTool matches by ID fallback: {tool_id_fallbacks}\nMissing jaws: {missing_jaws}\nMissing tools: {missing_tools}",
        total=total_works,
        resolved=fully_resolved,
        issues=works_with_issues,
        jaw_matches=jaw_match_count,
        tool_uid_matches=tool_uid_match_count,
        tool_id_fallbacks=tool_id_fallback_count,
        missing_jaws=missing_jaw_count,
        missing_tools=missing_tool_count,
    )

    return {
        "summary": summary,
        "details": "\n".join(issue_lines[:200]),
        "has_issues": bool(works_with_issues),
    }


def build_compatibility_report_bundle(target_path, draw_service, row_to_work, translate):
    tool_refs = draw_service.list_tool_refs(force_reload=True, dedupe_by_id=False)
    jaw_refs = draw_service.list_jaw_refs(force_reload=True)
    works = load_works_for_compatibility(target_path, row_to_work)
    report = build_compatibility_report(works, tool_refs, jaw_refs, translate)
    informative = translate(
        "preferences.database.compatibility.informative",
        "Setup DB: {setup_db}\nTool DB: {tool_db}\nJaw DB: {jaw_db}",
        setup_db=str(target_path),
        tool_db=str(draw_service.tool_db_path),
        jaw_db=str(draw_service.jaw_db_path),
    )
    return {
        "report": report,
        "informative": informative,
    }
