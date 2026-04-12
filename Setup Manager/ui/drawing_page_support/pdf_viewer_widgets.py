"""
Drawing page support – self-contained PDF viewer widgets.

Extracted from drawing_page.py for responsibility separation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QActionGroup, QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.icon_helpers import toolbar_icon as _toolbar_icon_impl, toolbar_icon_with_svg_render_fallback as _toolbar_icon_with_svg_render_fallback
from ui.widgets.common import repolish_widget


def _toolbar_icon(name: str) -> QIcon:
    return _toolbar_icon_impl(name, png_first=False)


# ---------------------------------------------------------------------------
# PDF overlay / viewer widgets
# ---------------------------------------------------------------------------

@dataclass
class _TextHighlight:
    page: int
    pdf_rects: list[QRectF]  # coordinates in PDF point space — stable across zoom changes
    color: QColor


class _MarkerOverlay(QWidget):
    def __init__(self, pdf_view, parent=None):
        super().__init__(parent)
        self._pdf_view = pdf_view
        self._highlights: list[_TextHighlight] = []
        self._highlights_visible = True
        self._preview_rects: list[QRectF] = []   # content-px space; cleared after each gesture
        self._preview_color: QColor = QColor("#9fc7ee")
        self._search_rects: list[tuple[int, QRectF]] = []   # (page, pdf-point rect) for search hits
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.resize_to_viewport()
        self.show()

    def resize_to_viewport(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(parent.rect())
        self.raise_()

    def has_strokes(self) -> bool:
        return bool(self._highlights)

    def strokes_visible(self) -> bool:
        return self._highlights_visible

    def set_strokes_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if self._highlights_visible == visible:
            return
        self._highlights_visible = visible
        self.update()

    def clear_strokes(self) -> None:
        if not self._highlights and not self._preview_rects:
            return
        self._highlights.clear()
        self._preview_rects.clear()
        self.update()

    def set_preview_rects(self, rects: list[QRectF], color: QColor | None = None) -> None:
        self._preview_rects = [QRectF(r) for r in (rects or [])]
        if color is not None:
            self._preview_color = QColor(color)
        self.update()

    def clear_preview(self) -> None:
        if not self._preview_rects:
            return
        self._preview_rects.clear()
        self.update()

    def set_search_rects(self, page_rects: list[tuple[int, QRectF]]) -> None:
        self._search_rects = list(page_rects or [])
        self.update()

    def clear_search_rects(self) -> None:
        if not self._search_rects:
            return
        self._search_rects.clear()
        self.update()

    def add_highlight(self, page: int, pdf_rects: list[QRectF], color: QColor) -> None:
        if not pdf_rects:
            return
        self._highlights.append(_TextHighlight(int(page), [QRectF(r) for r in pdf_rects], QColor(color)))
        self.update()

    def _project_highlight_rects(self, highlight: _TextHighlight) -> list[QRectF]:
        """Project PDF-point rects to current viewport (screen) coordinates."""
        doc = self._pdf_view.document()
        if doc is None:
            return []
        scale = self._pdf_view._compute_actual_scale()
        margins = self._pdf_view.documentMargins()
        page_spacing = float(max(0, self._pdf_view.pageSpacing()))
        page_top = float(margins.top())
        for idx in range(highlight.page):
            page_top += float(doc.pagePointSize(idx).height()) * scale + page_spacing
        page_w = float(doc.pagePointSize(highlight.page).width()) * scale
        page_left = self._pdf_view._page_left_offset(page_w)
        scroll_x = float(self._pdf_view.horizontalScrollBar().value())
        scroll_y = float(self._pdf_view.verticalScrollBar().value())
        result = []
        for r in highlight.pdf_rects:
            result.append(QRectF(
                page_left + r.left() * scale - scroll_x,
                page_top + r.top() * scale - scroll_y,
                max(1.0, r.width() * scale),
                max(1.0, r.height() * scale),
            ))
        return result

    def _project_pdf_rect(self, page: int, pdf_rect: QRectF) -> QRectF | None:
        doc = self._pdf_view.document()
        if doc is None:
            return None
        scale = self._pdf_view._compute_actual_scale()
        margins = self._pdf_view.documentMargins()
        page_spacing = float(max(0, self._pdf_view.pageSpacing()))
        page_top = float(margins.top())
        for idx in range(page):
            page_top += float(doc.pagePointSize(idx).height()) * scale + page_spacing
        page_w = float(doc.pagePointSize(page).width()) * scale
        page_left = self._pdf_view._page_left_offset(page_w)
        scroll_x = float(self._pdf_view.horizontalScrollBar().value())
        scroll_y = float(self._pdf_view.verticalScrollBar().value())
        return QRectF(
            page_left + pdf_rect.left() * scale - scroll_x,
            page_top + pdf_rect.top() * scale - scroll_y,
            max(1.0, pdf_rect.width() * scale),
            max(1.0, pdf_rect.height() * scale),
        )

    def paintEvent(self, event) -> None:
        del event
        has_visible_highlights = self._highlights_visible and bool(self._highlights)
        if not has_visible_highlights and not self._preview_rects and not self._search_rects:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        if self._search_rects:
            search_color = QColor("#ffd95c")
            search_color.setAlpha(140)
            painter.setBrush(search_color)
            pad = 3.0
            for page, pdf_rect in self._search_rects:
                vp = self._project_pdf_rect(page, pdf_rect)
                if vp is not None:
                    painter.drawRoundedRect(
                        QRectF(vp.left() - pad, vp.top() - pad, vp.width() + pad * 2, vp.height() + pad * 2),
                        3, 3,
                    )
        if self._highlights_visible:
            for highlight in self._highlights:
                painter.setBrush(highlight.color)
                for rect in self._project_highlight_rects(highlight):
                    painter.drawRoundedRect(rect, 2, 2)
        if self._preview_rects:
            painter.setBrush(self._preview_color)
            scroll_x = float(self._pdf_view.horizontalScrollBar().value())
            scroll_y = float(self._pdf_view.verticalScrollBar().value())
            pad = getattr(self, "_preview_pad", 0.0)
            for rect in self._preview_rects:
                painter.drawRoundedRect(
                    QRectF(
                        rect.left() - scroll_x - pad,
                        rect.top() - scroll_y - pad,
                        rect.width() + pad * 2,
                        rect.height() + pad * 2,
                    ),
                    3, 3,
                )


class InteractivePdfView(QPdfView):
    toolChanged = Signal(str)
    markupsChanged = Signal(bool)
    markupsVisibilityChanged = Signal(bool)

    TOOL_SELECT = "select"
    TOOL_HAND = "hand"
    TOOL_MARKER = "marker"

    _COLOR_OPTIONS = {
        "yellow": QColor(255, 232, 92, 165),
        "green": QColor(104, 224, 111, 165),
        "blue": QColor(117, 204, 238, 165),
        "pink": QColor(236, 134, 198, 165),
        "red": QColor(245, 85, 85, 165),
    }
    _OPACITY_OPTIONS = {
        "light": 0.35,
        "medium": 0.55,
        "strong": 0.75,
    }

    def __init__(self, parent=None, translate: Callable[[str, str | None], str] | None = None):
        super().__init__(parent)
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or "")
        self._tool = self.TOOL_SELECT
        self._hand_drag_active = False
        self._last_drag_pos = QPoint()
        self._marker_color_key = "yellow"
        self._marker_opacity_key = "medium"
        self._last_markup_zoom: float | None = None
        self._select_drag_active = False
        self._select_drag_start = QPoint()
        self._pending_highlights: list[tuple[int, list[QRectF]]] = []

        self.setObjectName("drawingPdfView")
        self.setPageMode(QPdfView.PageMode.MultiPage)
        self.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.viewport().installEventFilter(self)
        self.viewport().setMouseTracking(True)
        self.viewport().setAutoFillBackground(True)

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#eef3f8"))
        palette.setColor(QPalette.ColorRole.Window, QColor("#eef3f8"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#ffd95c"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#111111"))
        self.setPalette(palette)
        self.viewport().setPalette(palette)

        self._overlay = _MarkerOverlay(self, self.viewport())
        self.horizontalScrollBar().valueChanged.connect(self._overlay.update)
        self.verticalScrollBar().valueChanged.connect(self._overlay.update)
        self.zoomFactorChanged.connect(self._on_zoom_factor_changed)
        self.zoomModeChanged.connect(lambda *_args: QTimer.singleShot(0, self.sync_markup_zoom_reference))

        self._apply_cursor()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def apply_localization(self, translate: Callable[[str, str | None], str] | None = None) -> None:
        if translate is not None:
            self._translate = translate

    def tool_name(self) -> str:
        return self._tool

    def tool_icon(self) -> QIcon:
        if self._tool == self.TOOL_HAND:
            return _toolbar_icon("pan_tool")
        if self._tool == self.TOOL_MARKER:
            return _toolbar_icon("ink_highlighter")
        return _toolbar_icon("arrow_selector")

    def clear_markups(self) -> None:
        had_marks = self.has_markups()
        visibility_changed = not self.markups_visible()
        self._overlay.clear_strokes()
        self._overlay.set_strokes_visible(True)
        if visibility_changed:
            self.markupsVisibilityChanged.emit(True)
        if had_marks:
            self.markupsChanged.emit(False)

    def has_markups(self) -> bool:
        return self._overlay.has_strokes()

    def markups_visible(self) -> bool:
        return self._overlay.strokes_visible()

    def set_markups_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if self._overlay.strokes_visible() == visible:
            return
        self._overlay.set_strokes_visible(visible)
        self.markupsVisibilityChanged.emit(visible)

    def toggle_markups_visibility(self) -> bool:
        if not self.has_markups():
            self.set_markups_visible(True)
            return True
        new_visible = not self.markups_visible()
        self.set_markups_visible(new_visible)
        return new_visible

    def reset_markup_state(self, clear_marks: bool = True) -> None:
        if clear_marks:
            self.clear_markups()
        else:
            self.set_markups_visible(True)
        self._last_markup_zoom = None
        QTimer.singleShot(0, self.sync_markup_zoom_reference)

    def marker_color(self) -> QColor:
        color = QColor(self._COLOR_OPTIONS.get(self._marker_color_key, self._COLOR_OPTIONS["yellow"]))
        opacity = float(self._OPACITY_OPTIONS.get(self._marker_opacity_key, self._OPACITY_OPTIONS["medium"]))
        color.setAlpha(max(0, min(255, round(opacity * 255))))
        return color

    def set_tool(self, tool_name: str) -> None:
        tool_name = str(tool_name or "").strip().lower()
        if tool_name not in {self.TOOL_SELECT, self.TOOL_HAND, self.TOOL_MARKER}:
            tool_name = self.TOOL_SELECT
        if tool_name == self._tool and not self._hand_drag_active:
            return
        self._tool = tool_name
        self._hand_drag_active = False
        self._select_drag_active = False
        self._pending_highlights.clear()
        self._overlay.clear_preview()
        self._apply_cursor()
        self.toolChanged.emit(self._tool)

    def set_marker_color_key(self, color_key: str) -> None:
        if color_key in self._COLOR_OPTIONS:
            self._marker_color_key = color_key

    def set_marker_opacity_key(self, opacity_key: str) -> None:
        if opacity_key in self._OPACITY_OPTIONS:
            self._marker_opacity_key = opacity_key

    def sync_markup_zoom_reference(self) -> None:
        zoom = self._effective_zoom_factor()
        if zoom > 0:
            self._last_markup_zoom = zoom

    def open_tools_menu(self, global_pos) -> None:
        menu = QMenu(self)
        menu.setProperty("drawingToolsMenu", True)
        tool_group = QActionGroup(menu)
        tool_group.setExclusive(True)

        for tool_name, icon, text in (
            (self.TOOL_SELECT, _toolbar_icon("arrow_selector"), self._t("drawing_page.tool.select", "Select")),
            (self.TOOL_HAND, _toolbar_icon("pan_tool"), self._t("drawing_page.tool.hand", "Hand")),
            (self.TOOL_MARKER, _toolbar_icon("ink_highlighter"), self._t("drawing_page.tool.marker", "Marker")),
        ):
            action = menu.addAction(icon, text)
            action.setCheckable(True)
            action.setChecked(tool_name == self._tool)
            action.setData(("tool", tool_name))
            tool_group.addAction(action)

        menu.addSeparator()

        color_menu = menu.addMenu(self._t("drawing_page.tool.color", "Marker Color"))
        color_menu.setProperty("drawingToolsMenu", True)
        for color_key in ("yellow", "green", "blue", "pink", "red"):
            action = color_menu.addAction(
                self._color_icon(self._COLOR_OPTIONS[color_key]),
                self._t(f"drawing_page.color.{color_key}", color_key.title()),
            )
            action.setCheckable(True)
            action.setChecked(color_key == self._marker_color_key)
            action.setData(("color", color_key))

        opacity_menu = menu.addMenu(self._t("drawing_page.tool.opacity", "Marker Opacity"))
        opacity_menu.setProperty("drawingToolsMenu", True)
        for opacity_key in ("light", "medium", "strong"):
            action = opacity_menu.addAction(
                self._t(f"drawing_page.tool.opacity.{opacity_key}", opacity_key.title())
            )
            action.setCheckable(True)
            action.setChecked(opacity_key == self._marker_opacity_key)
            action.setData(("opacity", opacity_key))

        menu.addSeparator()
        clear_action = menu.addAction(
            _toolbar_icon("comment_delete"),
            self._t("drawing_page.tool.clear_marks", "Clear Marks"),
        )
        clear_action.setEnabled(self.has_markups())
        clear_action.setData(("clear", None))

        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        payload = chosen.data()
        if not isinstance(payload, tuple) or len(payload) != 2:
            return
        action_type, value = payload
        if action_type == "tool":
            self.set_tool(str(value))
            return
        if action_type == "color":
            self.set_marker_color_key(str(value))
            return
        if action_type == "opacity":
            self.set_marker_opacity_key(str(value))
            return
        if action_type == "clear":
            self.clear_markups()

    def _color_icon(self, color: QColor) -> QIcon:
        swatch = QPixmap(30, 18)
        swatch.fill(Qt.transparent)
        painter = QPainter(swatch)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#2b3640"), 1))
        painter.setBrush(color)
        painter.drawEllipse(10, 1, 16, 16)
        painter.end()
        return QIcon(swatch)

    def _effective_zoom_factor(self) -> float:
        try:
            if self.zoomMode() == QPdfView.ZoomMode.Custom:
                factor = float(self.zoomFactor())
                return factor if factor > 0 else 1.0
        except Exception:
            pass
        navigator = self.pageNavigator()
        try:
            zoom = float(navigator.currentZoom())
        except Exception:
            zoom = 0.0
        if zoom > 0:
            return zoom
        try:
            factor = float(self.zoomFactor())
        except Exception:
            factor = 1.0
        return factor if factor > 0 else 1.0

    def _apply_cursor(self) -> None:
        if self._tool == self.TOOL_HAND:
            cursor = Qt.ClosedHandCursor if self._hand_drag_active else Qt.OpenHandCursor
        elif self._tool == self.TOOL_MARKER:
            cursor = Qt.CrossCursor
        else:
            cursor = Qt.IBeamCursor
        self.viewport().setCursor(cursor)

    def _compute_actual_scale(self) -> float:
        """Derive the actual rendering scale (logical px per PDF point) from the
        scrollbar range so we don't have to guess Qt's internal DPI conversion."""
        doc = self.document()
        if doc is None or doc.pageCount() <= 0:
            return 1.0
        n = doc.pageCount()
        total_pts = sum(float(doc.pagePointSize(i).height()) for i in range(n))
        if total_pts <= 0:
            return 1.0
        margins = self.documentMargins()
        margin_v = float(margins.top() + margins.bottom())
        spacing_px = float(max(0, (n - 1) * self.pageSpacing()))
        content_h_px = float(self.verticalScrollBar().maximum() + self.viewport().height())
        page_area_px = content_h_px - spacing_px - margin_v
        return max(0.01, page_area_px / total_pts)

    def _page_left_offset(self, page_w_px: float) -> float:
        """X offset (in content coordinates) of the page's left edge."""
        margins = self.documentMargins()
        h_margins = float(margins.left() + margins.right())
        content_w = max(page_w_px + h_margins, float(self.viewport().width()))
        return (content_w - page_w_px) / 2.0

    def _content_pos_to_page_pos(self, content_pos: QPointF) -> tuple[int, QPointF] | None:
        document = self.document()
        if document is None or document.pageCount() <= 0:
            return None

        scale = self._compute_actual_scale()
        margins = self.documentMargins()
        page_spacing = float(max(0, self.pageSpacing()))
        y_cursor = float(margins.top())
        page_index = 0
        for idx in range(document.pageCount()):
            page_h = float(document.pagePointSize(idx).height()) * scale
            if content_pos.y() < y_cursor + page_h or idx == document.pageCount() - 1:
                page_index = idx
                break
            y_cursor += page_h + page_spacing

        pts = document.pagePointSize(page_index)
        page_w = float(pts.width()) * scale
        page_h = float(pts.height()) * scale
        if page_w <= 0 or page_h <= 0:
            return None

        page_left = self._page_left_offset(page_w)
        local_x = min(max(content_pos.x() - page_left, 0.0), page_w)
        local_y = min(max(content_pos.y() - y_cursor, 0.0), page_h)

        page_point = QPointF(local_x / scale, local_y / scale)
        return page_index, page_point

    def _selection_rects_for_page(self, page: int, selection) -> list[QRectF]:
        rects: list[QRectF] = []
        document = self.document()
        if document is None:
            return rects

        scale = self._compute_actual_scale()
        margins = self.documentMargins()
        page_spacing = float(max(0, self.pageSpacing()))

        page_top = float(margins.top())
        for idx in range(page):
            page_top += float(document.pagePointSize(idx).height()) * scale + page_spacing

        page_w = float(document.pagePointSize(page).width()) * scale
        if page_w <= 0:
            return rects
        page_left = self._page_left_offset(page_w)

        for bound in (selection.bounds() or []):
            if hasattr(bound, "boundingRect"):
                bound_rect = QRectF(bound.boundingRect())
            else:
                bound_rect = QRectF(bound)
            rects.append(
                QRectF(
                    page_left + bound_rect.left() * scale,
                    page_top + bound_rect.top() * scale,
                    max(1.0, bound_rect.width() * scale),
                    max(1.0, bound_rect.height() * scale),
                )
            )
        return rects

    def _compute_selection(
        self, viewport_start: QPoint, viewport_end: QPoint
    ) -> list[tuple[int, list[QRectF], list[QRectF]]]:
        """Return [(page, pdf_rects, content_px_rects), ...] for text under the drag area."""
        document = self.document()
        if document is None or document.pageCount() <= 0:
            return []

        start_content = QPointF(
            float(self.horizontalScrollBar().value() + viewport_start.x()),
            float(self.verticalScrollBar().value() + viewport_start.y()),
        )
        end_content = QPointF(
            float(self.horizontalScrollBar().value() + viewport_end.x()),
            float(self.verticalScrollBar().value() + viewport_end.y()),
        )

        start_hit = self._content_pos_to_page_pos(start_content)
        end_hit = self._content_pos_to_page_pos(end_content)
        if not start_hit or not end_hit:
            return []

        start_page, start_point = start_hit
        end_page, end_point = end_hit
        low_page = min(start_page, end_page)
        high_page = max(start_page, end_page)
        low_point = start_point if start_page == low_page else end_point
        high_point = start_point if start_page == high_page else end_point

        results: list[tuple[int, list[QRectF], list[QRectF]]] = []
        for page in range(low_page, high_page + 1):
            try:
                page_size = document.pagePointSize(page)
            except Exception:
                continue

            if low_page == high_page:
                page_start = start_point
                page_end = end_point
            elif page == low_page:
                page_start = low_point
                page_end = QPointF(float(page_size.width()), float(page_size.height()))
            elif page == high_page:
                page_start = QPointF(0.0, 0.0)
                page_end = high_point
            else:
                page_start = QPointF(0.0, 0.0)
                page_end = QPointF(float(page_size.width()), float(page_size.height()))

            try:
                selection = document.getSelection(page, page_start, page_end)
            except Exception:
                continue
            if not selection.isValid() or not (selection.text() or "").strip():
                continue

            pdf_rects: list[QRectF] = []
            for bound in (selection.bounds() or []):
                if hasattr(bound, "boundingRect"):
                    pdf_rects.append(QRectF(bound.boundingRect()))
                else:
                    pdf_rects.append(QRectF(bound))
            if pdf_rects:
                results.append((page, pdf_rects, self._selection_rects_for_page(page, selection)))

        return results

    def _update_text_selection(self, viewport_start: QPoint, viewport_end: QPoint) -> None:
        results = self._compute_selection(viewport_start, viewport_end)
        if not results:
            self._overlay.clear_preview()
            return
        preview = [r for _, _, px_rects in results for r in px_rects]
        sel_color = QColor("#9fc7ee")
        sel_color.setAlpha(160)
        self._overlay.set_preview_rects(preview, sel_color)

    def _update_marker_selection(self, viewport_start: QPoint, viewport_end: QPoint) -> None:
        results = self._compute_selection(viewport_start, viewport_end)
        self._pending_highlights = [(page, pdf_rects) for page, pdf_rects, _ in results]
        if not results:
            self._overlay.clear_preview()
            return
        preview = [r for _, _, px_rects in results for r in px_rects]
        self._overlay.set_preview_rects(preview, self.marker_color())

    def _commit_marker_highlight(self) -> bool:
        if not self._pending_highlights:
            self._overlay.clear_preview()
            return False
        color = self.marker_color()
        for page, pdf_rects in self._pending_highlights:
            self._overlay.add_highlight(page, pdf_rects, color)
        self._pending_highlights.clear()
        self._overlay.clear_preview()
        return True

    def _on_zoom_factor_changed(self, *_args) -> None:
        zoom = self._effective_zoom_factor()
        if zoom <= 0:
            return
        self._overlay.clear_preview()
        self._last_markup_zoom = zoom

    def set_custom_zoom(self, new_zoom: float, anchor_viewport_pos: QPoint | None = None) -> None:
        old_zoom = self._effective_zoom_factor()
        new_zoom = max(0.1, min(8.0, float(new_zoom)))
        if old_zoom <= 0 or anchor_viewport_pos is None:
            self.setZoomMode(QPdfView.ZoomMode.Custom)
            self.setZoomFactor(new_zoom)
            return

        anchor = QPoint(anchor_viewport_pos)
        content_x = float(self.horizontalScrollBar().value() + anchor.x())
        content_y = float(self.verticalScrollBar().value() + anchor.y())
        scale = new_zoom / old_zoom

        self.setZoomMode(QPdfView.ZoomMode.Custom)
        self.setZoomFactor(new_zoom)

        def restore_anchor() -> None:
            self.horizontalScrollBar().setValue(max(0, round(content_x * scale - anchor.x())))
            self.verticalScrollBar().setValue(max(0, round(content_y * scale - anchor.y())))

        QTimer.singleShot(0, restore_anchor)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                multiplier = 1.15 if delta > 0 else 1 / 1.15
                new_zoom = max(0.1, min(8.0, self._effective_zoom_factor() * multiplier))
                self.set_custom_zoom(new_zoom, event.position().toPoint())
            event.accept()
            return
        super().wheelEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.viewport():
            if event.type() == QEvent.Resize:
                self._overlay.resize_to_viewport()
                return False
            if event.type() == QEvent.ContextMenu:
                self.open_tools_menu(event.globalPos())
                return True
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                if self._tool == self.TOOL_SELECT:
                    self._select_drag_active = True
                    self._select_drag_start = event.pos()
                    self._overlay.clear_preview()
                    return True
                if self._tool == self.TOOL_HAND:
                    self._hand_drag_active = True
                    self._last_drag_pos = event.pos()
                    self._apply_cursor()
                    return True
                if self._tool == self.TOOL_MARKER:
                    self._select_drag_active = True
                    self._select_drag_start = event.pos()
                    self._overlay.clear_preview()
                    return True
            if event.type() == QEvent.MouseMove:
                if self._tool == self.TOOL_SELECT and self._select_drag_active:
                    self._update_text_selection(self._select_drag_start, event.pos())
                    return True
                if self._tool == self.TOOL_HAND and self._hand_drag_active:
                    delta = event.pos() - self._last_drag_pos
                    self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
                    self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
                    self._last_drag_pos = event.pos()
                    return True
                if self._tool == self.TOOL_MARKER and self._select_drag_active:
                    self._update_marker_selection(self._select_drag_start, event.pos())
                    return True
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                if self._tool == self.TOOL_SELECT and self._select_drag_active:
                    self._select_drag_active = False
                    self._update_text_selection(self._select_drag_start, event.pos())
                    return True
                if self._tool == self.TOOL_HAND and self._hand_drag_active:
                    self._hand_drag_active = False
                    self._apply_cursor()
                    return True
                if self._tool == self.TOOL_MARKER and self._select_drag_active:
                    self._select_drag_active = False
                    created = self._commit_marker_highlight()
                    if created:
                        self.markupsChanged.emit(True)
                    return True
        return super().eventFilter(watched, event)


# ---------------------------------------------------------------------------
# Drawing list card
# ---------------------------------------------------------------------------

class DrawingListCard(QFrame):
    clicked = Signal()
    doubleClicked = Signal()

    def __init__(self, drawing: dict, parent=None):
        super().__init__(parent)
        self.drawing = dict(drawing or {})
        self.setProperty("toolListCard", True)
        self.setProperty("drawingRowCard", True)
        self.setProperty("selected", False)
        self.setMinimumHeight(58)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(0)

        title = self.drawing.get("drawing_id") or self.drawing.get("name") or "-"
        self.title_label = QLabel(str(title))
        self.title_label.setProperty("toolCardValue", True)
        self.title_label.setProperty("drawingRowTitle", True)
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.title_label)

    def set_selected(self, selected: bool) -> None:
        selected = bool(selected)
        if bool(self.property("selected")) == selected:
            return
        self.setProperty("selected", selected)
        repolish_widget(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
