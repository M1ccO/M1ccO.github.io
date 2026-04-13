"""Link/open actions for HomePage detail interactions."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

__all__ = ["part_clicked"]


def part_clicked(page, part: dict) -> None:
    """Open external URL for a part row, with user-friendly error handling."""
    if not isinstance(part, dict):
        return
    link = str(part.get('link') or '').strip()
    name = str(part.get('name') or part.get('label') or page._t('tool_library.field.part', 'Part')).strip()
    if not link:
        QMessageBox.information(
            page,
            page._t('tool_library.part.missing_link_title', 'Link missing'),
            page._t('tool_library.part.no_link', 'No link set for: {name}', name=name),
        )
        return
    if not QDesktopServices.openUrl(QUrl(link)):
        QMessageBox.warning(
            page,
            page._t('tool_library.part.open_failed_title', 'Open failed'),
            page._t('tool_library.part.open_failed', 'Could not open link: {link}', link=link),
        )
