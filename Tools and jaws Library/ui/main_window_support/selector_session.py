from __future__ import annotations


def empty_selector_session_state() -> dict:
    return {
        "active": False,
        "mode": "",
        "callback_server": "",
        "request_id": "",
        "head": "",
        "spindle": "",
        "target_key": "",
        "assignments": [],
        "assignment_buckets": {},
    }


def selector_session_from_payload(payload: dict) -> dict:
    mode = str((payload or {}).get("selector_mode", "") or "").strip().lower()
    if mode not in {"tools", "jaws", "fixtures"}:
        return empty_selector_session_state()

    raw_assignments = (payload or {}).get("current_assignments")
    assignments = [dict(item) for item in (raw_assignments or []) if isinstance(item, dict)]

    raw_buckets = (payload or {}).get("current_assignments_by_target") if mode in {"tools", "fixtures"} else {}
    if isinstance(raw_buckets, dict):
        assignment_buckets = {
            str(key): [dict(item) for item in value if isinstance(item, dict)]
            for key, value in raw_buckets.items()
            if isinstance(value, list)
        }
    else:
        assignment_buckets = {}

    return {
        "active": True,
        "mode": mode,
        "callback_server": str((payload or {}).get("selector_callback_server", "") or "").strip(),
        "request_id": str((payload or {}).get("selector_request_id", "") or "").strip(),
        "head": str((payload or {}).get("selector_head", "") or "").strip(),
        "spindle": str((payload or {}).get("selector_spindle", "") or "").strip(),
        "target_key": str((payload or {}).get("target_key", "") or "").strip(),
        "assignments": assignments,
        "assignment_buckets": assignment_buckets,
        "geometry": str((payload or {}).get("geometry", "") or "").strip(),
    }
