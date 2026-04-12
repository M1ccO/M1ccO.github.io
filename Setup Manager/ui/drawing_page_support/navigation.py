"""Navigation helpers for DrawingPage — page/zoom controls."""

from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView


def update_page_status(page, *_args) -> None:
    total_pages = int(page._pdf_document.pageCount() or 0)
    current_page = int(page.pdf_view.pageNavigator().currentPage() or 0) + 1 if total_pages else 0
    if total_pages:
        page.page_status.setText(
            page._t(
                "drawing_page.page_status.ready",
                "Page {current} / {total}",
                current=current_page,
                total=total_pages,
            )
        )
    else:
        page.page_status.setText(page._t("drawing_page.page_status.empty", "Page - / -"))

    ready = page._pdf_document.status() == QPdfDocument.Status.Ready and total_pages > 0
    page.prev_page_btn.setEnabled(ready and current_page > 1)
    page.next_page_btn.setEnabled(ready and current_page < total_pages)


def effective_zoom_factor(page) -> float:
    try:
        if page.pdf_view.zoomMode() == QPdfView.ZoomMode.Custom:
            factor = float(page.pdf_view.zoomFactor())
            return factor if factor > 0 else 1.0
    except Exception:
        pass
    navigator = page.pdf_view.pageNavigator()
    try:
        zoom = float(navigator.currentZoom())
    except Exception:
        zoom = 0.0
    if zoom > 0:
        return zoom
    try:
        factor = float(page.pdf_view.zoomFactor())
    except Exception:
        factor = 1.0
    return factor if factor > 0 else 1.0


def update_zoom_status(page, *_args) -> None:
    ready = page._pdf_document.status() == QPdfDocument.Status.Ready
    if not ready:
        page.zoom_status.setText("-%")
    else:
        page.zoom_status.setText(f"{round(effective_zoom_factor(page) * 100)}%")

    page.zoom_out_btn.setEnabled(ready)
    page.zoom_in_btn.setEnabled(ready)
    page.fit_width_btn.setEnabled(ready)
    page.fit_page_btn.setEnabled(ready)


def fit_width(page) -> None:
    if page._pdf_document.status() != QPdfDocument.Status.Ready:
        return
    page.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
    update_zoom_status(page)


def fit_page(page) -> None:
    if page._pdf_document.status() != QPdfDocument.Status.Ready:
        return
    page.pdf_view.setZoomMode(QPdfView.ZoomMode.FitInView)
    update_zoom_status(page)


def step_zoom(page, multiplier: float) -> None:
    if page._pdf_document.status() != QPdfDocument.Status.Ready:
        return
    new_zoom = max(0.1, min(8.0, effective_zoom_factor(page) * float(multiplier)))
    page.pdf_view.set_custom_zoom(new_zoom, page.pdf_view.viewport().rect().center())
    update_zoom_status(page)


def jump_page(page, delta: int) -> None:
    if page._pdf_document.status() != QPdfDocument.Status.Ready:
        return
    current_page = int(page.pdf_view.pageNavigator().currentPage() or 0)
    go_to_page(page, current_page + int(delta))


def go_to_page(page, page_index: int) -> None:
    total_pages = int(page._pdf_document.pageCount() or 0)
    if total_pages <= 0:
        return
    page_index = max(0, min(int(page_index), total_pages - 1))
    page.pdf_view.pageNavigator().jump(page_index, QPointF(0.0, 0.0), 0)
    update_page_status(page)


__all__ = [
    "effective_zoom_factor",
    "fit_page",
    "fit_width",
    "go_to_page",
    "jump_page",
    "step_zoom",
    "update_page_status",
    "update_zoom_status",
]
