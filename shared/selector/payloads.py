"""Normalized selector payload schema.

Defined by WORK_EDITOR_SELECTOR_ARCHITECTURE_BLUEPRINT.md (PAYLOAD SCHEMA).
These are the only types selector sessions may return. Pure data: no Qt
types, no mutation, picklable for logging and replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4


class ToolBucket(str, Enum):
    MAIN = "main"
    SUB = "sub"
    UPPER = "upper"
    LOWER = "lower"


class SpindleKey(str, Enum):
    MAIN = "main"
    SUB = "sub"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ToolSelectionPayload:
    bucket: ToolBucket
    head_key: str
    tool_id: str
    source_library_rev: int
    selected_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not isinstance(self.bucket, ToolBucket):
            raise TypeError(f"bucket must be ToolBucket, got {type(self.bucket).__name__}")
        if not isinstance(self.head_key, str) or not self.head_key:
            raise ValueError("head_key must be non-empty str")
        if not isinstance(self.tool_id, str) or not self.tool_id:
            raise ValueError("tool_id must be non-empty str")
        if not isinstance(self.source_library_rev, int) or self.source_library_rev < 0:
            raise ValueError("source_library_rev must be non-negative int")


@dataclass(frozen=True)
class JawSelectionPayload:
    spindle: SpindleKey
    jaw_id: str
    source_library_rev: int
    selected_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not isinstance(self.spindle, SpindleKey):
            raise TypeError(f"spindle must be SpindleKey, got {type(self.spindle).__name__}")
        if not isinstance(self.jaw_id, str) or not self.jaw_id:
            raise ValueError("jaw_id must be non-empty str")
        if not isinstance(self.source_library_rev, int) or self.source_library_rev < 0:
            raise ValueError("source_library_rev must be non-negative int")


@dataclass(frozen=True)
class SelectionBatch:
    """All selections emitted by one selector session on OK.

    Cancel produces no batch. Empty batch (both tuples empty) is legal if
    session OKs with no changes.
    """

    session_id: UUID = field(default_factory=uuid4)
    tools: tuple[ToolSelectionPayload, ...] = ()
    jaws: tuple[JawSelectionPayload, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, UUID):
            raise TypeError("session_id must be UUID")
        if not isinstance(self.tools, tuple):
            raise TypeError("tools must be tuple (for immutability)")
        if not isinstance(self.jaws, tuple):
            raise TypeError("jaws must be tuple (for immutability)")
        for t in self.tools:
            if not isinstance(t, ToolSelectionPayload):
                raise TypeError("tools entries must be ToolSelectionPayload")
        for j in self.jaws:
            if not isinstance(j, JawSelectionPayload):
                raise TypeError("jaws entries must be JawSelectionPayload")

    @property
    def is_empty(self) -> bool:
        return not self.tools and not self.jaws
