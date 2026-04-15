"""Lightweight profile view shared between Setup Manager and Tools Library.

Setup Manager can produce a ToolLibProfileView from a full MachineProfile.
Tools Library consumes it in place of an ad-hoc profile dict.

Only the fields actually consumed by the Tools Library are included here.
Adding a field to this file is the single required change when the library
needs a new piece of profile data.
"""

from __future__ import annotations

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
    heads: tuple[HeadView, ...] = (
        HeadView("HEAD1", "tool_library.head_filter.head1", "HEAD1"),
        HeadView("HEAD2", "tool_library.head_filter.head2", "HEAD2"),
    )

    def is_machining_center(self) -> bool:
        return self.machine_type == "machining_center"

    def head_keys(self) -> list[str]:
        return [head.key for head in self.heads]


_DEFAULT_HEADS: tuple[HeadView, ...] = (
    HeadView("HEAD1", "tool_library.head_filter.head1", "HEAD1"),
    HeadView("HEAD2", "tool_library.head_filter.head2", "HEAD2"),
)


def profile_view_from_key(raw_key: str | None) -> ToolLibProfileView:
    """Build a ToolLibProfileView from a raw profile key string.

    The Tools Library keeps process boundaries and does not depend on
    Setup Manager registry modules.
    The only semantic encoded here is the stable key-prefix contract:
    machining-center keys begin with 'machining_center'.
    """

    key = str(raw_key or "").strip().lower() or "ntx_2sp_2h"
    is_machining_center = key.startswith("machining_center")
    return ToolLibProfileView(
        key=key,
        machine_type="machining_center" if is_machining_center else "lathe",
        heads=_DEFAULT_HEADS,
    )
