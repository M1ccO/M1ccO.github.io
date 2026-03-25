from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon
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
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from config import ICONS_DIR
from ui.widgets.common import apply_shared_dropdown_style, clear_focused_dropdown_on_outside_click


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


def _apply_tool_library_combo_style(combo: QComboBox):
    combo.setProperty("modernDropdown", False)
    combo.setProperty("toolLibraryCombo", True)
    arrow_icon_path = (Path(ICONS_DIR) / "tools" / "menu_open.svg").as_posix()
    if Path(arrow_icon_path).exists():
        # Fallback icon rule to guarantee visible arrows even if parent-scoped
        # stylesheet selectors do not match at runtime.
        combo.setStyleSheet(
            "QComboBox::drop-down { width: 28px; border: none; background: transparent; }"
            f"QComboBox::down-arrow {{ image: url('{arrow_icon_path}'); width: 20px; height: 20px; }}"
        )
    apply_shared_dropdown_style(combo)


class _ResponsiveColumnsHost(QWidget):
    """Lay out child panels in two columns when wide, stack vertically when narrow."""

    def __init__(
        self,
        switch_width: int = 980,
        parent=None,
        separator_property: str | None = None,
    ):
        super().__init__(parent)
        self._switch_width = switch_width
        self._separator_property = separator_property
        self._added_widgets = 0
        self._separators: list[QFrame] = []
        self._layout = QBoxLayout(QBoxLayout.LeftToRight, self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(16)

    def add_widget(self, widget: QWidget, stretch: int = 1):
        if self._separator_property and self._added_widgets > 0:
            separator = QFrame()
            separator.setProperty(self._separator_property, True)
            separator.setFrameShadow(QFrame.Plain)
            separator.setLineWidth(1)
            self._separators.append(separator)
            self._layout.addWidget(separator, 0)
        self._layout.addWidget(widget, stretch)
        self._added_widgets += 1
        self._update_separator_shapes()

    def _update_separator_shapes(self):
        if not self._separators:
            return
        is_vertical = self._layout.direction() == QBoxLayout.LeftToRight
        for separator in self._separators:
            if is_vertical:
                separator.setFrameShape(QFrame.VLine)
                separator.setFixedWidth(1)
                separator.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
            else:
                separator.setFrameShape(QFrame.HLine)
                separator.setFixedHeight(1)
                separator.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        direction = (
            QBoxLayout.TopToBottom
            if event.size().width() < self._switch_width
            else QBoxLayout.LeftToRight
        )
        if self._layout.direction() != direction:
            self._layout.setDirection(direction)
        self._update_separator_shapes()


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
    ):
        super().__init__(parent)
        self._translate = translate or _noop_translate
        self._filter_placeholder_key = filter_placeholder_key
        self._filter_placeholder_default = filter_placeholder_default
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Dynamic input section: border/title always present to avoid layout jump.
        self.dynamic_input_group = QGroupBox(
            " "
        )
        self.dynamic_input_group.setProperty("jawInputGroup", True)
        search_layout = QVBoxLayout(self.dynamic_input_group)
        search_layout.setContentsMargins(10, 8, 10, 8)
        search_layout.setSpacing(0)

        self.search = QLineEdit()
        self.search.setPlaceholderText(self._t(self._filter_placeholder_key, self._filter_placeholder_default))
        self.search.textChanged.connect(self._on_dynamic_input_changed)
        search_layout.addWidget(self.search)
        layout.addWidget(self.dynamic_input_group)

        selection_group = QGroupBox(title)
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
    ):
        super().__init__(parent)
        self._translate = translate or _noop_translate
        self.setWindowTitle(self._t("work_editor.tool_picker.title", "Select Tools"))
        self.resize(760, 560)
        self.setProperty("toolPickerDialog", True)
        self._all_tools = all_tools
        self._selected_ids = {str(item).strip() for item in (current_ids or []) if str(item).strip()}
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
            self.type_filter.addItem(tool_type, tool_type)
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
        _apply_tool_library_combo_style(combo)

    def _tool_types(self) -> list:
        values = {
            (tool.get("tool_type") or "").strip()
            for tool in (self._all_tools or [])
            if (tool.get("tool_type") or "").strip()
        }
        return sorted(values, key=lambda value: value.lower())

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
        tool_type = (tool.get("tool_type") or "").strip()
        selected_type = self.type_filter.currentData() if hasattr(self, "type_filter") else ""
        if selected_type and tool_type.lower() != str(selected_type).lower():
            return False

        query = self.search.text().strip().lower() if self._search_visible else ""
        if not query:
            return True
        tool_id = (tool.get("id") or "").strip()
        description = (tool.get("description") or "").strip()
        text = f"{tool_id} {description} {tool_type}".lower()
        return query in text

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
            item.setData(Qt.UserRole, tool_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if tool_id in self._selected_ids else Qt.Unchecked)
            self.tool_list.addItem(item)
        self._updating_list = False

    def _on_item_changed(self, item: QListWidgetItem):
        if self._updating_list:
            return
        tool_id = (item.data(Qt.UserRole) or "").strip()
        if not tool_id:
            return
        if item.checkState() == Qt.Checked:
            self._selected_ids.add(tool_id)
        else:
            self._selected_ids.discard(tool_id)

    def get_selected_ids(self) -> list:
        selected = self._selected_ids
        return [
            (tool.get("id") or "").strip()
            for tool in (self._all_tools or [])
            if (tool.get("id") or "").strip() in selected
        ]


class _OrderedToolList(QWidget):
    """Per-head tool assignment editor with separate SP1/SP2 lists."""

    _SPINDLE_OPTIONS = (
        ("SP1", "main"),
        ("SP2", "sub"),
    )

    class _ToolAssignmentRowWidget(QWidget):
        def __init__(self, text: str, comment: str, parent=None):
            super().__init__(parent)
            self.setAttribute(Qt.WA_StyledBackground, False)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(6, 3, 6, 3)
            layout.setSpacing(8)

            text_label = QLabel(text)
            text_label.setWordWrap(True)
            text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            text_label.setStyleSheet("background: transparent;")
            layout.addWidget(text_label, 1)

            comment_badge = QLabel("[C]")
            comment_badge.setVisible(bool(comment))
            comment_badge.setToolTip(comment)
            comment_badge.setProperty("detailFieldKey", True)
            comment_badge.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            comment_badge.setMinimumWidth(28)
            comment_badge.setStyleSheet("background: transparent;")
            layout.addWidget(comment_badge, 0, Qt.AlignRight | Qt.AlignVCenter)

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
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self._translate = translate or _noop_translate
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
        _apply_tool_library_combo_style(self.spindle_selector)
        for label, value in self._SPINDLE_OPTIONS:
            self.spindle_selector.addItem(label, value)
        header_row.addStretch(1)
        header_row.addWidget(self.spindle_selector)
        layout.addLayout(header_row)

        list_panel = QGroupBox(head_label)
        list_panel.setProperty("toolIdsPanel", True)
        list_panel_layout = QVBoxLayout(list_panel)
        list_panel_layout.setContentsMargins(8, 10, 8, 8)
        list_panel_layout.setSpacing(0)

        self.tool_list = QListWidget()
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

        self.select_btn = QPushButton(self._t("work_editor.tools.select_tools", "Select Tools\u2026"))
        self.select_btn.setProperty("panelActionButton", True)
        self.select_btn.setMinimumWidth(112)
        self.select_btn.setMaximumWidth(150)
        self.select_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        btn_row.addWidget(self.select_btn)
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
        self.select_btn.clicked.connect(self._open_picker)
        self.comment_btn.clicked.connect(self._add_or_edit_comment)
        self.delete_comment_btn.clicked.connect(self._delete_comment)
        self.spindle_selector.currentIndexChanged.connect(self._render_current_spindle)
        self.tool_list.currentRowChanged.connect(self._update_action_states)

        self._all_tools: list = []
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

    def _tool_label(self, tool_id: str) -> str:
        desc = self._labels_by_tool_id().get(tool_id, tool_id)
        return desc

    def _tool_assignment(self, row: int | None = None) -> dict | None:
        target_row = self.tool_list.currentRow() if row is None else row
        if target_row < 0 or target_row >= self.tool_list.count():
            return None
        item = self.tool_list.item(target_row)
        data = item.data(Qt.UserRole)
        return dict(data) if isinstance(data, dict) else None

    def _render_assignment_row(self, item: QListWidgetItem, row_index: int, assignment: dict):
        label = self._tool_label(assignment.get("tool_id", ""))
        display_text = f"{row_index + 1}. {label}"
        item.setText("")
        widget = self._ToolAssignmentRowWidget(display_text, assignment.get("comment", ""), self.tool_list)
        self.tool_list.setItemWidget(item, widget)

    def _render_current_spindle(self):
        current_row = self.tool_list.currentRow()
        self.tool_list.clear()
        for index, assignment in enumerate(self._current_assignments()):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, dict(assignment))
            item.setSizeHint(QSize(0, 36))
            self.tool_list.addItem(item)
            self._render_assignment_row(item, index, assignment)
        if self.tool_list.count() > 0:
            target_row = current_row if 0 <= current_row < self.tool_list.count() else 0
            self.tool_list.setCurrentRow(target_row)
        self._update_action_states()

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

    def _open_picker(self):
        current_ids = [item.get("tool_id", "") for item in self._current_assignments() if item.get("tool_id")]
        dlg = _ToolPickerDialog(self._all_tools, current_ids, self, translate=self._t)
        if dlg.exec() != QDialog.Accepted:
            return
        selected = dlg.get_selected_ids()
        # Keep existing order for retained items; append newly selected.
        current_assignments = self._current_assignments()
        kept = [item for item in current_assignments if item.get("tool_id") in set(selected)]
        kept_ids = {item.get("tool_id") for item in kept}
        added = [
            {
                "tool_id": tid,
                "spindle": self._current_spindle(),
                "comment": "",
            }
            for tid in selected
            if tid not in kept_ids
        ]
        self._assignments_by_spindle[self._current_spindle()] = kept + added
        self._render_current_spindle()

    def _labels_by_tool_id(self) -> dict:
        id_to_label: dict = {}
        for tool in self._all_tools:
            tid = (tool.get("id") or "").strip()
            if not tid:
                continue
            desc = (tool.get("description") or "").strip()
            id_to_label[tid] = f"{tid}  \u2014  {desc}" if desc else tid
        return id_to_label

    def set_tool_assignments(self, assignments: list):
        grouped = {"main": [], "sub": []}
        for item in assignments or []:
            if not isinstance(item, dict):
                tool_id = str(item or "").strip()
                spindle = "main"
                comment = ""
            else:
                tool_id = str(item.get("tool_id") or item.get("id") or "").strip()
                spindle = str(item.get("spindle") or "main").strip().lower()
                comment = str(item.get("comment") or "").strip()
            if not tool_id:
                continue
            if spindle not in grouped:
                spindle = "main"
            grouped[spindle].append({
                "tool_id": tool_id,
                "spindle": spindle,
                "comment": comment,
            })
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
                assignments.append({
                    "tool_id": tool_id,
                    "spindle": spindle,
                    "comment": (item.get("comment") or "").strip(),
                })
        return assignments


# ======================================================================


class WorkEditorDialog(QDialog):
    _tool_cache = None       # all tools (kept for backward compat)
    _tool_cache_h1 = None    # HEAD1-filtered tools
    _tool_cache_h2 = None    # HEAD2-filtered tools
    _jaw_cache = None

    def __init__(
        self,
        draw_service,
        work=None,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self.draw_service = draw_service
        self.work = dict(work or {})
        self.is_edit = bool(work)
        self._translate = translate or _noop_translate

        self.setWindowTitle(self._dialog_title())
        self.resize(960, 680)
        self.setMinimumSize(760, 560)
        self.setSizeGripEnabled(True)
        self.setProperty("workEditorDialog", True)

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

        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            clear_focused_dropdown_on_outside_click(obj, self)
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _dialog_title(self) -> str:
        if self.is_edit:
            return self._t("work_editor.window_title.edit", "Edit Work")
        return self._t("work_editor.window_title.new", "New Work")

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
        _apply_tool_library_combo_style(combo)

    def _make_axis_input(self, value_attr_name: str, axis: str) -> QLineEdit:
        value_input = QLineEdit()
        value_input.setPlaceholderText(axis.upper())
        value_input.setMinimumWidth(88)
        setattr(self, value_attr_name, value_input)
        return value_input

    def _build_head_zero_group(self, title: str, prefix: str) -> QGroupBox:
        group = QGroupBox(title)
        grid = QGridLayout(group)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        spacer = QLabel("")
        spacer.setMinimumWidth(82)
        grid.addWidget(spacer, 0, 0)

        coord_header = QLabel("WCS")
        coord_header.setProperty("detailFieldKey", True)
        coord_header.setAlignment(Qt.AlignCenter)
        grid.addWidget(coord_header, 0, 1)

        for col, axis in enumerate(ZERO_AXES, start=2):
            axis_header = QLabel(axis.upper())
            axis_header.setProperty("detailFieldKey", True)
            axis_header.setAlignment(Qt.AlignCenter)
            grid.addWidget(axis_header, 0, col)

        for row, spindle_key in enumerate(("main", "sub"), start=1):
            spindle_label = QLabel("SP1" if spindle_key == "main" else "SP2")
            spindle_label.setWordWrap(False)
            grid.addWidget(spindle_label, row, 0)

            combo_attr_name = f"{prefix}_{spindle_key}_coord_combo"
            coord_combo = QComboBox()
            coord_combo.addItems(WORK_COORDINATES)
            coord_combo.setProperty("modernDropdown", True)
            coord_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            coord_combo.setMinimumWidth(92)
            self._apply_coord_combo_popup_style(coord_combo)
            setattr(self, combo_attr_name, coord_combo)
            grid.addWidget(coord_combo, row, 1)

            for col, axis in enumerate(ZERO_AXES, start=2):
                value_attr_name = f"{prefix}_{spindle_key}_{axis}_input"
                value_input = self._make_axis_input(value_attr_name, axis)
                grid.addWidget(value_input, row, col)

        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        for col in range(2, 6):
            grid.setColumnStretch(col, 1)
        return group

    def _set_coord_combo(self, combo: QComboBox, value: str, default: str):
        target = (value or "").strip() or default
        index = combo.findText(target)
        combo.setCurrentIndex(index if index >= 0 else combo.findText(default))

    def _build_general_tab(self):
        form = QFormLayout(self.general_tab)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(10)

        self.work_id_input = QLineEdit()
        self.drawing_id_input = QLineEdit()
        self.description_input = QLineEdit()

        drawing_row = QWidget()
        drawing_layout = QHBoxLayout(drawing_row)
        drawing_layout.setContentsMargins(0, 0, 0, 0)
        self.drawing_path_input = QLineEdit()
        browse_btn = QPushButton(self._t("work_editor.action.browse", "Browse"))
        browse_btn.clicked.connect(self._browse_drawing)
        drawing_layout.addWidget(self.drawing_path_input, 1)
        drawing_layout.addWidget(browse_btn)

        form.addRow(self._t("setup_page.field.work_id", "Work ID"), self.work_id_input)
        form.addRow(self._t("setup_page.field.drawing_id", "Drawing ID"), self.drawing_id_input)
        form.addRow(self._t("setup_page.field.description", "Description"), self.description_input)
        form.addRow(self._t("work_editor.field.drawing_path", "Drawing path"), drawing_row)

    def _build_spindles_tab(self):
        layout = QVBoxLayout(self.spindles_tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.main_jaw_selector = _JawSelectorPanel(
            self._t("work_editor.spindles.sp1_jaw", "SP1 Jaw"),
            translate=self._t,
            filter_placeholder_key="work_editor.jaw.filter_sp1_placeholder",
            filter_placeholder_default="Filter SP1 jaws...",
        )
        self.sub_jaw_selector = _JawSelectorPanel(
            self._t("work_editor.spindles.sp2_jaw", "SP2 Jaw"),
            translate=self._t,
            filter_placeholder_key="work_editor.jaw.filter_sp2_placeholder",
            filter_placeholder_default="Filter SP2 jaws...",
        )
        self.main_jaw_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.sub_jaw_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        host = _ResponsiveColumnsHost(switch_width=860, separator_property="jawColumnSeparator")
        host.add_widget(self.main_jaw_selector, 1)
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

        programs_group = QGroupBox(self._t("work_editor.zeros.nc_programs", "NC Programs"))
        programs_form = QFormLayout(programs_group)
        programs_form.setSpacing(8)
        self.main_program_input = QLineEdit()
        self.head1_sub_program_input = QLineEdit()
        self.head2_sub_program_input = QLineEdit()
        programs_form.addRow(self._t("setup_page.field.main_program", "Main program"), self.main_program_input)
        programs_form.addRow(
            self._t("setup_page.field.sub_programs_head1", "Sub program Head 1"),
            self.head1_sub_program_input,
        )
        programs_form.addRow(
            self._t("setup_page.field.sub_programs_head2", "Sub program Head 2"),
            self.head2_sub_program_input,
        )
        content_layout.addWidget(programs_group)

        head1_group = self._build_head_zero_group(self._t("work_editor.zeros.head1", "Head 1 Zero Points"), "head1")
        head2_group = self._build_head_zero_group(self._t("work_editor.zeros.head2", "Head 2 Zero Points"), "head2")

        zeros_host = _ResponsiveColumnsHost(switch_width=1320)
        zeros_host.add_widget(head1_group, 1)
        zeros_host.add_widget(head2_group, 1)
        content_layout.addWidget(zeros_host)

        sub_group = QGroupBox(self._t("setup_page.field.sp2", "SP2"))
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

        self.tools_spindle_switch = QComboBox()
        self.tools_spindle_switch.setProperty("modernDropdown", True)
        self.tools_spindle_switch.setMinimumWidth(112)
        self.tools_spindle_switch.setMaximumWidth(146)
        self._apply_coord_combo_popup_style(self.tools_spindle_switch)
        self.tools_spindle_switch.addItem("SP1", "main")
        self.tools_spindle_switch.addItem("SP2", "sub")
        self.tools_spindle_switch.currentIndexChanged.connect(self._sync_tool_spindle_view)
        toolbar.addWidget(self.tools_spindle_switch)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.head1_ordered = _OrderedToolList(
            self._t("work_editor.tools.head1", "Head 1 Tools"),
            translate=self._t,
        )
        self.head2_ordered = _OrderedToolList(
            self._t("work_editor.tools.head2", "Head 2 Tools"),
            translate=self._t,
        )
        self.head1_ordered.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.head2_ordered.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.head1_ordered.spindle_selector.setVisible(False)
        self.head2_ordered.spindle_selector.setVisible(False)

        host = _ResponsiveColumnsHost(switch_width=820)
        host.add_widget(self.head1_ordered, 1)
        host.add_widget(self.head2_ordered, 1)

        host_surface = QFrame()
        host_surface.setProperty("toolIdsHostSurface", True)
        host_surface_layout = QVBoxLayout(host_surface)
        host_surface_layout.setContentsMargins(8, 8, 8, 8)
        host_surface_layout.setSpacing(0)
        host_surface_layout.addWidget(host, 1)
        layout.addWidget(host_surface, 1)

    def _sync_tool_spindle_view(self):
        spindle = (self.tools_spindle_switch.currentData() or "main").strip().lower()
        self.head1_ordered.set_current_spindle(spindle)
        self.head2_ordered.set_current_spindle(spindle)

    def _build_notes_tab(self):
        layout = QVBoxLayout(self.notes_tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(8)
        self.notes_input = QTextEdit()
        self.robot_info_input = QTextEdit()
        self.notes_input.setMinimumHeight(150)
        self.robot_info_input.setMaximumHeight(96)

        notes_group = QGroupBox(self._t("setup_page.field.notes", "Notes"))
        notes_group_layout = QVBoxLayout(notes_group)
        notes_group_layout.setContentsMargins(10, 8, 10, 10)
        notes_group_layout.addWidget(self.notes_input, 1)
        layout.addWidget(notes_group, 1)

        robot_group = QGroupBox(self._t("setup_page.field.robot_info", "Robot info"))
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
        if WorkEditorDialog._tool_cache_h1 is None:
            WorkEditorDialog._tool_cache_h1 = self.draw_service.list_tool_refs(head_filter='HEAD1')
        if WorkEditorDialog._tool_cache_h2 is None:
            WorkEditorDialog._tool_cache_h2 = self.draw_service.list_tool_refs(head_filter='HEAD2')
        # Fall back to combined list if head-specific filters returned nothing
        if not WorkEditorDialog._tool_cache_h1 and not WorkEditorDialog._tool_cache_h2:
            if WorkEditorDialog._tool_cache is None:
                WorkEditorDialog._tool_cache = self.draw_service.list_tool_refs()
            WorkEditorDialog._tool_cache_h1 = WorkEditorDialog._tool_cache
            WorkEditorDialog._tool_cache_h2 = WorkEditorDialog._tool_cache
        if WorkEditorDialog._jaw_cache is None:
            WorkEditorDialog._jaw_cache = self.draw_service.list_jaw_refs()

        self.main_jaw_selector.populate(WorkEditorDialog._jaw_cache)
        self.sub_jaw_selector.populate(WorkEditorDialog._jaw_cache)
        self.head1_ordered._all_tools = WorkEditorDialog._tool_cache_h1
        self.head2_ordered._all_tools = WorkEditorDialog._tool_cache_h2

    def _load_work(self):
        if not self.work:
            return

        self.work_id_input.setText(self.work.get("work_id", ""))
        self.work_id_input.setEnabled(False)
        self.drawing_id_input.setText(self.work.get("drawing_id", ""))
        self.description_input.setText(self.work.get("description", ""))
        self.drawing_path_input.setText(self.work.get("drawing_path", ""))

        self.main_jaw_selector.set_value(self.work.get("main_jaw_id", ""))
        self.sub_jaw_selector.set_value(self.work.get("sub_jaw_id", ""))
        self.main_jaw_selector.set_stop_screws(self.work.get("main_stop_screws", ""))
        self.sub_jaw_selector.set_stop_screws(self.work.get("sub_stop_screws", ""))

        self.main_program_input.setText(self.work.get("main_program", ""))
        self.head1_sub_program_input.setText(self.work.get("head1_sub_program", ""))
        self.head2_sub_program_input.setText(self.work.get("head2_sub_program", ""))
        self._set_coord_combo(
            self.head1_main_coord_combo,
            self.work.get("head1_main_coord", self.work.get("head1_zero", "")),
            "G54",
        )
        self._set_coord_combo(
            self.head1_sub_coord_combo,
            self.work.get("head1_sub_coord", self.work.get("head1_zero", "")),
            "G54",
        )
        self._set_coord_combo(
            self.head2_main_coord_combo,
            self.work.get("head2_main_coord", self.work.get("head2_zero", "")),
            "G55",
        )
        self._set_coord_combo(
            self.head2_sub_coord_combo,
            self.work.get("head2_sub_coord", self.work.get("head2_zero", "")),
            "G55",
        )
        for prefix in ("head1_main", "head1_sub", "head2_main", "head2_sub"):
            for axis in ZERO_AXES:
                value_input = getattr(self, f"{prefix}_{axis}_input")
                value_input.setText(self.work.get(f"{prefix}_{axis}", ""))
        self.sub_pickup_z_input.setText(self.work.get("sub_pickup_z", ""))

        self.head1_ordered.set_tool_assignments(self.work.get("head1_tool_assignments", []))
        self.head2_ordered.set_tool_assignments(self.work.get("head2_tool_assignments", []))

        self.robot_info_input.setPlainText(self.work.get("robot_info", ""))
        self.notes_input.setPlainText(self.work.get("notes", ""))

    def get_work_data(self) -> dict:
        payload = {
            "work_id": self.work_id_input.text().strip(),
            "drawing_id": self.drawing_id_input.text().strip(),
            "description": self.description_input.text().strip(),
            "drawing_path": self.drawing_path_input.text().strip(),
            "main_jaw_id": self.main_jaw_selector.get_value(),
            "sub_jaw_id": self.sub_jaw_selector.get_value(),
            "main_stop_screws": self.main_jaw_selector.get_stop_screws(),
            "sub_stop_screws": self.sub_jaw_selector.get_stop_screws(),
            "main_program": self.main_program_input.text().strip(),
            "head1_sub_program": self.head1_sub_program_input.text().strip(),
            "head2_sub_program": self.head2_sub_program_input.text().strip(),
            "head1_main_coord": self.head1_main_coord_combo.currentText().strip(),
            "head1_sub_coord": self.head1_sub_coord_combo.currentText().strip(),
            "head2_main_coord": self.head2_main_coord_combo.currentText().strip(),
            "head2_sub_coord": self.head2_sub_coord_combo.currentText().strip(),
            "head1_zero": self.head1_main_coord_combo.currentText().strip(),
            "head2_zero": self.head2_main_coord_combo.currentText().strip(),
            "sub_pickup_z": self.sub_pickup_z_input.text().strip(),
            "head1_tool_assignments": self.head1_ordered.get_tool_assignments(),
            "head2_tool_assignments": self.head2_ordered.get_tool_assignments(),
            "robot_info": self.robot_info_input.toPlainText().strip(),
            "notes": self.notes_input.toPlainText().strip(),
        }
        for prefix in ("head1_main", "head1_sub", "head2_main", "head2_sub"):
            for axis in ZERO_AXES:
                key = f"{prefix}_{axis}"
                payload[key] = getattr(self, f"{key}_input").text().strip()
        return payload

    def _on_save(self):
        work_id = self.work_id_input.text().strip()
        if not work_id:
            QMessageBox.warning(
                self,
                self._t("work_editor.message.missing_id_title", "Missing ID"),
                self._t("work_editor.message.work_id_required", "Work ID is required."),
            )
            self.tabs.setCurrentWidget(self.general_tab)
            self.work_id_input.setFocus()
            return

        tool_ids = {item["id"] for item in (WorkEditorDialog._tool_cache or []) if item.get("id")}
        jaw_ids = {item["id"] for item in (WorkEditorDialog._jaw_cache or []) if item.get("id")}

        missing = []
        for jaw_key, jaw_value in (
            (self._t("work_editor.ref.main_jaw", "Main jaw"), self.main_jaw_selector.get_value()),
            (self._t("work_editor.ref.sub_jaw", "Sub jaw"), self.sub_jaw_selector.get_value()),
        ):
            if jaw_value and jaw_ids and jaw_value not in jaw_ids:
                missing.append(f"{jaw_key}: {jaw_value}")

        for head_name, values in (
            (self._t("work_editor.ref.head1_tool", "Head 1 tool"), self.head1_ordered.get_tool_ids()),
            (self._t("work_editor.ref.head2_tool", "Head 2 tool"), self.head2_ordered.get_tool_ids()),
        ):
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
