from html import escape
from pathlib import Path
import tempfile
import shutil
from datetime import datetime
from datetime import date
from typing import Callable

from PySide6.QtCore import QEvent, QSignalBlocker, Qt, Signal, QSize, QTimer, QModelIndex
from PySide6.QtGui import QIcon, QPainter, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QBoxLayout,
    QFormLayout,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDialog,
    QSpinBox,
)

from config import (
    ICONS_DIR,
    TOOL_ICONS_DIR,
    TOOL_LIBRARY_TOOL_ICONS_DIR,
    TOOL_TYPE_TO_ICON,
    DEFAULT_TOOL_ICON,
)
from ui.widgets.common import AutoShrinkLabel, repolish_widget, styled_list_item_height
from ui.setup_catalog_delegate import ROLE_WORK_DATA, ROLE_WORK_ID, SetupCatalogDelegate
from ui.work_editor_dialog import WorkEditorDialog
try:
    from shared.editor_helpers import ask_multi_edit_mode
except ModuleNotFoundError:
    from editor_helpers import ask_multi_edit_mode


def _toolbar_icon(name: str) -> QIcon:
    """Load toolbar icon with PNG-first fallback for better visibility."""
    png = ICONS_DIR / "tools" / f"{name}.png"
    if png.exists():
        return QIcon(str(png))
    shared_png = TOOL_LIBRARY_TOOL_ICONS_DIR / f"{name}.png"
    if shared_png.exists():
        return QIcon(str(shared_png))
    svg = ICONS_DIR / "tools" / f"{name}.svg"
    if svg.exists():
        return QIcon(str(svg))
    shared_svg = TOOL_LIBRARY_TOOL_ICONS_DIR / f"{name}.svg"
    if shared_svg.exists():
        return QIcon(str(shared_svg))
    return QIcon()


def _toolbar_icon_with_svg_render_fallback(name: str, size: int = 28) -> QIcon:
    """Load toolbar icons robustly even when Qt SVG image plugin is unavailable."""
    svg_candidates = [
        ICONS_DIR / "tools" / f"{name}.svg",
        TOOL_LIBRARY_TOOL_ICONS_DIR / f"{name}.svg",
    ]

    for svg_path in svg_candidates:
        if not svg_path.exists():
            continue

        icon = QIcon(str(svg_path))
        if not icon.isNull():
            return icon

        renderer = QSvgRenderer(str(svg_path))
        if renderer.isValid():
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            return QIcon(pixmap)

    return _toolbar_icon(name)


class ToolNameCardWidget(QFrame):
    """Compact read-only tool card: icon + tool name only."""

    def __init__(self, tool: dict, parent=None):
        super().__init__(parent)
        self.tool = tool or {}
        self.setProperty("toolListCard", True)
        self.setProperty("detailToolCard", True)
        self.setProperty("selected", False)
        self.setMinimumHeight(58)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setStyleSheet("background-color: transparent;")
        icon_name = self._pick_icon_name((self.tool.get("tool_type") or "").strip())
        icon_path = self._resolve_tool_icon(icon_name)
        if icon_path.exists():
            icon_label.setPixmap(QIcon(str(icon_path)).pixmap(QSize(34, 34)))
        icon_label.setFixedSize(40, 40)
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label, 0, Qt.AlignVCenter)

        tool_id = (self.tool.get("id") or "").strip()
        desc = (self.tool.get("description") or "").strip() or "No description"
        text = f"{tool_id} - {desc}" if tool_id else desc

        value = QLabel(text)
        value.setProperty("toolCardValue", True)
        value.setProperty("detailToolText", True)
        value.setWordWrap(True)
        value.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(value, 1)

    @staticmethod
    def _pick_icon_name(tool_type: str) -> str:
        mapped = TOOL_TYPE_TO_ICON.get(tool_type)
        return mapped if mapped else DEFAULT_TOOL_ICON

    @staticmethod
    def _resolve_tool_icon(icon_name: str) -> Path:
        local_path = TOOL_ICONS_DIR / icon_name
        if local_path.exists():
            return local_path
        shared_path = TOOL_LIBRARY_TOOL_ICONS_DIR / icon_name
        if shared_path.exists():
            return shared_path
        fallback_local = TOOL_ICONS_DIR / "tools_icon.svg"
        if fallback_local.exists():
            return fallback_local
        fallback_shared = TOOL_LIBRARY_TOOL_ICONS_DIR / DEFAULT_TOOL_ICON
        if fallback_shared.exists():
            return fallback_shared
        return local_path


class WorkRowWidget(QFrame):
    """Styled card widget for a single work entry in the list."""

    clicked = Signal()
    doubleClicked = Signal()

    def __init__(
        self,
        work_id: str,
        drawing_id: str,
        description: str,
        latest_text: str,
        headers: dict | None = None,
        no_runs_text: str = "No runs yet",
        parent=None,
    ):
        super().__init__(parent)
        self.setProperty("toolListCard", True)
        self.setProperty("workRowCard", True)
        self.setProperty("selected", False)
        self.setProperty("compactMode", False)
        self.setProperty("descriptionWrapped", False)
        self.setProperty("singleColumnMode", False)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(240)
        self._val_labels: list = []
        self._head_labels: list = []
        self._col_layouts: list = []
        self._column_wraps: dict = {}
        self._column_values: dict = {}
        self._column_texts: dict = {}
        self._compact_mode = False
        self._description_wrap_breakpoint = 430
        self._single_column_breakpoint = 350
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(10)
        self._root_layout = layout

        headers = headers or {}
        columns = [
            ("work_id", headers.get("work_id", "Work ID"), work_id or "-", 140),
            ("drawing", headers.get("drawing", "Drawing"), drawing_id or "-", 150),
            ("description", headers.get("description", "Description"), description or "-", 330),
            ("last_run", headers.get("last_run", "Last run"), latest_text or no_runs_text, 280),
        ]

        for key, title, value, stretch in columns:
            wrap = QWidget()
            wrap.setProperty("toolCardColumn", True)
            wrap.setStyleSheet("background: transparent;")
            wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            col = QVBoxLayout(wrap)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            self._col_layouts.append(col)

            header = QLabel(title)
            header.setProperty("toolCardHeader", True)
            header.setProperty("catalogRowHeader", True)
            header.setAlignment(Qt.AlignCenter)
            header.setWordWrap(True)
            self._head_labels.append(header)

            body = AutoShrinkLabel(value)
            body.setProperty("toolCardValue", True)
            body.setProperty("catalogRowValue", True)
            if key == "description":
                body.setProperty("catalogRowDescription", True)
            if key == "work_id":
                body.setProperty("catalogRowLead", True)
            body.setAlignment(Qt.AlignCenter)
            body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self._val_labels.append(body)
            self._column_wraps[key] = wrap
            self._column_values[key] = body
            self._column_texts[key] = value

            col.addWidget(header)
            col.addWidget(body)
            layout.addWidget(wrap, stretch, Qt.AlignVCenter)

        layout.addStretch(1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())

    def _set_responsive_property(self, name: str, value: bool) -> bool:
        value = bool(value)
        if bool(self.property(name)) == value:
            return False
        self.setProperty(name, value)
        return True

    @staticmethod
    def _split_responsive_token(text: str) -> str:
        value = (text or "").strip()
        if not value or len(value) <= 8:
            return value
        if "-" in value:
            pivot = value.find("-") + 1
            if 1 < pivot < len(value):
                return f"{value[:pivot]}\n{value[pivot:]}"
        pivot = max(4, len(value) // 2)
        return f"{value[:pivot]}\n{value[pivot:]}"

    @staticmethod
    def _set_label_point_size(label: QLabel, point_size: float):
        if isinstance(label, AutoShrinkLabel):
            label.set_target_point_size(point_size)
            return
        font = label.font()
        font.setPointSizeF(point_size)
        label.setFont(font)

    def _apply_responsive_layout(self, width: int):
        lay = self.layout()
        if lay is None:
            return

        description_wrap = self._column_wraps.get("description")
        description = self._column_values.get("description")
        work_id = self._column_values.get("work_id")
        state_changed = False
        single_column_mode = False
        description_wrapped = False

        if self._compact_mode:
            single_column_mode = width < self._single_column_breakpoint
            description_wrapped = not single_column_mode and width < self._description_wrap_breakpoint

            if single_column_mode:
                lay.setContentsMargins(10, 2, 10, 2)
                lay.setSpacing(6)
                v_size, h_size, col_spacing = 9.2, 8.2, 0
            elif description_wrapped:
                lay.setContentsMargins(10, 2, 10, 2)
                lay.setSpacing(7)
                v_size, h_size, col_spacing = 8.8, 8.4, 0
            elif width < 560:
                lay.setContentsMargins(11, 2, 9, 2)
                lay.setSpacing(8)
                v_size, h_size, col_spacing = 10.8, 9.0, 0
            else:
                lay.setContentsMargins(12, 2, 10, 2)
                lay.setSpacing(10)
                v_size, h_size, col_spacing = 11.2, 9.2, 0

            if description_wrap is not None:
                description_wrap.setVisible(not single_column_mode)
            if description is not None:
                description.setText(self._column_texts.get("description", ""))
                description.setWordWrap(description_wrapped)
                description.setMargin(0)
                description.setAlignment(Qt.AlignCenter)
                description.setMinimumHeight(38 if description_wrapped else 30)
                description.setMaximumHeight(38 if description_wrapped else 30)
                if isinstance(description, AutoShrinkLabel):
                    description.refresh_fit()
            if work_id is not None:
                work_id.setText(self._column_texts.get("work_id", ""))
                work_id.setWordWrap(False)
                work_id.setMargin(0)
                work_id.setAlignment(Qt.AlignCenter)
                work_id.setMinimumHeight(30)
                work_id.setMaximumHeight(30)
                if isinstance(work_id, AutoShrinkLabel):
                    work_id.refresh_fit()

            state_changed |= self._set_responsive_property("descriptionWrapped", description_wrapped)
            state_changed |= self._set_responsive_property("singleColumnMode", single_column_mode)
        elif width < 560:
            lay.setContentsMargins(7, 2, 7, 2)
            lay.setSpacing(7)
            v_size, h_size, col_spacing = 11.5, 8.6, 0
            if description_wrap is not None:
                description_wrap.setVisible(True)
            if description is not None:
                description.setText(self._column_texts.get("description", ""))
                description.setWordWrap(False)
                description.setMargin(0)
                description.setAlignment(Qt.AlignCenter)
                description.setMinimumHeight(30)
                description.setMaximumHeight(30)
                if isinstance(description, AutoShrinkLabel):
                    description.refresh_fit()
            if work_id is not None:
                work_id.setText(self._column_texts.get("work_id", ""))
                work_id.setWordWrap(False)
                work_id.setMargin(0)
                work_id.setAlignment(Qt.AlignCenter)
                work_id.setMinimumHeight(30)
                work_id.setMaximumHeight(30)
                if isinstance(work_id, AutoShrinkLabel):
                    work_id.refresh_fit()
            state_changed |= self._set_responsive_property("descriptionWrapped", False)
            state_changed |= self._set_responsive_property("singleColumnMode", False)
        else:
            lay.setContentsMargins(10, 2, 10, 2)
            lay.setSpacing(10)
            v_size, h_size, col_spacing = 12.8, 9.4, 0
            if description_wrap is not None:
                description_wrap.setVisible(True)
            if description is not None:
                description.setText(self._column_texts.get("description", ""))
                description.setWordWrap(False)
                description.setMargin(0)
                description.setAlignment(Qt.AlignCenter)
                description.setMinimumHeight(30)
                description.setMaximumHeight(30)
                if isinstance(description, AutoShrinkLabel):
                    description.refresh_fit()
            if work_id is not None:
                work_id.setText(self._column_texts.get("work_id", ""))
                work_id.setWordWrap(False)
                work_id.setMargin(0)
                work_id.setAlignment(Qt.AlignCenter)
                work_id.setMinimumHeight(30)
                work_id.setMaximumHeight(30)
                if isinstance(work_id, AutoShrinkLabel):
                    work_id.refresh_fit()
            state_changed |= self._set_responsive_property("descriptionWrapped", False)
            state_changed |= self._set_responsive_property("singleColumnMode", False)

        if state_changed:
            repolish_widget(self)
            for lbl in self._val_labels + self._head_labels:
                repolish_widget(lbl)

        for col in self._col_layouts:
            col.setSpacing(col_spacing)
        for lbl in self._val_labels:
            if isinstance(lbl, AutoShrinkLabel):
                lbl.set_target_point_size(v_size)
            else:
                f = lbl.font()
                f.setPointSizeF(v_size)
                lbl.setFont(f)
        for lbl in self._head_labels:
            f = lbl.font()
            f.setPointSizeF(h_size)
            lbl.setFont(f)

        if description is not None and isinstance(description, AutoShrinkLabel):
            self._set_label_point_size(description, 8.6 if self._compact_mode and description_wrapped else v_size)
        if work_id is not None and isinstance(work_id, AutoShrinkLabel):
            self._set_label_point_size(work_id, 8.8 if self._compact_mode and single_column_mode else v_size)

    def set_compact_mode(self, compact: bool):
        self._compact_mode = bool(compact)
        self.setProperty("compactMode", self._compact_mode)
        for key in ("drawing", "last_run"):
            wrap = self._column_wraps.get(key)
            if wrap is not None:
                wrap.setVisible(not self._compact_mode)
        description = self._column_values.get("description")
        if description is not None:
            description.setMargin(0)
            description.setAlignment(Qt.AlignCenter)
        work_id = self._column_values.get("work_id")
        if work_id is not None:
            work_id.setAlignment(Qt.AlignCenter)
            work_id.setMargin(0)
        repolish_widget(self)
        for lbl in self._val_labels + self._head_labels:
            repolish_widget(lbl)
        self._apply_responsive_layout(max(1, self.width()))
        self.updateGeometry()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


class AdaptiveColumnsWidget(QWidget):
    """Lay out child cards in two columns when space allows, else stack vertically."""

    def __init__(self, switch_width: int = 640, parent=None):
        super().__init__(parent)
        self._switch_width = switch_width
        self.setProperty("adaptiveColumnsHost", True)
        self._layout = QBoxLayout(QBoxLayout.LeftToRight, self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)

    def add_widget(self, widget: QWidget):
        self._layout.addWidget(widget, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        direction = QBoxLayout.TopToBottom if event.size().width() < self._switch_width else QBoxLayout.LeftToRight
        if self._layout.direction() != direction:
            self._layout.setDirection(direction)

class LogEntryDialog(QDialog):
    def __init__(
        self,
        work_id,
        next_serial="",
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or "")
        self._save_and_print = False
        self._next_serial_value = (next_serial or "").strip().upper()
        self.setWindowTitle(
            self._t("setup_page.log_entry.title_with_work", "Add Logbook Entry - {work_id}", work_id=work_id)
        )
        self.resize(520, 300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)
        self.order_input = QLineEdit()
        self.quantity_input = QSpinBox()
        self.quantity_input.setMinimum(1)
        self.quantity_input.setMaximum(10_000_000)
        self.notes_input = QTextEdit()
        self.notes_input.setFixedHeight(80)
        self.work_id_display = QLineEdit(work_id)
        self.work_id_display.setReadOnly(True)
        self.next_serial_display = QLineEdit(self._next_serial_value or "-")
        self.next_serial_display.setReadOnly(True)
        self.custom_serial_input = QLineEdit()
        self.custom_serial_input.setPlaceholderText(
            self._t("setup_page.log_entry.custom_serial_hint", "Optional override, e.g. Z26")
        )

        form.addRow(self._t("setup_page.log_entry.work", "Work"), self.work_id_display)
        form.addRow(self._t("setup_page.log_entry.next_serial", "Next serial"), self.next_serial_display)
        form.addRow(self._t("setup_page.log_entry.order", "Order"), self.order_input)
        form.addRow(self._t("setup_page.log_entry.quantity", "Quantity"), self.quantity_input)
        form.addRow(self._t("setup_page.log_entry.custom_serial", "Custom serial"), self.custom_serial_input)
        form.addRow(self._t("setup_page.log_entry.notes", "Notes"), self.notes_input)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        save_print_btn = QPushButton(self._t("setup_page.log_entry.save_and_print", "SAVE && PRINT CARD"))
        save_print_btn.setProperty("panelActionButton", True)
        save_print_btn.setProperty("primaryAction", True)
        save_btn = QPushButton(self._t("common.save", "Save"))
        save_btn.setProperty("panelActionButton", True)
        save_btn.setProperty("secondaryAction", True)
        cancel_btn = QPushButton(self._t("common.cancel", "Cancel"))
        cancel_btn.setProperty("panelActionButton", True)
        cancel_btn.setProperty("secondaryAction", True)
        save_print_btn.clicked.connect(self._on_save_and_print)
        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self.reject)
        for button in (save_print_btn, save_btn, cancel_btn):
            button.style().unpolish(button)
            button.style().polish(button)
        buttons.addWidget(save_print_btn)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def _on_save(self):
        self._save_and_print = False
        self.accept()

    def _on_save_and_print(self):
        self._save_and_print = True
        self.accept()

    def should_print_card(self) -> bool:
        return bool(self._save_and_print)

    def get_data(self):
        custom_serial = self.custom_serial_input.text().strip().upper()
        serial_to_save = custom_serial or self._next_serial_value
        return {
            "order_number": self.order_input.text().strip(),
            "quantity": int(self.quantity_input.value()),
            "notes": self.notes_input.toPlainText().strip(),
            "custom_serial": custom_serial,
            "serial_to_save": serial_to_save,
        }

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)


class SetupPage(QWidget):
    logbookChanged = Signal()
    openLibraryMasterFilterRequested = Signal(object, object)
    libraryLaunchContextChanged = Signal(object)

    def __init__(
        self,
        work_service,
        logbook_service,
        draw_service,
        print_service,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self.work_service = work_service
        self.logbook_service = logbook_service
        self.draw_service = draw_service
        self.print_service = print_service
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or "")

        self.current_work_id = None
        self.latest_entries_by_work = {}
        self._details_open = False
        self._search_visible = False
        self._last_detail_sizes: list = []  # remembers splitter sizes when detail was last visible
        self._min_list_panel_width = 340
        self._min_detail_panel_width = 420
        self._clamping_splitter = False
        self._row_headers = {
            "work_id": self._t("setup_page.row.work_id", "Work ID"),
            "drawing": self._t("setup_page.row.drawing", "Drawing"),
            "description": self._t("setup_page.row.description", "Description"),
            "last_run": self._t("setup_page.row.last_run", "Last run"),
        }
        self._section_title_keys = {
            "programs": ("setup_page.section.programs", "Programs"),
            "jaws": ("setup_page.section.jaw_setup", "Jaw Setup"),
            "head1": ("setup_page.section.head1", "Head 1"),
            "head1_tools": ("setup_page.section.head1_tools", "Head 1 Tools"),
            "head2": ("setup_page.section.head2", "Head 2"),
            "head2_tools": ("setup_page.section.head2_tools", "Head 2 Tools"),
            "robot": ("setup_page.section.robot", "Robot"),
            "notes": ("setup_page.section.notes", "Notes"),
            "sources": ("setup_page.section.data_sources", "Data Sources"),
        }
        self._section_titles = {
            key: self._t(translation_key, default)
            for key, (translation_key, default) in self._section_title_keys.items()
        }
        self._detail_section_title_labels: dict[str, QLabel] = {}
        self._tool_db_mtime = self._safe_mtime(self.draw_service.tool_db_path)
        self._jaw_db_mtime = self._safe_mtime(self.draw_service.jaw_db_path)

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
        self.search_toggle_btn.setToolTip(self._t("setup_page.search_toggle_tip", "Show/hide search"))
        self.search_toggle_btn.setIcon(self.search_icon)
        self.search_toggle_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.search_toggle_btn.setIconSize(QSize(28, 28))
        self.search_toggle_btn.setFixedSize(36, 36)
        self.search_toggle_btn.setAutoRaise(True)
        self.search_toggle_btn.clicked.connect(self._toggle_search)
        controls.addWidget(self.search_toggle_btn)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self._t("setup_page.search_placeholder", "Search works..."))
        self.search_input.textChanged.connect(self.refresh_works)
        self.search_input.setVisible(False)
        self.search_input.setFixedWidth(220)
        controls.addWidget(self.search_input)

        self.detail_toggle_btn = QToolButton()
        self.detail_toggle_btn.setProperty("topBarIconButton", True)
        self.detail_toggle_btn.setCheckable(True)
        self.detail_toggle_btn.setToolTip(self._t("setup_page.details_toggle_tip", "Show/hide work details"))
        self.detail_toggle_btn.setIcon(_toolbar_icon_with_svg_render_fallback("tooltip", 28))
        self.detail_toggle_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.detail_toggle_btn.setIconSize(QSize(28, 28))
        self.detail_toggle_btn.setFixedSize(36, 36)
        self.detail_toggle_btn.setAutoRaise(True)
        self.detail_toggle_btn.clicked.connect(self._on_detail_toggle_clicked)
        controls.addWidget(self.detail_toggle_btn)

        self.make_logbook_entry_btn = QPushButton(self._t("setup_page.make_logbook_entry", "Make logbook entry"))
        self.make_logbook_entry_btn.setProperty("panelActionButton", True)
        self.make_logbook_entry_btn.setProperty("secondaryAction", True)
        self.make_logbook_entry_btn.setFixedHeight(30)
        self.make_logbook_entry_btn.clicked.connect(self.add_log_entry)

        self.detail_close_btn = QToolButton()
        self.detail_close_btn.setProperty("topBarIconButton", True)
        self.detail_close_btn.setToolTip(self._t("setup_page.close_details_tip", "Close details"))
        if not self.close_icon.isNull():
            self.detail_close_btn.setIcon(self.close_icon)
            self.detail_close_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
            self.detail_close_btn.setIconSize(QSize(28, 28))
            self.detail_close_btn.setFixedSize(36, 36)
        else:
            self.detail_close_btn.setText("X")
            self.detail_close_btn.setFixedSize(36, 36)
        self.detail_close_btn.setAutoRaise(True)
        self.detail_close_btn.clicked.connect(self.hide_details)
        self.detail_close_btn.hide()
        controls.addStretch(1)

        self.new_btn = QPushButton(self._t("setup_page.new_work", "New Work"))
        self.edit_btn = QPushButton(self._t("setup_page.edit_work", "Edit Work"))
        self.delete_btn = QPushButton(self._t("setup_page.delete_work", "Delete Work"))
        self.copy_btn = QPushButton(self._t("setup_page.duplicate", "Duplicate"))
        self.print_btn = QPushButton(self._t("setup_page.view_setup_card", "View Setup Card"))
        self.print_btn.setProperty("panelActionButton", True)
        self.print_btn.setProperty("secondaryAction", True)
        self.print_btn.setFixedHeight(30)

        self.new_btn.clicked.connect(self.create_work)
        self.edit_btn.clicked.connect(self.edit_work)
        self.delete_btn.clicked.connect(self.delete_work)
        self.copy_btn.clicked.connect(self.duplicate_work)
        self.print_btn.clicked.connect(self.view_setup_card)

        controls.addWidget(self.print_btn)
        controls.addWidget(self.make_logbook_entry_btn)
        controls.addWidget(self.detail_close_btn)
        root.addWidget(controls_frame)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("setupWorkSplitter")
        splitter.setHandleWidth(1)
        self.work_list = QListView()
        self.work_list.setObjectName("setupWorkList")
        self.work_list.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.work_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.work_list.setSpacing(0)
        self.work_list.setSelectionMode(QListView.ExtendedSelection)
        self.work_list.setMouseTracking(True)
        self.work_list.setUniformItemSizes(True)
        self.work_list.setStyleSheet(
            "QListView#setupWorkList { border: none; outline: none; padding: 8px; }"
            " QListView#setupWorkList::item { background: transparent; border: none; }"
        )
        self._work_model = QStandardItemModel(self)
        self._work_delegate = SetupCatalogDelegate(
            self.work_list,
            headers=self._row_headers,
            compact_mode=False,
        )
        self.work_list.setModel(self._work_model)
        self.work_list.setItemDelegate(self._work_delegate)
        self.work_list.selectionModel().currentChanged.connect(self._on_selection_changed)
        self.work_list.selectionModel().selectionChanged.connect(self._on_multi_selection_changed)
        self.work_list.doubleClicked.connect(self._on_item_double_clicked)
        self.work_list.installEventFilter(self)
        self.work_list.viewport().installEventFilter(self)

        list_shell = QFrame()
        list_shell.setObjectName("setupWorkShell")
        list_shell.setProperty("catalogShell", True)
        list_shell_layout = QVBoxLayout(list_shell)
        list_shell_layout.setContentsMargins(0, 0, 8, 0)
        list_shell_layout.setSpacing(0)
        list_shell_layout.addWidget(self.work_list)

        list_shell_container = QWidget()
        list_shell_container_layout = QVBoxLayout(list_shell_container)
        list_shell_container_layout.setContentsMargins(0, 0, 0, 0)
        list_shell_container_layout.setSpacing(0)
        list_shell_container_layout.addWidget(list_shell)
        list_shell_container.setMinimumWidth(self._min_list_panel_width)
        splitter.addWidget(list_shell_container)

        detail_host = QWidget()
        detail_host.setProperty("detailPaneHost", True)
        detail_layout = QVBoxLayout(detail_host)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(2)

        # Hero header - mirror Tool Library detail style with a bordered heading field.
        detail_hero = QFrame()
        detail_hero.setProperty("detailHeader", True)
        hero_layout = QVBoxLayout(detail_hero)
        hero_layout.setContentsMargins(14, 14, 14, 12)
        hero_layout.setSpacing(6)

        heading_field = QFrame()
        heading_field.setProperty("detailField", True)
        heading_field.setProperty("detailHeroField", True)
        heading_layout = QVBoxLayout(heading_field)
        heading_layout.setContentsMargins(10, 8, 10, 8)
        heading_layout.setSpacing(4)

        self.detail_heading_key = QLabel(self._t("setup_page.field.drawing_id", "Drawing ID"))
        self.detail_heading_key.setProperty("detailFieldKey", True)

        self.detail_id_label = QLabel("-")
        self.detail_id_label.setProperty("detailHeroTitle", True)
        self.detail_id_label.setWordWrap(False)
        self.detail_id_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.detail_description_label = QLabel("-")
        self.detail_description_label.setProperty("detailHeroSubtitle", True)
        self.detail_description_label.setWordWrap(True)
        self.detail_description_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        heading_layout.addWidget(self.detail_heading_key)
        heading_layout.addWidget(self.detail_id_label)
        heading_layout.addWidget(self.detail_description_label)
        hero_layout.addWidget(heading_field)

        # Wrap the hero and all section cards in one scroll area so everything scrolls together
        detail_scroll = QScrollArea()
        detail_scroll.setObjectName("detailScrollArea")
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QFrame.NoFrame)
        detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        detail_scroll_content = QWidget()
        detail_scroll_content.setProperty("detailContentHost", True)
        detail_scroll_content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        detail_scroll_layout = QVBoxLayout(detail_scroll_content)
        detail_scroll_layout.setContentsMargins(0, 0, 0, 0)
        detail_scroll_layout.setSpacing(8)
        detail_scroll_layout.addWidget(detail_hero)

        self.detail_sections = {}
        for key, title in self._section_titles.items():
            card = QFrame()
            card.setProperty("subCard", True)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(8)
            title_label = QLabel(title)
            title_label.setProperty("detailSectionTitle", True)
            card_layout.addWidget(title_label)
            detail_scroll_layout.addWidget(card)
            self.detail_sections[key] = card_layout
            self._detail_section_title_labels[key] = title_label

        detail_scroll_layout.addStretch(1)
        detail_scroll.setWidget(detail_scroll_content)

        self.detail_card = QFrame()
        self.detail_card.setProperty("card", True)
        detail_card_layout = QVBoxLayout(self.detail_card)
        detail_card_layout.setContentsMargins(0, 0, 0, 0)
        detail_card_layout.setSpacing(0)
        detail_card_layout.addWidget(detail_scroll, 1)
        detail_layout.addWidget(self.detail_card, 1)

        self.detail_scroll = detail_scroll
        self.detail_scroll_content = detail_scroll_content
        self.detail_scroll.viewport().installEventFilter(self)

        self.detail_host = detail_host
        detail_host.setMinimumWidth(self._min_detail_panel_width)
        detail_host.setVisible(False)

        splitter.addWidget(detail_host)
        splitter.setChildrenCollapsible(False)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self._setup_splitter = splitter
        splitter.setSizes([1, 0])
        splitter.splitterMoved.connect(self._on_splitter_moved)

        splitter_host = QWidget()
        splitter_host_layout = QVBoxLayout(splitter_host)
        splitter_host_layout.setContentsMargins(0, 0, 12, 0)
        splitter_host_layout.setSpacing(0)
        splitter_host_layout.addWidget(splitter)
        root.addWidget(splitter_host, 1)

        button_bar = QFrame()
        button_bar.setProperty("bottomBar", True)
        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(10, 10, 10, 6)
        button_layout.setSpacing(8)
        button_layout.addStretch(1)

        self.new_btn.setProperty("panelActionButton", True)
        self.new_btn.setProperty("primaryAction", True)
        self.edit_btn.setProperty("panelActionButton", True)
        self.copy_btn.setProperty("panelActionButton", True)
        self.delete_btn.setProperty("panelActionButton", True)
        self.delete_btn.setProperty("dangerAction", True)

        self.selection_count_label = QLabel("")
        self.selection_count_label.setProperty("detailHint", True)
        self.selection_count_label.setStyleSheet("background: transparent; border: none;")
        self.selection_count_label.hide()
        button_layout.addWidget(self.selection_count_label, 0, Qt.AlignBottom)
        button_layout.addWidget(self.new_btn, 0, Qt.AlignBottom)
        button_layout.addWidget(self.edit_btn, 0, Qt.AlignBottom)
        button_layout.addWidget(self.delete_btn, 0, Qt.AlignBottom)
        button_layout.addWidget(self.copy_btn, 0, Qt.AlignBottom)
        root.addWidget(button_bar)

        self.refresh_works()

        self._external_refs_timer = QTimer(self)
        self._external_refs_timer.setInterval(1500)
        self._external_refs_timer.timeout.connect(self._on_external_references_maybe_changed)
        self._external_refs_timer.start()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    @staticmethod
    def _safe_mtime(path) -> float | None:
        try:
            p = Path(path)
            return p.stat().st_mtime if p.exists() else None
        except Exception:
            return None

    def _on_external_references_maybe_changed(self):
        tool_mtime = self._safe_mtime(self.draw_service.tool_db_path)
        jaw_mtime = self._safe_mtime(self.draw_service.jaw_db_path)
        changed = (tool_mtime != self._tool_db_mtime) or (jaw_mtime != self._jaw_db_mtime)
        if not changed:
            return

        self._tool_db_mtime = tool_mtime
        self._jaw_db_mtime = jaw_mtime

        # If details are open, refresh immediately so deleted/updated tools and jaws
        # are reflected without restarting Setup Manager.
        if self._details_open and self.current_work_id:
            self._refresh_details()

    def apply_localization(self, translate: Callable[[str, str | None], str] | None = None):
        if translate is not None:
            self._translate = translate
        self._row_headers = {
            "work_id": self._t("setup_page.row.work_id", "Work ID"),
            "drawing": self._t("setup_page.row.drawing", "Drawing"),
            "description": self._t("setup_page.row.description", "Description"),
            "last_run": self._t("setup_page.row.last_run", "Last run"),
        }
        self._section_titles = {
            key: self._t(translation_key, default)
            for key, (translation_key, default) in self._section_title_keys.items()
        }
        if hasattr(self, "_work_delegate"):
            self._work_delegate.set_headers(self._row_headers)
        if hasattr(self, "detail_heading_key"):
            self.detail_heading_key.setText(self._t("setup_page.field.drawing_id", "Drawing ID"))
        for key, label in self._detail_section_title_labels.items():
            label.setText(self._section_titles.get(key, label.text()))
        self.search_toggle_btn.setToolTip(self._t("setup_page.search_toggle_tip", "Show/hide search"))
        self.search_input.setPlaceholderText(self._t("setup_page.search_placeholder", "Search works..."))
        self.detail_toggle_btn.setToolTip(self._t("setup_page.details_toggle_tip", "Show/hide work details"))
        self.make_logbook_entry_btn.setText(self._t("setup_page.make_logbook_entry", "Make logbook entry"))
        self.detail_close_btn.setToolTip(self._t("setup_page.close_details_tip", "Close details"))
        self.new_btn.setText(self._t("setup_page.new_work", "New Work"))
        self.edit_btn.setText(self._t("setup_page.edit_work", "Edit Work"))
        self.delete_btn.setText(self._t("setup_page.delete_work", "Delete Work"))
        self.copy_btn.setText(self._t("setup_page.duplicate", "Duplicate"))
        self.print_btn.setText(self._t("setup_page.view_setup_card", "View Setup Card"))
        self._update_selection_count_label()
        if self._details_open:
            self._refresh_details()
        self.refresh_works()

    def _format_lookup(self, item_id, ref_lookup):
        item_id = (item_id or "").strip()
        if not item_id:
            return "-"
        ref = ref_lookup(item_id)
        if not ref:
            return self._t(
                "setup_page.message.missing_from_master_db",
                "{item_id} (missing from master database)",
                item_id=item_id,
            )
        description = (ref.get("description") or "").strip()
        return f"{item_id} - {description}" if description else item_id

    def _format_lookup_list(self, values, ref_lookup):
        clean_values = [str(value).strip() for value in (values or []) if str(value).strip()]
        if not clean_values:
            return "-"
        return "\n".join(self._format_lookup(value, ref_lookup) for value in clean_values)

    def refresh_works(self):
        search = self.search_input.text().strip()
        works = self.work_service.list_works(search)
        self.latest_entries_by_work = self.logbook_service.latest_entries_by_work_ids(
            [work.get("work_id") for work in works]
        )
        previous_id = self.current_work_id
        restored = False
        details_were_open = self._details_open

        blocker = QSignalBlocker(self.work_list.selectionModel())
        self._work_model.clear()
        restored_index = QModelIndex()
        for work in works:
            work_id = work.get("work_id", "")
            drawing_id = work.get("drawing_id", "")
            description = (work.get("description") or "").strip()
            latest_entry = self.latest_entries_by_work.get(work_id)
            latest_text = ""
            if latest_entry:
                latest_text = (
                    f"{latest_entry.get('date', '')}  |  {latest_entry.get('batch_serial', '')}"
                )
            row_data = {
                "work_id": work_id,
                "drawing_id": drawing_id,
                "description": description,
                "latest_text": latest_text or self._t("setup_page.row.no_runs", "No runs yet"),
            }
            item = QStandardItem()
            item.setData(work_id, ROLE_WORK_ID)
            item.setData(row_data, ROLE_WORK_DATA)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self._work_model.appendRow(item)

            if previous_id and work_id == previous_id:
                restored_index = self._work_model.index(self._work_model.rowCount() - 1, 0)
                restored = True

        if not restored:
            self.current_work_id = None
            self.work_list.selectionModel().clearSelection()
            self.work_list.setCurrentIndex(QModelIndex())

        del blocker

        self._sync_work_row_widths()
        QTimer.singleShot(0, self._sync_work_row_widths)

        if restored:
            self.current_work_id = previous_id
            self.work_list.setCurrentIndex(restored_index)
            self.work_list.scrollTo(restored_index)
            self._set_selected_card(self.current_work_id)
            if details_were_open:
                self.show_details()
            else:
                self.hide_details()
            selected_work = self.work_service.get_work(self.current_work_id)
            self._emit_library_launch_context(selected_work)
        else:
            self._set_selected_card(None)
            self.hide_details()
            self._emit_library_launch_context(None)

    def _selected_work_id(self):
        index = self.work_list.currentIndex()
        return index.data(ROLE_WORK_ID) if index.isValid() else None

    def _selected_work_ids(self) -> list[str]:
        model = self.work_list.selectionModel()
        if model is None:
            return []
        indexes = sorted(model.selectedIndexes(), key=lambda idx: idx.row())
        work_ids: list[str] = []
        for index in indexes:
            work_id = (index.data(ROLE_WORK_ID) or "").strip()
            if work_id and work_id not in work_ids:
                work_ids.append(work_id)
        return work_ids

    def _on_multi_selection_changed(self, _selected, _deselected):
        self._update_selection_count_label()

    def _update_selection_count_label(self):
        count = len(self._selected_work_ids())
        if count > 1:
            self.selection_count_label.setText(
                self._t("setup_page.selection.count", "{count} selected", count=count)
            )
            self.selection_count_label.show()
            return
        self.selection_count_label.hide()

    @staticmethod
    def _prune_backups(db_path: Path, tag: str, keep: int = 5):
        prefix = f"{db_path.stem}_{tag}_"
        backups = sorted(
            db_path.parent.glob(f"{prefix}*.bak"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for stale in backups[keep:]:
            try:
                stale.unlink()
            except Exception:
                pass

    def _create_db_backup(self, tag: str) -> Path:
        db_path = Path(self.work_service.db.path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = db_path.parent / f"{db_path.stem}_{tag}_{timestamp}.bak"
        shutil.copy2(db_path, backup_path)
        self._prune_backups(db_path, tag)
        return backup_path

    def _prompt_batch_cancel_behavior(self) -> str:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(self._t("setup_page.batch.cancel.title", "Batch edit cancelled"))
        box.setText(
            self._t(
                "setup_page.batch.cancel.body",
                "You stopped editing partway through the batch. Do you want to keep the changes you\'ve already saved, or undo all of them?",
            )
        )
        keep_btn = box.addButton(
            self._t("setup_page.batch.cancel.keep", "Keep"),
            QMessageBox.AcceptRole,
        )
        undo_btn = box.addButton(
            self._t("setup_page.batch.cancel.undo", "Undo"),
            QMessageBox.DestructiveRole,
        )
        box.addButton(self._t("common.cancel", "Cancel"), QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is undo_btn:
            return "undo"
        if clicked is keep_btn:
            return "keep"
        return "keep"

    def _batch_edit_works(self, work_ids: list[str]):
        saved_before: list[dict] = []
        total = len(work_ids)
        for idx, work_id in enumerate(work_ids, 1):
            work = self.work_service.get_work(work_id)
            if not work:
                continue
            dialog = WorkEditorDialog(
                self.draw_service,
                work=work,
                parent=self,
                translate=self._t,
                batch_label=f"{idx}/{total}",
            )
            if dialog.exec() != QDialog.Accepted:
                if saved_before:
                    action = self._prompt_batch_cancel_behavior()
                    if action == "undo":
                        for previous in reversed(saved_before):
                            self.work_service.save_work(previous)
                self.refresh_works()
                return
            saved_before.append(dict(work))
            self.work_service.save_work(dialog.get_work_data())
        self.refresh_works()

    def _group_edit_works(self, work_ids: list[str]):
        baseline_dialog = WorkEditorDialog(
            self.draw_service,
            parent=self,
            translate=self._t,
            group_edit_mode=True,
            group_count=len(work_ids),
        )
        baseline = baseline_dialog.get_work_data()
        if baseline_dialog.exec() != QDialog.Accepted:
            return
        edited_data = baseline_dialog.get_work_data()
        changed_fields = {
            key: value
            for key, value in edited_data.items()
            if value != baseline.get(key)
        }
        changed_fields.pop("work_id", None)
        if not changed_fields:
            QMessageBox.information(
                self,
                self._t("setup_page.group_edit.no_changes_title", "No changes"),
                self._t("setup_page.group_edit.no_changes_body", "No fields were changed."),
            )
            return

        self._create_db_backup("group_edit")
        for work_id in work_ids:
            work = self.work_service.get_work(work_id)
            if not work:
                continue
            updated = dict(work)
            updated.update(changed_fields)
            updated["work_id"] = work_id
            self.work_service.save_work(updated)
        self.refresh_works()

    def _toggle_search(self):
        show = self.search_toggle_btn.isChecked()
        self._search_visible = show
        self.search_input.setVisible(show)
        self.search_toggle_btn.setIcon(self.close_icon if show else self.search_icon)
        if show:
            self.search_input.setFocus()
            return
        # Match Tool Library behavior: closing search clears the filter.
        self.search_input.clear()
        self.refresh_works()

    def _set_current_item_by_work_id(self, work_id):
        for row in range(self._work_model.rowCount()):
            index = self._work_model.index(row, 0)
            if index.data(ROLE_WORK_ID) == work_id:
                self.work_list.setCurrentIndex(index)
                self.work_list.scrollTo(index)
                return index
        return QModelIndex()

    def eventFilter(self, obj, event):
        if hasattr(self, "detail_scroll") and obj is self.detail_scroll.viewport() and event.type() == QEvent.Resize:
            self._sync_detail_content_width()
        if obj is self.work_list.viewport() and event.type() == QEvent.Resize:
            self._sync_work_row_widths()
            QTimer.singleShot(0, self._sync_work_row_widths)
        if obj in (self.work_list, self.work_list.viewport()):
            if event.type() == QEvent.MouseButtonPress:
                # If the press starts on/near the splitter handle, let splitter drag begin
                # and do not treat it as an empty-list click that clears selection.
                if self._is_press_near_splitter_handle(event):
                    return False
                if not self.work_list.indexAt(event.pos()).isValid():
                    self._clear_selection()
        return super().eventFilter(obj, event)

    def _is_press_near_splitter_handle(self, event) -> bool:
        if not hasattr(self, "_setup_splitter") or self._setup_splitter is None:
            return False
        if not self._details_open:
            return False
        handle = self._setup_splitter.handle(1)
        if handle is None:
            return False
        handle_rect = handle.geometry().adjusted(-10, 0, 10, 0)
        if hasattr(event, "globalPosition"):
            global_pos = event.globalPosition().toPoint()
        elif hasattr(event, "globalPos"):
            global_pos = event.globalPos()
        else:
            return False
        pos_in_splitter = self._setup_splitter.mapFromGlobal(global_pos)
        return handle_rect.contains(pos_in_splitter)

    def _sync_detail_content_width(self):
        if not hasattr(self, "detail_scroll_content") or not hasattr(self, "detail_scroll"):
            return
        viewport_width = max(0, self.detail_scroll.viewport().width())
        right_margin = 8
        self.detail_scroll_content.setFixedWidth(max(0, viewport_width - right_margin))

    def _clear_selection(self):
        self.work_list.selectionModel().clearSelection()
        self.work_list.setCurrentIndex(QModelIndex())
        self.current_work_id = None
        self._update_selection_count_label()
        self._set_selected_card(None)
        self._update_open_library_viewer_visibility(None)
        self._emit_library_launch_context(None)
        self.hide_details()

    def _on_selection_changed(self, current, _previous):
        work_id = current.data(ROLE_WORK_ID) if current and current.isValid() else None
        self.current_work_id = work_id
        self._update_selection_count_label()
        self._set_selected_card(work_id)
        selected_work = self.work_service.get_work(work_id) if work_id else None
        self._update_open_library_viewer_visibility(selected_work)
        self._emit_library_launch_context(selected_work)
        if self._details_open:
            self._refresh_details()

    def _on_item_double_clicked(self, item):
        work_id = item.data(ROLE_WORK_ID) if item and item.isValid() else None
        if not work_id:
            return
        # Double-click selected row toggles details open/closed.
        if self._details_open and self.current_work_id == work_id:
            self.hide_details()
            return
        self.current_work_id = work_id
        self._set_selected_card(work_id)
        self.show_details()

    def _on_detail_toggle_clicked(self):
        if self._details_open:
            self.hide_details()
            return
        work_id = self._selected_work_id()
        if not work_id:
            QMessageBox.information(
                self,
                self._t("setup_page.message.no_work_title", "No work"),
                self._t("setup_page.message.select_work_first", "Select a work first."),
            )
            self.detail_toggle_btn.setChecked(False)
            return
        self.current_work_id = work_id
        self.show_details()

    def show_details(self):
        if not self.current_work_id:
            return
        self._details_open = True
        self.detail_host.setVisible(True)
        self.detail_close_btn.show()
        self.detail_toggle_btn.setChecked(True)
        if hasattr(self, "_setup_splitter"):
            if self._last_detail_sizes and sum(self._last_detail_sizes) > 0:
                self._setup_splitter.setSizes(self._last_detail_sizes)
            else:
                total = max(700, self._setup_splitter.width())
                # Keep first-open detail panel intentionally narrow and consistent.
                detail_width = min(420, max(320, int(total * 0.30)))
                self._setup_splitter.setSizes([max(1, total - detail_width), detail_width])
            self._sync_detail_content_width()
        self._sync_work_row_modes()
        self._refresh_details()

    def hide_details(self):
        if hasattr(self, "_setup_splitter") and self._details_open:
            sizes = self._setup_splitter.sizes()
            if sizes and sizes[1] > 0:
                self._last_detail_sizes = sizes
        self._details_open = False
        self.detail_host.setVisible(False)
        self.detail_close_btn.hide()
        self.detail_toggle_btn.setChecked(False)
        if hasattr(self, "_setup_splitter"):
            self._setup_splitter.setSizes([1, 0])
        self._sync_work_row_modes()

    def _on_splitter_moved(self, pos: int, index: int):
        """Save current splitter ratio whenever the user drags it."""
        if not self._details_open or not hasattr(self, "_setup_splitter"):
            return
        if self._clamping_splitter:
            return
        sizes = self._setup_splitter.sizes()
        if not sizes:
            return

        if sizes[1] <= 0:
            total = max(1, sum(sizes))
            clamped_right = min(max(self._min_detail_panel_width, 1), max(1, total - self._min_list_panel_width))
            clamped_left = max(self._min_list_panel_width, total - clamped_right)
            self._clamping_splitter = True
            try:
                self._setup_splitter.setSizes([clamped_left, clamped_right])
            finally:
                self._clamping_splitter = False
            sizes = self._setup_splitter.sizes()
            if not sizes or sizes[1] <= 0:
                return

        left, right = sizes[0], sizes[1]
        clamped_left = max(self._min_list_panel_width, left)
        clamped_right = max(self._min_detail_panel_width, right)
        total = left + right
        if clamped_left + clamped_right > total:
            clamped_right = max(self._min_detail_panel_width, total - clamped_left)
            if clamped_left + clamped_right > total:
                clamped_left = max(self._min_list_panel_width, total - clamped_right)

        if clamped_left != left or clamped_right != right:
            self._clamping_splitter = True
            try:
                self._setup_splitter.setSizes([clamped_left, clamped_right])
            finally:
                self._clamping_splitter = False
            sizes = self._setup_splitter.sizes()

        if sizes and sizes[1] > 0:
            self._last_detail_sizes = sizes

    def _set_selected_card(self, work_id):
        _ = work_id
        self.work_list.viewport().update()

    def _sync_work_row_modes(self):
        compact = bool(self._details_open)
        self._work_delegate.set_compact_mode(compact)
        self._sync_work_row_widths()
        QTimer.singleShot(0, self._sync_work_row_widths)

    def _sync_work_row_widths(self):
        if not hasattr(self, "work_list"):
            return
        self.work_list.doItemsLayout()
        self.work_list.viewport().update()

    def _set_section_fields(self, key: str, fields: list):
        """Rebuild a detail section with (label, value) field pairs.

        Matches the Tool Library detailField / detailFieldKey / detailFieldValue pattern.
        """
        layout = self.detail_sections[key]
        # Remove everything except the section title (always index 0)
        while layout.count() > 1:
            item = layout.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()
        added = 0
        for label_text, value_text in fields:
            vt = (value_text or "").strip()
            if not vt or vt == "-":
                continue
            layout.addWidget(self._make_detail_field(label_text, vt))
            added += 1
        if added == 0:
            placeholder = QLabel("-")
            placeholder.setProperty("detailHint", True)
            layout.addWidget(placeholder)

    def _make_detail_field(self, label_text: str, value_text: str) -> QFrame:
        field = QFrame()
        field.setProperty("detailField", True)
        fl = QVBoxLayout(field)
        fl.setContentsMargins(6, 4, 6, 4)
        fl.setSpacing(4)
        key_lbl = QLabel(label_text)
        key_lbl.setProperty("detailFieldKey", True)
        val_lbl = QLabel((value_text or "").strip())
        val_lbl.setProperty("detailFieldValue", True)
        val_lbl.setWordWrap(True)
        val_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fl.addWidget(key_lbl)
        fl.addWidget(val_lbl)
        return field

    def _clear_section(self, key: str):
        layout = self.detail_sections[key]
        while layout.count() > 1:
            item = layout.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()

    def _set_jaw_overview(
        self,
        main_jaw_id: str,
        sub_jaw_id: str,
        main_stop_screws: str = "",
        sub_stop_screws: str = "",
    ):
        self._clear_section("jaws")
        layout = self.detail_sections["jaws"]
        layout.setSpacing(4)

        row_host = AdaptiveColumnsWidget()

        def _jaw_box(label: str, jaw_id: str, stop_screws: str):
            jaw = self.draw_service.get_full_jaw(jaw_id) if jaw_id else None
            box = QFrame()
            box.setProperty("jawGroupHost", True)
            box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            box_l = QVBoxLayout(box)
            box_l.setContentsMargins(0, 0, 0, 0)
            box_l.setSpacing(2)
            head = QLabel(label)
            head.setProperty("jawGroupTitle", True)
            box_l.addWidget(head)
            if not jaw:
                missing = QLabel(self._t("setup_page.field.not_specified", "Not specified"))
                missing.setProperty("detailHint", True)
                box_l.addWidget(missing)
                return box
            box_l.addWidget(self._make_detail_field(self._t("setup_page.field.jaw_id", "Jaw ID"), jaw.get("jaw_id", "") or "-"))
            box_l.addWidget(self._make_detail_field(self._t("setup_page.field.type", "Type"), jaw.get("jaw_type", "") or "-"))
            clamping = (jaw.get("clamping_diameter_text") or "").strip() or "-"
            box_l.addWidget(self._make_detail_field(self._t("setup_page.field.clamping", "Clamping"), clamping))
            stop_screws = (stop_screws or "").strip()
            if stop_screws:
                box_l.addWidget(self._make_detail_field(self._t("setup_page.field.stop_screws", "Stop Screws"), stop_screws))
            return box

        row_host.add_widget(_jaw_box(self._t("setup_page.field.sp1", "SP1"), main_jaw_id, main_stop_screws))
        row_host.add_widget(_jaw_box(self._t("setup_page.field.sp2", "SP2"), sub_jaw_id, sub_stop_screws))
        layout.addWidget(row_host)

    def _set_tool_cards(self, key: str, tool_assignments: list):
        self._clear_section(key)
        layout = self.detail_sections[key]
        normalized = []
        for entry in (tool_assignments or []):
            if isinstance(entry, dict):
                tool_id = str(entry.get("tool_id") or entry.get("id") or "").strip()
                raw_uid = entry.get("tool_uid", entry.get("uid"))
                try:
                    tool_uid = int(raw_uid) if raw_uid is not None and str(raw_uid).strip() else None
                except Exception:
                    tool_uid = None
                override_id = str(entry.get("override_id") or "").strip()
                override_description = str(entry.get("override_description") or "").strip()
                pot = str(entry.get("pot") or "").strip()
            else:
                tool_id = str(entry or "").strip()
                tool_uid = None
                override_id = ""
                override_description = ""
                pot = ""
            if tool_id:
                normalized.append((tool_id, tool_uid, override_id, override_description, pot))

        if not normalized:
            placeholder = QLabel(self._t("setup_page.message.no_tools_assigned", "No tools assigned"))
            placeholder.setProperty("detailHint", True)
            layout.addWidget(placeholder)
            return

        for tool_id, tool_uid, override_id, override_description, pot in normalized:
            tool = None
            if tool_uid is not None:
                tool = self.draw_service.get_tool_ref_by_uid(tool_uid)
            if not tool:
                tool = self.draw_service.get_tool_ref(tool_id)
            if not tool:
                deleted_label = self._t("work_editor.tools.deleted_tool", "DELETED TOOL")
                display_id = override_id or tool_id
                text = f"{display_id} - {deleted_label}" if display_id else deleted_label
            else:
                display_id = override_id or tool_id
                desc = override_description or (tool.get("description") or "").strip()
                text = f"{display_id} - {desc}" if desc else display_id
            from html import escape as _he
            row = QFrame()
            row.setProperty("toolCardRow", True)
            row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(6, 4, 6, 4)
            row_layout.setSpacing(8)

            text_lbl = QLabel(text)
            text_lbl.setWordWrap(False)
            text_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            text_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            text_lbl.setStyleSheet("background: transparent; font-size: 14pt; font-weight: 600; color: #171a1d;")
            row_layout.addWidget(text_lbl, 1)

            if pot:
                pot_lbl = QLabel(pot)
                pot_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                pot_lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                pot_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
                pot_lbl.setStyleSheet("background: transparent; font-size: 14pt; font-weight: 700; color: #171a1d;")
                row_layout.addWidget(pot_lbl, 0)

            layout.addWidget(row)

    def _update_open_library_viewer_visibility(self, work=None):
        tool_ids, jaw_ids = self._collect_library_filter_ids(work)
        return bool(tool_ids or jaw_ids)

    def _collect_library_filter_ids(self, work):
        if not work:
            return [], []

        jaw_ids = []
        for jid in (work.get("main_jaw_id") or "", work.get("sub_jaw_id") or ""):
            sid = str(jid).strip()
            if sid and sid not in jaw_ids:
                jaw_ids.append(sid)

        tool_ids = []
        for tid in (work.get("head1_tool_ids") or []) + (work.get("head2_tool_ids") or []):
            sid = str(tid).strip()
            if sid and sid not in tool_ids:
                tool_ids.append(sid)
        return tool_ids, jaw_ids

    def _emit_library_launch_context(self, work=None):
        tool_ids, jaw_ids = self._collect_library_filter_ids(work)
        payload = {
            "selected": bool(work),
            "work_id": (work.get("work_id") or "").strip() if work else "",
            "drawing_id": (work.get("drawing_id") or "").strip() if work else "",
            "drawing_path": (work.get("drawing_path") or "").strip() if work else "",
            "description": (work.get("description") or "").strip() if work else "",
            "tool_ids": tool_ids,
            "jaw_ids": jaw_ids,
            "has_tools": bool(tool_ids),
            "has_jaws": bool(jaw_ids),
            "has_data": bool(tool_ids or jaw_ids),
        }
        self.libraryLaunchContextChanged.emit(payload)

    def _refresh_details(self):
        if not self.current_work_id:
            self.hide_details()
            return
        if not self._details_open:
            return

        work = self.work_service.get_work(self.current_work_id)
        if not work:
            self.detail_id_label.setText(self._t("setup_page.message.missing_work", "Missing work"))
            self.detail_description_label.setText("")
            self.detail_description_label.hide()
            self._update_open_library_viewer_visibility(None)
            for key in self.detail_sections:
                self._set_section_fields(key, [])
            return

        status = self.draw_service.get_reference_source_status()
        tool_db_state = status["tool_db_path"] if status["tool_db_exists"] else self._t(
            "setup_page.message.missing_path", "missing: {path}", path=status["tool_db_path"]
        )
        jaw_db_state = status["jaw_db_path"] if status["jaw_db_exists"] else self._t(
            "setup_page.message.missing_path", "missing: {path}", path=status["jaw_db_path"]
        )

        self.detail_id_label.setText((work.get("drawing_id", "") or "").strip() or "-")
        description = (work.get("description", "") or "").strip()
        self.detail_description_label.setVisible(bool(description))
        self.detail_description_label.setText(description)

        main_jaw = (work.get("main_jaw_id") or "").strip()
        sub_jaw = (work.get("sub_jaw_id") or "").strip()
        main_stop_screws = (work.get("main_stop_screws") or "").strip()
        sub_stop_screws = (work.get("sub_stop_screws") or "").strip()
        self._update_open_library_viewer_visibility(work)

        # Show only zero-point axes that have an explicit value entered.
        def _spindle_zero_text(coord, axis_values):
            coord = (coord or "").strip()
            axis_colors = {
                "z": "#1E5AA8",  # blue
                "x": "#3A495A",
                "y": "#3A6E45",
                "c": "#C96A12",  # orange
            }
            axis_parts = []
            for axis in ("z", "x", "y", "c"):
                value = (axis_values.get(axis) or "").strip()
                if value:
                    color = axis_colors.get(axis, "#22303c")
                    axis_parts.append(
                        f"<span style='font-weight:700; color:{color};'>{axis.upper()}</span>{escape(value)}"
                    )
            if not axis_parts:
                return ""
            axis_text = " ".join(axis_parts)
            if coord:
                return f"{escape(coord)} | {axis_text}"
            return axis_text

        def _append_spindle_axis_field(fields, prefix, spindle_key, spindle_title):
            coord = work.get(f"{prefix}_{spindle_key}_coord") or work.get(f"{prefix}_zero")
            values = {
                axis: work.get(f"{prefix}_{spindle_key}_{axis}")
                for axis in ("z", "x", "y", "c")
            }
            text = _spindle_zero_text(coord, values)
            if text:
                fields.append((spindle_title, text))

        def _head_fields(prefix):
            fields = []
            _append_spindle_axis_field(fields, prefix, "main", self._t("setup_page.field.sp1", "SP1"))
            _append_spindle_axis_field(fields, prefix, "sub", self._t("setup_page.field.sp2", "SP2"))
            return fields

        self._set_section_fields("programs", [
            (self._t("setup_page.field.main_program", "Main Program"), (work.get("main_program", "") or "").strip()),
            (self._t("setup_page.field.sub_programs_head1", "Sub Programs Head 1"), (work.get("head1_sub_program", "") or "").strip()),
            (self._t("setup_page.field.sub_programs_head2", "Sub Programs Head 2"), (work.get("head2_sub_program", "") or "").strip()),
        ])
        self._set_jaw_overview(main_jaw, sub_jaw, main_stop_screws, sub_stop_screws)
        self._set_section_fields("head1", _head_fields("head1"))
        self._set_tool_cards(
            "head1_tools",
            work.get("head1_tool_assignments") or work.get("head1_tool_ids") or [],
        )
        head2_fields = _head_fields("head2")
        self._set_section_fields(
            "head2",
            head2_fields if head2_fields else [
                (self._t("setup_page.field.status", "Status"), self._t("setup_page.field.unused_setup", "Unused for this setup"))
            ],
        )
        self._set_tool_cards(
            "head2_tools",
            work.get("head2_tool_assignments") or work.get("head2_tool_ids") or [],
        )
        sub_pickup = (work.get("sub_pickup_z") or "").strip()
        robot_info = (work.get("robot_info", "") or "").strip()
        robot_fields = []
        if sub_pickup:
            robot_fields.append((self._t("setup_page.field.sub_pickup_z", "Sub pickup Z"), sub_pickup))
        if robot_info:
            robot_fields.append((self._t("setup_page.field.robot_info", "Robot info"), robot_info))
        self._set_section_fields("robot", robot_fields)
        notes_text = (work.get("notes", "") or "").strip()
        self._set_section_fields("notes", [(self._t("setup_page.field.notes", "Notes"), notes_text)] if notes_text else [])
        self._set_section_fields("sources", [
            (self._t("setup_page.field.tool_db", "Tool DB"), tool_db_state),
            (self._t("setup_page.field.jaw_db", "Jaw DB"), jaw_db_state),
        ])

    def _open_library_viewer(self):
        if not self.current_work_id:
            return
        work = self.work_service.get_work(self.current_work_id)
        if not work:
            return
        tool_ids, jaw_ids = self._collect_library_filter_ids(work)

        self.openLibraryMasterFilterRequested.emit(tool_ids, jaw_ids)

    # ------------------------------------------------------------------
    # CRUD actions
    # ------------------------------------------------------------------

    def create_work(self):
        dialog = WorkEditorDialog(self.draw_service, parent=self, translate=self._t)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.work_service.save_work(dialog.get_work_data())
            self.refresh_works()
        except Exception as exc:
            QMessageBox.critical(self, self._t("setup_page.message.save_failed", "Save failed"), str(exc))

    def edit_work(self):
        selected_ids = self._selected_work_ids()
        if not selected_ids:
            return
        if len(selected_ids) > 1:
            mode = ask_multi_edit_mode(self, len(selected_ids), self._t)
            if mode == "batch":
                self._batch_edit_works(selected_ids)
            elif mode == "group":
                self._group_edit_works(selected_ids)
            return

        work_id = selected_ids[0]
        work = self.work_service.get_work(work_id)
        if not work:
            QMessageBox.warning(
                self,
                self._t("setup_page.message.missing_title", "Missing"),
                self._t("setup_page.message.work_no_longer_exists", "Work no longer exists."),
            )
            self.refresh_works()
            return

        dialog = WorkEditorDialog(self.draw_service, work=work, parent=self, translate=self._t)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.work_service.save_work(dialog.get_work_data())
            self.refresh_works()
        except Exception as exc:
            QMessageBox.critical(self, self._t("setup_page.message.save_failed", "Save failed"), str(exc))

    def delete_work(self):
        work_id = self._selected_work_id()
        if not work_id:
            return
        answer = QMessageBox.question(
            self,
            self._t("setup_page.message.delete_work_title", "Delete work"),
            self._t("setup_page.message.delete_work_prompt", "Delete work '{work_id}'?", work_id=work_id),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.work_service.delete_work(work_id)
        self.refresh_works()

    def duplicate_work(self):
        work_id = self._selected_work_id()
        if not work_id:
            return
        new_id, ok = QInputDialog.getText(
            self,
            self._t("setup_page.message.duplicate_work_title", "Duplicate work"),
            self._t("setup_page.message.new_work_id", "New work ID"),
        )
        if not ok or not (new_id or "").strip():
            return
        desc, _ = QInputDialog.getText(
            self,
            self._t("setup_page.field.description", "Description"),
            self._t("setup_page.message.new_description_optional", "New description (optional)"),
        )
        try:
            self.work_service.duplicate_work(work_id, new_id.strip(), desc.strip())
            self.refresh_works()
        except Exception as exc:
            QMessageBox.critical(self, self._t("setup_page.message.duplicate_failed", "Duplicate failed"), str(exc))

    def add_log_entry(self):
        work_id = self._selected_work_id()
        if not work_id:
            QMessageBox.information(
                self,
                self._t("setup_page.message.no_work_title", "No work"),
                self._t("setup_page.message.select_work_first", "Select a work first."),
            )
            return

        try:
            next_serial = self.logbook_service.generate_next_serial(work_id, date.today().year)
        except Exception:
            next_serial = ""

        dialog = LogEntryDialog(work_id, next_serial, self, translate=self._t)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.get_data()
        try:
            created_entry = self.logbook_service.add_entry(
                work_id=work_id,
                order_number=payload["order_number"],
                quantity=payload["quantity"],
                notes=payload["notes"],
                custom_serial=payload["serial_to_save"],
            )
            self.refresh_works()
            self.logbookChanged.emit()
        except Exception as exc:
            QMessageBox.critical(self, self._t("setup_page.message.save_failed", "Save failed"), str(exc))
            return

        if dialog.should_print_card():
            try:
                work = self.work_service.get_work(work_id)
                if not work:
                    QMessageBox.warning(
                        self,
                        self._t("setup_page.message.print_card_title", "Print card"),
                        self._t(
                            "setup_page.message.entry_saved_missing_work",
                            "Entry saved, but the related work record could not be loaded.",
                        ),
                    )
                    QMessageBox.information(
                        self,
                        self._t("setup_page.message.saved_title", "Saved"),
                        self._t("setup_page.message.logbook_created", "Logbook entry created."),
                    )
                    return
                preview_dir = Path(tempfile.gettempdir()) / "setup_cards"
                preview_dir.mkdir(parents=True, exist_ok=True)
                entry_no = created_entry.get("id") if isinstance(created_entry, dict) else "latest"
                output_path = preview_dir / f"logbook_entry_card_{work_id}_{entry_no}.pdf"
                self.print_service.generate_logbook_entry_card(work, created_entry, output_path)
                saved_notice = QMessageBox(self)
                saved_notice.setIcon(QMessageBox.Information)
                saved_notice.setWindowTitle(self._t("setup_page.message.saved_title", "Saved"))
                saved_notice.setText(
                    self._t("setup_page.message.logbook_created_opening", "Logbook entry created. Opening card preview...")
                )
                saved_notice.setStandardButtons(QMessageBox.NoButton)
                saved_notice.setModal(False)
                saved_notice.show()

                def _open_card_after_delay():
                    try:
                        saved_notice.close()
                        saved_notice.deleteLater()
                    except Exception:
                        pass
                    if not self.draw_service.open_drawing(output_path):
                        QMessageBox.warning(
                            self,
                            self._t("setup_page.message.open_failed", "Open failed"),
                            self._t(
                                "setup_page.message.card_created_not_opened",
                                "Card created but could not be opened:\n{path}",
                                path=output_path,
                            ),
                        )

                notice_timer = QTimer(saved_notice)
                notice_timer.setSingleShot(True)
                notice_timer.timeout.connect(_open_card_after_delay)
                notice_timer.start(700)
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    self._t("setup_page.message.print_card_title", "Print card"),
                    self._t(
                        "setup_page.message.entry_saved_card_generation_failed",
                        "Entry saved, but card generation failed:\n{error}",
                        error=exc,
                    ),
                )
                QMessageBox.information(
                    self,
                    self._t("setup_page.message.saved_title", "Saved"),
                    self._t("setup_page.message.logbook_created", "Logbook entry created."),
                )
            return

        QMessageBox.information(
            self,
            self._t("setup_page.message.saved_title", "Saved"),
            self._t("setup_page.message.logbook_created", "Logbook entry created."),
        )

    def view_setup_card(self):
        work_id = self._selected_work_id()
        if not work_id:
            QMessageBox.information(
                self,
                self._t("setup_page.message.no_work_title", "No work"),
                self._t("setup_page.message.select_work_first", "Select a work first."),
            )
            return

        work = self.work_service.get_work(work_id)
        if not work:
            QMessageBox.warning(
                self,
                self._t("setup_page.message.missing_title", "Missing"),
                self._t("setup_page.message.work_no_longer_exists", "Work no longer exists."),
            )
            return

        entries = self.logbook_service.list_entries(filters={"work_id": work_id})
        entry = entries[0] if entries else None
        if not entry:
            answer = QMessageBox.question(
                self,
                self._t("setup_page.message.no_logbook_entry_title", "No logbook entry"),
                self._t(
                    "setup_page.message.no_logbook_entry_body",
                    "No logbook entry exists for this work. Continue printing without run data?",
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return

        try:
            preview_dir = Path(tempfile.gettempdir()) / "setup_cards"
            preview_dir.mkdir(parents=True, exist_ok=True)
            output_path = preview_dir / f"setup_card_{work_id}.pdf"
            self.print_service.generate_setup_card(work, entry, output_path)
            if not self.draw_service.open_drawing(output_path):
                QMessageBox.warning(
                    self,
                    self._t("setup_page.message.open_failed", "Open failed"),
                    self._t(
                        "setup_page.message.setup_card_created_not_opened",
                        "Setup card created but could not be opened:\n{path}",
                        path=output_path,
                    ),
                )
        except Exception as exc:
            QMessageBox.critical(self, self._t("setup_page.message.view_failed", "View failed"), str(exc))
