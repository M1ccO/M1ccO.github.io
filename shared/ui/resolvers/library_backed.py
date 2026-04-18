"""Library-backed resolver implementations.

Adapters around ToolService / JawService that satisfy ToolResolver /
JawResolver protocols. No direct DB access here; the library services
remain the only path into tool/jaw storage.

Cache is bounded (LRU-ish via OrderedDict) and keyed by
`(id, bucket_or_spindle, library_rev)` so stale entries cannot be
returned across library edits. Callers signal a library write by calling
`bump_revision()` on the resolver.
"""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from typing import Any, Mapping, Sequence

from shared.selector.payloads import SpindleKey, ToolBucket

from .contracts import ResolvedJaw, ResolvedTool


_CACHE_CAPACITY = 2048


def _lru_set(cache: OrderedDict, key, value) -> None:
    if key in cache:
        cache.move_to_end(key)
    cache[key] = value
    while len(cache) > _CACHE_CAPACITY:
        cache.popitem(last=False)


def _lru_get(cache: OrderedDict, key):
    if key not in cache:
        return None
    cache.move_to_end(key)
    return cache[key]


def _tool_display_name(record: Mapping[str, Any]) -> str:
    tool_id = str(record.get("id", "") or "").strip()
    description = str(record.get("description", "") or "").strip()
    if tool_id and description:
        return f"{tool_id} — {description}"
    return tool_id or description or "(unknown tool)"


def _tool_icon_key(record: Mapping[str, Any]) -> str:
    tool_type = str(record.get("tool_type", "") or "").strip().lower() or "tool"
    return f"tool/{tool_type}"


def _jaw_display_name(record: Mapping[str, Any]) -> str:
    jaw_id = str(record.get("jaw_id", "") or "").strip()
    jaw_type = str(record.get("jaw_type", "") or "").strip()
    if jaw_id and jaw_type:
        return f"{jaw_id} ({jaw_type})"
    return jaw_id or jaw_type or "(unknown jaw)"


def _jaw_icon_key(record: Mapping[str, Any]) -> str:
    jaw_type = str(record.get("jaw_type", "") or "").strip().lower().replace(" ", "_") or "jaw"
    return f"jaw/{jaw_type}"


def _coerce_pot_number(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class LibraryBackedToolResolver:
    """ToolResolver adapter backed by a ToolService instance."""

    def __init__(self, tool_service: Any):
        if tool_service is None:
            raise ValueError("tool_service is required")
        self._service = tool_service
        self._rev = 0
        self._cache: OrderedDict[tuple[str, str, int], ResolvedTool | None] = OrderedDict()
        self._lock = RLock()

    @property
    def library_rev(self) -> int:
        return self._rev

    def bump_revision(self) -> None:
        with self._lock:
            self._rev += 1
            self._cache.clear()

    def invalidate_tool(self, tool_id: str) -> int:
        """Drop cached entries for one tool_id across every bucket.

        Returns the number of cache entries removed. Does not bump the
        global revision — callers that prefer coarse invalidation should
        use `bump_revision` instead.
        """
        if not isinstance(tool_id, str) or not tool_id:
            return 0
        with self._lock:
            victims = [key for key in self._cache if key[0] == tool_id]
            for key in victims:
                self._cache.pop(key, None)
            return len(victims)

    def resolve_tool(self, tool_id: str, *, bucket: ToolBucket) -> ResolvedTool | None:
        if not isinstance(tool_id, str) or not tool_id:
            return None
        if not isinstance(bucket, ToolBucket):
            raise TypeError("bucket must be ToolBucket")
        key = (tool_id, bucket.value, self._rev)
        with self._lock:
            cached = _lru_get(self._cache, key)
            if cached is not None or key in self._cache:
                return cached
        record = self._service.get_tool(tool_id)
        resolved: ResolvedTool | None
        if record is None:
            resolved = None
        else:
            resolved = ResolvedTool(
                tool_id=tool_id,
                display_name=_tool_display_name(record),
                icon_key=_tool_icon_key(record),
                pot_number=_coerce_pot_number(record.get("pot_number")),
                metadata=dict(record),
                library_rev=self._rev,
            )
        with self._lock:
            _lru_set(self._cache, key, resolved)
        return resolved

    def resolve_many(
        self, tool_ids: Sequence[str], *, bucket: ToolBucket
    ) -> Mapping[str, ResolvedTool]:
        result: dict[str, ResolvedTool] = {}
        for tid in tool_ids:
            resolved = self.resolve_tool(tid, bucket=bucket)
            if resolved is not None:
                result[tid] = resolved
        return result


class LibraryBackedJawResolver:
    """JawResolver adapter backed by a JawService instance."""

    def __init__(self, jaw_service: Any):
        if jaw_service is None:
            raise ValueError("jaw_service is required")
        self._service = jaw_service
        self._rev = 0
        self._cache: OrderedDict[tuple[str, str, int], ResolvedJaw | None] = OrderedDict()
        self._lock = RLock()

    @property
    def library_rev(self) -> int:
        return self._rev

    def bump_revision(self) -> None:
        with self._lock:
            self._rev += 1
            self._cache.clear()

    def invalidate_jaw(self, jaw_id: str) -> int:
        """Drop cached entries for one jaw_id across every spindle."""
        if not isinstance(jaw_id, str) or not jaw_id:
            return 0
        with self._lock:
            victims = [key for key in self._cache if key[0] == jaw_id]
            for key in victims:
                self._cache.pop(key, None)
            return len(victims)

    def resolve_jaw(self, jaw_id: str, *, spindle: SpindleKey) -> ResolvedJaw | None:
        if not isinstance(jaw_id, str) or not jaw_id:
            return None
        if not isinstance(spindle, SpindleKey):
            raise TypeError("spindle must be SpindleKey")
        key = (jaw_id, spindle.value, self._rev)
        with self._lock:
            cached = _lru_get(self._cache, key)
            if cached is not None or key in self._cache:
                return cached
        record = self._service.get_jaw(jaw_id)
        resolved: ResolvedJaw | None
        if record is None:
            resolved = None
        else:
            resolved = ResolvedJaw(
                jaw_id=jaw_id,
                display_name=_jaw_display_name(record),
                icon_key=_jaw_icon_key(record),
                spindle=spindle,
                metadata=dict(record),
                library_rev=self._rev,
            )
        with self._lock:
            _lru_set(self._cache, key, resolved)
        return resolved
