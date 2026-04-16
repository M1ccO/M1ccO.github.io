"""
Shared MiniAssignmentCard widget — a compact card for tool/jaw assignment lists.

Used by both Setup Manager (work_editor_dialog) and Tool Library (selector panel)
to render assignment rows with icon, title, subtitle, and badges.
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)


class MiniAssignmentCard(QFrame):
    editRequested = Signal()

    def __init__(
        self,
        icon: QIcon,
        title: str,
        subtitle: str = "",
        badges: list[str] | None = None,
        editable: bool = False,
        compact: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._editable = bool(editable)
        self._compact = bool(compact)
        self._full_title = (title or "").strip()
        self._full_subtitle = (subtitle or "").strip()
        self.setProperty("toolListCard", True)
        self.setProperty("miniAssignmentCard", True)
        self.setProperty("selected", False)
        self.setFrameShape(QFrame.NoFrame)
        self.setAttribute(Qt.WA_StyledBackground, True)

        root = QHBoxLayout(self)
        if self._compact:
            root.setContentsMargins(6, 2, 6, 2)
            root.setSpacing(6)
        else:
            root.setContentsMargins(8, 4, 8, 4)
            root.setSpacing(8)

        self.icon_label = QLabel()
        if self._compact:
            self.icon_label.setFixedSize(24, 24)
            pixmap_size = QSize(22, 22)
        else:
            self.icon_label.setFixedSize(22, 22)
            pixmap_size = QSize(20, 20)
        self.icon_label.setAlignment(Qt.AlignCenter)
        if icon is not None and not icon.isNull():
            self.icon_label.setPixmap(icon.pixmap(pixmap_size))
        root.addWidget(self.icon_label, 0, Qt.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)
        self.title_label = QLabel(self._full_title)
        self.title_label.setProperty("miniAssignmentTitle", True)
        self.title_label.setWordWrap(False)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        text_col.addWidget(self.title_label)

        self.subtitle_label = QLabel(self._full_subtitle)
        self.subtitle_label.setProperty("miniAssignmentHint", True)
        self.subtitle_label.setWordWrap(False)
        self.subtitle_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.subtitle_label.setVisible(bool(self._full_subtitle))
        text_col.addWidget(self.subtitle_label)
        root.addLayout(text_col, 1)

        self.meta_label = QLabel("")
        self.meta_label.setProperty("miniAssignmentMeta", True)
        self.meta_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.meta_label.setVisible(False)
        root.addWidget(self.meta_label, 0, Qt.AlignVCenter)
        self.set_badges(badges or [])
        self._apply_elision()

    def set_selected(self, selected: bool):
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)

    def set_badges(self, badges: list[str]):
        clean = [str(item).strip() for item in (badges or []) if str(item).strip()]
        self.meta_label.setVisible(bool(clean))
        self.meta_label.setText("   ".join(clean))
        self._apply_elision()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elision()

    def _apply_elision(self) -> None:
        title_width = max(0, self.title_label.width())
        subtitle_width = max(0, self.subtitle_label.width())

        if title_width > 0:
            title_text = self.title_label.fontMetrics().elidedText(
                self._full_title,
                Qt.ElideRight,
                title_width,
            )
            self.title_label.setText(title_text)
        else:
            self.title_label.setText(self._full_title)

        if self._full_subtitle and subtitle_width > 0:
            subtitle_text = self.subtitle_label.fontMetrics().elidedText(
                self._full_subtitle,
                Qt.ElideRight,
                subtitle_width,
            )
            self.subtitle_label.setText(subtitle_text)
        else:
            self.subtitle_label.setText(self._full_subtitle)

    def mouseDoubleClickEvent(self, event):
        if self._editable:
            self.editRequested.emit()
        super().mouseDoubleClickEvent(event)
