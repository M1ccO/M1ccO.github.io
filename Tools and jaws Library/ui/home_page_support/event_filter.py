"""Event filter handler for HomePage.

Extracted from home_page.py (Phase 10 Pass 1).
The single public function handle_home_page_event() replaces the inline
eventFilter logic in home_page.py, keeping that file focused on orchestration.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtGui import QFontMetrics
from PySide6.QtCore import Qt
from shiboken6 import isValid

__all__ = ["handle_home_page_event", "refresh_elided_group_title"]


def _alive(widget) -> bool:
    """Return True when a Qt widget still has a valid C++ backing object."""
    return widget is not None and isValid(widget)


def _safe_viewport(widget):
    """Return viewport if widget is valid; otherwise None."""
    if not _alive(widget):
        return None
    try:
        viewport = widget.viewport()
    except RuntimeError:
        return None
    return viewport if _alive(viewport) else None


def handle_home_page_event(page, obj, event) -> bool:
    """Handle Qt events for HomePage.

    Returns True if the event was consumed, False to continue default handling.
    Called from HomePage.eventFilter(); the caller falls through to
    super().eventFilter() when this returns False.
    """
    event_type = event.type() if event is not None else None

    # Double-click on list → open details
    list_view = getattr(page, 'list_view', None)
    list_view_viewport = _safe_viewport(list_view)
    if event_type == QEvent.MouseButtonDblClick and _alive(list_view):
        if obj in {list_view, list_view_viewport}:
            pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            index = list_view.indexAt(pos)
            if index.isValid():
                page.on_item_double_clicked(index)
                return True

    # Elided group title refresh on resize/show
    if event_type in {QEvent.Resize, QEvent.Show, QEvent.LayoutRequest}:
        if hasattr(obj, 'property') and bool(obj.property('elideGroupTitle')):
            refresh_elided_group_title(obj)

    return False


def refresh_elided_group_title(group_widget) -> None:
    """Elide a QGroupBox title to fit its current width."""
    if group_widget is None or not hasattr(group_widget, 'property'):
        return
    full_title = str(
        group_widget.property('fullGroupTitle') or group_widget.title() or ''
    ).strip()
    if not full_title:
        return
    width = max(36, int(group_widget.width()) - 18)
    metrics = QFontMetrics(group_widget.font())
    group_widget.setTitle(metrics.elidedText(full_title, Qt.ElideRight, width))
