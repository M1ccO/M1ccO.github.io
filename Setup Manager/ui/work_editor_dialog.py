import json
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QIcon, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QBoxLayout,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from machine_profiles import NTX_MACHINE_PROFILE
from ui.work_editor_support import (
    WorkEditorPayloadAdapter,
    SelectorSessionBridge,
    apply_jaw_selector_items_to_selectors,
    apply_tool_selector_items_to_ordered_list,
    collect_unresolved_reference_messages,
    jaw_ref_key,
    merge_jaw_refs_and_sync_selectors,
    merge_tool_refs_and_sync_lists,
    normalize_selector_head,
    normalize_selector_spindle,
    parse_optional_int,
    selector_initial_tool_assignment_buckets,
    selector_initial_tool_assignments,
    tool_ref_key,
    build_general_tab_ui,
    build_notes_tab_ui,
    build_spindles_tab_ui,
    build_zeros_tab_ui,
    build_tools_tab_ui,
    open_jaw_selector_session,
    open_tool_selector_session,
    open_pot_editor_dialog,
    refresh_tool_head_widgets,
    refresh_external_refs,
    sync_tool_head_view,
    default_pot_for_assignment,
    populate_default_pots,
)
from config import (
    DEFAULT_TOOL_ICON,
    ICONS_DIR,
    TOOL_ICONS_DIR,
    TOOL_LIBRARY_EXE_CANDIDATES,
    TOOL_LIBRARY_MAIN_PATH,
    TOOL_LIBRARY_PROJECT_DIR,
    TOOL_LIBRARY_SERVER_NAME,
    TOOL_LIBRARY_TOOL_ICONS_DIR,
    TOOL_TYPE_TO_ICON,
)
from ui.widgets.common import apply_tool_library_combo_style, clear_focused_dropdown_on_outside_click
try:
    from shared.editor_helpers import (
        create_titled_section,
    )
except ModuleNotFoundError:
    from editor_helpers import create_titled_section


WORK_COORDINATES = ["G54", "G55", "G56", "G57", "G58", "G59"]
ZERO_AXES = ("z", "x", "y", "c")


def _noop_translate(_key: str, default: str | None = None, **_kwargs) -> str:
    return default or ""


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("sectionTitle", True)
    return lbl


def _toolbar_icon(name: str) -> QIcon:
    base = Path(ICONS_DIR) / "tools"
    png = base / f"{name}.png"
    if png.exists():
        return QIcon(str(png))
    svg = base / f"{name}.svg"
    if svg.exists():
        return QIcon(str(svg))
    return QIcon()


def _tool_icon_for_type(tool_type: str) -> QIcon:
    icon_name = TOOL_TYPE_TO_ICON.get((tool_type or "").strip(), DEFAULT_TOOL_ICON)
    candidates = [
        Path(TOOL_ICONS_DIR) / icon_name,
        Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / icon_name,
        Path(ICONS_DIR) / "tools" / icon_name,
        Path(TOOL_ICONS_DIR) / DEFAULT_TOOL_ICON,
        Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / DEFAULT_TOOL_ICON,
        Path(ICONS_DIR) / "tools" / DEFAULT_TOOL_ICON,
    ]
    for candidate in candidates:
        if candidate.exists():
            return QIcon(str(candidate))
    return QIcon()


_TURNING_TOOL_TYPES = {
    "O.D Turning",
    "I.D Turning",
    "O.D Groove",
    "I.D Groove",
    "Face Groove",
    "O.D Thread",
    "I.D Thread",
    "Turn Thread",
    "Turn Drill",
    "Turn Spot Drill",
}

WORK_EDITOR_TOOL_ASSIGNMENT_MIME = "application/x-setup-manager-tool-assignment"


def _encode_work_editor_tool_payload(mime: QMimeData, payload: list[dict]) -> None:
    clean_payload = [dict(item) for item in (payload or []) if isinstance(item, dict)]
    mime.setData(WORK_EDITOR_TOOL_ASSIGNMENT_MIME, json.dumps(clean_payload).encode("utf-8"))


def _decode_work_editor_tool_payload(mime: QMimeData) -> list[dict]:
    try:
        raw = bytes(mime.data(WORK_EDITOR_TOOL_ASSIGNMENT_MIME)).decode("utf-8").strip()
    except Exception:
        return []
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return [dict(item) for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


class _WorkEditorToolAssignmentListWidget(QListWidget):
    externalAssignmentsDropped = Signal(list, int, object)
    orderChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)

    def startDrag(self, supportedActions):
        indexes = sorted(self.selectedIndexes(), key=lambda idx: idx.row())
        if not indexes:
            current = self.currentIndex()
            if current.isValid():
                indexes = [current]
        if not indexes:
            return

        mime = self.model().mimeData(indexes) or QMimeData()
        payload: list[dict] = []
        for index in indexes:
            item = self.item(index.row())
            if item is None:
                continue
            assignment = item.data(Qt.UserRole)
            if isinstance(assignment, dict):
                payload.append(dict(assignment))
        _encode_work_editor_tool_payload(mime, payload)

        drag = QDrag(self)
        drag.setMimeData(mime)

        first_row = indexes[0].row()
        ghost_item = self.item(first_row)
        ghost_widget = self.itemWidget(ghost_item) if ghost_item is not None else None
        if isinstance(ghost_widget, QWidget):
            card_widget = ghost_widget.findChild(MiniAssignmentCard)
            preview_widget = card_widget if isinstance(card_widget, QWidget) else ghost_widget
            grabbed = preview_widget.grab()
            if not grabbed.isNull():
                translucent = QPixmap(grabbed.size())
                translucent.fill(Qt.transparent)
                painter = QPainter(translucent)
                painter.setOpacity(0.7)
                painter.drawPixmap(0, 0, grabbed)
                painter.end()
                drag.setPixmap(translucent)
                drag.setHotSpot(translucent.rect().center())
        elif payload:
            text = str(payload[0].get("tool_id") or "").strip()
            pixmap = QPixmap(220, 40)
            pixmap.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setOpacity(0.75)
            painter.setBrush(QColor("#f0f6fc"))
            painter.setPen(QColor("#637282"))
            painter.drawRoundedRect(1, 1, 218, 38, 6, 6)
            painter.setOpacity(1.0)
            painter.setPen(QColor("#22303c"))
            painter.drawText(10, 4, 200, 32, Qt.AlignVCenter | Qt.TextSingleLine, text)
            painter.end()
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())

        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(WORK_EDITOR_TOOL_ASSIGNMENT_MIME):
            event.acceptProposedAction()
            return
        if event.source() is self:
            super().dragEnterEvent(event)
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(WORK_EDITOR_TOOL_ASSIGNMENT_MIME):
            event.acceptProposedAction()
            return
        if event.source() is self:
            super().dragMoveEvent(event)
            return
        event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat(WORK_EDITOR_TOOL_ASSIGNMENT_MIME) and event.source() is not self:
            dropped = _decode_work_editor_tool_payload(event.mimeData())
            point = event.position().toPoint() if hasattr(event, "position") else event.pos()
            row = self.indexAt(point).row()
            if row < 0:
                row = self.count()
            self.externalAssignmentsDropped.emit(dropped if isinstance(dropped, list) else [], row, event.source())
            event.acceptProposedAction()
            return
        super().dropEvent(event)
        if event.source() is self:
            self.orderChanged.emit()

    def mousePressEvent(self, event):
        point = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if self.itemAt(point) is None:
            self.clearSelection()
            self.setCurrentRow(-1)
        super().mousePressEvent(event)


class _WorkEditorToolRemoveDropButton(QPushButton):
    assignmentsDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if _decode_work_editor_tool_payload(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if _decode_work_editor_tool_payload(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        dropped = _decode_work_editor_tool_payload(event.mimeData())
        if not dropped:
            event.ignore()
            return
        self.assignmentsDropped.emit(dropped)
        event.acceptProposedAction()


def _is_turning_tool_type(tool_type: str) -> bool:
    return (tool_type or "").strip() in _TURNING_TOOL_TYPES


def _tool_icon_for_type_in_spindle(tool_type: str, spindle: str) -> QIcon:
    icon = _tool_icon_for_type(tool_type)
    if icon.isNull():
        return icon
    is_sub = (spindle or "").strip().lower() == "sub"
    if not is_sub or not _is_turning_tool_type(tool_type):
        return icon
    pixmap = icon.pixmap(QSize(32, 32))
    if pixmap.isNull():
        return icon
    mirrored = pixmap.transformed(QTransform().scale(-1, 1), Qt.SmoothTransformation)
    return QIcon(mirrored)


def _tool_icon_for_ref(tool: dict | None) -> QIcon:
    if not isinstance(tool, dict):
        return _tool_icon_for_type("")
    return _tool_icon_for_type(tool.get("tool_type", ""))


try:
    from shared.mini_assignment_card import MiniAssignmentCard  # noqa: E402
except ModuleNotFoundError:
    # When launched with "Setup Manager" as app root, ensure workspace root is importable.
    _workspace_root = Path(__file__).resolve().parents[2]
    if str(_workspace_root) not in sys.path:
        sys.path.insert(0, str(_workspace_root))
    from shared.mini_assignment_card import MiniAssignmentCard  # noqa: E402


class _JawSelectorPanel(QWidget):
    """Compact single-jaw panel used by the work editor spindles tab."""

    selectionChanged = Signal(str)

    def __init__(
        self,
        title: str,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
        filter_placeholder_key: str = "work_editor.jaw.filter_placeholder",
        filter_placeholder_default: str = "Filter jaws...",
        spindle_side_filter: str | None = None,
    ):
        super().__init__(parent)
        self._translate = translate or _noop_translate
        self._filter_placeholder_key = filter_placeholder_key
        self._filter_placeholder_default = filter_placeholder_default
        self._spindle_side_filter = spindle_side_filter
        self._title = title
        self._all_jaws: list[dict] = []
        self._selected_jaw_id = ""
        self._stop_screws_value = ""
        self._is_stop_screws_mode = False
        self._assignment_card: MiniAssignmentCard | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        selection_group = create_titled_section(title)
        selection_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        selection_layout = QVBoxLayout(selection_group)
        self._selection_layout = selection_layout
        selection_layout.setContentsMargins(8, 10, 8, 8)
        selection_layout.setSpacing(6)

        self.assignment_placeholder = QLabel(self._t("work_editor.jaw.none_selected", "No jaw selected"))
        self.assignment_placeholder.setProperty("detailHint", True)
        self.assignment_placeholder.setStyleSheet("font-style: italic; font-weight: 400;")
        self.assignment_placeholder.setWordWrap(False)
        self.assignment_placeholder.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.assignment_placeholder.setFixedHeight(38)
        selection_layout.addWidget(self.assignment_placeholder)
        layout.addWidget(selection_group, 0)

        self.stop_screws_group = create_titled_section(self._t("setup_page.field.stop_screws", "Stop Screws"))
        self.stop_screws_group.setProperty("jawInputGroup", True)
        self.stop_screws_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        stop_layout = QVBoxLayout(self.stop_screws_group)
        stop_layout.setContentsMargins(10, 8, 10, 8)
        stop_layout.setSpacing(0)

        self.stop_screws_input = QLineEdit()
        self.stop_screws_input.setPlaceholderText(
            self._t("work_editor.jaw.stop_screws_placeholder", "e.g. 10mm")
        )
        self.stop_screws_input.textChanged.connect(self._on_stop_screws_changed)
        stop_layout.addWidget(self.stop_screws_input)
        layout.addWidget(self.stop_screws_group, 0)
        layout.addStretch(1)

        self._refresh_assignment_view()
        self._update_stop_screws_visibility()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    @staticmethod
    def _is_spiked_jaw(jaw: dict | None) -> bool:
        if not jaw:
            return False
        jaw_type = (jaw.get("jaw_type") or "").strip().lower()
        if jaw_type:
            return "spiked" in jaw_type
        description = (jaw.get("description") or "").strip().lower()
        return "spiked" in description

    def _selected_jaw(self) -> dict | None:
        if not self._selected_jaw_id:
            return None
        for jaw in self._all_jaws or []:
            jaw_id = str(jaw.get("id") or jaw.get("jaw_id") or "").strip()
            if jaw_id == self._selected_jaw_id:
                return jaw
        return None

    def _jaw_icon(self) -> QIcon:
        # Prefer spindle-specific jaw icons: sub uses jaw_sub, main uses jaw_main.
        # Fall back to jaw/hard_jaw icons if chuck images are missing.
        side = (self._spindle_side_filter or '').strip().lower()
        is_sub = side in {'sub', 'sub spindle', 'subspindle', 'counter spindle'}

        lookup = []
        if is_sub:
            lookup += [
                Path(TOOL_ICONS_DIR) / "jaw_sub.png",
                Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / "jaw_sub.png",
                Path(ICONS_DIR) / "tools" / "jaw_sub.png",
                Path(TOOL_ICONS_DIR) / "jaw_main.png",
                Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / "jaw_main.png",
                Path(ICONS_DIR) / "tools" / "jaw_main.png",
            ]
        else:
            lookup += [
                Path(TOOL_ICONS_DIR) / "jaw_main.png",
                Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / "jaw_main.png",
                Path(ICONS_DIR) / "tools" / "jaw_main.png",
                Path(TOOL_ICONS_DIR) / "jaw_sub.png",
                Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / "jaw_sub.png",
                Path(ICONS_DIR) / "tools" / "jaw_sub.png",
            ]

        # previous fallbacks
        lookup += [
            Path(TOOL_ICONS_DIR) / "jaw_icon.png",
            Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / "jaw_icon.png",
            Path(TOOL_ICONS_DIR) / "hard_jaw.png",
            Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / "hard_jaw.png",
            Path(ICONS_DIR) / "tools" / "hard_jaw.png",
        ]

        for candidate in lookup:
            if candidate.exists():
                icon = QIcon(str(candidate))
                if not icon.isNull():
                    return icon
        return QIcon()

    def _refresh_assignment_view(self):
        jaw = self._selected_jaw()
        has_selection = bool(self._selected_jaw_id)

        if not has_selection:
            self.assignment_placeholder.setText(self._t("work_editor.jaw.none_selected", "No jaw selected"))
            self.assignment_placeholder.setVisible(True)
            if self._assignment_card is not None:
                self._assignment_card.setVisible(False)
            return

        jaw_id = self._selected_jaw_id
        description = (jaw.get("description") or "").strip() if isinstance(jaw, dict) else ""
        if not description and isinstance(jaw, dict):
            description = str(jaw.get("jaw_type") or "").strip()
        label = f"{jaw_id}  -  {description}" if description else jaw_id
        if self._assignment_card is None:
            icon = self._jaw_icon()
            self._assignment_card = MiniAssignmentCard(
                icon=icon,
                title=label,
                subtitle="",
                badges=[],
                editable=False,
                compact=True,
                parent=self,
            )
            self._assignment_card.subtitle_label.setVisible(False)
            self._assignment_card.setMaximumWidth(420)
            self._assignment_card.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            if not icon.isNull():
                self._assignment_card.icon_label.setPixmap(icon.pixmap(QSize(32, 32)))
            self._selection_layout.insertWidget(0, self._assignment_card)
        else:
            self._assignment_card.title_label.setText(label)
            icon = self._jaw_icon()
            if not icon.isNull():
                self._assignment_card.icon_label.setPixmap(icon.pixmap(QSize(32, 32)))
            self._assignment_card.setMaximumWidth(420)
            self._assignment_card.setVisible(True)
        self._assignment_card.set_selected(False)
        self.assignment_placeholder.setVisible(False)

    def _update_stop_screws_visibility(self):
        stop_screws_mode = self._is_spiked_jaw(self._selected_jaw())
        self._is_stop_screws_mode = stop_screws_mode
        self.stop_screws_group.setVisible(stop_screws_mode)
        if stop_screws_mode:
            self.stop_screws_input.blockSignals(True)
            self.stop_screws_input.setText(self._stop_screws_value)
            self.stop_screws_input.blockSignals(False)

    def populate(self, jaws: list):
        self._all_jaws = [dict(item) for item in (jaws or []) if isinstance(item, dict)]
        self._refresh_assignment_view()
        self._update_stop_screws_visibility()

    def _on_stop_screws_changed(self, text: str):
        self._stop_screws_value = (text or "").strip()

    def get_value(self) -> str:
        return self._selected_jaw_id

    def set_value(self, jaw_id: str):
        self._selected_jaw_id = (jaw_id or "").strip()
        self._refresh_assignment_view()
        self._update_stop_screws_visibility()
        self.selectionChanged.emit(self.get_value())

    def set_stop_screws(self, value: str):
        self._stop_screws_value = (value or "").strip()
        if self._is_stop_screws_mode:
            self.stop_screws_input.blockSignals(True)
            self.stop_screws_input.setText(self._stop_screws_value)
            self.stop_screws_input.blockSignals(False)

    def get_stop_screws(self) -> str:
        if not self._is_spiked_jaw(self._selected_jaw()):
            return ""
        return self._stop_screws_value


class _ToolPickerDialog(QDialog):
    """Multi-select checkbox dialog that lets the user choose tools from the DB."""

    def __init__(
        self,
        all_tools: list,
        current_ids: list,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
        spindle_orientation_filter: str | None = None,
    ):
        super().__init__(parent)
        self._translate = translate or _noop_translate
        self._spindle_orientation_filter = (spindle_orientation_filter or "").strip().lower()
        self.setWindowTitle(self._t("work_editor.tool_picker.title", "Select Tools"))
        self.resize(760, 560)
        self.setProperty("toolPickerDialog", True)
        self._all_tools = all_tools
        self._selected_keys = {str(item).strip() for item in (current_ids or []) if str(item).strip()}
        self._updating_list = False
        self._search_visible = False
        self._search_icon = _toolbar_icon("search_icon")
        self._close_icon = _toolbar_icon("close_icon")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)

        self.search_toggle_btn = QToolButton()
        self.search_toggle_btn.setProperty("topBarIconButton", True)
        self.search_toggle_btn.setCheckable(True)
        self.search_toggle_btn.setToolTip(self._t("drawing_page.search_toggle_tip", "Show/hide search"))
        if not self._search_icon.isNull():
            self.search_toggle_btn.setIcon(self._search_icon)
            self.search_toggle_btn.setIconSize(QSize(22, 22))
        else:
            self.search_toggle_btn.setText(self._t("work_editor.tool_picker.search_label", "Search"))
        self.search_toggle_btn.setFixedSize(34, 34)
        self.search_toggle_btn.clicked.connect(self._toggle_search)
        controls.addWidget(self.search_toggle_btn)

        self.search = QLineEdit()
        self.search.setPlaceholderText(self._t("work_editor.tool_picker.search_placeholder", "Search tools..."))
        self.search.setVisible(False)
        self.search.textChanged.connect(self._build_list)
        self.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        controls.addWidget(self.search, 1)

        self.type_filter = QComboBox()
        self.type_filter.setObjectName("topTypeFilter")
        self.type_filter.setProperty("modernDropdown", True)
        self.type_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.type_filter.setMinimumWidth(160)
        self._style_combo_popup(self.type_filter)
        self.type_filter.addItem(self._t("work_editor.tool_picker.all_types", "All types"), "")
        for tool_type in self._tool_types():
            self.type_filter.addItem(self._localized_tool_type(tool_type), tool_type)
        self.type_filter.currentIndexChanged.connect(self._build_list)
        controls.addWidget(self.type_filter, 0)

        controls.addStretch(1)
        layout.addLayout(controls)

        list_panel = QFrame()
        list_panel.setProperty("toolPickerPanel", True)
        list_panel_layout = QVBoxLayout(list_panel)
        list_panel_layout.setContentsMargins(6, 6, 6, 6)
        list_panel_layout.setSpacing(0)

        self.tool_list = QListWidget()
        self.tool_list.setObjectName("toolPickerList")
        self.tool_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.tool_list.setFocusPolicy(Qt.NoFocus)
        self.tool_list.itemChanged.connect(self._on_item_changed)
        list_panel_layout.addWidget(self.tool_list, 1)
        layout.addWidget(list_panel, 1)

        self._build_list()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if ok_btn is not None:
            ok_btn.setProperty("panelActionButton", True)
            ok_btn.setProperty("primaryAction", True)
            ok_btn.setText(self._t("common.save", "Save"))
        if cancel_btn is not None:
            cancel_btn.setProperty("panelActionButton", True)
            cancel_btn.setProperty("secondaryAction", True)
            cancel_btn.setText(self._t("common.cancel", "Cancel"))
        layout.addWidget(buttons)

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _style_combo_popup(self, combo: QComboBox):
        apply_tool_library_combo_style(combo)

    def _localized_tool_type(self, tool_type: str) -> str:
        raw = (tool_type or "").strip()
        if not raw:
            return ""
        normalized = raw.lower().replace(".", "_").replace("/", "_").replace(" ", "_")
        while "__" in normalized:
            normalized = normalized.replace("__", "_")
        return self._t(f"work_editor.tool_type.{normalized}", raw)

    @staticmethod
    def _normalize_spindle_orientation(value: str) -> str:
        text = (value or "").strip().lower()
        if not text:
            return ""
        if "both" in text or "molem" in text:
            return "both"
        if text in ("sub", "sp2") or "sub" in text or "vasta" in text:
            return "sub"
        if text in ("main", "sp1") or "main" in text or "pää" in text or "paa" in text:
            return "main"
        return text

    def _tool_types(self) -> list:
        values = {
            (tool.get("tool_type") or "").strip()
            for tool in (self._all_tools or [])
            if (tool.get("tool_type") or "").strip()
        }
        return sorted(values, key=lambda value: self._localized_tool_type(value).lower())

    def _toggle_search(self):
        show = self.search_toggle_btn.isChecked()
        self._search_visible = show
        self.search.setVisible(show)
        if not self._search_icon.isNull() and not self._close_icon.isNull():
            self.search_toggle_btn.setIcon(self._close_icon if show else self._search_icon)
        else:
            self.search_toggle_btn.setText(
                self._t("work_editor.tool_picker.close_label", "Close")
                if show
                else self._t("work_editor.tool_picker.search_label", "Search")
            )
        if show:
            self.search.setFocus()
            return
        self.search.clear()
        self._build_list()

    def _matches_filters(self, tool: dict) -> bool:
        if self._spindle_orientation_filter:
            tool_spindle = self._normalize_spindle_orientation(tool.get("spindle_orientation") or "")
            if tool_spindle and tool_spindle not in (self._spindle_orientation_filter, "both"):
                return False

        tool_type = (tool.get("tool_type") or "").strip()
        selected_type = self.type_filter.currentData() if hasattr(self, "type_filter") else ""
        if selected_type and tool_type.lower() != str(selected_type).lower():
            return False

        query = self.search.text().strip().lower() if self._search_visible else ""
        if not query:
            return True
        tool_id = (tool.get("id") or "").strip()
        description = (tool.get("description") or "").strip()
        localized_type = self._localized_tool_type(tool_type)
        text = f"{tool_id} {description} {tool_type} {localized_type}".lower()
        return query in text

    @staticmethod
    def _tool_key(tool: dict) -> str:
        uid = tool.get("uid") if isinstance(tool, dict) else None
        if uid is not None and str(uid).strip():
            return f"uid:{uid}"
        return f"id:{(tool.get('id') or '').strip()}"

    def _build_list(self, *_args):
        self._updating_list = True

        self.tool_list.clear()
        for tool in self._all_tools:
            tool_id = (tool.get("id") or "").strip()
            if not tool_id:
                continue
            if not self._matches_filters(tool):
                continue
            description = (tool.get("description") or "").strip()
            label = f"{tool_id}  \u2014  {description}" if description else tool_id
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, self._tool_key(tool))
            item.setData(Qt.UserRole + 1, dict(tool))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if self._tool_key(tool) in self._selected_keys else Qt.Unchecked)
            self.tool_list.addItem(item)
        self._updating_list = False

    def _on_item_changed(self, item: QListWidgetItem):
        if self._updating_list:
            return
        tool_key = (item.data(Qt.UserRole) or "").strip()
        if not tool_key:
            return
        if item.checkState() == Qt.Checked:
            self._selected_keys.add(tool_key)
        else:
            self._selected_keys.discard(tool_key)

    def get_selected_tools(self) -> list[dict]:
        selected = self._selected_keys
        return [
            dict(tool)
            for tool in (self._all_tools or [])
            if self._tool_key(tool) in selected
        ]


class _OrderedToolList(QWidget):
    """Per-head tool assignment editor with separate SP1/SP2 lists."""

    selectorRequested = Signal(str, str)

    _SPINDLE_OPTIONS = (
        ("SP1", "main"),
        ("SP2", "sub"),
    )

    class _ToolAssignmentRowWidget(MiniAssignmentCard):
        def __init__(
            self,
            icon: QIcon,
            text: str,
            subtitle: str = "",
            comment: str = "",
            pot: str = "",
            edited: bool = False,
            parent=None,
        ):
            badges: list[str] = []
            if pot:
                badges.append(f"P:{pot}")
            if comment:
                badges.append("C")
            if edited:
                badges.append("E")
            super().__init__(
                icon=icon,
                title=text,
                subtitle=subtitle,
                badges=badges,
                editable=True,
                compact=True,
                parent=parent,
            )

    @staticmethod
    def _configure_icon_action(btn: QPushButton, icon_name: str, tooltip: str, *, danger: bool = False):
        btn.setText("")
        btn.setToolTip(tooltip)
        icon = _toolbar_icon(icon_name)
        if not icon.isNull():
            btn.setIcon(icon)
            btn.setIconSize(QSize(18, 18))
        btn.setFixedSize(52, 32)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn.setProperty("panelActionButton", True)
        if danger:
            btn.setProperty("dangerAction", True)

    def __init__(
        self,
        head_label: str,
        head_key: str,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self._translate = translate or _noop_translate
        self._head_key = (head_key or "").strip().upper()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        self.spindle_selector = QComboBox()
        self.spindle_selector.setProperty("modernDropdown", True)
        self.spindle_selector.setMinimumWidth(116)
        self.spindle_selector.setMaximumWidth(150)
        apply_tool_library_combo_style(self.spindle_selector)
        for label, value in self._SPINDLE_OPTIONS:
            self.spindle_selector.addItem(label, value)

        self.select_btn = QPushButton(self._t("work_editor.tools.select_tools", "Select Tools\u2026"))
        self.select_btn.setProperty("panelActionButton", True)
        self.select_btn.setProperty("primaryAction", True)
        self.select_btn.setMinimumWidth(112)
        self.select_btn.setMaximumWidth(150)
        self.select_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self.select_btn.setVisible(False)
        self.select_btn.setEnabled(False)
        header_row.addStretch(1)
        header_row.addWidget(self.spindle_selector)
        layout.addLayout(header_row)

        list_panel = create_titled_section(head_label)
        list_panel.setProperty("toolIdsPanel", True)
        list_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        list_panel_layout = QVBoxLayout(list_panel)
        list_panel_layout.setContentsMargins(8, 10, 8, 8)
        list_panel_layout.setSpacing(0)

        self.tool_list = _WorkEditorToolAssignmentListWidget()
        self.tool_list._owner = self
        self.tool_list.setObjectName("toolIdsOrderList")
        self.tool_list.setSortingEnabled(False)
        list_panel_layout.addWidget(self.tool_list, 1)
        layout.addWidget(list_panel, 1)

        self.controls_bar = QWidget()
        btn_row = QHBoxLayout(self.controls_bar)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        self.move_up_btn = QPushButton(self._t("work_editor.tools.move_up", "\u25B2"))
        self.move_down_btn = QPushButton(self._t("work_editor.tools.move_down", "\u25BC"))
        self.remove_btn = QPushButton(self._t("work_editor.tools.remove", "Remove"))
        for btn in (self.move_up_btn, self.move_down_btn, self.remove_btn):
            btn.setProperty("panelActionButton", True)
            btn.setMinimumWidth(64)
            btn.setMaximumWidth(92)
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.move_up_btn.setMinimumWidth(52)
        self.move_up_btn.setMaximumWidth(64)
        self.move_down_btn.setMinimumWidth(52)
        self.move_down_btn.setMaximumWidth(64)
        self.move_up_btn.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.move_down_btn.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.remove_btn.setProperty("dangerAction", True)

        btn_row.addWidget(self.move_up_btn)
        btn_row.addWidget(self.move_down_btn)
        btn_row.addWidget(self.remove_btn)

        self.comment_btn = QPushButton(self._t("work_editor.tools.add_comment", "Add Comment"))
        self.delete_comment_btn = QPushButton(self._t("work_editor.tools.delete_comment", "Delete Comment"))
        self.comment_btn.setMinimumWidth(112)
        self.comment_btn.setMaximumWidth(150)
        self.delete_comment_btn.setMinimumWidth(112)
        self.delete_comment_btn.setMaximumWidth(150)

        self._configure_icon_action(
            self.select_btn,
            "select",
            self._t("work_editor.tools.select_tools", "Select Tools"),
        )
        self._configure_icon_action(
            self.comment_btn,
            "comment",
            self._t("work_editor.tools.add_comment", "Add Comment"),
        )
        self._configure_icon_action(
            self.delete_comment_btn,
            "comment_delete",
            self._t("work_editor.tools.delete_comment", "Delete Comment"),
        )
        self._configure_icon_action(
            self.remove_btn,
            "delete",
            self._t("work_editor.tools.remove", "Remove Tool"),
            danger=True,
        )

        btn_row.addWidget(self.comment_btn)
        btn_row.addWidget(self.delete_comment_btn)

        btn_row.addStretch(1)
        layout.addWidget(self.controls_bar)

        self.move_up_btn.clicked.connect(self._move_up)
        self.move_down_btn.clicked.connect(self._move_down)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.select_btn.clicked.connect(self._request_selector)
        self.comment_btn.clicked.connect(self._add_or_edit_comment)
        self.delete_comment_btn.clicked.connect(self._delete_comment)
        self.spindle_selector.currentIndexChanged.connect(self._render_current_spindle)
        self.tool_list.currentRowChanged.connect(self._update_action_states)
        self.tool_list.itemSelectionChanged.connect(self._sync_row_selection_states)
        self.tool_list.orderChanged.connect(self._sync_assignment_order)
        self.tool_list.externalAssignmentsDropped.connect(self._on_external_assignments_dropped)

        self._all_tools: list = []
        self._show_pot: bool = False
        self._assignments_by_spindle = {"main": [], "sub": []}
        self._update_action_states()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _current_spindle(self) -> str:
        return (self.spindle_selector.currentData() or "main").strip().lower()

    def set_current_spindle(self, spindle: str):
        target = (spindle or "main").strip().lower()
        index = self.spindle_selector.findData(target)
        if index >= 0:
            self.spindle_selector.setCurrentIndex(index)

    def _current_assignments(self) -> list:
        spindle = self._current_spindle()
        return self._assignments_by_spindle.setdefault(spindle, [])

    def _request_selector(self):
        self.selectorRequested.emit(self._head_key, self._current_spindle())

    def set_controls_visible(self, visible: bool):
        self.controls_bar.setVisible(bool(visible))

    @staticmethod
    def _assignment_key(item: dict) -> str:
        if not isinstance(item, dict):
            return ""
        uid = item.get("tool_uid")
        if uid is not None and str(uid).strip():
            return f"uid:{uid}"
        tool_id = (item.get("tool_id") or "").strip()
        return f"id:{tool_id}" if tool_id else ""

    def _tool_label(self, assignment: dict) -> str:
        labels = self._labels_by_tool_key()
        key = self._assignment_key(assignment)
        tool_id = (assignment.get("tool_id") or "").strip()
        label = labels.get(key)
        if label is None:
            # Tool no longer exists in the database
            deleted = self._t("work_editor.tools.deleted_tool", "DELETED TOOL")
            return f"{tool_id}  -  {deleted}" if tool_id else deleted
        return label

    def _tool_ref_for_assignment(self, assignment: dict) -> dict | None:
        key = self._assignment_key(assignment)
        if not key:
            return None
        for tool in self._all_tools or []:
            if not isinstance(tool, dict):
                continue
            candidate_key = self._assignment_key(
                {
                    "tool_id": (tool.get("id") or "").strip(),
                    "tool_uid": tool.get("uid"),
                }
            )
            if candidate_key == key:
                return dict(tool)
        return None

    def _tool_assignment(self, row: int | None = None) -> dict | None:
        target_row = self.tool_list.currentRow() if row is None else row
        if target_row < 0 or target_row >= self.tool_list.count():
            return None
        item = self.tool_list.item(target_row)
        data = item.data(Qt.UserRole)
        return dict(data) if isinstance(data, dict) else None

    def _render_assignment_row(self, item: QListWidgetItem, row_index: int, assignment: dict):
        label = self._tool_label(assignment)
        override_id = (assignment.get("override_id") or "").strip()
        override_desc = (assignment.get("override_description") or "").strip()
        is_edited = bool(override_id or override_desc)
        if is_edited:
            lib_desc = ""
            if "  -  " in label:
                _, lib_desc = label.split("  -  ", 1)
            tool_id = override_id or (assignment.get("tool_id") or "").strip()
            desc = override_desc or lib_desc
            label = f"{tool_id}  -  {desc}" if desc else tool_id
        display_text = f"{row_index + 1}. {label}"
        item.setText("")
        pot = (assignment.get("pot") or "").strip() if self._show_pot else ""
        subtitle = str(assignment.get("comment") or "").strip()
        has_comment = bool(subtitle)
        icon = QIcon()
        ref = self._tool_ref_for_assignment(assignment)
        if isinstance(ref, dict):
            icon = _tool_icon_for_type_in_spindle(ref.get("tool_type", ""), self._current_spindle())
        widget = self._ToolAssignmentRowWidget(
            icon=icon,
            text=display_text,
            subtitle=subtitle,
            comment=assignment.get("comment", ""),
            pot=pot,
            edited=is_edited,
            parent=self.tool_list,
        )
        widget.setProperty("hasComment", has_comment)
        widget.editRequested.connect(lambda r=row_index: self._inline_edit_row(r))
        row_host = QWidget(self.tool_list)
        row_host.setAttribute(Qt.WA_StyledBackground, False)
        row_layout = QVBoxLayout(row_host)
        row_layout.setContentsMargins(0, 0, 0, 7)
        row_layout.setSpacing(0)
        row_layout.addWidget(widget)
        self.tool_list.setItemWidget(item, row_host)

    def _render_current_spindle(self):
        current_row = self.tool_list.currentRow()
        self.tool_list.clear()
        for index, assignment in enumerate(self._current_assignments()):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, dict(assignment))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
            has_comment = bool(str(assignment.get("comment") or "").strip())
            item.setSizeHint(QSize(0, 50 if has_comment else 42))
            self.tool_list.addItem(item)
            self._render_assignment_row(item, index, assignment)
        if self.tool_list.count() > 0:
            target_row = current_row if 0 <= current_row < self.tool_list.count() else 0
            self.tool_list.setCurrentRow(target_row)
        self._sync_row_selection_states()
        self._update_action_states()

    def _sync_row_selection_states(self):
        for row in range(self.tool_list.count()):
            item = self.tool_list.item(row)
            widget = self.tool_list.itemWidget(item)
            if isinstance(widget, MiniAssignmentCard):
                widget.set_selected(item.isSelected())
                continue
            card = widget.findChild(MiniAssignmentCard) if isinstance(widget, QWidget) else None
            if isinstance(card, MiniAssignmentCard):
                card.set_selected(item.isSelected())

    def _update_action_states(self):
        has_selection = self.tool_list.currentRow() >= 0
        assignment = self._tool_assignment()
        has_comment = bool((assignment or {}).get("comment"))
        self.move_up_btn.setEnabled(has_selection and self.tool_list.currentRow() > 0)
        self.move_down_btn.setEnabled(has_selection and self.tool_list.currentRow() < self.tool_list.count() - 1)
        self.remove_btn.setEnabled(has_selection)
        self.comment_btn.setEnabled(has_selection)
        self.delete_comment_btn.setEnabled(has_comment)
        self.delete_comment_btn.setVisible(has_comment)

    def _sync_assignment_order(self):
        ordered: list[dict] = []
        for row in range(self.tool_list.count()):
            item = self.tool_list.item(row)
            assignment = item.data(Qt.UserRole) if item is not None else None
            if isinstance(assignment, dict):
                ordered.append(dict(assignment))
        self._assignments_by_spindle[self._current_spindle()] = ordered
        self._sync_row_selection_states()
        self._update_action_states()

    def _normalized_assignment_for_current_spindle(self, assignment: dict | None) -> dict | None:
        if not isinstance(assignment, dict):
            return None
        tool_id = str(assignment.get("tool_id") or assignment.get("id") or "").strip()
        if not tool_id:
            return None
        entry = {
            "tool_id": tool_id,
            "spindle": self._current_spindle(),
            "comment": str(assignment.get("comment") or "").strip(),
            "pot": str(assignment.get("pot") or assignment.get("default_pot") or "").strip(),
            "override_id": str(assignment.get("override_id") or "").strip(),
            "override_description": str(assignment.get("override_description") or "").strip(),
        }
        tool_uid = assignment.get("tool_uid", assignment.get("uid"))
        try:
            parsed_uid = int(tool_uid) if tool_uid is not None and str(tool_uid).strip() else None
        except Exception:
            parsed_uid = None
        if parsed_uid is not None:
            entry["tool_uid"] = parsed_uid
        return entry

    def _insert_assignments(self, dropped_items: list[dict], insert_row: int) -> list[str]:
        assignments = self._current_assignments()
        existing_keys = {self._assignment_key(item) for item in assignments if self._assignment_key(item)}
        insert_at = insert_row if isinstance(insert_row, int) and insert_row >= 0 else len(assignments)
        insert_at = min(insert_at, len(assignments))
        added_keys: list[str] = []
        for raw_item in dropped_items or []:
            normalized = self._normalized_assignment_for_current_spindle(raw_item)
            if normalized is None:
                continue
            key = self._assignment_key(normalized)
            if not key or key in existing_keys:
                continue
            assignments.insert(insert_at, normalized)
            existing_keys.add(key)
            added_keys.append(key)
            insert_at += 1
        return added_keys

    def _remove_assignments_by_keys(self, assignment_keys: list[str] | set[str], *, render: bool = True):
        keys = {str(item).strip() for item in (assignment_keys or []) if str(item).strip()}
        if not keys:
            return
        remaining = [item for item in self._current_assignments() if self._assignment_key(item) not in keys]
        self._assignments_by_spindle[self._current_spindle()] = remaining
        if render:
            self._render_current_spindle()

    def _on_external_assignments_dropped(self, dropped_items: list[dict], insert_row: int, source_widget):
        added_keys = self._insert_assignments(dropped_items, insert_row)
        if not added_keys:
            return
        source_owner = getattr(source_widget, "_owner", None)
        if source_owner is not None and source_owner is not self:
            source_owner._remove_assignments_by_keys(added_keys)
        self._render_current_spindle()
        target_row = min(insert_row, self.tool_list.count() - 1) if self.tool_list.count() else -1
        if target_row >= 0:
            self.tool_list.setCurrentRow(target_row)

    def _move_up(self):
        assignments = self._current_assignments()
        row = self.tool_list.currentRow()
        if row <= 0:
            return
        assignments[row - 1], assignments[row] = assignments[row], assignments[row - 1]
        self._render_current_spindle()
        self.tool_list.setCurrentRow(row - 1)

    def _move_down(self):
        assignments = self._current_assignments()
        row = self.tool_list.currentRow()
        if row < 0 or row >= len(assignments) - 1:
            return
        assignments[row + 1], assignments[row] = assignments[row], assignments[row + 1]
        self._render_current_spindle()
        self.tool_list.setCurrentRow(row + 1)

    def _remove_selected(self):
        row = self.tool_list.currentRow()
        if row >= 0:
            del self._current_assignments()[row]
            self._render_current_spindle()

    def _add_or_edit_comment(self):
        row = self.tool_list.currentRow()
        if row < 0:
            return
        assignments = self._current_assignments()
        assignment = assignments[row]
        tool_id = assignment.get("tool_id", "")
        text, ok = QInputDialog.getText(
            self,
            self._t("work_editor.tools.comment_title", "Tool Comment"),
            self._t("work_editor.tools.comment_prompt", "Comment for {tool_id}", tool_id=tool_id),
            text=assignment.get("comment", ""),
        )
        if not ok:
            return
        assignment["comment"] = (text or "").strip()
        self._render_current_spindle()
        self.tool_list.setCurrentRow(row)

    def _delete_comment(self):
        row = self.tool_list.currentRow()
        if row < 0:
            return
        assignments = self._current_assignments()
        assignments[row]["comment"] = ""
        self._render_current_spindle()
        self.tool_list.setCurrentRow(row)

    def _inline_edit_row(self, row_index: int):
        """Open an inline editing dialog for T-code, description, and pot overrides."""
        assignments = self._current_assignments()
        if row_index < 0 or row_index >= len(assignments):
            return
        assignment = assignments[row_index]
        tool_id = (assignment.get("tool_id") or "").strip()
        # Get current display values
        labels = self._labels_by_tool_key()
        key = self._assignment_key(assignment)
        lib_label = labels.get(key, tool_id)
        lib_id = tool_id
        lib_desc = ""
        if "  -  " in lib_label:
            lib_id, lib_desc = lib_label.split("  -  ", 1)

        dlg = QDialog(self)
        dlg.setWindowTitle(self._t("work_editor.tools.edit_row_title", "Edit Tool Row"))
        dlg.setModal(True)
        dlg.resize(420, 0)
        form = QFormLayout(dlg)
        form.setContentsMargins(14, 14, 14, 14)
        form.setSpacing(8)

        id_input = QLineEdit()
        id_input.setPlaceholderText(lib_id)
        id_input.setText((assignment.get("override_id") or "").strip())
        form.addRow(self._t("work_editor.tools.override_id", "T-code"), id_input)

        desc_input = QLineEdit()
        desc_input.setPlaceholderText(lib_desc)
        desc_input.setText((assignment.get("override_description") or "").strip())
        form.addRow(self._t("work_editor.tools.override_description", "Description"), desc_input)

        effective_pot = (assignment.get("pot") or "").strip() or default_pot_for_assignment(self, assignment)
        pot_input = QLineEdit()
        pot_input.setPlaceholderText(self._t("work_editor.tools.pot_placeholder", "e.g. P1"))
        pot_input.setText(effective_pot)
        form.addRow(self._t("work_editor.tools.pot_number", "Pot"), pot_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if ok_btn:
            ok_btn.setProperty("panelActionButton", True)
            ok_btn.setProperty("primaryAction", True)
        if cancel_btn:
            cancel_btn.setProperty("panelActionButton", True)
            cancel_btn.setProperty("secondaryAction", True)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)

        if dlg.exec() != QDialog.Accepted:
            return
        new_id = id_input.text().strip()
        new_desc = desc_input.text().strip()
        new_pot = pot_input.text().strip()
        # Only store overrides if user actually typed something different
        assignment["override_id"] = new_id if new_id and new_id != lib_id else ""
        assignment["override_description"] = new_desc if new_desc and new_desc != lib_desc else ""
        assignment["pot"] = new_pot
        self._render_current_spindle()
        self.tool_list.setCurrentRow(row_index)

    def _open_picker(self):
        current_keys = [self._assignment_key(item) for item in self._current_assignments() if self._assignment_key(item)]
        spindle_filter = self._current_spindle() if self._head_key == "HEAD2" else None
        dlg = _ToolPickerDialog(
            self._all_tools,
            current_keys,
            self,
            translate=self._t,
            spindle_orientation_filter=spindle_filter,
        )
        if dlg.exec() != QDialog.Accepted:
            return
        selected_tools = dlg.get_selected_tools()
        # Keep existing order for retained items; append newly selected.
        current_assignments = self._current_assignments()
        selected_keys = {
            f"uid:{tool.get('uid')}" if tool.get('uid') is not None and str(tool.get('uid')).strip() else f"id:{(tool.get('id') or '').strip()}"
            for tool in selected_tools
            if (tool.get('id') or '').strip()
        }
        kept = [item for item in current_assignments if self._assignment_key(item) in selected_keys]
        kept_keys = {self._assignment_key(item) for item in kept}
        added = []
        for tool in selected_tools:
            tool_id = (tool.get("id") or "").strip()
            if not tool_id:
                continue
            key = f"uid:{tool.get('uid')}" if tool.get('uid') is not None and str(tool.get('uid')).strip() else f"id:{tool_id}"
            if key in kept_keys:
                continue
            entry = {
                "tool_id": tool_id,
                "spindle": self._current_spindle(),
                "comment": "",
                "pot": (tool.get("default_pot") or "").strip(),
                "override_id": "",
                "override_description": "",
            }
            if tool.get("uid") is not None and str(tool.get("uid")).strip():
                entry["tool_uid"] = int(tool.get("uid"))
            added.append(entry)
        self._assignments_by_spindle[self._current_spindle()] = kept + added
        self._render_current_spindle()

    def _labels_by_tool_key(self) -> dict:
        key_to_label: dict = {}
        for tool in self._all_tools:
            tid = (tool.get("id") or "").strip()
            if not tid:
                continue
            desc = (tool.get("description") or "").strip()
            uid = tool.get("uid")
            key = f"uid:{uid}" if uid is not None and str(uid).strip() else f"id:{tid}"
            key_to_label[key] = f"{tid}  -  {desc}" if desc else tid
        return key_to_label

    def set_tool_assignments(self, assignments: list):
        grouped = {"main": [], "sub": []}
        for item in assignments or []:
            tool_uid = None
            if not isinstance(item, dict):
                tool_id = str(item or "").strip()
                spindle = "main"
                comment = ""
                pot = ""
                override_id = ""
                override_description = ""
            else:
                tool_id = str(item.get("tool_id") or item.get("id") or "").strip()
                raw_uid = item.get("tool_uid", item.get("uid"))
                try:
                    tool_uid = int(raw_uid) if raw_uid is not None and str(raw_uid).strip() else None
                except Exception:
                    tool_uid = None
                spindle = str(item.get("spindle") or "main").strip().lower()
                comment = str(item.get("comment") or "").strip()
                pot = str(item.get("pot") or "").strip()
                override_id = str(item.get("override_id") or "").strip()
                override_description = str(item.get("override_description") or "").strip()
            if not tool_id:
                continue
            if spindle not in grouped:
                spindle = "main"
            entry = {
                "tool_id": tool_id,
                "spindle": spindle,
                "comment": comment,
                "pot": pot,
                "override_id": override_id,
                "override_description": override_description,
            }
            if tool_uid is not None:
                entry["tool_uid"] = tool_uid
            grouped[spindle].append(entry)
        self._assignments_by_spindle.clear()
        self._assignments_by_spindle.update(grouped)
        self._render_current_spindle()

    def set_tool_ids(self, tool_ids: list):
        self.set_tool_assignments([
            {"tool_id": str(tid).strip(), "spindle": "main", "comment": ""}
            for tid in (tool_ids or [])
            if str(tid).strip()
        ])

    def get_tool_ids(self) -> list:
        ids = []
        for spindle in ("main", "sub"):
            for item in self._assignments_by_spindle.get(spindle, []):
                tool_id = (item.get("tool_id") or "").strip()
                if tool_id:
                    ids.append(tool_id)
        return ids

    def get_tool_assignments(self) -> list:
        assignments = []
        for spindle in ("main", "sub"):
            for item in self._assignments_by_spindle.get(spindle, []):
                tool_id = (item.get("tool_id") or "").strip()
                if not tool_id:
                    continue
                entry = {
                    "tool_id": tool_id,
                    "spindle": spindle,
                    "comment": (item.get("comment") or "").strip(),
                    "pot": (item.get("pot") or "").strip(),
                    "override_id": (item.get("override_id") or "").strip(),
                    "override_description": (item.get("override_description") or "").strip(),
                }
                if item.get("tool_uid") is not None:
                    try:
                        entry["tool_uid"] = int(item.get("tool_uid"))
                    except Exception:
                        pass
                assignments.append(entry)
        return assignments


# ======================================================================


class WorkEditorDialog(QDialog):
    def __init__(
        self,
        draw_service,
        work=None,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
        batch_label: str | None = None,
        group_edit_mode: bool = False,
        group_count: int | None = None,
        drawings_enabled: bool = True,
    ):
        super().__init__(parent)
        self.draw_service = draw_service
        self.work = dict(work or {})
        self.is_edit = bool(work)
        self._translate = translate or _noop_translate
        self._batch_label = (batch_label or "").strip()
        self._group_edit_mode = bool(group_edit_mode)
        self._group_count = int(group_count or 0)
        self._drawings_enabled = drawings_enabled
        self.machine_profile = NTX_MACHINE_PROFILE
        self._payload_adapter = WorkEditorPayloadAdapter(self.machine_profile)
        self._zero_axes = tuple(self.machine_profile.zero_axes)
        self._head_profiles = {head.key: head for head in self.machine_profile.heads}
        self._spindle_profiles = {spindle.key: spindle for spindle in self.machine_profile.spindles}
        self._zero_axis_widgets = {axis: [] for axis in self._zero_axes}
        self._zero_axis_inputs: dict[str, list[QLineEdit]] = {axis: [] for axis in self._zero_axes}
        self._zero_coord_inputs: dict[tuple[str, str], QComboBox] = {}
        self._zero_axis_input_map: dict[tuple[str, str, str], QLineEdit] = {}
        self._jaw_selectors: dict[str, _JawSelectorPanel] = {}
        self._ordered_tool_lists: dict[str, _OrderedToolList] = {}
        self._tool_column_lists: dict[str, dict[str, _OrderedToolList]] = {}
        self._all_tool_list_widgets: list[_OrderedToolList] = []
        self._active_tool_list: _OrderedToolList | None = None
        self._syncing_tool_list_state = False
        self._sub_program_inputs: dict[str, QLineEdit] = {}
        self._tool_cache_by_head: dict[str, list[dict]] = {}
        self._tool_cache_all: list[dict] = []
        self._jaw_cache: list[dict] = []

        self.setWindowTitle(self._dialog_title())
        self.resize(960, 680)
        self.setMinimumSize(760, 560)
        self.setSizeGripEnabled(True)
        self.setProperty("workEditorDialog", True)
        self._zero_point_grids: list[QGridLayout] = []
        self._zero_coord_combos: list[QComboBox] = []
        self._zero_row_spacers: list[QLabel] = []
        self._zero_grids_with_groups: list[tuple] = []
        self._selector_bridge = SelectorSessionBridge(
            parent=self,
            translate=self._t,
            show_warning=self._show_selector_warning,
            normalize_head=self._normalize_selector_head,
            normalize_spindle=self._normalize_selector_spindle,
            default_spindle=self._default_selector_spindle,
            initial_tool_assignment_buckets=self._selector_initial_tool_assignment_buckets,
            apply_tool_result=self._apply_tool_selector_result,
            apply_jaw_result=self._apply_jaw_selector_result,
            open_jaw_selector=self._open_jaw_selector,
            tool_library_server_name=TOOL_LIBRARY_SERVER_NAME,
            tool_library_main_path=TOOL_LIBRARY_MAIN_PATH,
            tool_library_project_dir=TOOL_LIBRARY_PROJECT_DIR,
            tool_library_exe_candidates=TOOL_LIBRARY_EXE_CANDIDATES,
        )

        self.tabs = QTabWidget(self)

        self.general_tab = QWidget()
        self.zeros_tab = QWidget()
        self.tools_tab = QWidget()
        self.notes_tab = QWidget()

        self.tabs.addTab(self.general_tab, self._t("work_editor.tab.general", "General"))
        self.tabs.addTab(self.zeros_tab, self._t("work_editor.tab.zero_points", "Zero Points"))
        self.tabs.addTab(self.tools_tab, self._t("work_editor.tab.tool_ids", "Tool IDs"))
        self.tabs.addTab(self.notes_tab, self._t("work_editor.tab.notes", "Notes"))

        self._build_general_tab()
        self._build_zeros_tab()
        self._build_tools_tab()
        self._build_notes_tab()

        root = QVBoxLayout(self)
        root.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        self._dialog_buttons = buttons
        root.addWidget(buttons)

        # Keep dialog actions visually consistent with secondary gray buttons.
        self._set_secondary_button_theme()

        self._load_external_refs()
        self._load_work()

        # Force re-polish now that all combos are in the full widget hierarchy so
        # parent selectors like QDialog[workEditorDialog="true"] resolve correctly.
        for _combo in self.findChildren(QComboBox):
            if _combo.property("toolLibraryCombo"):
                _combo.style().unpolish(_combo)
                _combo.style().polish(_combo)

        self._ensure_selector_callback_server()
        self.destroyed.connect(lambda *_args: self._shutdown_selector_bridge())
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ToolTip and isinstance(obj, QWidget):
            if obj is self or self.isAncestorOf(obj):
                return True
        if event.type() == QEvent.MouseButtonPress:
            clear_focused_dropdown_on_outside_click(obj, self)
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)

    def closeEvent(self, event):
        self._shutdown_selector_bridge()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _head_label(self, head_key: str, fallback: str | None = None) -> str:
        profile = self._head_profiles.get(self._normalize_selector_head(head_key))
        default = fallback or (profile.label_default if profile is not None else head_key)
        if profile is None:
            return default
        return self._t(profile.label_key, default)

    def _spindle_label(self, spindle_key: str, fallback: str | None = None) -> str:
        profile = self._spindle_profiles.get(self._normalize_selector_spindle(spindle_key))
        default = fallback or (profile.label_default if profile is not None else spindle_key)
        if profile is None:
            return default
        return self._t(profile.label_key, default)

    @staticmethod
    def _normalize_selector_head(value: str | None) -> str:
        return normalize_selector_head(value)

    @staticmethod
    def _normalize_selector_spindle(value: str | None) -> str:
        return normalize_selector_spindle(value)

    def _selector_target_ordered_list(self, head_key: str):
        normalized = self._normalize_selector_head(head_key)
        if normalized in self._ordered_tool_lists:
            return self._ordered_tool_lists[normalized]
        return next(iter(self._ordered_tool_lists.values()))

    def _default_selector_spindle(self) -> str:
        current_head = self._current_tools_head_value()
        head_columns = self._tool_column_lists.get(current_head, {})
        for spindle in ("main", "sub"):
            ordered = head_columns.get(spindle)
            if ordered is not None and hasattr(ordered, "tool_list") and ordered.tool_list.hasFocus():
                return spindle
        return self.machine_profile.default_tools_spindle

    def _current_tools_head_value(self) -> str:
        if not hasattr(self, "tools_head_switch"):
            return next(iter(self._head_profiles.keys()), "HEAD1")
        return self._normalize_selector_head(
            self.tools_head_switch.property("head") or next(iter(self._head_profiles.keys()), "HEAD1")
        )

    def _update_tools_head_switch_text(self):
        if not hasattr(self, "tools_head_switch"):
            return
        head = self._current_tools_head_value()
        head_profile = self._head_profiles.get(head)
        label = self._head_label(head, head_profile.label_default if head_profile else head)
        self.tools_head_switch.setText(label)
        self.tools_head_switch.setChecked(head == "HEAD2")

    def _set_tools_head_value(self, head: str):
        normalized = self._normalize_selector_head(head)
        if not hasattr(self, "tools_head_switch"):
            return
        self.tools_head_switch.setProperty("head", normalized)
        self._update_tools_head_switch_text()

    def _toggle_tools_head_view(self):
        if not hasattr(self, "tools_head_switch"):
            return
        target = "HEAD2" if self.tools_head_switch.isChecked() else "HEAD1"
        self._set_tools_head_value(target)
        sync_tool_head_view(self)

    def _default_selector_head(self) -> str:
        for head_key, columns in self._tool_column_lists.items():
            for ordered_list in columns.values():
                if hasattr(ordered_list, "tool_list") and ordered_list.tool_list.hasFocus():
                    return head_key
        return self._current_tools_head_value()

    def _default_jaw_selector_spindle(self) -> str:
        for spindle_key, selector in self._jaw_selectors.items():
            focus_widget = selector.focusWidget()
            if focus_widget is not None and selector.isAncestorOf(focus_widget):
                return spindle_key
        return self._default_selector_spindle()

    def _show_selector_warning(self, title: str, body: str):
        QMessageBox.warning(self, title, body)

    def _ensure_selector_callback_server(self) -> bool:
        return self._selector_bridge.ensure_server()

    def _shutdown_selector_bridge(self):
        self._selector_bridge.shutdown()

    def _open_external_selector_session(
        self,
        *,
        kind: str,
        head: str | None = None,
        spindle: str | None = None,
        follow_up: dict | None = None,
        initial_assignments: list[dict] | None = None,
    ) -> bool:
        return self._selector_bridge.open_session(
            kind=kind,
            head=head,
            spindle=spindle,
            follow_up=follow_up,
            initial_assignments=initial_assignments,
        )

    @staticmethod
    def _parse_optional_int(value) -> int | None:
        return parse_optional_int(value)

    @staticmethod
    def _tool_ref_key(tool: dict | None) -> str:
        return tool_ref_key(tool)

    @staticmethod
    def _jaw_ref_key(jaw: dict | None) -> str:
        return jaw_ref_key(jaw)

    def _merge_tool_refs(self, head_key: str, selected_items: list[dict]):
        target_head = self._normalize_selector_head(head_key)
        self._tool_cache_by_head, self._tool_cache_all = merge_tool_refs_and_sync_lists(
            self._tool_cache_by_head,
            self._tool_cache_all,
            head_key=target_head,
            selected_items=selected_items,
            tool_column_lists=self._tool_column_lists,
        )

    def _merge_jaw_refs(self, selected_items: list[dict]):
        jaw_refs, changed = merge_jaw_refs_and_sync_selectors(
            self._jaw_cache,
            selected_items,
            self._jaw_selectors,
        )
        if changed:
            self._jaw_cache = jaw_refs

    def _apply_tool_selector_result(self, request: dict, selected_items: list[dict]) -> bool:
        head_key = self._normalize_selector_head(request.get("head"))
        spindle = self._normalize_selector_spindle(request.get("spindle"))
        ordered_list = self._selector_target_ordered_list(head_key)
        self._merge_tool_refs(head_key, selected_items)

        # Selector order is authoritative for the active target bucket.
        apply_tool_selector_items_to_ordered_list(
            ordered_list,
            selected_items,
            spindle=spindle,
        )

        # Keep both spindle columns in sync for the target head and show that head.
        self._set_tools_head_value(head_key)
        sync_tool_head_view(self)
        refresh_tool_head_widgets(self, head_key)
        return True

    def _apply_jaw_selector_result(self, request: dict, selected_items: list[dict]) -> bool:
        spindle = self._normalize_selector_spindle(request.get("spindle"))
        self._merge_jaw_refs(selected_items)
        return apply_jaw_selector_items_to_selectors(
            self._jaw_selectors,
            selected_items,
            target_spindle=spindle,
            normalize_spindle_fn=self._normalize_selector_spindle,
        )

    def _dialog_title(self) -> str:
        if self._group_edit_mode:
            if self._group_count > 1:
                return self._t(
                    "work_editor.window_title.group",
                    "Group Edit ({count} items)",
                    count=self._group_count,
                )
            return self._t("work_editor.window_title.group", "Group Edit")
        if self.is_edit:
            base = self._t("work_editor.window_title.edit", "Edit Work")
        else:
            base = self._t("work_editor.window_title.new", "New Work")
        if self._batch_label:
            return f"{base} ({self._batch_label})"
        return base

    def _set_secondary_button_theme(self):
        save_btn = None
        cancel_btn = None
        if hasattr(self, "_dialog_buttons"):
            save_btn = self._dialog_buttons.button(QDialogButtonBox.Save)
            cancel_btn = self._dialog_buttons.button(QDialogButtonBox.Cancel)
            if save_btn is not None:
                save_btn.setText(self._t("common.save", "Save"))
            if cancel_btn is not None:
                cancel_btn.setText(self._t("common.cancel", "Cancel"))
        for btn in self.findChildren(QPushButton):
            btn.setProperty("secondaryAction", False)
            btn.setProperty("panelActionButton", True)
            if btn is save_btn:
                btn.setProperty("primaryAction", True)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _apply_coord_combo_popup_style(self, combo: QComboBox):
        apply_tool_library_combo_style(combo)

    def _make_axis_input(self, value_attr_name: str, axis: str) -> QLineEdit:
        value_input = QLineEdit()
        value_input.setPlaceholderText(axis.upper())
        value_input.setMinimumWidth(88)
        setattr(self, value_attr_name, value_input)
        return value_input

    def _set_zero_xy_visibility(self, show_xy: bool) -> None:
        for axis in ("z", "c"):
            for widget in self._zero_axis_widgets.get(axis, []):
                widget.setVisible(True)
        for axis in ("x", "y"):
            for widget in self._zero_axis_widgets.get(axis, []):
                widget.setVisible(show_xy)

        for spacer in self._zero_row_spacers:
            spacer.setMinimumWidth(56 if show_xy else 0)

        for combo in self._zero_coord_combos:
            if show_xy:
                combo.setMinimumWidth(92)
                combo.setMaximumWidth(16777215)
            else:
                combo.setMinimumWidth(74)
                combo.setMaximumWidth(16777215)
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        zc_min = 74 if not show_xy else 88
        for axis in ("z", "c"):
            for value_input in self._zero_axis_inputs.get(axis, []):
                value_input.setMinimumWidth(zc_min)
                value_input.setMaximumWidth(16777215)
                value_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        axis_columns = {"z": 2, "x": 3, "y": 4, "c": 5}
        axis_stretch = {"z": 1, "x": 1 if show_xy else 0, "y": 1 if show_xy else 0, "c": 1}
        for grid in self._zero_point_grids:
            grid.setHorizontalSpacing(6 if show_xy else 2)
            for axis, col in axis_columns.items():
                grid.setColumnStretch(col, axis_stretch[axis])
            grid.setColumnStretch(1, 1 if show_xy else 0)
            grid.setColumnStretch(0, 0)
            grid.setColumnMinimumWidth(0, 72 if show_xy else 58)

        for grid, group in self._zero_grids_with_groups:
            if show_xy:
                grid.setContentsMargins(12, 8, 12, 8)
            else:
                grid.setContentsMargins(8, 6, 8, 6)

        if hasattr(self, "zero_points_host"):
            self.zero_points_host._switch_width = 1320 if show_xy else 820
            direction = (
                QBoxLayout.TopToBottom
                if self.zero_points_host.width() < self.zero_points_host._switch_width
                else QBoxLayout.LeftToRight
            )
            if self.zero_points_host._layout.direction() != direction:
                self.zero_points_host._layout.setDirection(direction)
                self.zero_points_host._update_separator_shapes()

    def _build_spindle_zero_group(self, title: str, spindle_key: str) -> QGroupBox:
        group = create_titled_section(title)
        group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        root = QVBoxLayout(group)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(8)

        grid_host = QWidget(group)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        self._zero_point_grids.append(grid)
        self._zero_grids_with_groups.append((grid, group))

        spacer = QLabel("")
        spacer.setMinimumWidth(56)
        grid.addWidget(spacer, 0, 0)
        self._zero_row_spacers.append(spacer)

        coord_header = QLabel("WCS")
        coord_header.setProperty("detailFieldKey", True)
        coord_header.setAlignment(Qt.AlignCenter)
        grid.addWidget(coord_header, 0, 1)

        for col, axis in enumerate(self._zero_axes, start=2):
            axis_header = QLabel(axis.upper())
            axis_header.setProperty("detailFieldKey", True)
            axis_header.setAlignment(Qt.AlignCenter)
            grid.addWidget(axis_header, 0, col)
            self._zero_axis_widgets[axis].append(axis_header)

        for row, head in enumerate(self.machine_profile.heads, start=1):
            head_key = head.key
            head_prefix = head_key.lower()
            head_label = QLabel(
                self._t(f"setup_page.section.{head_key.lower()}", head_key)
            )
            head_label.setWordWrap(False)
            grid.addWidget(head_label, row, 0)

            combo_attr_name = f"{head_prefix}_{spindle_key}_coord_combo"
            coord_combo = QComboBox()
            coord_combo.addItems(WORK_COORDINATES)
            coord_combo.setProperty("modernDropdown", True)
            coord_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            coord_combo.setMinimumWidth(92)
            self._apply_coord_combo_popup_style(coord_combo)
            self._zero_coord_combos.append(coord_combo)
            self._zero_coord_inputs[(head_key, spindle_key)] = coord_combo
            setattr(self, combo_attr_name, coord_combo)
            grid.addWidget(coord_combo, row, 1)

            for col, axis in enumerate(self._zero_axes, start=2):
                value_attr_name = f"{head_prefix}_{spindle_key}_{axis}_input"
                value_input = self._make_axis_input(value_attr_name, axis)
                grid.addWidget(value_input, row, col)
                self._zero_axis_widgets[axis].append(value_input)
                self._zero_axis_inputs[axis].append(value_input)
                self._zero_axis_input_map[(head_key, spindle_key, axis)] = value_input

        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        for col in range(2, 2 + len(self._zero_axes)):
            grid.setColumnStretch(col, 1)
        root.addWidget(grid_host, 0)

        return group

    def _set_coord_combo(self, combo: QComboBox, value: str, default: str):
        target = (value or "").strip() or default
        index = combo.findText(target)
        combo.setCurrentIndex(index if index >= 0 else combo.findText(default))

    def _apply_machine_profile_to_jaw_selectors(self):
        """Sync jaw selector affordances from the active machine profile."""
        for spindle_key, selector in self._jaw_selectors.items():
            profile = self._spindle_profiles.get(spindle_key)
            if profile is None:
                selector.setVisible(False)
                continue
            selector._spindle_side_filter = profile.jaw_filter

    def _build_general_tab(self):
        build_general_tab_ui(self, create_titled_section_fn=create_titled_section)

    def _build_spindles_tab(self):
        build_spindles_tab_ui(self, jaw_selector_panel_cls=_JawSelectorPanel)

    def _build_zeros_tab(self):
        build_zeros_tab_ui(
            self,
            jaw_selector_panel_cls=_JawSelectorPanel,
            create_titled_section_fn=create_titled_section,
        )

    def _build_tools_tab(self):
        build_tools_tab_ui(
            self,
            ordered_tool_list_cls=_OrderedToolList,
            remove_drop_button_cls=_WorkEditorToolRemoveDropButton,
            section_label_factory=_section_label,
        )

    def _on_print_pots_toggled(self, checked: bool):
        if checked:
            populate_default_pots(self)
        for ordered_list in self._all_tool_list_widgets:
            ordered_list._show_pot = checked
            ordered_list._render_current_spindle()

    def _open_pot_editor(self):
        open_pot_editor_dialog(self)

    def _open_tool_selector_for_bucket(self, head_key: str, spindle: str):
        self._open_tool_selector(
            initial_head=head_key,
            initial_spindle=spindle,
            initial_assignments=self._selector_initial_tool_assignments(head_key, spindle),
        )

    def _selector_initial_tool_assignments(self, head_key: str, spindle: str) -> list[dict]:
        target_head = self._normalize_selector_head(head_key)
        ordered_list = self._selector_target_ordered_list(target_head)
        return selector_initial_tool_assignments(ordered_list, spindle)

    def _selector_initial_tool_assignment_buckets(self) -> dict[str, list[dict]]:
        return selector_initial_tool_assignment_buckets(
            self._ordered_tool_lists,
            tuple(self._head_profiles.keys()),
            tuple(self._spindle_profiles.keys()),
        )

    def _open_tool_selector(
        self,
        initial_head: str | None = None,
        initial_spindle: str | None = None,
        initial_assignments: list[dict] | None = None,
    ) -> bool:
        return open_tool_selector_session(
            self,
            initial_head=initial_head,
            initial_spindle=initial_spindle,
            initial_assignments=initial_assignments,
        )

    def _open_jaw_selector(self, initial_spindle: str | None = None) -> bool:
        return open_jaw_selector_session(self, initial_spindle=initial_spindle)

    def _build_notes_tab(self):
        build_notes_tab_ui(self, create_titled_section_fn=create_titled_section)

    # ------------------------------------------------------------------
    # IO helpers
    # ------------------------------------------------------------------

    def _browse_drawing(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t("work_editor.dialog.select_drawing", "Select drawing"),
            "",
            self._t("work_editor.dialog.pdf_filter", "PDF Files (*.pdf)"),
        )
        if path:
            self.drawing_path_input.setText(path)

    def _load_external_refs(self):
        refresh_external_refs(self)

    def _load_work(self):
        if not self.work:
            return
        self._payload_adapter.populate_dialog(self, self.work)
        for head_key in self._head_profiles.keys():
            refresh_tool_head_widgets(self, head_key)
        sync_tool_head_view(self)

    def get_work_data(self) -> dict:
        return self._payload_adapter.collect_payload(
            self,
            persisted_work=self.work,
            drawings_enabled=self._drawings_enabled,
        )

    def _on_save(self):
        work_id = self.work_id_input.text().strip()
        if not work_id and not self._group_edit_mode:
            QMessageBox.warning(
                self,
                self._t("work_editor.message.missing_id_title", "Missing ID"),
                self._t("work_editor.message.work_id_required", "Work ID is required."),
            )
            self.tabs.setCurrentWidget(self.general_tab)
            self.work_id_input.setFocus()
            return

        missing = collect_unresolved_reference_messages(self)

        if missing:
            answer = QMessageBox.question(
                self,
                self._t("work_editor.message.unresolved_title", "Unresolved references"),
                self._t(
                    "work_editor.message.unresolved_body",
                    "Some IDs were not found in master databases:\n\n{missing}\n\nSave anyway?",
                    missing="\n".join(missing),
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return

        self.accept()
