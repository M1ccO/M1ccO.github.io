from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QGraphicsDropShadowEffect,
    QLabel,
    QSizePolicy,
    QStyledItemDelegate,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_COMBO_SURFACE = QColor("#FCFCFC")
_COMBO_TEXT = QColor("#111111")
_COMBO_HOVER = QColor("#F0F0F0")
_SHADOW_COLOR = QColor(121, 138, 156, 72)


class AutoShrinkLabel(QLabel):
    def __init__(self, text: str = "", parent=None, min_point_size: float = 6):
        super().__init__(text, parent)
        self._min_point_size = min_point_size
        self._orig_point_size = self.font().pointSizeF() or 0
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_font()

    def _adjust_font(self):
        if not self.text():
            return
        if self.wordWrap():
            if not self.property("shrinkWrappedText"):
                if self._orig_point_size:
                    font = self.font()
                    if font.pointSizeF() != self._orig_point_size:
                        font.setPointSizeF(self._orig_point_size)
                        self.setFont(font)
                return
            available_w = max(1, self.width() - 4)
            available_h = max(1, self.height() - 2)
            font = self.font()
            size = self._orig_point_size or font.pointSizeF()
            if size <= 0:
                size = QApplication.font(self).pointSizeF() or 12.0
            while size > self._min_point_size:
                font.setPointSizeF(size)
                fm = QFontMetrics(font)
                rect = fm.boundingRect(0, 0, available_w, 1000, Qt.TextWordWrap, self.text())
                if rect.height() <= available_h:
                    break
                size -= 0.5
            font.setPointSizeF(size)
            self.setFont(font)
            return
        available = max(1, self.width() - 4)
        font = self.font()
        fm = QFontMetrics(font)
        if fm.horizontalAdvance(self.text()) <= available:
            if self._orig_point_size and font.pointSizeF() < self._orig_point_size:
                font.setPointSizeF(self._orig_point_size)
                self.setFont(font)
            return
        size = font.pointSizeF()
        while size > self._min_point_size and fm.horizontalAdvance(self.text()) > available:
            size -= 0.5
            font.setPointSizeF(size)
            fm = QFontMetrics(font)
        self.setFont(font)

    def set_target_point_size(self, point_size: float):
        font = self.font()
        font.setPointSizeF(point_size)
        self._orig_point_size = point_size
        self.setFont(font)
        self._adjust_font()

    def refresh_fit(self):
        self._orig_point_size = self.font().pointSizeF() or self._orig_point_size
        self._adjust_font()


class BorderOnlyComboItemDelegate(QStyledItemDelegate):
    """Paint combobox popup rows with subtle fill hover/selection."""

    def paint(self, painter: QPainter, option, index):
        painter.save()

        painter.fillRect(option.rect, _COMBO_SURFACE)

        model = index.model()
        row_count = model.rowCount(index.parent()) if model is not None else 0
        is_last_row = index.row() >= max(0, row_count - 1)

        if not is_last_row:
            sep_pen = QPen(QColor("#E0E0E0"))
            sep_pen.setWidth(1)
            painter.setPen(sep_pen)
            painter.drawLine(option.rect.left() + 10, option.rect.bottom(), option.rect.right() - 10, option.rect.bottom())

        active = bool(option.state & QStyle.State_MouseOver)
        if active:
            fill_rect = option.rect.adjusted(1, 1, -1, -1)
            painter.fillRect(fill_rect, _COMBO_HOVER)

        text = str(index.data(Qt.DisplayRole) or "")
        text_rect = option.rect.adjusted(12, 0, -12, 0)
        painter.setPen(_COMBO_TEXT)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)

        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), 44))


def _reposition_combo_popup(combo: QComboBox):
    view = combo.view()
    if view is None:
        return
    popup = view.window()
    if popup is None or not popup.isVisible():
        return

    bottom_left = combo.mapToGlobal(combo.rect().bottomLeft())
    screen = combo.screen() or QGuiApplication.screenAt(bottom_left) or QGuiApplication.primaryScreen()
    if screen is None:
        return

    available = screen.availableGeometry()
    margin = 4
    available_below = available.bottom() - bottom_left.y() - margin
    target_height = popup.height()
    if available_below > 0:
        target_height = max(80, min(target_height, available_below))

    popup.resize(max(combo.width(), popup.width()), target_height)
    popup.move(bottom_left.x(), bottom_left.y())


def add_shadow(widget, blur_radius: int = 6, x_offset: int = 0, y_offset: int = 1):
    """Apply a subtle drop shadow effect to *widget*."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur_radius)
    effect.setOffset(x_offset, y_offset)
    effect.setColor(_SHADOW_COLOR)
    widget.setGraphicsEffect(effect)


class _ComboHoverFilter(QObject):
    def __init__(self, combo):
        super().__init__(combo)
        self.combo = combo

    def eventFilter(self, obj, event):
        event_type = event.type()
        if event_type in (QEvent.Enter, QEvent.HoverEnter):
            self.combo.setProperty("hovered", True)
            self.combo.style().polish(self.combo)
            self.combo.update()
        elif event_type in (QEvent.Leave, QEvent.HoverLeave, QEvent.Hide, QEvent.FocusOut):
            self.combo.setProperty("hovered", False)
            self.combo.style().polish(self.combo)
            self.combo.update()
        return False


class _ComboWheelGuardFilter(QObject):
    def __init__(self, combo):
        super().__init__(combo)
        self.combo = combo

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and not self.combo.view().isVisible():
            return True
        return False


class _ComboPopupResetFilter(QObject):
    def __init__(self, combo):
        super().__init__(combo)
        self.combo = combo

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Hide, QEvent.HideToParent):
            _reset_popup_visual_state(self.combo)
        return False


class _ComboPopupPositionFilter(QObject):
    def __init__(self, combo):
        super().__init__(combo)
        self.combo = combo

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show:
            QTimer.singleShot(0, lambda: _reposition_combo_popup(self.combo))
        return False


class _ComboPopupWindowStyleFilter(QObject):
    """Re-apply popup-window style each time the combo popup opens.

    Qt creates the floating popup frame lazily on first showPopup(), so
    view.window() at apply_shared_dropdown_style() time still points to the
    host dialog.  By catching QEvent.Show on the view we get the real frame.
    """

    def __init__(self, combo, view_palette, popup_height: int | None):
        super().__init__(combo)
        self.combo = combo
        self.view_palette = view_palette
        self.popup_height = popup_height

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show:
            view = self.combo.view()
            if view is None:
                return False
            popup_window = view.window()
            if popup_window is not self.combo:  # genuine popup frame
                popup_window.setAttribute(Qt.WA_StyledBackground, True)
                popup_window.setPalette(self.view_palette)
                popup_window.setStyleSheet(
                    'background-color: #FCFCFC; border: 1px solid #c8d0d8;'
                )
                if self.popup_height is not None:
                    popup_window.setMinimumHeight(0)
                    popup_window.setMaximumHeight(self.popup_height + 6)
        return False


def _reset_popup_visual_state(combo):
    view = combo.view()
    if view is None:
        return
    selection_model = view.selectionModel()
    if selection_model is not None:
        selection_model.clearSelection()
    view.clearSelection()
    view.viewport().update()


def _is_widget_in_tree(source: QWidget, target: QWidget) -> bool:
    widget = source
    while widget is not None:
        if widget is target:
            return True
        widget = widget.parentWidget()
    return False


def clear_focused_dropdown_on_outside_click(event_source: QWidget, top_window: QWidget) -> bool:
    """Clear focused combobox when a click occurs outside the combo and its popup."""
    if not isinstance(event_source, QWidget) or event_source.window() is not top_window:
        return False

    focused = QApplication.focusWidget()
    if not isinstance(focused, QComboBox) or focused.window() is not top_window:
        return False

    if _is_widget_in_tree(event_source, focused):
        return False

    popup = focused.view().window() if focused.view() is not None else None
    if popup is not None and popup.isVisible() and _is_widget_in_tree(event_source, popup):
        return False

    focused.clearFocus()
    return True


class CollapsibleGroup(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.base_title = title
        self.toggle = QToolButton(text=f"{title} (collapsed)")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(False)
        self.toggle.toggled.connect(self._on_toggled)
        self.body = QWidget()
        self.body.setVisible(False)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 6, 0, 0)
        self.body_layout.setSpacing(6)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle)
        layout.addWidget(self.body)

    def _on_toggled(self, checked):
        self.body.setVisible(checked)
        self.toggle.setText(f"{self.base_title} ({'expanded' if checked else 'collapsed'})")


def apply_shared_dropdown_style(combo):
    """Apply unified popup and hover behavior for comboboxes across the app."""
    combo.setProperty('hovered', False)
    combo.setAttribute(Qt.WA_Hover, True)
    combo.setAttribute(Qt.WA_StyledBackground, True)

    combo_palette = QPalette(combo.palette())
    combo_palette.setColor(QPalette.Button, QColor('#FAFAFA'))
    combo_palette.setColor(QPalette.Base, _COMBO_SURFACE)
    combo_palette.setColor(QPalette.Window, _COMBO_SURFACE)
    combo_palette.setColor(QPalette.Text, _COMBO_TEXT)
    combo_palette.setColor(QPalette.ButtonText, _COMBO_TEXT)
    combo_palette.setColor(QPalette.WindowText, _COMBO_TEXT)
    combo_palette.setColor(QPalette.Highlight, _COMBO_HOVER)
    combo_palette.setColor(QPalette.HighlightedText, _COMBO_TEXT)
    combo.setPalette(combo_palette)

    view = combo.view()
    view.setMouseTracking(True)
    view.viewport().setMouseTracking(True)
    view.setAutoFillBackground(True)
    view.viewport().setAutoFillBackground(True)
    view.setItemDelegate(BorderOnlyComboItemDelegate(view))

    view_palette = QPalette(view.palette())
    view_palette.setColor(QPalette.Base, _COMBO_SURFACE)
    view_palette.setColor(QPalette.Window, _COMBO_SURFACE)
    view_palette.setColor(QPalette.Text, _COMBO_TEXT)
    view_palette.setColor(QPalette.WindowText, _COMBO_TEXT)
    view_palette.setColor(QPalette.Highlight, _COMBO_HOVER)
    view_palette.setColor(QPalette.HighlightedText, _COMBO_TEXT)
    view.setPalette(view_palette)
    view.viewport().setPalette(view_palette)

    popup_row_height = combo.property('dropdownPopupRowHeight')
    if popup_row_height is None:
        size_profile = str(combo.property('dropdownSizeProfile') or '')
        if size_profile == 'compact':
            popup_row_height = 22
        else:
            popup_row_height = 44
    if popup_row_height is not None:
        try:
            popup_row_height = int(popup_row_height)
        except (TypeError, ValueError):
            popup_row_height = None

    popup_height: int | None = None
    if popup_row_height:
        max_rows = max(1, combo.maxVisibleItems())
        popup_height = max_rows * popup_row_height
        view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        view.setMinimumHeight(0)
        view.setMaximumHeight(popup_height)

    hover_filter = _ComboHoverFilter(combo)
    combo.installEventFilter(hover_filter)
    view.installEventFilter(hover_filter)
    view.viewport().installEventFilter(hover_filter)

    wheel_guard = _ComboWheelGuardFilter(combo)
    combo.installEventFilter(wheel_guard)

    popup_reset_filter = _ComboPopupResetFilter(combo)
    view.installEventFilter(popup_reset_filter)
    view.viewport().installEventFilter(popup_reset_filter)
    view.window().installEventFilter(popup_reset_filter)

    # Style the popup window on every Show so the real floating frame is always
    # styled — Qt creates it lazily and view.window() is wrong before first open.
    popup_window_style_filter = _ComboPopupWindowStyleFilter(combo, view_palette, popup_height)
    view.installEventFilter(popup_window_style_filter)

    popup_position_filter = _ComboPopupPositionFilter(combo)
    view.window().installEventFilter(popup_position_filter)

    combo.activated.connect(lambda _idx: QTimer.singleShot(0, lambda: _reset_popup_visual_state(combo)))

    combo._shared_dropdown_hover_filter = hover_filter
    combo._shared_dropdown_wheel_guard = wheel_guard
    combo._shared_dropdown_popup_reset_filter = popup_reset_filter
    combo._shared_dropdown_popup_window_style_filter = popup_window_style_filter
    combo._shared_dropdown_popup_position_filter = popup_position_filter

    # Force QSS to be evaluated immediately so the combo looks correct before
    # the user ever hovers over it (the hover filter also calls polish, but that
    # only fires on first mouse-enter).
    combo.style().unpolish(combo)
    combo.style().polish(combo)
    combo.update()


def repolish_widget(widget: QWidget | None):
    """Re-apply QSS after dynamic property changes."""
    if widget is None:
        return
    widget.ensurePolished()
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.updateGeometry()
    widget.update()


def styled_list_item_height(widget: QWidget | None, spacing: int = 0) -> int:
    """Return a list-item height driven by the widget's polished style metrics."""
    if widget is None:
        return max(0, spacing)
    repolish_widget(widget)
    widget.adjustSize()
    return max(
        widget.sizeHint().height(),
        widget.minimumSizeHint().height(),
        widget.minimumHeight(),
    ) + max(0, spacing)
