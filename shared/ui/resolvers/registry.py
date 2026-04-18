"""Process-wide resolver registry.

Per blueprint: one ToolResolver and one JawResolver per process. The
library-backed implementation is wired in at app startup (preload
manager) via `set_resolver`. Until then `get_resolver` raises so that
accidental early use surfaces immediately rather than silently falling
back to a stale local cache.
"""

from __future__ import annotations

from typing import Literal, overload

from .contracts import JawResolver, ToolResolver


_tool_resolver: ToolResolver | None = None
_jaw_resolver: JawResolver | None = None


class ResolverNotConfiguredError(RuntimeError):
    pass


@overload
def get_resolver(kind: Literal["tool"]) -> ToolResolver: ...
@overload
def get_resolver(kind: Literal["jaw"]) -> JawResolver: ...
def get_resolver(kind):
    if kind == "tool":
        if _tool_resolver is None:
            raise ResolverNotConfiguredError(
                "ToolResolver not configured. Call set_resolver('tool', ...) at startup."
            )
        return _tool_resolver
    if kind == "jaw":
        if _jaw_resolver is None:
            raise ResolverNotConfiguredError(
                "JawResolver not configured. Call set_resolver('jaw', ...) at startup."
            )
        return _jaw_resolver
    raise ValueError(f"unknown resolver kind: {kind!r}")


@overload
def set_resolver(kind: Literal["tool"], resolver: ToolResolver | None) -> None: ...
@overload
def set_resolver(kind: Literal["jaw"], resolver: JawResolver | None) -> None: ...
def set_resolver(kind, resolver):
    global _tool_resolver, _jaw_resolver
    if kind == "tool":
        if resolver is not None and not isinstance(resolver, ToolResolver):
            raise TypeError("resolver does not satisfy ToolResolver protocol")
        _tool_resolver = resolver
        return
    if kind == "jaw":
        if resolver is not None and not isinstance(resolver, JawResolver):
            raise TypeError("resolver does not satisfy JawResolver protocol")
        _jaw_resolver = resolver
        return
    raise ValueError(f"unknown resolver kind: {kind!r}")
