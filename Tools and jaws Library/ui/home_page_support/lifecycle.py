from __future__ import annotations

from PySide6.QtCore import QTimer


def schedule_initial_load(page) -> None:
    if page._initial_load_done or page._initial_load_scheduled:
        return
    page._initial_load_scheduled = True
    QTimer.singleShot(0, page._perform_initial_load)


def perform_initial_load(page) -> None:
    page._initial_load_scheduled = False
    if page._initial_load_done or not page.isVisible():
        return
    page._initial_load_done = True
    page._deferred_refresh_needed = False
    page.refresh_catalog()


def on_show_event(page) -> None:
    if not page._initial_load_done:
        schedule_initial_load(page)
        return
    if page._deferred_refresh_needed:
        page._deferred_refresh_needed = False
        QTimer.singleShot(0, page.refresh_catalog)


def refresh_guard(page) -> bool:
    if page._initial_load_done or page.isVisible():
        return True
    page._deferred_refresh_needed = True
    return False


def before_refresh_catalog(page) -> None:
    page._initial_load_done = True
    page._deferred_refresh_needed = False
