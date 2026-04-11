"""Selector assignment state helpers for HomePage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ui.selector_state_helpers import (
    normalize_selector_bucket,
    selector_assignments_for_target,
    selector_bucket_map,
)
from ui.selector_ui_helpers import normalize_selector_spindle


@dataclass(frozen=True)
class PreparedSelectorAssignmentContext:
    head: str
    spindle: str
    assignments: list[dict]
    buckets: dict[str, list[dict]]


class SelectorAssignmentState:
    def __init__(self, *, normalize_head: Callable[[str], str]) -> None:
        self._normalize_head = normalize_head

    def selector_tool_key(self, tool: dict | None) -> str:
        if not isinstance(tool, dict):
            return ""
        tool_uid = tool.get("tool_uid", tool.get("uid"))
        if tool_uid is not None and str(tool_uid).strip():
            return f"uid:{tool_uid}"
        tool_id = str(tool.get("tool_id") or tool.get("id") or "").strip()
        return f"id:{tool_id}" if tool_id else ""

    def normalize_selector_tool(self, tool: dict | None) -> dict | None:
        if not isinstance(tool, dict):
            return None
        tool_id = str(tool.get("tool_id") or tool.get("id") or "").strip()
        if not tool_id:
            return None
        normalized = {"tool_id": tool_id}
        tool_uid = tool.get("tool_uid", tool.get("uid"))
        try:
            parsed_uid = int(tool_uid) if tool_uid is not None and str(tool_uid).strip() else None
        except Exception:
            parsed_uid = None
        if parsed_uid is not None:
            normalized["tool_uid"] = parsed_uid
        for key in ("description", "tool_type", "default_pot"):
            value = str(tool.get(key) or "").strip()
            if value:
                normalized[key] = value
        comment = str(tool.get("comment") or "").strip()
        if comment:
            normalized["comment"] = comment
        return normalized

    def selector_target_key(self, head: str, spindle: str) -> str:
        return f"{self._normalize_head(head)}:{normalize_selector_spindle(spindle)}"

    def current_target_key(self, head: str, spindle: str) -> str:
        return self.selector_target_key(head, spindle)

    def store_bucket_for_target(
        self,
        assignments_by_target: dict[str, list[dict]],
        assigned_tools: list[dict],
        *,
        head: str,
        spindle: str,
    ) -> None:
        key = self.current_target_key(head, spindle)
        assignments_by_target[key] = [dict(item) for item in assigned_tools]

    def load_bucket_for_target(
        self,
        assignments_by_target: dict[str, list[dict]],
        *,
        head: str,
        spindle: str,
    ) -> list[dict]:
        return selector_assignments_for_target(
            assignments_by_target,
            self.current_target_key(head, spindle),
        )

    def apply_dropped_tools(
        self,
        assigned_tools: list[dict],
        dropped_items: list,
        insert_row: int,
    ) -> tuple[list[dict], int | None]:
        if not isinstance(dropped_items, list):
            return list(assigned_tools), None

        updated = list(assigned_tools)
        existing_keys = {
            self.selector_tool_key(item)
            for item in updated
            if self.selector_tool_key(item)
        }
        insert_at = insert_row if isinstance(insert_row, int) and insert_row >= 0 else len(updated)
        insert_at = min(insert_at, len(updated))
        added = False
        for tool in dropped_items:
            normalized = self.normalize_selector_tool(tool)
            if normalized is None:
                continue
            key = self.selector_tool_key(normalized)
            if not key or key in existing_keys:
                continue
            updated.insert(insert_at, normalized)
            existing_keys.add(key)
            insert_at += 1
            added = True

        if not added:
            return updated, None
        return updated, min(insert_at - 1, len(updated) - 1)

    def remove_assignments_by_keys(
        self,
        assigned_tools: list[dict],
        tool_keys: list[tuple[str, str | None]],
    ) -> list[dict]:
        if not tool_keys:
            return list(assigned_tools)
        target_counts: dict[tuple[str, str | None], int] = {}
        for key in tool_keys:
            target_counts[key] = target_counts.get(key, 0) + 1
        remaining: list[dict] = []
        for assignment in assigned_tools:
            tool_id = str(assignment.get("tool_id") or "").strip()
            tool_uid_raw = assignment.get("tool_uid")
            tool_uid = str(tool_uid_raw).strip() if tool_uid_raw is not None and str(tool_uid_raw).strip() else None
            key = (tool_id, tool_uid)
            if tool_id and target_counts.get(key, 0) > 0:
                target_counts[key] -= 1
                continue
            remaining.append(assignment)
        return remaining

    def prepare_context(
        self,
        *,
        head: str,
        spindle: str,
        initial_assignments: list[dict] | None = None,
        initial_assignment_buckets: dict[str, list[dict]] | None = None,
    ) -> PreparedSelectorAssignmentContext:
        normalized_head = self._normalize_head(head)
        normalized_spindle = normalize_selector_spindle(spindle)
        loaded_buckets = selector_bucket_map(
            initial_assignment_buckets,
            self.normalize_selector_tool,
            self.selector_tool_key,
            self.selector_target_key,
        )
        if not loaded_buckets and isinstance(initial_assignments, list):
            current_target = self.current_target_key(normalized_head, normalized_spindle)
            # Preserve the legacy fallback: older callers may only pass a flat list.
            loaded_buckets[current_target] = normalize_selector_bucket(
                initial_assignments,
                self.normalize_selector_tool,
                self.selector_tool_key,
            )
        assignments = self.load_bucket_for_target(
            loaded_buckets,
            head=normalized_head,
            spindle=normalized_spindle,
        )
        return PreparedSelectorAssignmentContext(
            head=normalized_head,
            spindle=normalized_spindle,
            assignments=assignments,
            buckets=loaded_buckets,
        )

    def setup_assignment_payload(
        self,
        assignments_by_target: dict[str, list[dict]],
        *,
        head: str,
    ) -> list[dict]:
        normalized_head = self._normalize_head(head)
        payload: list[dict] = []
        for key, tools in assignments_by_target.items():
            parts = key.split(":", 1)
            bucket_head = self._normalize_head(parts[0]) if parts else normalized_head
            bucket_spindle = normalize_selector_spindle(parts[1]) if len(parts) > 1 else "main"
            if bucket_head != normalized_head:
                continue
            for item in tools:
                entry = dict(item)
                entry["spindle"] = bucket_spindle
                entry["head"] = normalized_head
                payload.append(entry)
        return payload

    def setup_assignment_buckets(
        self,
        assignments_by_target: dict[str, list[dict]],
        *,
        head: str,
    ) -> dict[str, list[dict]]:
        normalized_head = self._normalize_head(head)
        result: dict[str, list[dict]] = {}
        for key, tools in assignments_by_target.items():
            parts = key.split(":", 1)
            bucket_head = self._normalize_head(parts[0]) if parts else normalized_head
            bucket_spindle = normalize_selector_spindle(parts[1]) if len(parts) > 1 else "main"
            if bucket_head != normalized_head:
                continue
            normalized_tools: list[dict] = []
            for item in tools:
                entry = dict(item)
                entry["spindle"] = bucket_spindle
                entry["head"] = normalized_head
                normalized_tools.append(entry)
            result[key] = normalized_tools
        return result
