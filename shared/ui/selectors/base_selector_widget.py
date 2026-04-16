from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class BaseSelectorWidget(QWidget):
    """Common signal contract and shell for embedded selector widgets."""

    submitted = Signal(dict)
    canceled = Signal()

    def __init__(
        self,
        *,
        title: str,
        details_text: str,
        translate: Callable[[str, str | None], str],
        parent=None,
    ):
        super().__init__(parent)
        self._t = translate

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_label = QLabel(title, self)
        title_label.setProperty("detailHeader", True)
        layout.addWidget(title_label)

        details = QLabel(details_text, self)
        details.setWordWrap(True)
        details.setProperty("detailHint", True)
        layout.addWidget(details)
        layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        button_row.addStretch(1)

        done_btn = QPushButton(self._t("common.done", "Done"), self)
        done_btn.setProperty("panelActionButton", True)
        done_btn.setProperty("primaryAction", True)
        done_btn.clicked.connect(self._emit_submit)
        button_row.addWidget(done_btn, 0, Qt.AlignRight)

        cancel_btn = QPushButton(self._t("common.cancel", "Cancel"), self)
        cancel_btn.setProperty("panelActionButton", True)
        cancel_btn.setProperty("secondaryAction", True)
        cancel_btn.clicked.connect(self.canceled.emit)
        button_row.addWidget(cancel_btn, 0, Qt.AlignRight)

        layout.addLayout(button_row)

    def _build_submit_payload(self) -> dict:
        return {}

    def _emit_submit(self) -> None:
        self.submitted.emit(self._build_submit_payload())
