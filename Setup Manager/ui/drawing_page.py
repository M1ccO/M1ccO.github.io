from typing import Callable

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import ICONS_DIR, TOOL_LIBRARY_TOOL_ICONS_DIR


def _toolbar_icon(name: str) -> QIcon:
    png = ICONS_DIR / 'tools' / f'{name}.png'
    if png.exists():
        return QIcon(str(png))
    shared_png = TOOL_LIBRARY_TOOL_ICONS_DIR / f'{name}.png'
    if shared_png.exists():
        return QIcon(str(shared_png))
    svg = ICONS_DIR / 'tools' / f'{name}.svg'
    if svg.exists():
        return QIcon(str(svg))
    shared_svg = TOOL_LIBRARY_TOOL_ICONS_DIR / f'{name}.svg'
    if shared_svg.exists():
        return QIcon(str(shared_svg))
    return QIcon()


class DrawingPage(QWidget):
    def __init__(
        self,
        draw_service,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self.draw_service = draw_service
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')

        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.search_icon = _toolbar_icon('search_icon')
        self.close_icon = _toolbar_icon('close_icon')

        self.search_toggle_btn = QToolButton()
        self.search_toggle_btn.setProperty('topBarIconButton', True)
        self.search_toggle_btn.setCheckable(True)
        self.search_toggle_btn.setToolTip(self._t('drawing_page.search_toggle_tip', 'Show/hide search'))
        self.search_toggle_btn.setIcon(self.search_icon)
        self.search_toggle_btn.setIconSize(QSize(24, 24))
        self.search_toggle_btn.setFixedSize(34, 34)
        self.search_toggle_btn.setAutoRaise(True)
        self.search_toggle_btn.clicked.connect(self._toggle_search)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self._t('drawing_page.search_placeholder', 'Search drawings...'))
        self.search_input.textChanged.connect(self.refresh_list)
        self.search_input.setVisible(False)
        self.search_input.setMaximumWidth(320)
        self.search_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.refresh_btn = QPushButton(self._t('drawing_page.action.refresh', 'Refresh'))
        self.refresh_btn.setProperty("panelActionButton", True)
        self.refresh_btn.setMinimumWidth(130)
        self.refresh_btn.setMaximumWidth(180)
        self.refresh_btn.clicked.connect(self.refresh_list)
        self.open_btn = QPushButton(self._t('drawing_page.action.open', 'Open'))
        self.open_btn.setProperty("panelActionButton", True)
        self.open_btn.setMinimumWidth(130)
        self.open_btn.setMaximumWidth(180)
        self.open_btn.clicked.connect(self.open_selected)

        controls.addWidget(self.search_toggle_btn)
        controls.addWidget(self.search_input)
        controls.addWidget(self.refresh_btn)
        controls.addWidget(self.open_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.title = QLabel(self._t('drawing_page.title', 'Drawings'))
        self.title.setProperty("pageTitle", True)
        layout.addWidget(self.title)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("drawingList")
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.open_selected())
        layout.addWidget(self.list_widget, 1)

        self.refresh_list()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _toggle_search(self):
        show = self.search_toggle_btn.isChecked()
        self.search_input.setVisible(show)
        self.search_toggle_btn.setIcon(self.close_icon if show else self.search_icon)
        if show:
            self.search_input.setFocus()
            return
        self.search_input.clear()
        self.refresh_list()

    def refresh_list(self):
        drawings = self.draw_service.list_drawings(self.search_input.text())
        self.list_widget.clear()
        for drawing in drawings:
            item = QListWidgetItem(f"{drawing['drawing_id']}")
            item.setData(Qt.UserRole, drawing)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def open_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        drawing = item.data(Qt.UserRole)
        ok = self.draw_service.open_drawing(drawing.get("path", ""))
        if not ok:
            QMessageBox.warning(
                self,
                self._t('setup_page.message.open_failed', 'Open failed'),
                self._t('drawing_page.message.open_failed', 'Unable to open drawing file.'),
            )

    def apply_localization(self, translate: Callable[[str, str | None], str] | None = None):
        if translate is not None:
            self._translate = translate
        self.search_toggle_btn.setToolTip(self._t('drawing_page.search_toggle_tip', 'Show/hide search'))
        self.search_input.setPlaceholderText(self._t('drawing_page.search_placeholder', 'Search drawings...'))
        self.refresh_btn.setText(self._t('drawing_page.action.refresh', 'Refresh'))
        self.open_btn.setText(self._t('drawing_page.action.open', 'Open'))
        self.title.setText(self._t('drawing_page.title', 'Drawings'))
