"""Resolver contract for tool/jaw display data.

Defined by WORK_EDITOR_SELECTOR_ARCHITECTURE_BLUEPRINT.md (RESOLVER CONTRACT).

Work Editor, Selector, and Setup Card all obtain display-ready metadata
through this contract. No caller reads library DB directly for display.

Resolved* types are frozen; callers may not mutate. Returned `None` for
unknown IDs means caller must render placeholder, never crash.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from shared.selector.payloads import SpindleKey, ToolBucket


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if value is None:
        return MappingProxyType({})
    if isinstance(value, MappingProxyType):
        return value
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class ResolvedTool:
    tool_id: str
    display_name: str
    icon_key: str
    pot_number: int | None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    library_rev: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True)
class ResolvedJaw:
    jaw_id: str
    display_name: str
    icon_key: str
    spindle: SpindleKey
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    library_rev: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@runtime_checkable
class ToolResolver(Protocol):
    def resolve_tool(
        self, tool_id: str, *, bucket: ToolBucket
    ) -> ResolvedTool | None: ...

    def resolve_many(
        self, tool_ids: Sequence[str], *, bucket: ToolBucket
    ) -> Mapping[str, ResolvedTool]: ...

    @property
    def library_rev(self) -> int: ...


@runtime_checkable
class JawResolver(Protocol):
    def resolve_jaw(
        self, jaw_id: str, *, spindle: SpindleKey
    ) -> ResolvedJaw | None: ...

    @property
    def library_rev(self) -> int: ...
