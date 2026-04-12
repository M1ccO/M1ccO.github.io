from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QPoint, QSignalBlocker, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtPdf import QPdfDocument, QPdfSearchModel
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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

from ui.widgets.common import styled_list_item_height
from ui.drawing_page_support import (
    DrawingListCard as _DrawingListCard,
    InteractivePdfView,
    _toolbar_icon,
    _toolbar_icon_with_svg_render_fallback,
    effective_zoom_factor as _effective_zoom_factor_fn,
    fit_page as _fit_page_fn,
    fit_width as _fit_width_fn,
    go_to_page as _go_to_page_fn,
    jump_page as _jump_page_fn,
    step_zoom as _step_zoom_fn,
    update_page_status as _update_page_status_fn,
    update_zoom_status as _update_zoom_status_fn,
    focus_first_search_result as _focus_first_search_result_fn,
    focus_search_result as _focus_search_result_fn,
    on_find_text_changed as _on_find_text_changed_fn,
    on_search_model_changed as _on_search_model_changed_fn,
    reapply_search_text as _reapply_search_text_fn,
    refresh_search_overlay as _refresh_search_overlay_fn,
    step_search_result as _step_search_result_fn,
    update_search_status as _update_search_status_fn,
)

_MAX_WIDGET_SIZE = 16777215


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

        self.search_icon = _toolbar_icon_with_svg_render_fallback("search_icon", 28)
        self.close_icon = _toolbar_icon_with_svg_render_fallback("close_icon", 28)

        self.search_toggle_btn = QToolButton()
        self.search_toggle_btn.setProperty("topBarIconButton", True)
        self.search_toggle_btn.setCheckable(True)
        self.search_toggle_btn.setToolTip(self._t("drawing_page.search_toggle_tip", "Show/hide search"))
        self.search_toggle_btn.setIcon(self.search_icon)
        self.search_toggle_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
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
        self.pdf_view.markupsVisibilityChanged.connect(lambda *_args: self._update_markup_buttons())
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

        self.toggle_marks_btn = self._make_icon_button(
            _toolbar_icon("comment_delete"),
            self._t("drawing_page.tool.hide_marks", "Hide Markings"),
            icon_size=22,
            button_size=36,
        )
        self.toggle_marks_btn.clicked.connect(self.pdf_view.toggle_markups_visibility)
        pdf_controls.addWidget(self.toggle_marks_btn)

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
        _update_page_status_fn(self)

    def _effective_zoom_factor(self) -> float:
        return _effective_zoom_factor_fn(self)

    def _update_zoom_status(self, *_args) -> None:
        _update_zoom_status_fn(self)

    def _fit_width(self) -> None:
        _fit_width_fn(self)

    def _fit_page(self) -> None:
        _fit_page_fn(self)

    def _step_zoom(self, multiplier: float) -> None:
        _step_zoom_fn(self, multiplier)

    def _jump_page(self, delta: int) -> None:
        _jump_page_fn(self, delta)

    def _go_to_page(self, page_index: int) -> None:
        _go_to_page_fn(self, page_index)

    def _reapply_search_text(self) -> None:
        _reapply_search_text_fn(self)

    def _focus_first_search_result(self) -> None:
        _focus_first_search_result_fn(self)

    def _on_find_text_changed(self, text: str) -> None:
        _on_find_text_changed_fn(self, text)

    def _on_search_model_changed(self) -> None:
        _on_search_model_changed_fn(self)

    def _step_search_result(self, delta: int) -> None:
        _step_search_result_fn(self, delta)

    def _refresh_search_overlay(self) -> None:
        _refresh_search_overlay_fn(self)

    def _focus_search_result(self, result_index: int) -> None:
        _focus_search_result_fn(self, result_index)

    def _update_search_status(self, *_args) -> None:
        _update_search_status_fn(self)

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
        has_markups = self.pdf_view.has_markups()
        marks_visible = self.pdf_view.markups_visible()
        button_text = self._t(
            "drawing_page.tool.hide_marks",
            "Hide Markings",
        ) if marks_visible else self._t(
            "drawing_page.tool.show_marks",
            "Show Markings",
        )
        button_icon = _toolbar_icon("comment_delete" if marks_visible else "comment")
        self.toggle_marks_btn.setEnabled(has_markups)
        self.toggle_marks_btn.setText("")
        self.toggle_marks_btn.setIcon(button_icon)
        self.toggle_marks_btn.setToolTip(button_text)

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
        self._update_markup_buttons()
        self._update_context_labels()
        self.refresh_list()
