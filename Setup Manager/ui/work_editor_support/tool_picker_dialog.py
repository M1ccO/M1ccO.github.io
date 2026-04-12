from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
)


def _noop_translate(_key: str, default: str | None = None, **_kwargs) -> str:
    return default or ""


class WorkEditorToolPickerDialog(QDialog):
    """Multi-select checkbox dialog that lets the user choose tools from the DB."""

    def __init__(
        self,
        all_tools: list,
        current_ids: list,
        *,
        icon_resolver: Callable[[str], object],
        combo_popup_styler: Callable[[QComboBox], None],
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
        spindle_orientation_filter: str | None = None,
    ):
        super().__init__(parent)
        self._translate = translate or _noop_translate
        self._spindle_orientation_filter = (spindle_orientation_filter or "").strip().lower()
        self._icon_resolver = icon_resolver
        self._combo_popup_styler = combo_popup_styler
        self.setWindowTitle(self._t("work_editor.tool_picker.title", "Select Tools"))
        self.resize(760, 560)
        self.setProperty("toolPickerDialog", True)
        self._all_tools = all_tools
        self._selected_keys = {str(item).strip() for item in (current_ids or []) if str(item).strip()}
        self._updating_list = False
        self._search_visible = False
        self._search_icon = self._icon_resolver("search_icon")
        self._close_icon = self._icon_resolver("close_icon")

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
        self._combo_popup_styler(combo)

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
            label = f"{tool_id}  -  {description}" if description else tool_id
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
