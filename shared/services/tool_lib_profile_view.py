"""Lightweight profile view shared between Setup Manager and Tools Library.

Setup Manager can produce a ToolLibProfileView from a full MachineProfile.
Tools Library consumes it in place of an ad-hoc profile dict.

Only the fields actually consumed by the Tools Library are included here.
Adding a field to this file is the single required change when the library
needs a new piece of profile data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class HeadView:
    """One head entry as seen by the Tools Library UI."""

    key: str
    label_i18n_key: str
    label_default: str


@dataclass(frozen=True)
class ToolLibProfileView:
    key: str = "ntx_2sp_2h"
    machine_type: str = "lathe"
    spindle_keys: tuple[str, ...] = ("main", "sub")
    default_tools_spindle: str = "main"
    use_op_terminology: bool = False
    heads: tuple[HeadView, ...] = (
        HeadView("HEAD1", "tool_library.head_filter.head1", "HEAD1"),
        HeadView("HEAD2", "tool_library.head_filter.head2", "HEAD2"),
    )

    def is_machining_center(self) -> bool:
        return self.machine_type == "machining_center"

    def head_keys(self) -> list[str]:
        return [head.key for head in self.heads]

    def spindle_count(self) -> int:
        return len(self.spindle_keys)

    def has_multiple_spindles(self) -> bool:
        return self.spindle_count() > 1

    def has_multiple_heads(self) -> bool:
        return len(self.heads) > 1


_DEFAULT_HEADS: tuple[HeadView, ...] = (
    HeadView("HEAD1", "tool_library.head_filter.head1", "HEAD1"),
    HeadView("HEAD2", "tool_library.head_filter.head2", "HEAD2"),
    HeadView("HEAD3", "tool_library.head_filter.head3", "HEAD3"),
)


def _extract_int_group(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _infer_spindle_count(key: str, is_machining_center: bool) -> int:
    if is_machining_center:
        return 1
    parsed = _extract_int_group(r"(\d+)sp", key)
    if parsed in {1, 2}:
        return parsed
    return 2


def _infer_head_count(key: str, is_machining_center: bool) -> int:
    if is_machining_center:
        return 1
    parsed_h = _extract_int_group(r"(\d+)h", key)
    if parsed_h is not None and parsed_h > 0:
        return parsed_h
    parsed_mill = _extract_int_group(r"(\d+)mill", key)
    if parsed_mill is not None and parsed_mill > 0:
        return parsed_mill
    return 2


def _build_heads(count: int) -> tuple[HeadView, ...]:
    if count <= 0:
        return (HeadView("HEAD1", "tool_library.head_filter.head1", "HEAD1"),)
    if count <= len(_DEFAULT_HEADS):
        return tuple(_DEFAULT_HEADS[:count])
    generated = list(_DEFAULT_HEADS)
    for idx in range(len(_DEFAULT_HEADS) + 1, count + 1):
        generated.append(
            HeadView(
                f"HEAD{idx}",
                f"tool_library.head_filter.head{idx}",
                f"HEAD{idx}",
            )
        )
    return tuple(generated)


def profile_view_from_key(raw_key: str | None) -> ToolLibProfileView:
    """Build a ToolLibProfileView from a raw profile key string.

    The Tools Library keeps process boundaries and does not depend on
    Setup Manager registry modules.
    The only semantic encoded here is the stable key-prefix contract:
    machining-center keys begin with 'machining_center'.
    """

    key = str(raw_key or "").strip().lower() or "ntx_2sp_2h"
    is_machining_center = key.startswith("machining_center")
    spindle_count = _infer_spindle_count(key, is_machining_center)
    head_count = _infer_head_count(key, is_machining_center)
    use_op_terminology = bool(is_machining_center or spindle_count == 1)
    return ToolLibProfileView(
        key=key,
        machine_type="machining_center" if is_machining_center else "lathe",
        spindle_keys=("main", "sub") if spindle_count > 1 else ("main",),
        default_tools_spindle="main",
        use_op_terminology=use_op_terminology,
        heads=_build_heads(head_count),
    )
