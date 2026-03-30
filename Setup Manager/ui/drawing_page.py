from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QModelIndex, QPoint, QPointF, QSignalBlocker, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QActionGroup, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtPdf import QPdfDocument, QPdfSearchModel
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
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


def _toolbar_icon(name: str) -> QIcon:
    png = ICONS_DIR / "tools" / f"{name}.png"
    if png.exists():
        return QIcon(str(png))
    shared_png = TOOL_LIBRARY_TOOL_ICONS_DIR / f"{name}.png"
    if shared_png.exists():
        return QIcon(str(shared_png))
    svg = ICONS_DIR / "tools" / f"{name}.svg"
    if svg.exists():
        return QIcon(str(svg))
    shared_svg = TOOL_LIBRARY_TOOL_ICONS_DIR / f"{name}.svg"
    if shared_svg.exists():
        return QIcon(str(shared_svg))
    return QIcon()


@dataclass
class _MarkerStroke:
    color: QColor
    width: float
    points: list[QPointF] = field(default_factory=list)


class _MarkerOverlay(QWidget):
    def __init__(self, pdf_view, parent=None):
        super().__init__(parent)
        self._pdf_view = pdf_view
        self._strokes: list[_MarkerStroke] = []
        self._active_stroke: _MarkerStroke | None = None
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
        return bool(self._strokes or self._active_stroke)

    def clear_strokes(self) -> None:
        if not self.has_strokes():
            return
        self._strokes.clear()
        self._active_stroke = None
        self.update()

    def scale_strokes(self, ratio: float) -> None:
        if ratio <= 0:
            return
        for stroke in self._strokes:
            stroke.width *= ratio
            stroke.points = [QPointF(point.x() * ratio, point.y() * ratio) for point in stroke.points]
        if self._active_stroke is not None:
            self._active_stroke.width *= ratio
            self._active_stroke.points = [
                QPointF(point.x() * ratio, point.y() * ratio) for point in self._active_stroke.points
            ]
        self.update()

    def begin_stroke(self, viewport_pos: QPoint, color: QColor, width: float) -> None:
        self._active_stroke = _MarkerStroke(QColor(color), float(width), [self._content_point(viewport_pos)])
        self.update()

    def append_stroke(self, viewport_pos: QPoint) -> None:
        if self._active_stroke is None:
            return
        point = self._content_point(viewport_pos)
        if self._active_stroke.points and point == self._active_stroke.points[-1]:
            return
        self._active_stroke.points.append(point)
        self.update()

    def finish_stroke(self, viewport_pos: QPoint | None = None) -> bool:
        if self._active_stroke is None:
            return False
        if viewport_pos is not None:
            self.append_stroke(viewport_pos)
        if not self._active_stroke.points:
            self._active_stroke = None
            self.update()
            return False
        self._strokes.append(self._active_stroke)
        self._active_stroke = None
        self.update()
        return True

    def cancel_stroke(self) -> None:
        if self._active_stroke is None:
            return
        self._active_stroke = None
        self.update()

    def _content_point(self, viewport_pos: QPoint) -> QPointF:
        return QPointF(
            float(viewport_pos.x() + self._pdf_view.horizontalScrollBar().value()),
            float(viewport_pos.y() + self._pdf_view.verticalScrollBar().value()),
        )

    def _viewport_point(self, content_pos: QPointF) -> QPointF:
        return QPointF(
            content_pos.x() - self._pdf_view.horizontalScrollBar().value(),
            content_pos.y() - self._pdf_view.verticalScrollBar().value(),
        )

    def _draw_stroke(self, painter: QPainter, stroke: _MarkerStroke) -> None:
        if not stroke.points:
            return
        pen = QPen(stroke.color, stroke.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        if len(stroke.points) == 1:
            point = self._viewport_point(stroke.points[0])
            radius = stroke.width / 2.0
            painter.drawEllipse(point, radius, radius)
            return
        path = QPainterPath(self._viewport_point(stroke.points[0]))
        for point in stroke.points[1:]:
            path.lineTo(self._viewport_point(point))
        painter.drawPath(path)

    def paintEvent(self, event) -> None:
        del event
        if not self.has_strokes():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for stroke in self._strokes:
            self._draw_stroke(painter, stroke)
        if self._active_stroke is not None:
            self._draw_stroke(painter, self._active_stroke)


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
    _WIDTH_OPTIONS = {
        "thin": 10.0,
        "medium": 16.0,
        "bold": 24.0,
    }

    def __init__(self, parent=None, translate: Callable[[str, str | None], str] | None = None):
        super().__init__(parent)
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or "")
        self._tool = self.TOOL_SELECT
        self._hand_drag_active = False
        self._last_drag_pos = QPoint()
        self._marker_color_key = "yellow"
        self._marker_width_key = "medium"
        self._last_markup_zoom: float | None = None

        self.setPageMode(QPdfView.PageMode.MultiPage)
        self.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.viewport().installEventFilter(self)
        self.viewport().setMouseTracking(True)

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
            return _toolbar_icon("import_export")
        if self._tool == self.TOOL_MARKER:
            return _toolbar_icon("comment")
        return _toolbar_icon("select")

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
        return QColor(self._COLOR_OPTIONS.get(self._marker_color_key, self._COLOR_OPTIONS["yellow"]))

    def marker_width(self) -> float:
        return float(self._WIDTH_OPTIONS.get(self._marker_width_key, self._WIDTH_OPTIONS["medium"]))

    def set_tool(self, tool_name: str) -> None:
        tool_name = str(tool_name or "").strip().lower()
        if tool_name not in {self.TOOL_SELECT, self.TOOL_HAND, self.TOOL_MARKER}:
            tool_name = self.TOOL_SELECT
        if tool_name == self._tool and not self._hand_drag_active:
            return
        self._tool = tool_name
        self._hand_drag_active = False
        self._overlay.cancel_stroke()
        self._apply_cursor()
        self.toolChanged.emit(self._tool)

    def set_marker_color_key(self, color_key: str) -> None:
        if color_key in self._COLOR_OPTIONS:
            self._marker_color_key = color_key

    def set_marker_width_key(self, width_key: str) -> None:
        if width_key in self._WIDTH_OPTIONS:
            self._marker_width_key = width_key

    def sync_markup_zoom_reference(self) -> None:
        zoom = self._effective_zoom_factor()
        if zoom > 0:
            self._last_markup_zoom = zoom

    def open_tools_menu(self, global_pos) -> None:
        menu = QMenu(self)
        tool_group = QActionGroup(menu)
        tool_group.setExclusive(True)

        for tool_name, icon, text in (
            (self.TOOL_SELECT, _toolbar_icon("select"), self._t("drawing_page.tool.select", "Select")),
            (self.TOOL_HAND, _toolbar_icon("import_export"), self._t("drawing_page.tool.hand", "Hand")),
            (self.TOOL_MARKER, _toolbar_icon("comment"), self._t("drawing_page.tool.marker", "Marker")),
        ):
            action = menu.addAction(icon, text)
            action.setCheckable(True)
            action.setChecked(tool_name == self._tool)
            action.setData(("tool", tool_name))
            tool_group.addAction(action)

        menu.addSeparator()

        color_menu = menu.addMenu(self._t("drawing_page.tool.color", "Marker Color"))
        for color_key in ("yellow", "green", "blue", "pink", "red"):
            action = color_menu.addAction(
                self._color_icon(self._COLOR_OPTIONS[color_key]),
                self._t(f"drawing_page.color.{color_key}", color_key.title()),
            )
            action.setCheckable(True)
            action.setChecked(color_key == self._marker_color_key)
            action.setData(("color", color_key))

        width_menu = menu.addMenu(self._t("drawing_page.tool.width", "Marker Width"))
        for width_key in ("thin", "medium", "bold"):
            action = width_menu.addAction(
                self._t(f"drawing_page.tool.width.{width_key}", width_key.title())
            )
            action.setCheckable(True)
            action.setChecked(width_key == self._marker_width_key)
            action.setData(("width", width_key))

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
        if action_type == "width":
            self.set_marker_width_key(str(value))
            return
        if action_type == "clear":
            self.clear_markups()

    def _color_icon(self, color: QColor) -> QIcon:
        swatch = QPixmap(18, 18)
        swatch.fill(Qt.transparent)
        painter = QPainter(swatch)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#2b3640"), 1))
        painter.setBrush(color)
        painter.drawEllipse(1, 1, 16, 16)
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
            cursor = Qt.ArrowCursor
        self.viewport().setCursor(cursor)

    def _on_zoom_factor_changed(self, *_args) -> None:
        zoom = self._effective_zoom_factor()
        if zoom <= 0:
            return
        if self._last_markup_zoom and self.has_markups():
            ratio = zoom / self._last_markup_zoom
            if abs(ratio - 1.0) > 0.001:
                self._overlay.scale_strokes(ratio)
        self._last_markup_zoom = zoom

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                multiplier = 1.15 if delta > 0 else 1 / 1.15
                new_zoom = max(0.1, min(8.0, self._effective_zoom_factor() * multiplier))
                self.setZoomMode(QPdfView.ZoomMode.Custom)
                self.setZoomFactor(new_zoom)
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
                if self._tool == self.TOOL_HAND:
                    self._hand_drag_active = True
                    self._last_drag_pos = event.pos()
                    self._apply_cursor()
                    return True
                if self._tool == self.TOOL_MARKER:
                    self._overlay.begin_stroke(event.pos(), self.marker_color(), self.marker_width())
                    return True
            if event.type() == QEvent.MouseMove:
                if self._tool == self.TOOL_HAND and self._hand_drag_active:
                    delta = event.pos() - self._last_drag_pos
                    self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
                    self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
                    self._last_drag_pos = event.pos()
                    return True
                if self._tool == self.TOOL_MARKER and event.buttons() & Qt.LeftButton:
                    self._overlay.append_stroke(event.pos())
                    return True
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                if self._tool == self.TOOL_HAND and self._hand_drag_active:
                    self._hand_drag_active = False
                    self._apply_cursor()
                    return True
                if self._tool == self.TOOL_MARKER:
                    created = self._overlay.finish_stroke(event.pos())
                    if created:
                        self.markupsChanged.emit(True)
                    return True
        return super().eventFilter(watched, event)


class _DrawingListCard(QFrame):
    def __init__(self, drawing: dict, parent=None):
        super().__init__(parent)
        self.drawing = dict(drawing or {})
        self.setProperty("toolListCard", True)
        self.setProperty("drawingRowCard", True)
        self.setProperty("selected", False)
        self.setMinimumHeight(58)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(0)

        title = self.drawing.get("drawing_id") or self.drawing.get("name") or "-"
        self.title_label = QLabel(str(title))
        self.title_label.setProperty("toolCardValue", True)
        self.title_label.setProperty("drawingRowTitle", True)
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.title_label)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", bool(selected))
        repolish_widget(self)


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

        self.close_focus_btn = self._make_icon_button(
            self.close_icon,
            self._t("drawing_page.action.close_focus", "Close focused drawing"),
            icon_size=16,
        )
        self.close_focus_btn.clicked.connect(self._dismiss_focus_viewer)
        self.close_focus_btn.setVisible(False)
        controls.addWidget(self.close_focus_btn, 0, Qt.AlignRight)

        root.addWidget(controls_frame)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)

        self._build_list_panel()
        self._build_viewer_panel()

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
    ) -> QToolButton:
        button = QToolButton()
        button.setProperty("topBarIconButton", True)
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        button.setFixedSize(30, 30)
        if not icon.isNull():
            button.setIcon(icon)
            button.setIconSize(QSize(icon_size, icon_size))
        elif fallback_text:
            button.setText(fallback_text)
        return button

    def _build_list_panel(self) -> None:
        self.list_host = QFrame()
        self.list_host.setProperty("catalogShell", True)
        list_layout = QVBoxLayout(self.list_host)
        list_layout.setContentsMargins(8, 8, 8, 8)
        list_layout.setSpacing(8)

        self.list_title = QLabel(self._t("drawing_page.list.title", "Drawing"))
        self.list_title.setProperty("sectionTitle", True)
        list_layout.addWidget(self.list_title)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("drawingList")
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setSpacing(6)
        self.list_widget.currentItemChanged.connect(self._on_current_item_changed)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.open_selected())
        list_layout.addWidget(self.list_widget, 1)

        self.splitter.addWidget(self.list_host)

    def _build_viewer_panel(self) -> None:
        viewer_host = QWidget()
        viewer_layout = QVBoxLayout(viewer_host)
        viewer_layout.setContentsMargins(8, 8, 8, 8)
        viewer_layout.setSpacing(0)
        self._viewer_host_layout = viewer_layout

        self.viewer_surface = QFrame()
        self.viewer_surface.setProperty("catalogShell", True)
        viewer_surface_layout = QVBoxLayout(self.viewer_surface)
        viewer_surface_layout.setContentsMargins(10, 10, 10, 10)
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
        self.viewer_stack.addWidget(self.pdf_view)

        viewer_surface_layout.addWidget(self.viewer_stack, 1)
        viewer_layout.addWidget(self.viewer_surface, 1)
        self.splitter.addWidget(viewer_host)

    def _build_pdf_toolbar(self, viewer_layout: QVBoxLayout) -> None:
        pdf_toolbar = QFrame()
        pdf_toolbar.setProperty("detailCard", True)
        pdf_controls = QHBoxLayout(pdf_toolbar)
        pdf_controls.setContentsMargins(8, 6, 8, 6)
        pdf_controls.setSpacing(6)

        self.viewer_tools_btn = self._make_icon_button(
            _toolbar_icon("select"),
            self._t("drawing_page.tool.menu_tip", "Viewer tools"),
        )
        self.viewer_tools_btn.clicked.connect(self._open_viewer_tools_menu_from_button)
        pdf_controls.addWidget(self.viewer_tools_btn)

        self.clear_marks_btn = self._make_icon_button(
            _toolbar_icon("comment_delete"),
            self._t("drawing_page.tool.clear_marks", "Clear Marks"),
        )
        self.clear_marks_btn.clicked.connect(self.pdf_view.clear_markups)
        pdf_controls.addWidget(self.clear_marks_btn)

        self.open_external_btn = self._make_icon_button(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton),
            self._t("drawing_page.action.open", "Open"),
            fallback_text=self._t("drawing_page.action.open", "Open"),
        )
        self.open_external_btn.clicked.connect(self.open_selected)
        pdf_controls.addWidget(self.open_external_btn)

        self.prev_page_btn = self._make_icon_button(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack),
            self._t("drawing_page.action.page_prev", "Previous page"),
            fallback_text="<",
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
        )
        self.next_page_btn.clicked.connect(lambda: self._jump_page(1))
        pdf_controls.addWidget(self.next_page_btn)

        self.zoom_out_btn = self._make_icon_button(
            QIcon(),
            self._t("drawing_page.action.zoom_out", "Zoom out"),
            fallback_text="-",
        )
        self.zoom_out_btn.clicked.connect(lambda: self._step_zoom(1 / 1.15))
        pdf_controls.addWidget(self.zoom_out_btn)

        self.zoom_status = QLabel(self._t("drawing_page.zoom_status.empty", "Zoom -"))
        self.zoom_status.setProperty("drawingViewerStat", True)
        pdf_controls.addWidget(self.zoom_status)

        self.zoom_in_btn = self._make_icon_button(
            QIcon(),
            self._t("drawing_page.action.zoom_in", "Zoom in"),
            fallback_text="+",
        )
        self.zoom_in_btn.clicked.connect(lambda: self._step_zoom(1.15))
        pdf_controls.addWidget(self.zoom_in_btn)

        self.fit_width_btn = self._make_text_action_button(self._t("drawing_page.action.fit_width", "Width"), min_width=64)
        self.fit_width_btn.clicked.connect(self._fit_width)
        pdf_controls.addWidget(self.fit_width_btn)

        self.fit_page_btn = self._make_text_action_button(self._t("drawing_page.action.fit_page", "Page"), min_width=58)
        self.fit_page_btn.clicked.connect(self._fit_page)
        pdf_controls.addWidget(self.fit_page_btn)

        pdf_controls.addStretch(1)

        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText(self._t("drawing_page.find.placeholder", "Find text in PDF..."))
        self.find_input.setMaximumWidth(220)
        self.find_input.textChanged.connect(self._on_find_text_changed)
        pdf_controls.addWidget(self.find_input)

        self.prev_hit_btn = self._make_icon_button(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack),
            self._t("drawing_page.action.find_prev", "Previous hit"),
            fallback_text="<",
        )
        self.prev_hit_btn.clicked.connect(lambda: self._step_search_result(-1))
        pdf_controls.addWidget(self.prev_hit_btn)

        self.next_hit_btn = self._make_icon_button(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward),
            self._t("drawing_page.action.find_next", "Next hit"),
            fallback_text=">",
        )
        self.next_hit_btn.clicked.connect(lambda: self._step_search_result(1))
        pdf_controls.addWidget(self.next_hit_btn)

        self.search_status = QLabel(self._t("drawing_page.find.status.idle", "Text search"))
        self.search_status.setProperty("drawingViewerStat", True)
        pdf_controls.addWidget(self.search_status)

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
        return bool(self._setup_context.get("selected")) and not self._focus_viewer_dismissed

    def _dismiss_focus_viewer(self) -> None:
        if not self._focus_mode_active():
            return
        self._focus_viewer_dismissed = True
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
            self._fit_width()
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
            self.zoom_status.setText(self._t("drawing_page.zoom_status.empty", "Zoom -"))
        else:
            mode = self.pdf_view.zoomMode()
            if mode == QPdfView.ZoomMode.FitToWidth:
                prefix = self._t("drawing_page.zoom_status.fit_width", "Fit Width")
            elif mode == QPdfView.ZoomMode.FitInView:
                prefix = self._t("drawing_page.zoom_status.fit_page", "Fit Page")
            else:
                prefix = self._t("drawing_page.zoom_status.custom", "Zoom")
            self.zoom_status.setText(f"{prefix} {round(self._effective_zoom_factor() * 100)}%")

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
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.pdf_view.setZoomFactor(new_zoom)
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
        elif not search_text:
            self.pdf_view.setCurrentSearchResultIndex(-1)
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
        self._update_search_status()

    def _update_search_status(self, *_args) -> None:
        ready = self._pdf_document.status() == QPdfDocument.Status.Ready
        search_text = self.find_input.text().strip()
        result_count = self._search_model.rowCount(QModelIndex()) if ready else 0
        current = int(self.pdf_view.currentSearchResultIndex()) if ready else -1

        self.find_input.setEnabled(ready)
        if not ready or not search_text:
            self.prev_hit_btn.setEnabled(False)
            self.next_hit_btn.setEnabled(False)
            self.search_status.setText(self._t("drawing_page.find.status.idle", "Text search"))
            return

        if result_count <= 0:
            self.prev_hit_btn.setEnabled(False)
            self.next_hit_btn.setEnabled(False)
            self.search_status.setText(self._t("drawing_page.find.status.none", "0 matches"))
            return

        display_index = max(0, current) + 1
        self.search_status.setText(
            self._t(
                "drawing_page.find.status.ready",
                "Match {current} / {total}",
                current=display_index,
                total=result_count,
            )
        )
        self.prev_hit_btn.setEnabled(current > 0)
        self.next_hit_btn.setEnabled(current < result_count - 1)

    def _apply_viewer_presentation(self, focus_mode: bool, viewer_width: int, panel_height: int) -> None:
        if focus_mode:
            self.viewer_surface.setMinimumSize(0, 0)
            self.viewer_surface.setMaximumSize(_MAX_WIDGET_SIZE, _MAX_WIDGET_SIZE)
            self.viewer_surface.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._viewer_host_layout.setAlignment(self.viewer_surface, Qt.Alignment())
            return

        available_width = max(300, viewer_width - 24)
        available_height = max(260, panel_height - 24)
        preview_width = min(680, max(380, int(viewer_width * 0.78)), available_width)
        preview_height = min(500, max(320, int(panel_height * 0.58)), available_height)

        self.viewer_surface.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.viewer_surface.setFixedSize(preview_width, preview_height)
        self._viewer_host_layout.setAlignment(self.viewer_surface, Qt.AlignTop | Qt.AlignRight)

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
            list_width = min(520, max(360, int(total_width * 0.42)))
        viewer_width = max(1, total_width - list_width)
        self.splitter.setSizes([list_width, viewer_width])
        self._apply_viewer_presentation(focus_mode, viewer_width, total_height)
        if self.splitter.width() <= 0:
            QTimer.singleShot(0, self._apply_splitter_layout)

    def _update_tool_button(self) -> None:
        icon = self.pdf_view.tool_icon()
        label_key = f"drawing_page.tool.{self.pdf_view.tool_name()}"
        label_default = self.pdf_view.tool_name().title()
        label = self._t(label_key, label_default)
        self.viewer_tools_btn.setIcon(icon)
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
        QTimer.singleShot(0, self._apply_splitter_layout)

    def apply_localization(self, translate: Callable[[str, str | None], str] | None = None) -> None:
        if translate is not None:
            self._translate = translate

        self.pdf_view.apply_localization(self._translate)
        self.search_toggle_btn.setToolTip(self._t("drawing_page.search_toggle_tip", "Show/hide search"))
        self.search_input.setPlaceholderText(self._t("drawing_page.search_placeholder", "Search drawings..."))
        self.refresh_btn.setText(self._t("drawing_page.action.refresh", "Refresh"))
        self.list_title.setText(self._t("drawing_page.list.title", "Drawing"))
        self.close_focus_btn.setToolTip(self._t("drawing_page.action.close_focus", "Close focused drawing"))

        self.viewer_tools_btn.setToolTip(self._t("drawing_page.tool.menu_tip", "Viewer tools"))
        self.clear_marks_btn.setToolTip(self._t("drawing_page.tool.clear_marks", "Clear Marks"))
        self.open_external_btn.setToolTip(self._t("drawing_page.action.open", "Open"))
        self.prev_page_btn.setToolTip(self._t("drawing_page.action.page_prev", "Previous page"))
        self.next_page_btn.setToolTip(self._t("drawing_page.action.page_next", "Next page"))
        self.zoom_out_btn.setToolTip(self._t("drawing_page.action.zoom_out", "Zoom out"))
        self.zoom_in_btn.setToolTip(self._t("drawing_page.action.zoom_in", "Zoom in"))
        self.fit_width_btn.setText(self._t("drawing_page.action.fit_width", "Fit Width"))
        self.fit_page_btn.setText(self._t("drawing_page.action.fit_page", "Fit Page"))
        self.find_input.setPlaceholderText(self._t("drawing_page.find.placeholder", "Find text in PDF..."))
        self.prev_hit_btn.setToolTip(self._t("drawing_page.action.find_prev", "Previous hit"))
        self.next_hit_btn.setToolTip(self._t("drawing_page.action.find_next", "Next hit"))

        self._update_tool_button()
        self._update_context_labels()
        self.refresh_list()
