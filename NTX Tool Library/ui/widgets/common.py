from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget, QToolButton, QVBoxLayout, QLabel, QSizePolicy, QStyledItemDelegate, QStyle


class AutoShrinkLabel(QLabel):
    def __init__(self, text='', parent=None, min_point_size=6):
        super().__init__(text, parent)
        self._min_point_size = min_point_size
        self._orig_point_size = self.font().pointSizeF() or 0
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_font()

    def _adjust_font(self):
        # shrink the font if the text no longer fits in the available width
        if not self.text():
            return
        if self.wordWrap():
            if self._orig_point_size:
                font = self.font()
                if font.pointSizeF() != self._orig_point_size:
                    font.setPointSizeF(self._orig_point_size)
                    self.setFont(font)
            return
        available = max(1, self.width() - 4)
        font = self.font()
        fm = QFontMetrics(font)
        if fm.horizontalAdvance(self.text()) <= available:
            # text fits; restore original point size if we previously shrunk
            if self._orig_point_size and font.pointSizeF() < self._orig_point_size:
                font.setPointSizeF(self._orig_point_size)
                self.setFont(font)
            return
        # otherwise repeatedly decrease until it fits or hits min
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

        base_color = QColor('#FCFCFC')
        painter.fillRect(option.rect, base_color)

        model = index.model()
        row_count = model.rowCount(index.parent()) if model is not None else 0
        is_last_row = index.row() >= max(0, row_count - 1)

        # Draw a consistent 1px separator between rows.
        if not is_last_row:
            sep_pen = QPen(QColor('#E0E0E0'))
            sep_pen.setWidth(1)
            painter.setPen(sep_pen)
            painter.drawLine(option.rect.left() + 10, option.rect.bottom(), option.rect.right() - 10, option.rect.bottom())

        active = bool(option.state & QStyle.State_Selected or option.state & QStyle.State_MouseOver)
        if active:
            fill_rect = option.rect.adjusted(1, 1, -1, -1)
            painter.fillRect(fill_rect, QColor('#F0F0F0'))

        text = str(index.data(Qt.DisplayRole) or '')
        text_rect = option.rect.adjusted(12, 0, -12, 0)
        painter.setPen(QColor('#000000'))
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)

        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), 32))


from PySide6.QtWidgets import QGraphicsDropShadowEffect


def add_shadow(widget, blur_radius=6, x_offset=0, y_offset=1):
    """Apply a subtle drop shadow effect to *widget*."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur_radius)
    effect.setOffset(x_offset, y_offset)
    effect.setColor(widget.palette().color(widget.backgroundRole()).darker(110))
    widget.setGraphicsEffect(effect)


class _ComboHoverFilter(QObject):
    def __init__(self, combo):
        super().__init__(combo)
        self.combo = combo

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Enter:
            self.combo.setProperty('hovered', True)
            self.combo.style().polish(self.combo)
            self.combo.update()
        elif event.type() == QEvent.Leave:
            self.combo.setProperty('hovered', False)
            self.combo.style().polish(self.combo)
            self.combo.update()
        return False


class _ComboWheelGuardFilter(QObject):
    def __init__(self, combo):
        super().__init__(combo)
        self.combo = combo

    def eventFilter(self, obj, event):
        # Prevent accidental value changes when scrolling over a closed combo.
        if event.type() == QEvent.Wheel and not self.combo.view().isVisible():
            return True
        return False


def apply_shared_dropdown_style(combo):
    """Apply unified popup and hover behavior for comboboxes across the app."""
    combo.setProperty('hovered', False)
    combo.setAttribute(Qt.WA_Hover, True)

    view = combo.view()
    view.setMouseTracking(True)
    view.viewport().setMouseTracking(True)
    view.setItemDelegate(BorderOnlyComboItemDelegate(view))

    hover_filter = _ComboHoverFilter(combo)
    combo.installEventFilter(hover_filter)
    view.installEventFilter(hover_filter)
    view.viewport().installEventFilter(hover_filter)

    wheel_guard = _ComboWheelGuardFilter(combo)
    combo.installEventFilter(wheel_guard)

    # Keep an owning reference so the filter stays alive.
    combo._shared_dropdown_hover_filter = hover_filter
    combo._shared_dropdown_wheel_guard = wheel_guard


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
