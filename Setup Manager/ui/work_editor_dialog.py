import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QBoxLayout,
    QCheckBox,
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
    QScrollArea,
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
    jaw_ref_key,
    load_external_tool_refs,
    merge_jaw_refs,
    merge_tool_refs,
    normalize_selector_head,
    normalize_selector_spindle,
    parse_optional_int,
    selector_initial_tool_assignment_buckets,
    selector_initial_tool_assignments,
    tool_ref_key,
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
        ResponsiveColumnsHost,
        apply_shared_checkbox_style,
        apply_titled_section_style,
        create_titled_section,
    )
except ModuleNotFoundError:
    from editor_helpers import ResponsiveColumnsHost, apply_shared_checkbox_style, apply_titled_section_style, create_titled_section


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
    """Single-jaw selection panel backed by live jaw DB data.

    Mirrors the Tool IDs checkable list style but enforces single selection
    (radio-button behaviour via itemChanged guard).
    """

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
        self._spindle_side_filter = spindle_side_filter  # e.g. 'Main spindle' or 'Sub spindle'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Dynamic input section: border/title always present to avoid layout jump.
        self.dynamic_input_group = create_titled_section(" ")
        self.dynamic_input_group.setProperty("jawInputGroup", True)
        self.dynamic_input_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        search_layout = QVBoxLayout(self.dynamic_input_group)
        search_layout.setContentsMargins(10, 8, 10, 8)
        search_layout.setSpacing(0)

        self.search = QLineEdit()
        self.search.setPlaceholderText(self._t(self._filter_placeholder_key, self._filter_placeholder_default))
        self.search.textChanged.connect(self._on_dynamic_input_changed)
        search_layout.addWidget(self.search)
        layout.addWidget(self.dynamic_input_group)

        selection_group = create_titled_section(title)
        selection_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        selection_layout = QVBoxLayout(selection_group)
        selection_layout.setContentsMargins(8, 10, 8, 8)
        selection_layout.setSpacing(0)

        self.jaw_list = QListWidget()
        self.jaw_list.setProperty("jawListWidget", True)
        self.jaw_list.setFrameShape(QFrame.NoFrame)
        self.jaw_list.setLineWidth(0)
        selection_layout.addWidget(self.jaw_list, 1)
        layout.addWidget(selection_group, 1)

        self._all_jaws: list = []
        self._updating = False
        self._filter_text = ""
        self._stop_screws_value = ""
        self._is_stop_screws_mode = False
        self.jaw_list.itemChanged.connect(self._on_item_changed)
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
        selected_id = self.get_value()
        if not selected_id:
            return None
        for jaw in self._all_jaws:
            if (jaw.get("id") or "").strip() == selected_id:
                return jaw
        return None

    def _update_stop_screws_visibility(self):
        stop_screws_mode = self._is_spiked_jaw(self._selected_jaw())
        if self._is_stop_screws_mode == stop_screws_mode:
            return
        self._is_stop_screws_mode = stop_screws_mode
        self.search.blockSignals(True)
        if stop_screws_mode:
            helper = self._t(
                "work_editor.jaw.deselect_to_filter_hint",
                "(deselect jaws to filter)",
            )
            self.dynamic_input_group.setTitle(
                f"{self._t('setup_page.field.stop_screws', 'Stop Screws')} {helper}"
            )
            self.search.setPlaceholderText(
                self._t("work_editor.jaw.stop_screws_placeholder", "e.g. 10mm")
            )
            self.search.setText(self._stop_screws_value)
        else:
            self.dynamic_input_group.setTitle(
                " "
            )
            self.search.setPlaceholderText(
                self._t(self._filter_placeholder_key, self._filter_placeholder_default)
            )
            self.search.setText(self._filter_text)
            self._rebuild(self._filter_text)
        self.search.blockSignals(False)

    def _on_item_changed(self, changed_item):
        if self._updating:
            return
        if changed_item.checkState() == Qt.Checked:
            # Enforce single selection: uncheck every other item.
            self._updating = True
            for i in range(self.jaw_list.count()):
                item = self.jaw_list.item(i)
                if item is not changed_item:
                    item.setCheckState(Qt.Unchecked)
            self._updating = False
        self._update_stop_screws_visibility()
        self.selectionChanged.emit(self.get_value())

    def populate(self, jaws: list):
        self._all_jaws = jaws
        self._rebuild(self._filter_text)
        self._update_stop_screws_visibility()

    def _rebuild(self, filter_text: str):
        self._updating = True
        q = filter_text.strip().lower()
        current = self.get_value()
        self.jaw_list.clear()
        for jaw in self._all_jaws:
            jaw_id = (jaw.get("id") or "").strip()
            if not jaw_id:
                continue
            # Filter by spindle side if a filter is set; jaws with 'Both' always pass.
            if self._spindle_side_filter:
                jaw_side = (jaw.get("spindle_side") or "").strip()
                if jaw_side and jaw_side.lower() not in (self._spindle_side_filter.lower(), "both"):
                    continue
            description = (jaw.get("description") or "").strip()
            label = f"{jaw_id}  \u2014  {description}" if description else jaw_id
            if q and q not in label.lower():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, jaw_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if jaw_id == current else Qt.Unchecked)
            self.jaw_list.addItem(item)
        self._updating = False

    def _on_dynamic_input_changed(self, text: str):
        if self._is_stop_screws_mode:
            self._stop_screws_value = text.strip()
            return
        self._filter_text = text
        self._rebuild(self._filter_text)

    def get_value(self) -> str:
        for i in range(self.jaw_list.count()):
            item = self.jaw_list.item(i)
            if item.checkState() == Qt.Checked:
                return item.data(Qt.UserRole)
        return ""

    def set_value(self, jaw_id: str):
        self._updating = True
        jaw_id = (jaw_id or "").strip()
        for i in range(self.jaw_list.count()):
            item = self.jaw_list.item(i)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) == jaw_id else Qt.Unchecked)
        self._updating = False
        self._update_stop_screws_visibility()
        self.selectionChanged.emit(self.get_value())

    def set_stop_screws(self, value: str):
        self._stop_screws_value = (value or "").strip()
        if self._is_stop_screws_mode:
            self.search.blockSignals(True)
            self.search.setText(self._stop_screws_value)
            self.search.blockSignals(False)

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

        class _DeselectableList(QListWidget):
            def mousePressEvent(self_inner, event):
                point = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                if self_inner.itemAt(point) is None:
                    self_inner.clearSelection()
                    self_inner.setCurrentRow(-1)
                super(_DeselectableList, self_inner).mousePressEvent(event)

        self.tool_list = _DeselectableList()
        self.tool_list.setObjectName("toolIdsOrderList")
        self.tool_list.setSortingEnabled(False)
        list_panel_layout.addWidget(self.tool_list, 1)
        layout.addWidget(list_panel, 1)

        btn_row = QHBoxLayout()
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
        layout.addLayout(btn_row)

        self.move_up_btn.clicked.connect(self._move_up)
        self.move_down_btn.clicked.connect(self._move_down)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.select_btn.clicked.connect(self._request_selector)
        self.comment_btn.clicked.connect(self._add_or_edit_comment)
        self.delete_comment_btn.clicked.connect(self._delete_comment)
        self.spindle_selector.currentIndexChanged.connect(self._render_current_spindle)
        self.tool_list.currentRowChanged.connect(self._update_action_states)
        self.tool_list.itemSelectionChanged.connect(self._sync_row_selection_states)

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
            icon = _tool_icon_for_ref(ref)
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

        effective_pot = (assignment.get("pot") or "").strip() or self._default_pot_for_assignment(self, assignment)
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
        self._assignments_by_spindle = grouped
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
        self.spindles_tab = QWidget()
        self.zeros_tab = QWidget()
        self.tools_tab = QWidget()
        self.notes_tab = QWidget()

        self.tabs.addTab(self.general_tab, self._t("work_editor.tab.general", "General"))
        self.tabs.addTab(self.spindles_tab, self._t("work_editor.tab.spindles", "Spindles"))
        self.tabs.addTab(self.zeros_tab, self._t("work_editor.tab.zero_points", "Zero Points"))
        self.tabs.addTab(self.tools_tab, self._t("work_editor.tab.tool_ids", "Tool IDs"))
        self.tabs.addTab(self.notes_tab, self._t("work_editor.tab.notes", "Notes"))

        self._build_general_tab()
        self._build_spindles_tab()
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
        if hasattr(self, "tools_spindle_switch"):
            return self._current_tools_spindle_value()
        return self.machine_profile.default_tools_spindle

    def _current_tools_spindle_value(self) -> str:
        if not hasattr(self, "tools_spindle_switch"):
            return self.machine_profile.default_tools_spindle
        return self._normalize_selector_spindle(
            self.tools_spindle_switch.property("spindle") or self.machine_profile.default_tools_spindle
        )

    def _update_tools_spindle_switch_text(self):
        if not hasattr(self, "tools_spindle_switch"):
            return
        spindle = self._current_tools_spindle_value()
        label = self._spindle_label(spindle, "Main spindle")
        self.tools_spindle_switch.setText(label)
        self.tools_spindle_switch.setChecked(spindle == "sub")

    def _set_tools_spindle_value(self, spindle: str):
        normalized = self._normalize_selector_spindle(spindle)
        if not hasattr(self, "tools_spindle_switch"):
            return
        self.tools_spindle_switch.setProperty("spindle", normalized)
        self._update_tools_spindle_switch_text()

    def _toggle_tools_spindle_view(self):
        if not hasattr(self, "tools_spindle_switch"):
            return
        target = "sub" if self.tools_spindle_switch.isChecked() else "main"
        self._set_tools_spindle_value(target)
        self._sync_tool_spindle_view()

    def _default_selector_head(self) -> str:
        for head_key, ordered_list in self._ordered_tool_lists.items():
            if hasattr(ordered_list, "tool_list") and ordered_list.tool_list.hasFocus():
                return head_key
        return next(iter(self._head_profiles.keys()), "HEAD1")

    def _default_jaw_selector_spindle(self) -> str:
        for spindle_key, selector in self._jaw_selectors.items():
            if hasattr(selector, "jaw_list") and selector.jaw_list.hasFocus():
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
        self._tool_cache_by_head, self._tool_cache_all = merge_tool_refs(
            self._tool_cache_by_head,
            self._tool_cache_all,
            head_key=target_head,
            selected_items=selected_items,
        )
        for head, ordered_list in self._ordered_tool_lists.items():
            ordered_list._all_tools = self._tool_cache_by_head.get(head, self._tool_cache_all) or []

    def _merge_jaw_refs(self, selected_items: list[dict]):
        jaw_refs, changed = merge_jaw_refs(self._jaw_cache, selected_items)
        if changed:
            self._jaw_cache = jaw_refs
            for selector in self._jaw_selectors.values():
                selector.populate(jaw_refs)

    def _apply_tool_selector_result(self, request: dict, selected_items: list[dict]) -> bool:
        head_key = self._normalize_selector_head(request.get("head"))
        spindle = self._normalize_selector_spindle(request.get("spindle"))
        ordered_list = self._selector_target_ordered_list(head_key)
        self._merge_tool_refs(head_key, selected_items)

        bucket = ordered_list._assignments_by_spindle.setdefault(spindle, [])
        seen_keys = {ordered_list._assignment_key(item) for item in bucket if ordered_list._assignment_key(item)}
        added_any = False

        for item in selected_items:
            if not isinstance(item, dict):
                continue
            tool_id = str(item.get("tool_id") or item.get("id") or "").strip()
            if not tool_id:
                continue
            entry = {
                "tool_id": tool_id,
                "spindle": spindle,
                "comment": "",
                "pot": "",
                "override_id": "",
                "override_description": "",
            }
            tool_uid = self._parse_optional_int(item.get("tool_uid", item.get("uid")))
            if tool_uid is not None:
                entry["tool_uid"] = tool_uid
            key = ordered_list._assignment_key(entry)
            if not key or key in seen_keys:
                continue
            bucket.append(entry)
            seen_keys.add(key)
            added_any = True

        # Switch the spindle combo to match the target spindle so the list shows the new tools
        ordered_list.set_current_spindle(spindle)
        ordered_list._render_current_spindle()
        self._sync_tool_spindle_view()
        return added_any or bool(selected_items)

    def _apply_jaw_selector_result(self, request: dict, selected_items: list[dict]) -> bool:
        spindle = self._normalize_selector_spindle(request.get("spindle"))
        self._merge_jaw_refs(selected_items)

        selected_jaw = None
        for item in selected_items:
            if not isinstance(item, dict):
                continue
            jaw_id = str(item.get("jaw_id") or item.get("id") or "").strip()
            if jaw_id:
                selected_jaw = jaw_id
                break
        if not selected_jaw:
            self._show_selector_warning(
                self._t("work_editor.selector.malformed_callback.title", "Selection callback failed"),
                self._t(
                    "work_editor.selector.malformed_callback.body",
                    "Tool Library returned an empty jaw selection.",
                ),
            )
            return False

        target_selector = self._jaw_selectors.get(spindle, self._jaw_selectors.get("main"))
        target_selector.set_value(selected_jaw)
        return True

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
            spacer.setMinimumWidth(82 if show_xy else 0)

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
            grid.setColumnMinimumWidth(0, 96 if show_xy else 78)

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

    def _build_head_zero_group(self, title: str, head_key: str) -> QGroupBox:
        group = create_titled_section(title)
        group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        grid = QGridLayout(group)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        self._zero_point_grids.append(grid)
        self._zero_grids_with_groups.append((grid, group))

        spacer = QLabel("")
        spacer.setMinimumWidth(82)
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

        head_prefix = head_key.lower()
        for row, spindle_key in enumerate(self._spindle_profiles.keys(), start=1):
            spindle_profile = self._spindle_profiles.get(spindle_key)
            spindle_label = QLabel(
                spindle_profile.short_label if spindle_profile is not None else spindle_key.upper()
            )
            spindle_label.setWordWrap(False)
            grid.addWidget(spindle_label, row, 0)

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
            selector.search.setPlaceholderText(
                self._t(profile.jaw_filter_placeholder_key, profile.jaw_filter_placeholder_default)
            )
            selector._spindle_side_filter = profile.jaw_filter

    def _build_general_tab(self):
        layout = QVBoxLayout(self.general_tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.work_id_input = QLineEdit()
        self.drawing_id_input = QLineEdit()
        self.description_input = QLineEdit()
        self.raw_part_od_input = QLineEdit()
        self.raw_part_id_input = QLineEdit()
        self.raw_part_length_input = QLineEdit()

        drawing_row = QWidget()
        drawing_layout = QHBoxLayout(drawing_row)
        drawing_layout.setContentsMargins(0, 0, 0, 0)
        self.drawing_path_input = QLineEdit()
        browse_btn = QPushButton(self._t("work_editor.action.browse", "Browse"))
        browse_btn.clicked.connect(self._browse_drawing)
        drawing_layout.addWidget(self.drawing_path_input, 1)
        drawing_layout.addWidget(browse_btn)

        general_group = create_titled_section(self._t("work_editor.general.section.general", "General"))
        general_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        general_form = QFormLayout(general_group)
        general_form.setSpacing(8)
        general_form.addRow(self._t("setup_page.field.work_id", "Work ID"), self.work_id_input)
        general_form.addRow(self._t("setup_page.field.drawing_id", "Drawing ID"), self.drawing_id_input)
        general_form.addRow(self._t("setup_page.field.description", "Description"), self.description_input)
        self._drawing_row = drawing_row
        self._drawing_row_label = self._t("work_editor.field.drawing_path", "Drawing path")
        if self._drawings_enabled:
            general_form.addRow(self._drawing_row_label, drawing_row)

        raw_part_group = create_titled_section(self._t("work_editor.general.section.raw_part", "Raw Part"))
        raw_part_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        raw_form = QFormLayout(raw_part_group)
        raw_form.setSpacing(8)
        raw_form.addRow(
            self._t("work_editor.general.raw_outer_diameter", "Outer diameter"),
            self.raw_part_od_input,
        )
        raw_form.addRow(
            self._t("work_editor.general.raw_inner_diameter", "Inner diameter"),
            self.raw_part_id_input,
        )
        raw_form.addRow(
            self._t("work_editor.general.raw_length", "Length"),
            self.raw_part_length_input,
        )

        layout.addWidget(general_group)
        layout.addWidget(raw_part_group)

        selector_row = QHBoxLayout()
        selector_row.setContentsMargins(0, 4, 0, 0)
        selector_row.setSpacing(8)
        self.tools_jaws_selector_btn = QPushButton(
            self._t("work_editor.selector.tools_jaws_button", "Tools && Jaws Selector")
        )
        self.tools_jaws_selector_btn.setProperty("panelActionButton", True)
        self.tools_jaws_selector_btn.clicked.connect(self._open_combined_tools_jaws_selector)
        selector_row.addWidget(self.tools_jaws_selector_btn, 0)
        selector_row.addStretch(1)
        layout.addLayout(selector_row)

        layout.addStretch(1)

    def _build_spindles_tab(self):
        layout = QVBoxLayout(self.spindles_tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        selector_row = QHBoxLayout()
        selector_row.setContentsMargins(0, 0, 0, 0)
        selector_row.setSpacing(8)
        self.open_jaw_selector_btn = QPushButton(
            self._t("work_editor.selector.jaws_button", "Select Jaws")
        )
        self.open_jaw_selector_btn.setProperty("panelActionButton", True)
        self.open_jaw_selector_btn.clicked.connect(self._open_jaw_selector)
        selector_row.addWidget(self.open_jaw_selector_btn, 0)
        selector_row.addStretch(1)
        layout.addLayout(selector_row)

        self.main_jaw_selector = _JawSelectorPanel(
            self._t("work_editor.spindles.sp1_jaw", "Pääkara"),
            translate=self._t,
            filter_placeholder_key="work_editor.jaw.filter_sp1_placeholder",
            filter_placeholder_default="Suodata Pääkara-leukoja...",
            spindle_side_filter="Main spindle",
        )
        self.sub_jaw_selector = _JawSelectorPanel(
            self._t("work_editor.spindles.sp2_jaw", "Vastakara"),
            translate=self._t,
            filter_placeholder_key="work_editor.jaw.filter_sp2_placeholder",
            filter_placeholder_default="Suodata Vastakara-leukoja...",
            spindle_side_filter="Sub spindle",
        )
        self.main_jaw_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.sub_jaw_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._jaw_selectors["main"] = self.main_jaw_selector
        self._jaw_selectors["sub"] = self.sub_jaw_selector
        self.sub_jaw_selector.setVisible("sub" in self._spindle_profiles)
        self._apply_machine_profile_to_jaw_selectors()

        host = ResponsiveColumnsHost(switch_width=860, separator_property="jawColumnSeparator")
        host.add_widget(self.main_jaw_selector, 1)
        if "sub" in self._spindle_profiles:
            host.add_widget(self.sub_jaw_selector, 1)
        layout.addWidget(host, 1)

    def _build_zeros_tab(self):
        self.zeros_tab.setProperty("zeroPointsSurface", True)
        layout = QVBoxLayout(self.zeros_tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content.setProperty("zeroPointsSurface", True)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        programs_group = create_titled_section(self._t("work_editor.zeros.nc_programs", "NC Programs"))
        programs_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        programs_form = QFormLayout(programs_group)
        programs_form.setSpacing(8)
        self.main_program_input = QLineEdit()
        programs_form.addRow(self._t("setup_page.field.main_program", "Main program"), self.main_program_input)
        for head in self.machine_profile.heads:
            sub_program_input = QLineEdit()
            self._sub_program_inputs[head.key] = sub_program_input
            setattr(self, f"{head.key.lower()}_sub_program_input", sub_program_input)
            programs_form.addRow(
                self._t(
                    f"setup_page.field.sub_programs_{head.key.lower()}",
                    f"Sub program {head.label_default}",
                ),
                sub_program_input,
            )
        content_layout.addWidget(programs_group)

        xy_toggle_row = QHBoxLayout()
        xy_toggle_row.setContentsMargins(2, 0, 2, 0)
        self.zero_show_xy_checkbox = QCheckBox(
            self._t("work_editor.zeros.show_xy", "Show X/Y columns")
        )
        apply_shared_checkbox_style(self.zero_show_xy_checkbox, indicator_size=16)
        self.zero_show_xy_checkbox.setChecked(self.machine_profile.default_zero_xy_visible)
        self.zero_show_xy_checkbox.toggled.connect(self._set_zero_xy_visibility)
        self.zero_show_xy_checkbox.setVisible(self.machine_profile.supports_zero_xy_toggle)
        xy_toggle_row.addWidget(self.zero_show_xy_checkbox)
        xy_toggle_row.addStretch(1)
        content_layout.addLayout(xy_toggle_row)

        self.zero_points_host = ResponsiveColumnsHost(switch_width=1320)
        for head in self.machine_profile.heads:
            self.zero_points_host.add_widget(
                self._build_head_zero_group(
                    self._t(f"work_editor.zeros.{head.key.lower()}", f"{head.label_default} Zero Points"),
                    head.key,
                ),
                1,
            )
        content_layout.addWidget(self.zero_points_host)
        self._set_zero_xy_visibility(self.zero_show_xy_checkbox.isChecked())

        if self.machine_profile.supports_sub_pickup:
            sub_group = create_titled_section(self._t("setup_page.field.sp2", "SP2"))
            sub_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            sub_form = QFormLayout(sub_group)
            sub_form.setSpacing(8)
            self.sub_pickup_z_input = QLineEdit()
            sub_form.addRow(self._t("setup_page.field.sub_pickup_z", "Pickup Z"), self.sub_pickup_z_input)
            content_layout.addWidget(sub_group)
        content_layout.addStretch(1)

    def _build_tools_tab(self):
        layout = QVBoxLayout(self.tools_tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)
        toolbar.addWidget(_section_label(self._t("work_editor.tools.spindle_view", "Spindle View")))

        self.tools_spindle_switch = QPushButton()
        self.tools_spindle_switch.setProperty("panelActionButton", True)
        self.tools_spindle_switch.setCheckable(True)
        self.tools_spindle_switch.setMinimumWidth(112)
        self.tools_spindle_switch.setMaximumWidth(146)
        self.tools_spindle_switch.setFixedHeight(30)
        self.tools_spindle_switch.clicked.connect(self._toggle_tools_spindle_view)
        self.tools_spindle_switch.setProperty("spindle", self.machine_profile.default_tools_spindle)
        self._update_tools_spindle_switch_text()
        self.tools_spindle_switch.setVisible(len(self.machine_profile.spindles) > 1)
        toolbar.addWidget(self.tools_spindle_switch)

        self.open_tool_selector_btn = QPushButton(
            self._t("work_editor.selector.tools_button", "Select Tools")
        )
        self.open_tool_selector_btn.setProperty("panelActionButton", True)
        self.open_tool_selector_btn.clicked.connect(self._open_tool_selector)
        toolbar.addWidget(self.open_tool_selector_btn)

        toolbar.addStretch(1)

        self.print_pots_checkbox = QCheckBox(self._t("work_editor.tools.print_pot_numbers", "Print Pot Numbers"))
        apply_shared_checkbox_style(self.print_pots_checkbox, indicator_size=16, min_height=30)
        self.print_pots_checkbox.setFixedHeight(30)
        self.print_pots_checkbox.setVisible(self.machine_profile.supports_print_pots)

        self.edit_pots_btn = QPushButton(self._t("work_editor.tools.edit_pots", "Edit Pots"))
        self.edit_pots_btn.setProperty("secondaryButton", True)
        self.edit_pots_btn.setFixedHeight(30)
        button_metrics = QFontMetrics(self.edit_pots_btn.font())
        button_text = self.edit_pots_btn.text().upper()
        button_width = max(180, button_metrics.horizontalAdvance(button_text) + 42)
        self.edit_pots_btn.setFixedWidth(button_width)
        edit_pots_size_policy = self.edit_pots_btn.sizePolicy()
        edit_pots_size_policy.setRetainSizeWhenHidden(True)
        self.edit_pots_btn.setSizePolicy(edit_pots_size_policy)
        self.edit_pots_btn.setVisible(False)
        self.edit_pots_btn.clicked.connect(self._open_pot_editor)
        toolbar.addWidget(self.edit_pots_btn)
        toolbar.addWidget(self.print_pots_checkbox)

        self.print_pots_checkbox.toggled.connect(
            lambda checked: self.edit_pots_btn.setVisible(self.machine_profile.supports_print_pots and checked)
        )
        self.print_pots_checkbox.toggled.connect(self._on_print_pots_toggled)

        layout.addLayout(toolbar)

        host = ResponsiveColumnsHost(switch_width=820)
        for head in self.machine_profile.heads:
            ordered = _OrderedToolList(
                self._t(f"work_editor.tools.{head.key.lower()}", f"{head.label_default} Tools"),
                head.key,
                translate=self._t,
            )
            ordered.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            ordered.spindle_selector.setVisible(False)
            ordered.selectorRequested.connect(self._open_tool_selector_for_bucket)
            self._ordered_tool_lists[head.key] = ordered
            if head.key == "HEAD1":
                self.head1_ordered = ordered
            elif head.key == "HEAD2":
                self.head2_ordered = ordered
            host.add_widget(ordered, 1)

        host_surface = QFrame()
        host_surface.setProperty("toolIdsHostSurface", True)
        host_surface_layout = QVBoxLayout(host_surface)
        host_surface_layout.setContentsMargins(8, 8, 8, 8)
        host_surface_layout.setSpacing(0)
        host_surface_layout.addWidget(host, 1)
        layout.addWidget(host_surface, 1)

    def _sync_tool_spindle_view(self):
        spindle = self._current_tools_spindle_value()
        for ordered_list in self._ordered_tool_lists.values():
            ordered_list.set_current_spindle(spindle)

    def _on_print_pots_toggled(self, checked: bool):
        if checked:
            self._populate_default_pots()
        for ordered_list in self._ordered_tool_lists.values():
            ordered_list._show_pot = checked
            ordered_list._render_current_spindle()

    @staticmethod
    def _default_pot_for_assignment(ordered_list, assignment: dict) -> str:
        assignment_key = ordered_list._assignment_key(assignment)
        tool_id = (assignment.get("tool_id") or "").strip()
        for tool in ordered_list._all_tools or []:
            if not isinstance(tool, dict):
                continue
            tool_key = ordered_list._assignment_key(
                {
                    "tool_id": (tool.get("id") or "").strip(),
                    "tool_uid": tool.get("uid"),
                }
            )
            if tool_key == assignment_key:
                return str(tool.get("default_pot") or "").strip()
        if not tool_id:
            return ""
        for tool in ordered_list._all_tools or []:
            if not isinstance(tool, dict):
                continue
            if str(tool.get("id") or "").strip() == tool_id:
                return str(tool.get("default_pot") or "").strip()
        return ""

    def _populate_default_pots(self):
        changed = False
        for ordered_list in self._ordered_tool_lists.values():
            for spindle in self._spindle_profiles.keys():
                for assignment in ordered_list._assignments_by_spindle.get(spindle, []):
                    if (assignment.get("pot") or "").strip():
                        continue
                    default_pot = self._default_pot_for_assignment(ordered_list, assignment)
                    if default_pot:
                        assignment["pot"] = default_pot
                        changed = True
        if changed:
            for ordered_list in self._ordered_tool_lists.values():
                ordered_list._render_current_spindle()

    def _open_pot_editor(self):
        self._populate_default_pots()
        all_items = []
        for head_name, ordered_list in self._ordered_tool_lists.items():
            for spindle in self._spindle_profiles.keys():
                for item in ordered_list._assignments_by_spindle.get(spindle, []):
                    tool_id = (item.get("tool_id") or "").strip()
                    if not tool_id:
                        continue
                    label = ordered_list._tool_label(item)
                    all_items.append((item, label, head_name, spindle))

        dlg = QDialog(self)
        dlg.setWindowTitle(self._t("work_editor.tools.pot_editor_title", "Pot Editor"))
        dlg.setMinimumWidth(420)
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(16, 16, 16, 16)
        dlg_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(8)

        pot_inputs = []
        for item, label, head_name, spindle in all_items:
            inp = QLineEdit()
            inp.setPlaceholderText(self._t("work_editor.tools.pot_placeholder", "Pot #"))
            inp.setMaximumWidth(100)
            inp.setText(item.get("pot") or "")
            form.addRow(QLabel(f"[{head_name}/{spindle.upper()}]  {label}"), inp)
            pot_inputs.append((item, inp))

        scroll.setWidget(container)
        dlg_layout.addWidget(scroll, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        dlg_layout.addWidget(btn_box)

        if dlg.exec() == QDialog.Accepted:
            for item, inp in pot_inputs:
                item["pot"] = inp.text().strip()
            for ordered_list in self._ordered_tool_lists.values():
                ordered_list._render_current_spindle()

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
        self._load_external_refs()
        resolved_head = initial_head or self._default_selector_head()
        resolved_spindle = initial_spindle or self._default_selector_spindle()
        if initial_assignments is None:
            initial_assignments = self._selector_initial_tool_assignments(resolved_head, resolved_spindle)
        return self._open_external_selector_session(
            kind="tools",
            head=resolved_head,
            spindle=resolved_spindle,
            initial_assignments=initial_assignments,
        )

    def _open_jaw_selector(self, initial_spindle: str | None = None) -> bool:
        self._load_external_refs()
        return self._open_external_selector_session(
            kind="jaws",
            spindle=initial_spindle or self._default_jaw_selector_spindle(),
        )

    def _open_combined_tools_jaws_selector(self):
        spindle = self._default_selector_spindle()
        default_head = self._default_selector_head()
        self._open_external_selector_session(
            kind="tools",
            head=default_head,
            spindle=spindle,
            follow_up={"kind": "jaws", "spindle": spindle},
            initial_assignments=self._selector_initial_tool_assignments(default_head, spindle),
        )

    def _build_notes_tab(self):
        layout = QVBoxLayout(self.notes_tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(8)
        self.notes_input = QTextEdit()
        self.robot_info_input = QTextEdit()
        self.notes_input.setMinimumHeight(150)
        self.robot_info_input.setMaximumHeight(96)

        notes_group = create_titled_section(self._t("setup_page.field.notes", "Notes"))
        notes_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        notes_group_layout = QVBoxLayout(notes_group)
        notes_group_layout.setContentsMargins(10, 8, 10, 10)
        notes_group_layout.addWidget(self.notes_input, 1)
        layout.addWidget(notes_group, 1)

        robot_group = create_titled_section(self._t("setup_page.field.robot_info", "Robot info"))
        robot_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        robot_group_layout = QVBoxLayout(robot_group)
        robot_group_layout.setContentsMargins(10, 8, 10, 10)
        robot_group_layout.addWidget(self.robot_info_input, 0)
        layout.addWidget(robot_group, 0)

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
        # Keep selector caches head-aware so future machine profiles can expose
        # different stations without duplicating lookup/merge rules in the dialog.
        self._tool_cache_by_head, self._tool_cache_all = load_external_tool_refs(
            self.draw_service,
            tuple(self._head_profiles.keys()),
        )
        self._jaw_cache = self.draw_service.list_jaw_refs(force_reload=True)

        for selector in self._jaw_selectors.values():
            selector.populate(self._jaw_cache)
        for head_key, ordered_list in self._ordered_tool_lists.items():
            ordered_list._all_tools = self._tool_cache_by_head.get(head_key, self._tool_cache_all)

    def _load_work(self):
        if not self.work:
            return
        self._payload_adapter.populate_dialog(self, self.work)

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

        tool_ids = {item["id"] for item in (self._tool_cache_all or []) if item.get("id")}
        jaw_ids = {item["id"] for item in (self._jaw_cache or []) if item.get("id")}

        missing = []
        for spindle_key, selector in self._jaw_selectors.items():
            jaw_key = self._spindle_label(spindle_key, spindle_key)
            jaw_value = selector.get_value()
            if jaw_value and jaw_ids and jaw_value not in jaw_ids:
                missing.append(f"{jaw_key}: {jaw_value}")

        for head_key, ordered_list in self._ordered_tool_lists.items():
            head_name = self._head_label(head_key, head_key)
            values = ordered_list.get_tool_ids()
            for tool_id in values:
                if tool_ids and tool_id not in tool_ids:
                    missing.append(f"{head_name}: {tool_id}")

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
