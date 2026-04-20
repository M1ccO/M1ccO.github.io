from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QComboBox,
    QHBoxLayout,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    from shared.ui.helpers.editor_helpers import create_titled_section
except ModuleNotFoundError:
    from editor_helpers import create_titled_section
try:
    from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
except ModuleNotFoundError:
    _workspace_root = Path(__file__).resolve().parents[3]
    if str(_workspace_root) not in sys.path:
        sys.path.insert(0, str(_workspace_root))
    from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
from ui.widgets.common import apply_tool_library_combo_style
from shared.ui.tool_assignment_editing import edit_tool_assignment_dialog
from shared.ui.tool_assignment_display import build_badges, compose_title, effective_fields
from .dragdrop_widgets import WorkEditorToolAssignmentListWidget


def _noop_translate(_key: str, default: str | None = None, **_kwargs) -> str:
    return default or ""


def _noop_icon_resolver(_name: str) -> QIcon:
    return QIcon()


def _noop_tool_icon_for_spindle(_tool_type: str, _spindle: str) -> QIcon:
    return QIcon()


def _noop_default_pot_for_assignment(_ordered_list, _assignment: dict) -> str:
    return ""


def _noop_combo_popup_styler(_combo: QComboBox) -> None:
    return


def _noop_direct_tool_ref_resolver(_assignment: dict) -> dict | None:
    return None


def _find_tool_ref_for_assignment(all_tools: list, assignment: dict, assignment_key_fn) -> dict | None:
    if not isinstance(assignment, dict):
        return None

    assignment_key = assignment_key_fn(assignment)
    tool_id = str(assignment.get("tool_id") or "").strip()
    fallback_ref = None

    for tool in all_tools or []:
        if not isinstance(tool, dict):
            continue
        ref_tool_id = str(tool.get("id") or "").strip()
        candidate_key = assignment_key_fn(
            {
                "tool_id": ref_tool_id,
                "tool_uid": tool.get("uid"),
            }
        )
        if assignment_key and candidate_key == assignment_key:
            return dict(tool)
        if tool_id and ref_tool_id == tool_id and fallback_ref is None:
            fallback_ref = dict(tool)

    return fallback_ref


class WorkEditorOrderedToolList(QWidget):
    """Per-head tool assignment editor with separate SP1/SP2 lists."""

    selectorRequested = Signal(str, str)

    _SPINDLE_OPTIONS = (
        ("SP1", "main"),
        ("SP2", "sub"),
    )

    _toolbar_icon_resolver: Callable[[str], QIcon] = staticmethod(_noop_icon_resolver)
    _tool_icon_for_spindle_resolver: Callable[[str, str], QIcon] = staticmethod(_noop_tool_icon_for_spindle)
    _default_pot_for_assignment_resolver: Callable[[object, dict], str] = staticmethod(
        _noop_default_pot_for_assignment
    )
    _combo_popup_styler: Callable[[QComboBox], None] = staticmethod(_noop_combo_popup_styler)
    _direct_tool_ref_resolver: Callable[[dict], dict | None] = staticmethod(_noop_direct_tool_ref_resolver)

    class _ToolAssignmentRowWidget(MiniAssignmentCard):
        def __init__(
            self,
            icon: QIcon,
            text: str,
            subtitle: str = "",
            comment: str = "",
            pot: str = "",
            edited: bool = False,
            flip_vertical: bool = False,
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
                flip_vertical=flip_vertical,
                parent=parent,
            )

    @classmethod
    def configure_dependencies(
        cls,
        *,
        toolbar_icon_resolver: Callable[[str], QIcon],
        tool_icon_for_spindle_resolver: Callable[[str, str], QIcon],
        default_pot_for_assignment_resolver: Callable[[object, dict], str],
        combo_popup_styler: Callable[[QComboBox], None] = apply_tool_library_combo_style,
        direct_tool_ref_resolver: Callable[[dict], dict | None] = _noop_direct_tool_ref_resolver,
    ) -> None:
        # Store as static callables so instance access does not bind `self`.
        cls._toolbar_icon_resolver = staticmethod(toolbar_icon_resolver)
        cls._tool_icon_for_spindle_resolver = staticmethod(tool_icon_for_spindle_resolver)
        cls._default_pot_for_assignment_resolver = staticmethod(default_pot_for_assignment_resolver)
        cls._combo_popup_styler = staticmethod(combo_popup_styler)
        cls._direct_tool_ref_resolver = staticmethod(direct_tool_ref_resolver)

    @classmethod
    def _configure_icon_action(cls, btn: QPushButton, icon_name: str, tooltip: str, *, danger: bool = False):
        btn.setText("")
        btn.setToolTip(tooltip)
        icon = cls._toolbar_icon_resolver(icon_name)
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

        self.spindle_selector = QComboBox(self)
        self.spindle_selector.setProperty("modernDropdown", True)
        self.spindle_selector.setMinimumWidth(116)
        self.spindle_selector.setMaximumWidth(150)
        self._combo_popup_styler(self.spindle_selector)
        for label, value in self._SPINDLE_OPTIONS:
            self.spindle_selector.addItem(label, value)

        self.select_btn = QPushButton(self._t("work_editor.tools.select_tools", "Select Tools..."), self)
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

        list_panel = create_titled_section(head_label, parent=self)
        list_panel.setProperty("toolIdsPanel", True)
        list_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        list_panel_layout = QVBoxLayout(list_panel)
        list_panel_layout.setContentsMargins(8, 10, 8, 8)
        list_panel_layout.setSpacing(0)

        self.tool_list = WorkEditorToolAssignmentListWidget(list_panel)
        self.tool_list._owner = self
        self.tool_list.setObjectName("toolIdsOrderList")
        self.tool_list.setSortingEnabled(False)
        # Keep a tiny right inset so card borders never clip at narrow widths.
        self.tool_list.setViewportMargins(0, 0, 2, 0)
        list_panel_layout.addWidget(self.tool_list, 1)
        self._list_panel = list_panel
        layout.addWidget(list_panel, 1)

        self.controls_bar = QWidget(self)
        btn_row = QHBoxLayout(self.controls_bar)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        self.move_up_btn = QPushButton(self._t("work_editor.tools.move_up", "▲"), self.controls_bar)
        self.move_down_btn = QPushButton(self._t("work_editor.tools.move_down", "▼"), self.controls_bar)
        self.remove_btn = QPushButton(self._t("work_editor.tools.remove", "Remove"), self.controls_bar)
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

        self._configure_icon_action(
            self.select_btn,
            "select",
            self._t("work_editor.tools.select_tools", "Select Tools"),
        )
        self._configure_icon_action(
            self.remove_btn,
            "delete",
            self._t("work_editor.tools.remove", "Remove Tool"),
            danger=True,
        )

        btn_row.addStretch(1)
        layout.addWidget(self.controls_bar)

        self.move_up_btn.clicked.connect(self._move_up)
        self.move_down_btn.clicked.connect(self._move_down)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.select_btn.clicked.connect(self._request_selector)
        self.spindle_selector.currentIndexChanged.connect(self._render_current_spindle)
        self.tool_list.currentRowChanged.connect(self._update_action_states)
        self.tool_list.itemSelectionChanged.connect(self._sync_row_selection_states)
        self.tool_list.orderChanged.connect(self._sync_assignment_order)
        self.tool_list.externalAssignmentsDropped.connect(self._on_external_assignments_dropped)
        self.tool_list.internalReorderRequested.connect(self._on_internal_reorder)

        self._all_tools: list = []
        self._show_pot: bool = False
        self._assignments_by_spindle = {"main": [], "sub": []}
        self._list_scrolling_enabled: bool = True
        self._read_only: bool = False
        self._update_action_states()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Force list geometry refresh when parent width changes.
        self.tool_list.doItemsLayout()
        self.tool_list.viewport().update()
        if not self._list_scrolling_enabled:
            self._update_list_height_for_content()

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

    def set_read_only(self, read_only: bool) -> None:
        self._read_only = bool(read_only)
        self.tool_list.setDragEnabled(not self._read_only)
        self.tool_list.setAcceptDrops(not self._read_only)
        self.tool_list.setDragDropMode(
            QAbstractItemView.NoDragDrop if self._read_only else QAbstractItemView.DragDrop
        )
        self.tool_list.setDefaultDropAction(Qt.MoveAction)
        self._render_current_spindle()

    def set_list_scrolling_enabled(self, enabled: bool) -> None:
        self._list_scrolling_enabled = bool(enabled)
        if self._list_scrolling_enabled:
            self.tool_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.tool_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.tool_list.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)
            self.tool_list.setMinimumHeight(120)
            self.tool_list.setMaximumHeight(16777215)
            # In scrolling mode the panel must be allowed to grow to fill the
            # available height so the list has room to scroll.
            self._list_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        else:
            self.tool_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.tool_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.tool_list.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
            # In content-sized mode the panel must NOT expand — it should be
            # only as tall as the tool list content.
            self._list_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            self._update_list_height_for_content()

    def _update_list_height_for_content(self) -> None:
        if self._list_scrolling_enabled:
            return
        row_count = self.tool_list.count()
        if row_count <= 0:
            self.tool_list.setFixedHeight(42)
            return
        total_rows_height = 0
        fallback_row_height = 44
        for row in range(row_count):
            row_height = self.tool_list.sizeHintForRow(row)
            total_rows_height += row_height if row_height > 0 else fallback_row_height
        frame_height = self.tool_list.frameWidth() * 2
        # Keep a small breathing space under the last card.
        self.tool_list.setFixedHeight(total_rows_height + frame_height + 6)

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
        ref = self._tool_ref_for_assignment(assignment)
        tool_id = (assignment.get("tool_id") or "").strip()
        assignment_desc = str(assignment.get("description") or "").strip()
        if isinstance(ref, dict):
            ref_id = str(ref.get("id") or "").strip() or tool_id
            description = str(ref.get("description") or "").strip() or assignment_desc
            return f"{ref_id}  -  {description}" if description else ref_id
        if assignment_desc:
            return f"{tool_id}  -  {assignment_desc}" if tool_id else assignment_desc
        deleted = self._t("work_editor.tools.deleted_tool", "DELETED TOOL")
        return f"{tool_id}  -  {deleted}" if tool_id else deleted

    def _tool_ref_for_assignment(self, assignment: dict) -> dict | None:
        resolver = getattr(self, "_direct_tool_ref_resolver", None)
        if callable(resolver):
            try:
                resolved = resolver(dict(assignment or {}))
            except Exception:
                resolved = None
            if isinstance(resolved, dict):
                return dict(resolved)
        cached_ref = _find_tool_ref_for_assignment(self._all_tools or [], assignment, self._assignment_key)
        if isinstance(cached_ref, dict):
            return cached_ref
        return None

    def _tool_assignment(self, row: int | None = None) -> dict | None:
        target_row = self.tool_list.currentRow() if row is None else row
        if target_row < 0 or target_row >= self.tool_list.count():
            return None
        item = self.tool_list.item(target_row)
        data = item.data(Qt.UserRole)
        return dict(data) if isinstance(data, dict) else None

    def _render_assignment_row(self, item: QListWidgetItem, row_index: int, assignment: dict):
        lib_tool_id = (assignment.get("tool_id") or "").strip()
        lib_desc = str(assignment.get("description") or "").strip()
        ref = self._tool_ref_for_assignment(assignment)
        if isinstance(ref, dict):
            lib_tool_id = str(ref.get("id") or "").strip() or lib_tool_id
            lib_desc = str(ref.get("description") or "").strip() or lib_desc
        effective_tool_id, effective_desc, is_edited = effective_fields(
            assignment,
            library_tool_id=lib_tool_id,
            library_description=lib_desc,
        )
        if effective_tool_id and effective_desc.startswith(effective_tool_id):
            tail = effective_desc[len(effective_tool_id):].lstrip(" \t\u2014\u2013-")
            effective_desc = tail
        display_text = compose_title(row_index=row_index, tool_id=effective_tool_id, description=effective_desc)
        comment = str(assignment.get("comment") or "").strip()
        effective_pot = str(assignment.get("pot") or "").strip()
        override_id = (assignment.get("override_id") or "").strip()
        override_desc = (assignment.get("override_description") or "").strip()
        item.setText("")
        badges = build_badges(
            comment=comment,
            pot=effective_pot,
            edited=is_edited or bool(override_id or override_desc),
            show_pot=self._show_pot,
        )
        has_comment = bool(comment)
        icon = QIcon()
        tool_type = str(assignment.get("tool_type") or "").strip()
        if isinstance(ref, dict):
            tool_type = str(ref.get("tool_type") or "").strip() or tool_type
        if tool_type:
            icon = self._tool_icon_for_spindle_resolver(tool_type, self._current_spindle())
        flip_vertical = self._head_key == "HEAD2"
        widget = self._ToolAssignmentRowWidget(
            icon=icon,
            text=display_text,
            subtitle=comment,
            comment=comment,
            pot=effective_pot if self._show_pot else "",
            edited=is_edited,
            flip_vertical=flip_vertical,
            parent=self.tool_list,
        )
        widget.set_badges(badges)
        widget._editable = not self._read_only
        # Keep assignment cards pure white regardless of surrounding panel tint.
        widget.setStyleSheet(
            'QFrame[miniAssignmentCard="true"] { background-color: #ffffff; }'
            'QFrame[miniAssignmentCard="true"]:hover { background-color: #ffffff; }'
            'QFrame[miniAssignmentCard="true"][selected="true"],'
            'QFrame[miniAssignmentCard="true"][selected="true"]:hover { background-color: #ffffff; }'
        )
        widget.setProperty("hasComment", has_comment)
        if not self._read_only:
            widget.editRequested.connect(lambda r=row_index: self._inline_edit_row(r))
        row_host = QWidget(self.tool_list)
        row_host.setAttribute(Qt.WA_StyledBackground, False)
        row_layout = QVBoxLayout(row_host)
        # A tiny horizontal inset prevents border clipping on very narrow widths.
        row_layout.setContentsMargins(1, 0, 1, 7)
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
        # In non-scroll mode, keep rows visually anchored from the top.
        self.tool_list.scrollToTop()
        self._update_list_height_for_content()
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
        actions_enabled = has_selection and not self._read_only
        self.move_up_btn.setEnabled(actions_enabled and self.tool_list.currentRow() > 0)
        self.move_down_btn.setEnabled(actions_enabled and self.tool_list.currentRow() < self.tool_list.count() - 1)
        self.remove_btn.setEnabled(actions_enabled)

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

    def _on_internal_reorder(self, moved_items: list, target_row: int) -> None:
        """Handle a same-list drag reorder without ever letting Qt touch items."""
        assignments = self._current_assignments()
        moved_keys = {self._assignment_key(a) for a in moved_items if self._assignment_key(a)}

        # Split into moved vs remaining, preserving original order for each.
        moved = [a for a in assignments if self._assignment_key(a) in moved_keys]
        remaining = [a for a in assignments if self._assignment_key(a) not in moved_keys]

        # Adjust target row: count how many moved items were positioned before it.
        items_above = sum(
            1 for i, a in enumerate(assignments)
            if self._assignment_key(a) in moved_keys and i < target_row
        )
        insert_at = max(0, min(target_row - items_above, len(remaining)))

        for i, item in enumerate(moved):
            remaining.insert(insert_at + i, item)

        self._assignments_by_spindle[self._current_spindle()] = remaining
        self._render_current_spindle()

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
        # Backstop: reject drops from a different head or a different spindle.
        source_owner = getattr(source_widget, "_owner", None)
        if source_owner is not None and source_owner is not self:
            src_head = (getattr(source_owner, "_head_key", "") or "").strip().upper()
            my_head = self._head_key.strip().upper()
            try:
                src_spindle = (source_owner._current_spindle() or "").strip().lower()
            except Exception:
                src_spindle = ""
            if src_head != my_head or src_spindle != self._current_spindle():
                return
        added_keys = self._insert_assignments(dropped_items, insert_row)
        if not added_keys:
            return
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

    def _inline_edit_row(self, row_index: int):
        assignments = self._current_assignments()
        if row_index < 0 or row_index >= len(assignments):
            return
        assignment = assignments[row_index]
        tool_id = (assignment.get("tool_id") or "").strip()
        lib_id = tool_id
        lib_desc = str(assignment.get("description") or "").strip()
        ref = self._tool_ref_for_assignment(assignment)
        if isinstance(ref, dict):
            lib_id = str(ref.get("id") or "").strip() or lib_id
            if not lib_desc:
                lib_desc = str(ref.get("description") or "").strip()
        result = edit_tool_assignment_dialog(
            self,
            translate=self._t,
            library_tool_id=lib_id,
            library_description=lib_desc,
            override_id=str(assignment.get("override_id") or "").strip(),
            override_description=str(assignment.get("override_description") or "").strip(),
            comment_value=str(assignment.get("comment") or "").strip(),
            pot_value=str(assignment.get("pot") or "").strip(),
            default_pot=self._default_pot_for_assignment_resolver(self, assignment),
        )
        if not isinstance(result, dict):
            return
        assignment["override_id"] = str(result.get("override_id") or "").strip()
        assignment["override_description"] = str(result.get("override_description") or "").strip()
        assignment["comment"] = str(result.get("comment") or "").strip()
        assignment["pot"] = str(result.get("pot") or "").strip()
        self._render_current_spindle()
        self.tool_list.setCurrentRow(row_index)

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
                description = ""
                tool_type = ""
                default_pot = ""
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
                description = str(item.get("description") or "").strip()
                tool_type = str(item.get("tool_type") or "").strip()
                default_pot = str(item.get("default_pot") or "").strip()
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
            if description:
                entry["description"] = description
            if tool_type:
                entry["tool_type"] = tool_type
            if default_pot:
                entry["default_pot"] = default_pot
            if tool_uid is not None:
                entry["tool_uid"] = tool_uid
            grouped[spindle].append(entry)
        self._assignments_by_spindle.clear()
        self._assignments_by_spindle.update(grouped)
        self._render_current_spindle()

    def set_tool_ids(self, tool_ids: list):
        self.set_tool_assignments(
            [
                {"tool_id": str(tid).strip(), "spindle": "main", "comment": ""}
                for tid in (tool_ids or [])
                if str(tid).strip()
            ]
        )

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
                description = str(item.get("description") or "").strip()
                if description:
                    entry["description"] = description
                tool_type = str(item.get("tool_type") or "").strip()
                if tool_type:
                    entry["tool_type"] = tool_type
                default_pot = str(item.get("default_pot") or "").strip()
                if default_pot:
                    entry["default_pot"] = default_pot
                if item.get("tool_uid") is not None:
                    try:
                        entry["tool_uid"] = int(item.get("tool_uid"))
                    except Exception:
                        pass
                assignments.append(entry)
        return assignments

