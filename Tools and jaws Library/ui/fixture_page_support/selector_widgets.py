"""Selector slot widgets for FixturePage."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QDrag, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel, QPushButton, QSizePolicy, QVBoxLayout

from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
from shared.ui.helpers.editor_helpers import apply_titled_section_style
from ui.fixture_catalog_delegate import jaw_icon_for_row
from ui.selector_mime import SELECTOR_JAW_MIME, encode_selector_payload, first_dropped_jaw, jaw_payload_ids


class _DraggableJawAssignmentCard(MiniAssignmentCard):
    slotClicked = Signal(bool)
    dragRequested = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            ctrl = bool(event.modifiers() & Qt.ControlModifier)
            self.slotClicked.emit(ctrl)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(event)
        if self._drag_start_pos is None:
            return super().mouseMoveEvent(event)
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)
        self.dragRequested.emit()
        self._drag_start_pos = None
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)


class FixtureAssignmentSlot(QGroupBox):
    jawDropped = Signal(str, dict)
    slotClicked = Signal(str, bool)

    def __init__(self, slot_key: str, title: str, parent=None, translate=None):
        super().__init__(parent)
        self._slot_key = slot_key
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self._assignment: dict | None = None
        self._drop_placeholder = "Drop fixture here"
        self._assignment_card: MiniAssignmentCard | None = None
        self._selected = False
        self._content_height = 38
        self._drag_start_pos = None
        self._invalid_drop_active = False
        self._invalid_drop_timer = QTimer(self)
        self._invalid_drop_timer.setSingleShot(True)
        self._invalid_drop_timer.timeout.connect(self._clear_invalid_drop_feedback)
        self.setAcceptDrops(True)
        self.setProperty("toolIdsPanel", True)
        apply_titled_section_style(self)
        self.setTitle(title)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(6)

        self.value_label = QLabel("")
        self.value_label.setProperty("detailHint", True)
        self.value_label.setWordWrap(False)
        self.value_label.setFixedHeight(self._content_height)
        self.value_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.value_label)
        self._refresh_ui()

    def set_title(self, title: str):
        self.setTitle(title)

    def set_drop_placeholder_text(self, text: str):
        self._drop_placeholder = str(text or "Drop fixture here")
        self._refresh_ui()

    def set_selected(self, selected: bool):
        self._selected = bool(selected)
        if self._assignment_card is not None:
            self._assignment_card.set_selected(self._selected)

    def flash_invalid_drop(self):
        self._invalid_drop_active = True
        self.setStyleSheet(
            "QGroupBox {"
            " border: 2px solid #d84a4a;"
            " border-radius: 8px;"
            "}"
            "QGroupBox::title {"
            " color: #c83a3a;"
            "}"
        )
        self._invalid_drop_timer.start(550)

    def _clear_invalid_drop_feedback(self):
        self._invalid_drop_active = False
        self.setStyleSheet("")

    def assignment(self) -> dict | None:
        return dict(self._assignment) if isinstance(self._assignment, dict) else None

    def set_assignment(self, fixture: dict | None):
        normalized = None
        if isinstance(fixture, dict):
            fixture_id = str(fixture.get("fixture_id") or fixture.get("id") or "").strip()
            if fixture_id:
                normalized = {
                    "fixture_id": fixture_id,
                    "fixture_type": str(fixture.get("fixture_type") or "").strip(),
                }
                fixture_kind = str(fixture.get("fixture_kind") or "").strip()
                if fixture_kind:
                    normalized["fixture_kind"] = fixture_kind
        self._assignment = normalized
        self._refresh_ui()

    def _localized_jaw_type(self, raw_type: str) -> str:
        normalized = (raw_type or '').strip().lower().replace(' ', '_')
        return self._translate(f'jaw_library.fixture_type.{normalized}', raw_type)

    def _refresh_ui(self):
        if isinstance(self._assignment, dict):
            fixture_id = str(self._assignment.get("fixture_id") or "").strip()
            fixture_type = self._localized_jaw_type(str(self._assignment.get("fixture_type") or "").strip())
            title = f"{fixture_id}  -  {fixture_type}" if fixture_type else fixture_id
            icon_jaw = {**self._assignment, "fixture_kind": "sub" if self._slot_key == "sub" else "main"}
            if self._assignment_card is None:
                icon = jaw_icon_for_row(icon_jaw)
                self._assignment_card = _DraggableJawAssignmentCard(
                    icon=icon,
                    title=title,
                    subtitle="",
                    badges=[],
                    editable=False,
                    compact=True,
                    parent=self,
                )
                self._assignment_card.slotClicked.connect(
                    lambda ctrl: self.slotClicked.emit(self._slot_key, ctrl)
                )
                self._assignment_card.dragRequested.connect(self._start_assignment_drag)
                self._assignment_card.setFixedHeight(self._content_height)
                self._assignment_card.icon_label.setFixedSize(32, 32)
                if not icon.isNull():
                    self._assignment_card.icon_label.setPixmap(icon.pixmap(QSize(32, 32)))
                self.layout().insertWidget(0, self._assignment_card)
            else:
                icon = jaw_icon_for_row(icon_jaw)
                self._assignment_card.icon_label.setFixedSize(32, 32)
                if icon is not None and not icon.isNull():
                    self._assignment_card.icon_label.setPixmap(icon.pixmap(QSize(32, 32)))
                self._assignment_card.title_label.setText(title)
                self._assignment_card.setFixedHeight(self._content_height)
            self._assignment_card.subtitle_label.setVisible(False)
            self._assignment_card.set_badges([])
            self._assignment_card.setVisible(True)
            self._assignment_card.set_selected(self._selected)
            self.value_label.setVisible(False)
            return
        self.value_label.setText(self._drop_placeholder)
        self.value_label.setVisible(True)
        if self._assignment_card is not None:
            self._assignment_card.setVisible(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        ctrl = bool(event.modifiers() & Qt.ControlModifier)
        self.slotClicked.emit(self._slot_key, ctrl)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(event)
        if self._assignment is None or self._drag_start_pos is None:
            return super().mouseMoveEvent(event)
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)

        self._start_assignment_drag()
        self._drag_start_pos = None
        super().mouseMoveEvent(event)

    def _start_assignment_drag(self):
        if self._assignment is None:
            return
        payload = [dict(self._assignment)]
        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_JAW_MIME, payload)

        drag = QDrag(self)
        drag.setMimeData(mime)

        ghost_source = self._assignment_card if self._assignment_card is not None else self
        ghost = ghost_source.grab()
        if not ghost.isNull():
            translucent = QPixmap(ghost.size())
            translucent.fill(Qt.transparent)
            painter = QPainter(translucent)
            painter.setOpacity(0.7)
            painter.drawPixmap(0, 0, ghost)
            painter.end()
            drag.setPixmap(translucent)
            drag.setHotSpot(translucent.rect().center())

        drag.exec(Qt.CopyAction)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    @staticmethod
    def _normalized_first_dropped_jaw(mime: QMimeData) -> dict | None:
        return first_dropped_jaw(mime)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_JAW_MIME):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_JAW_MIME):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        fixture = self._normalized_first_dropped_jaw(event.mimeData())
        if fixture is None:
            event.ignore()
            return
        self.jawDropped.emit(self._slot_key, fixture)
        event.acceptProposedAction()


class SelectorRemoveDropButton(QPushButton):
    jawsDropped = Signal(list)

    def __init__(self, parent=None, *, enable_drop: bool = True):
        super().__init__(parent)
        if enable_drop:
            self.setAcceptDrops(True)

    @staticmethod
    def _payload_jaw_ids(mime: QMimeData) -> list[str]:
        return jaw_payload_ids(mime)

    def dragEnterEvent(self, event):
        if self._payload_jaw_ids(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if self._payload_jaw_ids(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        jaw_ids = self._payload_jaw_ids(event.mimeData())
        if not jaw_ids:
            event.ignore()
            return
        self.jawsDropped.emit(jaw_ids)
        event.acceptProposedAction()
