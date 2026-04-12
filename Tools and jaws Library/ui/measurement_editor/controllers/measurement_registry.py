"""Pure list-management helpers for measurement registry orchestration."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem


def measurement_kind_order() -> tuple[str, ...]:
    """Return the canonical display order for measurement kinds."""
    return ('length', 'diameter', 'radius', 'angle')


def find_item_by_uid(
    src_list: QListWidget,
    uid: str,
) -> tuple[int, QListWidgetItem | None]:
    """Search *src_list* for an item whose UserRole data contains ``_uid == uid``.

    Returns ``(row_index, item)`` on match or ``(-1, None)`` when not found.
    """
    uid_str = str(uid or '').strip()
    if not uid_str:
        return -1, None
    for row in range(src_list.count()):
        item = src_list.item(row)
        data = dict(item.data(Qt.UserRole) or {})
        if str(data.get('_uid') or '').strip() == uid_str:
            return row, item
    return -1, None


__all__ = ["measurement_kind_order", "find_item_by_uid"]
