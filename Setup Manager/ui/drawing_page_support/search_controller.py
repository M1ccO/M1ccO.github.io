"""Search controller helpers for DrawingPage — find/highlight logic."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPointF, QRectF
from PySide6.QtPdf import QPdfDocument, QPdfSearchModel


def reapply_search_text(page) -> None:
    page._search_model.setSearchString(page.find_input.text().strip())
    on_search_model_changed(page)


def focus_first_search_result(page) -> None:
    page.find_input.setFocus()
    if page._pdf_document.status() != QPdfDocument.Status.Ready:
        return
    if page._search_model.rowCount(QModelIndex()) <= 0:
        return
    page.pdf_view.setCurrentSearchResultIndex(0)
    focus_search_result(page, 0)


def on_find_text_changed(page, text: str) -> None:
    page._search_model.setSearchString((text or "").strip())
    on_search_model_changed(page)


def on_search_model_changed(page) -> None:
    if page._pdf_document.status() != QPdfDocument.Status.Ready:
        update_search_status(page)
        return
    search_text = page.find_input.text().strip()
    result_count = page._search_model.rowCount(QModelIndex())
    if search_text and result_count > 0 and page.pdf_view.currentSearchResultIndex() < 0:
        page.pdf_view.setCurrentSearchResultIndex(0)
        focus_search_result(page, 0)
    elif not search_text:
        page.pdf_view.setCurrentSearchResultIndex(-1)
    refresh_search_overlay(page)
    update_search_status(page)


def step_search_result(page, delta: int) -> None:
    if page._pdf_document.status() != QPdfDocument.Status.Ready:
        return
    count = page._search_model.rowCount(QModelIndex())
    if count <= 0:
        return
    current = int(page.pdf_view.currentSearchResultIndex())
    if current < 0:
        current = 0 if delta >= 0 else count - 1
    else:
        current = max(0, min(count - 1, current + int(delta)))
    page.pdf_view.setCurrentSearchResultIndex(current)
    focus_search_result(page, current)
    update_search_status(page)


def refresh_search_overlay(page) -> None:
    overlay = page.pdf_view._overlay
    count = page._search_model.rowCount(QModelIndex())
    if count <= 0 or not page.find_input.text().strip():
        overlay.clear_search_rects()
        return
    page_rects: list[tuple[int, QRectF]] = []
    for i in range(count):
        idx = page._search_model.index(i, 0, QModelIndex())
        if not idx.isValid():
            continue
        page_data = idx.data(QPdfSearchModel.Role.Page.value)
        rect_data = idx.data(QPdfSearchModel.Role.Location.value)
        try:
            pg = int(page_data)
        except (TypeError, ValueError):
            continue
        if rect_data is not None:
            try:
                page_rects.append((pg, QRectF(rect_data)))
            except Exception:
                pass
    overlay.set_search_rects(page_rects)


def focus_search_result(page, result_index: int) -> None:
    if page._pdf_document.status() != QPdfDocument.Status.Ready:
        return
    if result_index < 0 or result_index >= page._search_model.rowCount(QModelIndex()):
        return
    model_index = page._search_model.index(result_index, 0, QModelIndex())
    if not model_index.isValid():
        return

    page_data = model_index.data(QPdfSearchModel.Role.Page.value)
    location_data = model_index.data(QPdfSearchModel.Role.Location.value)
    try:
        pg = int(page_data)
    except (TypeError, ValueError):
        return

    if isinstance(location_data, QPointF):
        location = QPointF(float(location_data.x()), float(location_data.y()))
    else:
        location = QPointF(0.0, 0.0)

    page.pdf_view.pageNavigator().jump(pg, location, 0)
    page.pdf_view.viewport().update()


def update_search_status(page, *_args) -> None:
    ready = page._pdf_document.status() == QPdfDocument.Status.Ready
    search_text = page.find_input.text().strip()
    result_count = page._search_model.rowCount(QModelIndex()) if ready else 0
    current = int(page.pdf_view.currentSearchResultIndex()) if ready else -1

    page.find_input.setEnabled(ready)
    if not ready or not search_text:
        page.prev_hit_btn.setEnabled(False)
        page.next_hit_btn.setEnabled(False)
        page.search_result_label.setText("")
        page.search_status.setText(page._t("drawing_page.find.status.idle", "Text search"))
        return

    if result_count <= 0:
        page.prev_hit_btn.setEnabled(False)
        page.next_hit_btn.setEnabled(False)
        page.search_result_label.setText(page._t("drawing_page.find.status.none", "0 matches"))
        page.search_status.setText(page._t("drawing_page.find.status.none", "0 matches"))
        return

    display_index = max(0, current) + 1
    status_text = page._t(
        "drawing_page.find.status.ready",
        "{current} / {total}",
        current=display_index,
        total=result_count,
    )
    page.search_result_label.setText(status_text)
    page.search_status.setText(status_text)
    page.prev_hit_btn.setEnabled(current > 0)
    page.next_hit_btn.setEnabled(current < result_count - 1)


__all__ = [
    "focus_first_search_result",
    "focus_search_result",
    "on_find_text_changed",
    "on_search_model_changed",
    "reapply_search_text",
    "refresh_search_overlay",
    "step_search_result",
    "update_search_status",
]
