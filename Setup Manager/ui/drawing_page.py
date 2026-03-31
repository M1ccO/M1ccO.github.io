from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QModelIndex, QPoint, QPointF, QRectF, QSignalBlocker, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QActionGroup, QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtPdf import QPdfDocument, QPdfSearchModel
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import ICONS_DIR, TOOL_LIBRARY_TOOL_ICONS_DIR
from ui.widgets.common import repolish_widget, styled_list_item_height

_MAX_WIDGET_SIZE = 16777215


def _svg_icon(path: Path, size: int = 24) -> QIcon:
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return QIcon()
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def _toolbar_icon(name: str) -> QIcon:
    png = ICONS_DIR / "tools" / f"{name}.png"
    if png.exists():
        return QIcon(str(png))
    shared_png = TOOL_LIBRARY_TOOL_ICONS_DIR / f"{name}.png"
    if shared_png.exists():
        return QIcon(str(shared_png))
    svg = ICONS_DIR / "tools" / f"{name}.svg"
    if svg.exists():
        return _svg_icon(svg)
    shared_svg = TOOL_LIBRARY_TOOL_ICONS_DIR / f"{name}.svg"
    if shared_svg.exists():
        return _svg_icon(shared_svg)
    return QIcon()
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
        if not self._highlights and not self._preview_rects and not self._search_rects:
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
        self._overlay.clear_strokes()
        if had_marks:
            self.markupsChanged.emit(False)

    def has_markups(self) -> bool:
        return self._overlay.has_strokes()

    def reset_markup_state(self, clear_marks: bool = True) -> None:
        if clear_marks:
            self.clear_markups()
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


class _DrawingListCard(QFrame):
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


class DrawingPage(QWidget):
    def __init__(
        self,
        draw_service,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self.draw_service = draw_service
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or "")
        self._setup_context: dict = {}
        self._drawings: list[dict] = []
        self._current_drawing: dict | None = None
        self._current_drawing_path = ""
        self._prefer_context_focus = False
        self._focus_viewer_dismissed = False
        self._manual_focus_viewer = False
        self._last_layout_signature: tuple[bool, int, int] | None = None

        self._pdf_document = QPdfDocument(self)
        self._search_model = QPdfSearchModel(self)
        self._search_model.setDocument(self._pdf_document)

        self._pdf_document.statusChanged.connect(self._on_document_status_changed)
        self._pdf_document.pageCountChanged.connect(self._update_page_status)
        self._search_model.modelReset.connect(self._on_search_model_changed)
        self._search_model.rowsInserted.connect(lambda *_args: self._on_search_model_changed())
        self._search_model.rowsRemoved.connect(lambda *_args: self._on_search_model_changed())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        controls_frame = QFrame()
        controls_frame.setProperty("topBarContainer", True)
        controls = QHBoxLayout(controls_frame)
        controls.setContentsMargins(8, 6, 8, 6)
        controls.setSpacing(8)

        self.search_icon = _toolbar_icon("search_icon")
        self.close_icon = _toolbar_icon("close_icon")

        self.search_toggle_btn = QToolButton()
        self.search_toggle_btn.setProperty("topBarIconButton", True)
        self.search_toggle_btn.setCheckable(True)
        self.search_toggle_btn.setToolTip(self._t("drawing_page.search_toggle_tip", "Show/hide search"))
        self.search_toggle_btn.setIcon(self.search_icon)
        self.search_toggle_btn.setIconSize(QSize(28, 28))
        self.search_toggle_btn.setFixedSize(36, 36)
        self.search_toggle_btn.setAutoRaise(True)
        self.search_toggle_btn.clicked.connect(self._toggle_search)
        controls.addWidget(self.search_toggle_btn)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self._t("drawing_page.search_placeholder", "Search drawings..."))
        self.search_input.textChanged.connect(self.refresh_list)
        self.search_input.setVisible(False)
        self.search_input.setMaximumWidth(320)
        self.search_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        controls.addWidget(self.search_input)

        self.refresh_btn = QPushButton(self._t("drawing_page.action.refresh", "Refresh"))
        self.refresh_btn.setProperty("panelActionButton", True)
        self.refresh_btn.setMinimumWidth(130)
        self.refresh_btn.setMaximumWidth(180)
        self.refresh_btn.clicked.connect(self.refresh_list)
        controls.addWidget(self.refresh_btn)

        controls.addStretch(1)

        self.context_label = QLabel("")
        self.context_label.setProperty("detailHint", True)
        self.context_label.setProperty("drawingViewerStat", True)
        self.context_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        controls.addWidget(self.context_label, 0, Qt.AlignRight)

        self.close_focus_btn = QToolButton()
        self.close_focus_btn.setProperty("topBarIconButton", True)
        self.close_focus_btn.setAutoRaise(True)
        self.close_focus_btn.setIcon(self.close_icon)
        self.close_focus_btn.setIconSize(QSize(18, 18))
        self.close_focus_btn.setText(self._t("drawing_page.action.close_focus", "Close viewer"))
        self.close_focus_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.close_focus_btn.setFixedHeight(36)
        self.close_focus_btn.clicked.connect(self._dismiss_focus_viewer)
        self.close_focus_btn.setVisible(False)
        controls.addWidget(self.close_focus_btn, 0, Qt.AlignRight)

        root.addWidget(controls_frame)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName("drawingListSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(2)

        self._build_list_panel()
        self._build_viewer_panel()
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)

        root.addWidget(self.splitter, 1)

        self._update_context_labels()
        self._show_empty_state(
            self._t("drawing_page.empty.title", "No drawing selected"),
            self._t("drawing_page.empty.body", "Select a drawing to preview it here."),
        )
        self.refresh_list()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _make_text_action_button(self, text: str, min_width: int = 72) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("panelActionButton", True)
        button.setMinimumWidth(min_width)
        button.setMaximumWidth(max(min_width, 90))
        return button

    def _make_icon_button(
        self,
        icon: QIcon,
        tooltip: str,
        fallback_text: str = "",
        icon_size: int = 18,
        button_size: int = 30,
    ) -> QToolButton:
        button = QToolButton()
        button.setProperty("topBarIconButton", True)
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        button.setFixedSize(button_size, button_size)
        if not icon.isNull():
            button.setIcon(icon)
            button.setIconSize(QSize(icon_size, icon_size))
        elif fallback_text:
            button.setText(fallback_text)
        return button

    def _build_list_panel(self) -> None:
        self.list_host = QFrame()
        self.list_host.setProperty("catalogShell", True)
        self.list_host.setMinimumWidth(320)
        list_layout = QVBoxLayout(self.list_host)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("drawingList")
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setSpacing(8)
        self.list_widget.currentItemChanged.connect(self._on_current_item_changed)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._focus_selected_in_app())
        self.list_widget.installEventFilter(self)
        self.list_widget.viewport().installEventFilter(self)
        list_layout.addWidget(self.list_widget, 1)

        self.splitter.addWidget(self.list_host)

    def _build_viewer_panel(self) -> None:
        self.viewer_host = QWidget()
        self.viewer_host.setMinimumWidth(420)
        viewer_layout = QVBoxLayout(self.viewer_host)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(0)
        self._viewer_host_layout = viewer_layout

        self.viewer_surface = QFrame()
        self.viewer_surface.setProperty("catalogShell", True)
        self.viewer_surface.setProperty("drawingViewerShell", True)
        viewer_surface_layout = QVBoxLayout(self.viewer_surface)
        viewer_surface_layout.setContentsMargins(8, 8, 8, 8)
        viewer_surface_layout.setSpacing(8)

        self.pdf_view = InteractivePdfView(translate=self._t)
        self._build_pdf_toolbar(viewer_surface_layout)

        self.viewer_stack = QStackedWidget()

        self.empty_view = QWidget()
        empty_layout = QVBoxLayout(self.empty_view)
        empty_layout.setContentsMargins(32, 32, 32, 32)
        empty_layout.setSpacing(8)
        empty_layout.addStretch(1)
        self.empty_title = QLabel(self._t("drawing_page.empty.title", "No drawing selected"))
        self.empty_title.setProperty("pageTitle", True)
        self.empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_title)
        self.empty_body = QLabel(self._t("drawing_page.empty.body", "Select a drawing to preview it here."))
        self.empty_body.setProperty("detailHint", True)
        self.empty_body.setWordWrap(True)
        self.empty_body.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_body)
        empty_layout.addStretch(1)
        self.viewer_stack.addWidget(self.empty_view)

        self.pdf_view.setDocument(self._pdf_document)
        self.pdf_view.setSearchModel(self._search_model)
        self.pdf_view.pageNavigator().currentPageChanged.connect(self._update_page_status)
        self.pdf_view.pageNavigator().currentZoomChanged.connect(self._update_zoom_status)
        self.pdf_view.currentSearchResultIndexChanged.connect(self._update_search_status)
        self.pdf_view.zoomFactorChanged.connect(self._update_zoom_status)
        self.pdf_view.zoomModeChanged.connect(self._update_zoom_status)
        self.pdf_view.toolChanged.connect(lambda *_args: self._update_tool_button())
        self.pdf_view.markupsChanged.connect(lambda *_args: self._update_markup_buttons())
        self.pdf_view.installEventFilter(self)
        self.viewer_stack.addWidget(self.pdf_view)

        viewer_surface_layout.addWidget(self.viewer_stack, 1)
        self._build_viewer_zoom_overlay()
        viewer_layout.addWidget(self.viewer_surface, 1)
        self.splitter.addWidget(self.viewer_host)

    def _build_viewer_zoom_overlay(self) -> None:
        self.viewer_zoom_overlay = QWidget(self.pdf_view)
        overlay_layout = QVBoxLayout(self.viewer_zoom_overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(2)

        self.zoom_status.setParent(self.viewer_zoom_overlay)
        self.zoom_status.setProperty("pdfFloatingZoomStatus", True)
        self.zoom_status.setAlignment(Qt.AlignCenter)
        self.zoom_status.setFixedSize(36, 24)
        _shadow = QGraphicsDropShadowEffect(self.zoom_status)
        _shadow.setBlurRadius(3)
        _shadow.setOffset(0, 0)
        _shadow.setColor(QColor(0, 0, 0, 200))
        self.zoom_status.setGraphicsEffect(_shadow)
        overlay_layout.addWidget(self.zoom_status, 0, Qt.AlignCenter)

        self.zoom_in_btn.setParent(self.viewer_zoom_overlay)
        self.zoom_in_btn.setFixedSize(36, 32)
        overlay_layout.addWidget(self.zoom_in_btn, 0, Qt.AlignCenter)

        self.zoom_out_btn.setParent(self.viewer_zoom_overlay)
        self.zoom_out_btn.setFixedSize(36, 32)
        overlay_layout.addWidget(self.zoom_out_btn, 0, Qt.AlignCenter)

        self.viewer_zoom_overlay.adjustSize()
        self.viewer_zoom_overlay.raise_()
        self._position_viewer_overlays()

    def _position_viewer_overlays(self) -> None:
        if not hasattr(self, "viewer_zoom_overlay"):
            return
        margin = 18
        hint = self.viewer_zoom_overlay.sizeHint()
        width = max(hint.width(), 34)
        height = hint.height()
        self.viewer_zoom_overlay.setGeometry(
            max(margin, self.pdf_view.width() - width - margin),
            margin,
            width,
            height,
        )
        self.viewer_zoom_overlay.raise_()

    def _build_pdf_toolbar(self, viewer_layout: QVBoxLayout) -> None:
        pdf_toolbar = QFrame()
        pdf_toolbar.setProperty("pdfToolbarCard", True)
        pdf_toolbar.setFixedHeight(50)
        pdf_controls = QHBoxLayout(pdf_toolbar)
        pdf_controls.setContentsMargins(8, 6, 8, 6)
        pdf_controls.setSpacing(4)

        self.viewer_tools_btn = self._make_icon_button(
            _toolbar_icon("menu_icon"),
            self._t("drawing_page.tool.menu_tip", "Viewer tools"),
            icon_size=22,
            button_size=36,
        )
        self.viewer_tools_btn.clicked.connect(self._open_viewer_tools_menu_from_button)
        pdf_controls.addWidget(self.viewer_tools_btn)

        self.clear_marks_btn = self._make_icon_button(
            _toolbar_icon("comment_delete"),
            self._t("drawing_page.tool.clear_marks", "Clear Marks"),
            icon_size=22,
            button_size=36,
        )
        self.clear_marks_btn.clicked.connect(self.pdf_view.clear_markups)
        pdf_controls.addWidget(self.clear_marks_btn)

        self.open_external_btn = self._make_icon_button(
            _toolbar_icon("file_open"),
            self._t("drawing_page.action.open", "Open"),
            fallback_text=self._t("drawing_page.action.open", "Open"),
            icon_size=22,
            button_size=36,
        )
        self.open_external_btn.clicked.connect(self.open_selected)
        pdf_controls.addWidget(self.open_external_btn)

        self.prev_page_btn = self._make_icon_button(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack),
            self._t("drawing_page.action.page_prev", "Previous page"),
            fallback_text="<",
            icon_size=20,
            button_size=36,
        )
        self.prev_page_btn.clicked.connect(lambda: self._jump_page(-1))
        pdf_controls.addWidget(self.prev_page_btn)

        self.page_status = QLabel(self._t("drawing_page.page_status.empty", "Page - / -"))
        self.page_status.setProperty("drawingViewerStat", True)
        pdf_controls.addWidget(self.page_status)

        self.next_page_btn = self._make_icon_button(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward),
            self._t("drawing_page.action.page_next", "Next page"),
            fallback_text=">",
            icon_size=20,
            button_size=36,
        )
        self.next_page_btn.clicked.connect(lambda: self._jump_page(1))
        pdf_controls.addWidget(self.next_page_btn)

        self.zoom_out_btn = self._make_icon_button(
            _toolbar_icon("minus"),
            self._t("drawing_page.action.zoom_out", "Zoom out"),
            fallback_text="-",
            icon_size=20,
            button_size=38,
        )
        self.zoom_out_btn.setProperty("panelActionSquareButton", True)
        self.zoom_out_btn.setProperty("viewerToolbarGlyphButton", True)
        self.zoom_out_btn.clicked.connect(lambda: self._step_zoom(1 / 1.15))

        self.zoom_status = QLabel(self._t("drawing_page.zoom_status.empty", "Zoom -"))
        self.zoom_status.setProperty("drawingViewerStat", True)

        self.zoom_in_btn = self._make_icon_button(
            _toolbar_icon("plus"),
            self._t("drawing_page.action.zoom_in", "Zoom in"),
            fallback_text="+",
            icon_size=20,
            button_size=38,
        )
        self.zoom_in_btn.setProperty("panelActionSquareButton", True)
        self.zoom_in_btn.setProperty("viewerToolbarGlyphButton", True)
        self.zoom_in_btn.clicked.connect(lambda: self._step_zoom(1.15))

        self.fit_width_btn = self._make_icon_button(
            _toolbar_icon("fit_width"),
            self._t("drawing_page.action.fit_width", "Fit Width"),
            icon_size=22,
            button_size=36,
        )
        self.fit_width_btn.clicked.connect(self._fit_width)
        pdf_controls.addWidget(self.fit_width_btn)

        self.fit_page_btn = self._make_icon_button(
            _toolbar_icon("fit_page"),
            self._t("drawing_page.action.fit_page", "Fit Page"),
            icon_size=22,
            button_size=36,
        )
        self.fit_page_btn.clicked.connect(self._fit_page)
        pdf_controls.addWidget(self.fit_page_btn)

        pdf_controls.addStretch(1)

        self.find_trigger_btn = self._make_icon_button(
            self.search_icon,
            self._t("drawing_page.action.find", "Find text"),
            icon_size=22,
            button_size=36,
        )
        self.find_trigger_btn.setCheckable(True)
        self.find_trigger_btn.clicked.connect(self._toggle_pdf_search)
        pdf_controls.addWidget(self.find_trigger_btn)

        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText(self._t("drawing_page.find.placeholder", "Find text in PDF..."))
        self.find_input.setMaximumWidth(180)
        self.find_input.setFixedHeight(36)
        self.find_input.textChanged.connect(self._on_find_text_changed)
        self.find_input.setVisible(False)
        pdf_controls.addWidget(self.find_input)

        self.prev_hit_btn = self._make_icon_button(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack),
            self._t("drawing_page.action.find_prev", "Previous hit"),
            fallback_text="<",
            icon_size=20,
            button_size=36,
        )
        self.prev_hit_btn.clicked.connect(lambda: self._step_search_result(-1))
        self.prev_hit_btn.setVisible(False)
        pdf_controls.addWidget(self.prev_hit_btn)

        self.next_hit_btn = self._make_icon_button(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward),
            self._t("drawing_page.action.find_next", "Next hit"),
            fallback_text=">",
            icon_size=20,
            button_size=36,
        )
        self.next_hit_btn.clicked.connect(lambda: self._step_search_result(1))
        self.next_hit_btn.setVisible(False)
        pdf_controls.addWidget(self.next_hit_btn)

        self.search_result_label = QLabel()
        self.search_result_label.setProperty("drawingViewerStat", True)
        self.search_result_label.setVisible(False)
        pdf_controls.addWidget(self.search_result_label)

        self.search_status = QLabel(self._t("drawing_page.find.status.idle", "Text search"))
        self.search_status.setProperty("drawingViewerStat", True)
        self.search_status.setVisible(False)

        viewer_layout.addWidget(pdf_toolbar)

    def _toggle_search(self) -> None:
        show = self.search_toggle_btn.isChecked()
        self.search_input.setVisible(show)
        self.search_toggle_btn.setIcon(self.close_icon if show else self.search_icon)
        if show:
            self.search_input.setFocus()
            return
        self.search_input.clear()
        self.refresh_list()

    def _open_viewer_tools_menu_from_button(self) -> None:
        anchor = self.viewer_tools_btn.mapToGlobal(self.viewer_tools_btn.rect().bottomLeft())
        self.pdf_view.open_tools_menu(anchor)
        self._update_tool_button()
        self._update_markup_buttons()

    def _toggle_pdf_search(self) -> None:
        visible = self.find_trigger_btn.isChecked()
        self.find_trigger_btn.setIcon(self.close_icon if visible else self.search_icon)
        self.find_input.setVisible(visible)
        self.prev_hit_btn.setVisible(visible)
        self.next_hit_btn.setVisible(visible)
        self.search_result_label.setVisible(visible)
        self.fit_width_btn.setVisible(not visible)
        self.fit_page_btn.setVisible(not visible)
        self.search_status.setVisible(False)
        if visible:
            self.find_input.setFocus()
            self.find_input.selectAll()
            if self.find_input.text().strip():
                self._focus_first_search_result()
            return
        self.find_input.clear()
        self.pdf_view._overlay.clear_search_rects()
        self._update_search_status()

    def set_setup_context(self, context: dict | None) -> None:
        new_context = dict(context or {})
        if new_context == self._setup_context:
            return
        context_signature = (
            bool(new_context.get("selected")),
            str(new_context.get("work_id") or "").strip(),
            str(new_context.get("drawing_id") or "").strip(),
            str(new_context.get("drawing_path") or "").strip(),
        )
        old_signature = (
            bool(self._setup_context.get("selected")),
            str(self._setup_context.get("work_id") or "").strip(),
            str(self._setup_context.get("drawing_id") or "").strip(),
            str(self._setup_context.get("drawing_path") or "").strip(),
        )
        self._setup_context = new_context
        self._prefer_context_focus = context_signature != old_signature
        if context_signature != old_signature:
            self._focus_viewer_dismissed = False
        self._update_context_labels()
        self.refresh_list()

    def _focus_mode_active(self) -> bool:
        return self._manual_focus_viewer or (
            bool(self._setup_context.get("selected")) and not self._focus_viewer_dismissed
        )

    def _focus_selected_in_app(self) -> None:
        drawing = self._selected_drawing() or self._current_drawing
        if not drawing:
            return
        self._manual_focus_viewer = True
        self._focus_viewer_dismissed = False
        self._last_layout_signature = None
        self._update_context_labels()
        self._apply_splitter_layout()

    def _dismiss_focus_viewer(self) -> None:
        if not self._focus_mode_active():
            return
        self._manual_focus_viewer = False
        self._focus_viewer_dismissed = bool(self._setup_context.get("selected"))
        self._last_layout_signature = None
        self._update_context_labels()
        self._apply_splitter_layout()

    def _update_context_labels(self) -> None:
        selected = bool(self._setup_context.get("selected"))
        work_id = str(self._setup_context.get("work_id") or "").strip()
        drawing_id = str(self._setup_context.get("drawing_id") or "").strip()
        focus_mode = self._focus_mode_active()

        if selected:
            if work_id and drawing_id:
                self.context_label.setText(
                    self._t(
                        "drawing_page.context.selected_with_drawing",
                        "Selected work {work_id} | Drawing {drawing_id}",
                        work_id=work_id,
                        drawing_id=drawing_id,
                    )
                )
            elif work_id:
                self.context_label.setText(
                    self._t(
                        "drawing_page.context.selected_work",
                        "Selected work {work_id}",
                        work_id=work_id,
                    )
                )
            else:
                self.context_label.setText(self._t("drawing_page.context.selected", "Selected setup"))
        else:
            self.context_label.clear()
        self.close_focus_btn.setVisible(focus_mode)

    def refresh_list(self, *_args) -> None:
        previous_path = self._current_drawing_path
        drawings = self.draw_service.list_drawings_with_context(
            search=self.search_input.text(),
            context=self._setup_context,
        )
        self._drawings = drawings

        with QSignalBlocker(self.list_widget):
            self.list_widget.clear()
            for drawing in drawings:
                item = QListWidgetItem()
                item.setData(Qt.UserRole, drawing)
                card = _DrawingListCard(drawing)
                card.clicked.connect(lambda list_item=item: self._select_list_item(list_item))
                card.doubleClicked.connect(lambda list_item=item: self._activate_card_double_click(list_item))
                item.setSizeHint(QSize(0, styled_list_item_height(card, spacing=2)))
                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, card)

        target_path = ""
        if not self._prefer_context_focus and previous_path:
            target_path = previous_path
        if not target_path:
            target_path = self._preferred_context_path()
        if not target_path and drawings:
            target_path = str(drawings[0].get("path") or "")

        self._prefer_context_focus = False
        self._apply_splitter_layout()

        if drawings and target_path and self._select_drawing_by_path(target_path):
            self._update_card_selection_states()
            return
        if drawings:
            self.list_widget.setCurrentRow(0)
            self._update_card_selection_states()
            self._load_selected_preview()
            return

        self._current_drawing = None
        self._current_drawing_path = ""
        self._update_card_selection_states()
        self.pdf_view.reset_markup_state(clear_marks=True)
        self._show_empty_state(
            self._t("drawing_page.empty.title.no_results", "No drawings found"),
            self._t(
                "drawing_page.empty.body.no_results",
                "No PDF drawings matched the current search or setup selection.",
            ),
        )
        self._update_page_status()
        self._update_zoom_status()
        self._update_search_status()
        self._update_open_button_state()

    def _preferred_context_path(self) -> str:
        for drawing in self._drawings:
            if int(drawing.get("context_score") or 0) > 0:
                return str(drawing.get("path") or "")
        return ""

    def _select_list_item(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        self.list_widget.setCurrentItem(item)
        self.list_widget.scrollToItem(item)

    def _activate_card_double_click(self, item: QListWidgetItem | None) -> None:
        self._select_list_item(item)
        self._focus_selected_in_app()

    def _select_drawing_by_path(self, drawing_path: str) -> bool:
        target = str(drawing_path or "").strip().lower()
        if not target:
            return False
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            drawing = item.data(Qt.UserRole) if item is not None else None
            candidate = str((drawing or {}).get("path") or "").strip().lower()
            if candidate == target:
                self.list_widget.setCurrentItem(item)
                self.list_widget.scrollToItem(item)
                self._load_selected_preview()
                return True
        return False

    def _on_current_item_changed(self, _current, _previous) -> None:
        self._update_card_selection_states()
        self._load_selected_preview()

    def _update_card_selection_states(self) -> None:
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            card = self.list_widget.itemWidget(item)
            if isinstance(card, _DrawingListCard):
                card.set_selected(item is self.list_widget.currentItem())

    def _selected_drawing(self) -> dict | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        drawing = item.data(Qt.UserRole)
        return dict(drawing) if isinstance(drawing, dict) else None

    def eventFilter(self, obj, event):
        if obj is self.list_widget.viewport() and event.type() == QEvent.MouseButtonPress:
            if self._is_press_near_splitter_handle(event):
                return False
            if not self.list_widget.itemAt(event.pos()):
                self._clear_selection()
        if obj is self.list_widget and event.type() == QEvent.MouseButtonPress:
            if self._is_press_near_splitter_handle(event):
                return False
            viewport_pos = self.list_widget.viewport().mapFrom(self.list_widget, event.pos())
            if not self.list_widget.itemAt(viewport_pos):
                self._clear_selection()
        return super().eventFilter(obj, event)

    def _is_press_near_splitter_handle(self, event) -> bool:
        handle = self.splitter.handle(1) if self.splitter.count() > 1 else None
        if handle is None or self._focus_mode_active():
            return False
        handle_rect = handle.geometry().adjusted(-10, 0, 10, 0)
        if hasattr(event, "globalPosition"):
            global_pos = event.globalPosition().toPoint()
        elif hasattr(event, "globalPos"):
            global_pos = event.globalPos()
        else:
            return False
        pos_in_splitter = self.splitter.mapFromGlobal(global_pos)
        return handle_rect.contains(pos_in_splitter)

    def _clear_selection(self) -> None:
        self.list_widget.clearSelection()
        self.list_widget.setCurrentItem(None)
        self._current_drawing = None
        self._current_drawing_path = ""
        self._manual_focus_viewer = False
        self._update_card_selection_states()
        self._update_context_labels()
        self._show_empty_state(
            self._t("drawing_page.empty.title", "No drawing selected"),
            self._t("drawing_page.empty.body", "Select a drawing to preview it here."),
        )
        self._update_page_status()
        self._update_zoom_status()
        self._update_search_status()
        self._update_open_button_state()

    def _load_selected_preview(self) -> None:
        drawing = self._selected_drawing()
        self._current_drawing = drawing
        self._current_drawing_path = str((drawing or {}).get("path") or "").strip()
        self._update_open_button_state()
        if not drawing:
            self.pdf_view.reset_markup_state(clear_marks=True)
            self._show_empty_state(
                self._t("drawing_page.empty.title", "No drawing selected"),
                self._t("drawing_page.empty.body", "Select a drawing to preview it here."),
            )
            return

        drawing_path = Path(self._current_drawing_path)
        if not drawing_path.exists():
            self._pdf_document.close()
            self.pdf_view.reset_markup_state(clear_marks=True)
            self._show_empty_state(
                self._t("drawing_page.empty.title.missing", "Drawing file missing"),
                self._t(
                    "drawing_page.empty.body.missing",
                    "The linked PDF file could not be found at:\n{path}",
                    path=self._current_drawing_path,
                ),
            )
            self._update_page_status()
            self._update_zoom_status()
            self._update_search_status()
            return

        self._show_empty_state(
            self._t("drawing_page.loading.title", "Loading drawing..."),
            self._t("drawing_page.loading.body", "Opening PDF preview."),
        )
        self._pdf_document.close()
        self.pdf_view.reset_markup_state(clear_marks=True)
        self._pdf_document.load(str(drawing_path))

    def _on_document_status_changed(self, status) -> None:
        if status == QPdfDocument.Status.Ready:
            self.viewer_stack.setCurrentWidget(self.pdf_view)
            self._fit_page()
            self.pdf_view.reset_markup_state(clear_marks=False)
            self._reapply_search_text()
            QTimer.singleShot(0, lambda: self._go_to_page(0))
        elif status == QPdfDocument.Status.Loading:
            self._show_empty_state(
                self._t("drawing_page.loading.title", "Loading drawing..."),
                self._t("drawing_page.loading.body", "Opening PDF preview."),
            )
        elif status == QPdfDocument.Status.Error:
            self._show_empty_state(
                self._t("drawing_page.empty.title.invalid", "Unable to preview drawing"),
                self._document_error_text(),
            )
        elif status == QPdfDocument.Status.Null and not self._current_drawing_path:
            self._show_empty_state(
                self._t("drawing_page.empty.title", "No drawing selected"),
                self._t("drawing_page.empty.body", "Select a drawing to preview it here."),
            )
        self._update_page_status()
        self._update_zoom_status()
        self._update_search_status()
        self._update_open_button_state()

    def _document_error_text(self) -> str:
        error = self._pdf_document.error()
        if error == QPdfDocument.Error.FileNotFound:
            return self._t("drawing_page.message.file_missing", "The PDF file could not be found.")
        if error == QPdfDocument.Error.InvalidFileFormat:
            return self._t("drawing_page.message.invalid_pdf", "The selected file is not a valid PDF.")
        if error == QPdfDocument.Error.IncorrectPassword:
            return self._t("drawing_page.message.password_pdf", "This PDF is password-protected.")
        if error == QPdfDocument.Error.UnsupportedSecurityScheme:
            return self._t("drawing_page.message.unsupported_security", "The PDF security scheme is not supported.")
        return self._t("drawing_page.message.preview_failed", "The PDF preview could not be loaded.")

    def _show_empty_state(self, title: str, body: str) -> None:
        self.empty_title.setText(title)
        self.empty_body.setText(body)
        self.viewer_stack.setCurrentWidget(self.empty_view)

    def _update_page_status(self, *_args) -> None:
        total_pages = int(self._pdf_document.pageCount() or 0)
        current_page = int(self.pdf_view.pageNavigator().currentPage() or 0) + 1 if total_pages else 0
        if total_pages:
            self.page_status.setText(
                self._t(
                    "drawing_page.page_status.ready",
                    "Page {current} / {total}",
                    current=current_page,
                    total=total_pages,
                )
            )
        else:
            self.page_status.setText(self._t("drawing_page.page_status.empty", "Page - / -"))

        ready = self._pdf_document.status() == QPdfDocument.Status.Ready and total_pages > 0
        self.prev_page_btn.setEnabled(ready and current_page > 1)
        self.next_page_btn.setEnabled(ready and current_page < total_pages)

    def _effective_zoom_factor(self) -> float:
        try:
            if self.pdf_view.zoomMode() == QPdfView.ZoomMode.Custom:
                factor = float(self.pdf_view.zoomFactor())
                return factor if factor > 0 else 1.0
        except Exception:
            pass
        navigator = self.pdf_view.pageNavigator()
        try:
            zoom = float(navigator.currentZoom())
        except Exception:
            zoom = 0.0
        if zoom > 0:
            return zoom
        try:
            factor = float(self.pdf_view.zoomFactor())
        except Exception:
            factor = 1.0
        return factor if factor > 0 else 1.0

    def _update_zoom_status(self, *_args) -> None:
        ready = self._pdf_document.status() == QPdfDocument.Status.Ready
        if not ready:
            self.zoom_status.setText("-%")
        else:
            self.zoom_status.setText(f"{round(self._effective_zoom_factor() * 100)}%")

        self.zoom_out_btn.setEnabled(ready)
        self.zoom_in_btn.setEnabled(ready)
        self.fit_width_btn.setEnabled(ready)
        self.fit_page_btn.setEnabled(ready)

    def _fit_width(self) -> None:
        if self._pdf_document.status() != QPdfDocument.Status.Ready:
            return
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self._update_zoom_status()

    def _fit_page(self) -> None:
        if self._pdf_document.status() != QPdfDocument.Status.Ready:
            return
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self._update_zoom_status()

    def _step_zoom(self, multiplier: float) -> None:
        if self._pdf_document.status() != QPdfDocument.Status.Ready:
            return
        new_zoom = max(0.1, min(8.0, self._effective_zoom_factor() * float(multiplier)))
        self.pdf_view.set_custom_zoom(new_zoom, self.pdf_view.viewport().rect().center())
        self._update_zoom_status()

    def _jump_page(self, delta: int) -> None:
        if self._pdf_document.status() != QPdfDocument.Status.Ready:
            return
        current_page = int(self.pdf_view.pageNavigator().currentPage() or 0)
        self._go_to_page(current_page + int(delta))

    def _go_to_page(self, page_index: int) -> None:
        total_pages = int(self._pdf_document.pageCount() or 0)
        if total_pages <= 0:
            return
        page_index = max(0, min(int(page_index), total_pages - 1))
        self.pdf_view.pageNavigator().jump(page_index, QPointF(0.0, 0.0), 0)
        self._update_page_status()

    def _reapply_search_text(self) -> None:
        self._search_model.setSearchString(self.find_input.text().strip())
        self._on_search_model_changed()

    def _focus_first_search_result(self) -> None:
        self.find_input.setFocus()
        if self._pdf_document.status() != QPdfDocument.Status.Ready:
            return
        if self._search_model.rowCount(QModelIndex()) <= 0:
            return
        self.pdf_view.setCurrentSearchResultIndex(0)
        self._focus_search_result(0)

    def _on_find_text_changed(self, text: str) -> None:
        self._search_model.setSearchString((text or "").strip())
        self._on_search_model_changed()

    def _on_search_model_changed(self) -> None:
        if self._pdf_document.status() != QPdfDocument.Status.Ready:
            self._update_search_status()
            return
        search_text = self.find_input.text().strip()
        result_count = self._search_model.rowCount(QModelIndex())
        if search_text and result_count > 0 and self.pdf_view.currentSearchResultIndex() < 0:
            self.pdf_view.setCurrentSearchResultIndex(0)
            self._focus_search_result(0)
        elif not search_text:
            self.pdf_view.setCurrentSearchResultIndex(-1)
        self._refresh_search_overlay()
        self._update_search_status()

    def _step_search_result(self, delta: int) -> None:
        if self._pdf_document.status() != QPdfDocument.Status.Ready:
            return
        count = self._search_model.rowCount(QModelIndex())
        if count <= 0:
            return
        current = int(self.pdf_view.currentSearchResultIndex())
        if current < 0:
            current = 0 if delta >= 0 else count - 1
        else:
            current = max(0, min(count - 1, current + int(delta)))
        self.pdf_view.setCurrentSearchResultIndex(current)
        self._focus_search_result(current)
        self._update_search_status()

    def _refresh_search_overlay(self) -> None:
        overlay = self.pdf_view._overlay
        count = self._search_model.rowCount(QModelIndex())
        if count <= 0 or not self.find_input.text().strip():
            overlay.clear_search_rects()
            return
        page_rects: list[tuple[int, QRectF]] = []
        for i in range(count):
            idx = self._search_model.index(i, 0, QModelIndex())
            if not idx.isValid():
                continue
            page_data = idx.data(QPdfSearchModel.Role.Page.value)
            rect_data = idx.data(QPdfSearchModel.Role.Location.value)
            try:
                page = int(page_data)
            except (TypeError, ValueError):
                continue
            if rect_data is not None:
                try:
                    page_rects.append((page, QRectF(rect_data)))
                except Exception:
                    pass
        overlay.set_search_rects(page_rects)

    def _focus_search_result(self, result_index: int) -> None:
        if self._pdf_document.status() != QPdfDocument.Status.Ready:
            return
        if result_index < 0 or result_index >= self._search_model.rowCount(QModelIndex()):
            return
        model_index = self._search_model.index(result_index, 0, QModelIndex())
        if not model_index.isValid():
            return

        page_data = model_index.data(QPdfSearchModel.Role.Page.value)
        location_data = model_index.data(QPdfSearchModel.Role.Location.value)
        try:
            page = int(page_data)
        except (TypeError, ValueError):
            return

        if isinstance(location_data, QPointF):
            location = QPointF(float(location_data.x()), float(location_data.y()))
        else:
            location = QPointF(0.0, 0.0)

        self.pdf_view.pageNavigator().jump(page, location, 0)
        self.pdf_view.viewport().update()

    def _update_search_status(self, *_args) -> None:
        ready = self._pdf_document.status() == QPdfDocument.Status.Ready
        search_text = self.find_input.text().strip()
        result_count = self._search_model.rowCount(QModelIndex()) if ready else 0
        current = int(self.pdf_view.currentSearchResultIndex()) if ready else -1

        self.find_input.setEnabled(ready)
        if not ready or not search_text:
            self.prev_hit_btn.setEnabled(False)
            self.next_hit_btn.setEnabled(False)
            self.search_result_label.setText("")
            self.search_status.setText(self._t("drawing_page.find.status.idle", "Text search"))
            return

        if result_count <= 0:
            self.prev_hit_btn.setEnabled(False)
            self.next_hit_btn.setEnabled(False)
            self.search_result_label.setText(self._t("drawing_page.find.status.none", "0 matches"))
            self.search_status.setText(self._t("drawing_page.find.status.none", "0 matches"))
            return

        display_index = max(0, current) + 1
        status_text = self._t(
            "drawing_page.find.status.ready",
            "{current} / {total}",
            current=display_index,
            total=result_count,
        )
        self.search_result_label.setText(status_text)
        self.search_status.setText(status_text)
        self.prev_hit_btn.setEnabled(current > 0)
        self.next_hit_btn.setEnabled(current < result_count - 1)

    def _apply_viewer_presentation(self, focus_mode: bool, viewer_width: int, panel_height: int) -> None:
        del focus_mode, viewer_width, panel_height
        self.viewer_surface.setMinimumSize(0, 0)
        self.viewer_surface.setMaximumSize(_MAX_WIDGET_SIZE, _MAX_WIDGET_SIZE)
        self.viewer_surface.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._viewer_host_layout.setAlignment(self.viewer_surface, Qt.Alignment())
        self._position_viewer_overlays()

    def _apply_splitter_layout(self) -> None:
        focus_mode = self._focus_mode_active()
        total_width = max(960, self.splitter.width() or self.width() or 1200)
        total_height = max(640, self.splitter.height() or self.height() or 820)
        layout_signature = (focus_mode, total_width, total_height)
        if self._last_layout_signature == layout_signature and self.splitter.width() > 0:
            return
        self._last_layout_signature = layout_signature

        if focus_mode:
            self.list_host.hide()
            list_width = 0
        else:
            self.list_host.show()
            list_width = min(520, max(380, int(total_width * 0.42)))
        viewer_width = max(1, total_width - list_width)
        self.splitter.setSizes([list_width, viewer_width])
        self._apply_viewer_presentation(focus_mode, viewer_width, total_height)
        if self.splitter.width() <= 0:
            QTimer.singleShot(0, self._apply_splitter_layout)

    def _update_tool_button(self) -> None:
        label_key = f"drawing_page.tool.{self.pdf_view.tool_name()}"
        label_default = self.pdf_view.tool_name().title()
        label = self._t(label_key, label_default)
        self.viewer_tools_btn.setIcon(_toolbar_icon("menu_icon"))
        self.viewer_tools_btn.setToolTip(
            self._t("drawing_page.tool.menu_tip", "Viewer tools") + f" ({label})"
        )

    def _update_markup_buttons(self) -> None:
        self.clear_marks_btn.setEnabled(self.pdf_view.has_markups())

    def _update_open_button_state(self) -> None:
        drawing_path = Path(self._current_drawing_path) if self._current_drawing_path else None
        self.open_external_btn.setEnabled(bool(drawing_path and drawing_path.exists()))
        self._update_markup_buttons()

    def open_selected(self, *_args) -> None:
        drawing = self._selected_drawing() or self._current_drawing
        if not drawing:
            return
        ok = self.draw_service.open_drawing(drawing.get("path", ""))
        if not ok:
            QMessageBox.warning(
                self,
                self._t("setup_page.message.open_failed", "Open failed"),
                self._t("drawing_page.message.open_failed", "Unable to open drawing file."),
            )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_viewer_overlays()
        QTimer.singleShot(0, self._apply_splitter_layout)

    def eventFilter(self, watched, event) -> bool:
        if hasattr(self, "pdf_view") and watched is self.pdf_view and event.type() == QEvent.Resize:
            self._position_viewer_overlays()
        return False

    def apply_localization(self, translate: Callable[[str, str | None], str] | None = None) -> None:
        if translate is not None:
            self._translate = translate

        self.pdf_view.apply_localization(self._translate)
        self.search_toggle_btn.setToolTip(self._t("drawing_page.search_toggle_tip", "Show/hide search"))
        self.search_input.setPlaceholderText(self._t("drawing_page.search_placeholder", "Search drawings..."))
        self.refresh_btn.setText(self._t("drawing_page.action.refresh", "Refresh"))
        self.close_focus_btn.setToolTip(self._t("drawing_page.action.close_focus", "Close focused drawing"))

        self.viewer_tools_btn.setToolTip(self._t("drawing_page.tool.menu_tip", "Viewer tools"))
        self.clear_marks_btn.setToolTip(self._t("drawing_page.tool.clear_marks", "Clear Marks"))
        self.open_external_btn.setToolTip(self._t("drawing_page.action.open", "Open"))
        self.prev_page_btn.setToolTip(self._t("drawing_page.action.page_prev", "Previous page"))
        self.next_page_btn.setToolTip(self._t("drawing_page.action.page_next", "Next page"))
        self.zoom_out_btn.setToolTip(self._t("drawing_page.action.zoom_out", "Zoom out"))
        self.zoom_in_btn.setToolTip(self._t("drawing_page.action.zoom_in", "Zoom in"))
        self.fit_width_btn.setToolTip(self._t("drawing_page.action.fit_width", "Fit Width"))
        self.fit_page_btn.setToolTip(self._t("drawing_page.action.fit_page", "Fit Page"))
        self.find_trigger_btn.setToolTip(self._t("drawing_page.action.find", "Find text"))
        self.find_input.setPlaceholderText(self._t("drawing_page.find.placeholder", "Find text in PDF..."))
        self.prev_hit_btn.setToolTip(self._t("drawing_page.action.find_prev", "Previous hit"))
        self.next_hit_btn.setToolTip(self._t("drawing_page.action.find_next", "Next hit"))

        self._update_tool_button()
        self._update_context_labels()
        self.refresh_list()
