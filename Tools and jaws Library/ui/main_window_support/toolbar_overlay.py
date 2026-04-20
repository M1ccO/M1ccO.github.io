from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer
from PySide6.QtWidgets import QButtonGroup, QFrame, QToolButton, QVBoxLayout, QWidget


class RailToolbarOverlay(QObject):
    """Owns the floating icon rack overlay and its hover-trigger lifecycle."""

    def __init__(
        self,
        *,
        host: QWidget,
        rail: QWidget,
        nav_width: int,
        nav_button_count: int,
        on_nav_button_clicked: Callable[[int], None],
    ) -> None:
        super().__init__(host)
        self._host = host
        self._rail = rail
        self._nav_width = int(nav_width)
        self._revealed = False

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(160)
        self._hide_timer.timeout.connect(self.hide_nav)

        self.nav_frame = QFrame()
        self.nav_frame.setObjectName('navFrame')
        self.nav_frame.setFixedWidth(self._nav_width)

        nav_layout = QVBoxLayout(self.nav_frame)
        nav_layout.setContentsMargins(0, 10, 0, 8)
        nav_layout.setSpacing(10)

        self.nav_buttons: list[QToolButton] = []
        self.nav_button_group = QButtonGroup(self._host)
        self.nav_button_group.setExclusive(True)

        for index in range(max(0, int(nav_button_count))):
            button = QToolButton()
            button.setObjectName('sideNavButton')
            button.setIconSize(QSize(30, 30))
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setFixedSize(42, 46)
            button.clicked.connect(lambda checked=False, idx=index: on_nav_button_clicked(idx))
            self.nav_button_group.addButton(button, index)
            self.nav_buttons.append(button)
            nav_layout.addWidget(button, 0, Qt.AlignHCenter | Qt.AlignTop)

        nav_layout.addStretch(1)
        nav_height = (len(self.nav_buttons) * 50) + ((len(self.nav_buttons) - 1) * nav_layout.spacing()) + 18
        self.nav_frame.setFixedHeight(nav_height)

        self.nav_slot = QWidget()
        self.nav_slot.setFixedSize(self._nav_width, nav_height)
        self.nav_frame.setParent(self.nav_slot)
        self.nav_frame.move(0, 0)

        self.nav_hover_trigger = QWidget(self._rail)
        self.nav_hover_trigger.setObjectName('navHoverTrigger')
        self.nav_hover_trigger.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.nav_hover_trigger.setStyleSheet('background: transparent;')

        self._hover_widgets = [self.nav_hover_trigger, self.nav_slot]
        self.nav_hover_trigger.installEventFilter(self)
        self.nav_slot.installEventFilter(self)

    def attach_to_rail(self) -> None:
        self._revealed = False
        self.nav_slot.setParent(self._rail)
        self.nav_slot.setVisible(False)
        self.nav_slot.raise_()
        self.position_hover_trigger()
        self.nav_frame.move(0, 0)

    def show_nav(self) -> None:
        self._hide_timer.stop()
        if self._revealed:
            return
        self._revealed = True
        self.position_overlay()
        self.nav_slot.setVisible(True)
        self.nav_slot.raise_()

    def hide_nav(self) -> None:
        self._revealed = False
        self.nav_slot.setVisible(False)

    def position_overlay(self) -> None:
        slot_h = self.nav_slot.height()
        rail_w = self._rail.width()
        rail_h = self._rail.height()
        x = max(0, rail_w - self._nav_width - 4)
        y = max(0, (rail_h - slot_h) // 2)
        self.nav_slot.setGeometry(x, y, self._nav_width, slot_h)

    def position_hover_trigger(self) -> None:
        rail_w = self._rail.width()
        rail_h = self._rail.height()
        trigger_width = 12
        self.nav_hover_trigger.setGeometry(max(0, rail_w - trigger_width), 0, trigger_width, rail_h)

    def handle_host_resize(self) -> None:
        self.position_overlay()
        self.position_hover_trigger()

    def eventFilter(self, obj, event):
        if obj in self._hover_widgets:
            if event.type() == QEvent.Enter:
                self.show_nav()
            elif event.type() == QEvent.Leave:
                self._hide_timer.start()
        return super().eventFilter(obj, event)