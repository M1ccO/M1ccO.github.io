from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QAbstractItemView, QDialog, QFrame, QHBoxLayout, QPushButton, QVBoxLayout


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
    ):
        super().__init__(parent)
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
) -> tuple[QFrame, QPushButton, QPushButton]:
    """Build the shared selector DONE/CANCEL bottom bar."""

    def _t(key: str, default: str | None = None, **kwargs) -> str:
        return translate(key, default, **kwargs)

    bar = QFrame()
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
