from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QAbstractItemView, QDialog, QFrame, QHBoxLayout, QPushButton, QVBoxLayout, QWidget
from shared.ui.theme import apply_top_level_surface_palette, current_theme_color

_DEFAULT_THEME_BG = '#eceff2'


class SelectorDialogBase(QDialog):
    """Shared selector dialog lifecycle helpers.

    Provides consistent cancel/submit semantics and close handling for selector
    dialogs so caller callbacks fire exactly once.
    """

    def __init__(
        self,
        *,
        translate: Callable[[str, str | None], str],
        on_cancel: Callable[[], None],
        parent=None,
        window_flags: Qt.WindowType | Qt.WindowFlags = Qt.WindowFlags(),
    ):
        super().__init__(parent, window_flags)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty('pageFamilyDialog', True)
        self._translate = translate
        self._on_cancel = on_cancel
        self._submitted = False
        self._cancel_notified = False

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _notify_cancel_once(self) -> None:
        if self._cancel_notified:
            return
        self._cancel_notified = True
        self._on_cancel()

    def _finish_submit(self, on_submit: Callable[[dict], None], payload: dict) -> None:
        self._submitted = True
        on_submit(payload)
        self.accept()

    def _cancel_dialog(self) -> None:
        self._notify_cancel_once()
        self.reject()

    def closeEvent(self, event):
        if not self._submitted:
            self._notify_cancel_once()
        super().closeEvent(event)

    def paintEvent(self, event):
        """Fill the dialog background with the theme colour unconditionally.

        QPalette and QSS are both unreliable on Windows (Fusion style) for
        top-level QDialog windows, especially after setWindowFlag() recreates
        the native HWND.  paintEvent is always called and cannot be bypassed.
        """
        painter = QPainter(self)
        painter.fillRect(self.rect(), current_theme_color('page_bg', _DEFAULT_THEME_BG))
        painter.end()

    def _make_themed_inner_layout(
        self,
        *,
        margins: tuple[int, int, int, int] = (8, 8, 8, 8),
        spacing: int = 8,
    ) -> QVBoxLayout:
        """Return a QVBoxLayout hosted inside a themed background widget.

        This is the reliable way to get the outer frame to show #eceff2 on
        Windows: a child QWidget with QPalette + autoFillBackground covers the
        whole dialog area and paints the theme colour before its children draw
        on top.  The same mechanism is used by the filter-bar toolbar frame.
        """
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bg = QWidget(self)
        apply_top_level_surface_palette(bg, role='page_bg')
        _pal = bg.palette()
        _pal.setColor(QPalette.Window, current_theme_color('page_bg', _DEFAULT_THEME_BG))
        bg.setPalette(_pal)
        bg.setProperty('pageFamilyHost', True)
        root.addWidget(bg, 1)

        inner = QVBoxLayout(bg)
        inner.setContentsMargins(*margins)
        inner.setSpacing(spacing)
        return inner


class SelectorWidgetBase(QWidget):
    """Shared embedded selector widget lifecycle helpers."""

    submitted = Signal(dict)
    canceled = Signal()

    def __init__(
        self,
        *,
        translate: Callable[[str, str | None], str],
        on_cancel: Callable[[], None],
        parent=None,
        window_flags: Qt.WindowType | Qt.WindowFlags = Qt.Tool,
    ):
        super().__init__(parent, window_flags)
        self.setProperty('selectorEmbedded', True)
        self.setProperty('rowAreaSurface', True)
        self._translate = translate
        self._on_cancel = on_cancel
        self._submitted = False
        self._cancel_notified = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), current_theme_color('page_bg', _DEFAULT_THEME_BG))
        painter.end()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _notify_cancel_once(self) -> None:
        if self._cancel_notified:
            return
        self._cancel_notified = True
        self._on_cancel()
        self.canceled.emit()

    def _reset_selector_widget_state(self, *, on_cancel: Callable[[], None]) -> None:
        self._on_cancel = on_cancel
        self._submitted = False
        self._cancel_notified = False

    def _finish_submit(self, on_submit: Callable[[dict], None], payload: dict) -> None:
        self._submitted = True
        on_submit(payload)
        self.submitted.emit(payload)

    def _cancel_dialog(self) -> None:
        self._notify_cancel_once()

    def closeEvent(self, event):
        if not self._submitted:
            self._notify_cancel_once()
        super().closeEvent(event)


def selected_rows_or_current(view: QAbstractItemView) -> list:
    """Return selected rows, falling back to current row when nothing is selected."""

    selection_model = view.selectionModel()
    if selection_model is None:
        return []
    indexes = sorted(selection_model.selectedRows(), key=lambda idx: idx.row())
    if indexes:
        return indexes
    current = view.currentIndex()
    return [current] if current.isValid() else []


def build_selector_bottom_bar(
    host_layout: QVBoxLayout,
    *,
    translate: Callable[[str, str | None], str],
    on_cancel: Callable[[], None],
    on_done: Callable[[], None],
    parent=None,
) -> tuple[QFrame, QPushButton, QPushButton]:
    """Build the shared selector DONE/CANCEL bottom bar."""

    def _t(key: str, default: str | None = None, **kwargs) -> str:
        return translate(key, default, **kwargs)

    bar = QFrame(parent)
    bar.setProperty('bottomBar', True)
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(8)
    layout.addStretch(1)

    cancel_btn = QPushButton(_t('work_editor.selector.action.cancel', 'Peruuta'))
    cancel_btn.setProperty('panelActionButton', True)
    cancel_btn.clicked.connect(on_cancel)
    layout.addWidget(cancel_btn)

    done_btn = QPushButton(_t('work_editor.selector.action.complete', 'Valmis'))
    done_btn.setProperty('panelActionButton', True)
    done_btn.setProperty('primaryAction', True)
    done_btn.clicked.connect(on_done)
    layout.addWidget(done_btn)

    host_layout.addWidget(bar, 0)
    return bar, cancel_btn, done_btn
