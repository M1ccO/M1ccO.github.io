from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QListWidgetItem, QVBoxLayout, QWidget

from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
from shared.ui.helpers.topbar_common import rebuild_filter_row
from ui.selector_ui_helpers import selector_spindle_label
from ui.selectors.common import selected_rows_or_current
from ui.tool_catalog_delegate import (
    ROLE_TOOL_DATA,
    ROLE_TOOL_ID,
    ROLE_TOOL_ICON,
    ROLE_TOOL_UID,
    tool_icon_for_type,
)


class ToolSelectorStateMixin:
    @staticmethod
    def _normalize_head(value: str) -> str:
        normalized = str(value or 'HEAD1').strip().upper()
        return normalized if normalized in {'HEAD1', 'HEAD2'} else 'HEAD1'

    @staticmethod
    def _normalize_spindle(value: str) -> str:
        normalized = str(value or '').strip().lower()
        return 'sub' if normalized in {'sub', 'sp2', '2'} else 'main'

    @classmethod
    def _target_key(cls, head: str, spindle: str) -> str:
        return f'{cls._normalize_head(head)}:{cls._normalize_spindle(spindle)}'

    def _current_target_key(self) -> str:
        return self._target_key(self._current_head, self._current_spindle)

    def _normalize_tool(self, item: dict | None) -> dict | None:
        if not isinstance(item, dict):
            return None
        tool_id = str(item.get('tool_id') or item.get('id') or '').strip()
        uid_value = item.get('uid')
        try:
            uid = int(uid_value)
        except Exception:
            uid = 0
        if not tool_id and uid <= 0:
            return None

        spindle = self._normalize_spindle(item.get('spindle') or item.get('spindle_orientation') or self._current_spindle)
        head = self._normalize_head(item.get('tool_head') or item.get('head') or self._current_head)

        normalized = dict(item)
        normalized['tool_id'] = tool_id
        normalized['id'] = tool_id
        normalized['uid'] = uid
        normalized['tool_head'] = head
        normalized['spindle'] = spindle
        normalized['spindle_orientation'] = spindle
        return normalized

    def _tool_key(self, item: dict | None) -> str:
        if not isinstance(item, dict):
            return ''
        tool_id = str(item.get('tool_id') or item.get('id') or '').strip()
        uid = str(item.get('uid') or '').strip()
        head = self._normalize_head(item.get('tool_head') or item.get('head') or self._current_head)
        spindle = self._normalize_spindle(item.get('spindle') or item.get('spindle_orientation') or self._current_spindle)
        if tool_id:
            return f'{head}:{spindle}:{tool_id}'
        if uid:
            return f'{head}:{spindle}:uid:{uid}'
        return ''

    def _normalize_bucket(self, items: list[dict] | None) -> list[dict]:
        normalized_items: list[dict] = []
        seen: set[str] = set()
        for item in items or []:
            normalized = self._normalize_tool(item)
            if normalized is None:
                continue
            key = self._tool_key(normalized)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            normalized_items.append(normalized)
        return normalized_items

    def _build_initial_buckets(
        self,
        initial_assignments: list[dict] | None,
        initial_assignment_buckets: dict[str, list[dict]] | None,
    ) -> dict[str, list[dict]]:
        buckets: dict[str, list[dict]] = {}
        if isinstance(initial_assignment_buckets, dict):
            for raw_key, raw_items in initial_assignment_buckets.items():
                if not isinstance(raw_items, list):
                    continue
                text = str(raw_key or '').strip()
                head_part = 'HEAD1'
                spindle_part = 'main'
                if ':' in text:
                    head_part, spindle_part = text.split(':', 1)
                elif '/' in text:
                    head_part, spindle_part = text.split('/', 1)
                buckets[self._target_key(head_part, spindle_part)] = self._normalize_bucket(raw_items)

        if not buckets and isinstance(initial_assignments, list):
            buckets[self._current_target_key()] = self._normalize_bucket(initial_assignments)

        if self._current_target_key() not in buckets:
            buckets[self._current_target_key()] = []
        return buckets

    def _store_current_bucket(self) -> None:
        self._assignments_by_target[self._current_target_key()] = [dict(item) for item in self._assigned_tools if isinstance(item, dict)]

    def _load_current_bucket(self) -> None:
        self._assigned_tools = [
            dict(item)
            for item in self._assignments_by_target.get(self._current_target_key(), [])
            if isinstance(item, dict)
        ]

    def _tool_matches_spindle(self, tool: dict) -> bool:
        spindle = str(
            tool.get('spindle_orientation')
            or tool.get('spindle')
            or tool.get('spindle_side')
            or ''
        ).strip().lower()
        if not spindle:
            return True
        if self._current_spindle == 'main':
            return spindle in {'main', 'both', 'all'}
        return spindle in {'sub', 'both', 'all'}

    def _refresh_catalog(self) -> None:
        search_text = self.search_input.text().strip()
        tool_type = self.type_filter.currentData() or 'All'

        tools = self.tool_service.list_tools(
            search_text=search_text,
            tool_type=tool_type,
            tool_head=self._current_head,
        )
        # NOTE: spindle does NOT filter the catalog — it only switches the
        # assignment target bucket.  All tools applicable to the head are shown.

        self._model.clear()
        for tool in tools:
            item = QStandardItem()
            tool_id = str(tool.get('id') or '').strip()
            uid = int(tool.get('uid') or 0)
            item.setData(tool_id, ROLE_TOOL_ID)
            item.setData(uid, ROLE_TOOL_UID)
            item.setData(dict(tool), ROLE_TOOL_DATA)
            item.setData(tool_icon_for_type(str(tool.get('tool_type') or '').strip()), ROLE_TOOL_ICON)
            self._model.appendRow(item)

    def _rebuild_assignment_list(self) -> None:
        current_row = self.assignment_list.currentRow()
        self.assignment_list.blockSignals(True)
        self.assignment_list.clear()

        for row, assignment in enumerate(self._assigned_tools):
            tool_id = str(assignment.get('tool_id') or assignment.get('id') or '').strip()
            description = str(assignment.get('description') or '').strip()
            comment = str(assignment.get('comment') or '').strip()
            default_pot = str(assignment.get('default_pot') or '').strip()
            title = f'{row + 1}. {tool_id}' if tool_id else f'{row + 1}.'
            if description:
                title = f'{title}  -  {description}'

            badges: list[str] = []
            if default_pot:
                badges.append(f'P:{default_pot}')
            if comment:
                badges.append('C')

            item = QListWidgetItem()
            item.setData(Qt.UserRole, dict(assignment))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            item.setSizeHint(QSize(0, 50 if comment else 42))
            self.assignment_list.addItem(item)

            card = MiniAssignmentCard(
                icon=tool_icon_for_type(str(assignment.get('tool_type') or '').strip()),
                title=title,
                subtitle=comment,
                badges=badges,
                editable=False,
                compact=True,
                parent=self.assignment_list,
            )
            row_host = QWidget(self.assignment_list)
            row_host.setAttribute(Qt.WA_StyledBackground, False)
            row_layout = QVBoxLayout(row_host)
            row_layout.setContentsMargins(0, 0, 0, 7)
            row_layout.setSpacing(0)
            row_layout.addWidget(card)
            self.assignment_list.setItemWidget(item, row_host)

        self.assignment_list.blockSignals(False)
        if current_row >= 0 and current_row < self.assignment_list.count():
            self.assignment_list.setCurrentRow(current_row)
        self._sync_card_selection_states()
        self._update_assignment_buttons()

    def _sync_card_selection_states(self) -> None:
        for row in range(self.assignment_list.count()):
            item = self.assignment_list.item(row)
            widget = self.assignment_list.itemWidget(item)
            if isinstance(widget, MiniAssignmentCard):
                widget.set_selected(item.isSelected())
                continue
            card = widget.findChild(MiniAssignmentCard) if isinstance(widget, QWidget) else None
            if isinstance(card, MiniAssignmentCard):
                card.set_selected(item.isSelected())

    def _update_assignment_buttons(self) -> None:
        has_row = self.assignment_list.currentRow() >= 0
        has_assignments = bool(self._assigned_tools)
        has_comment = False
        if has_row:
            item = self.assignment_list.item(self.assignment_list.currentRow())
            payload = item.data(Qt.UserRole) if item is not None else None
            has_comment = bool(str((payload or {}).get('comment') or '').strip()) if isinstance(payload, dict) else False
        self.remove_btn.setEnabled(has_row or has_assignments)
        self.move_up_btn.setEnabled(has_row and self.assignment_list.currentRow() > 0)
        self.move_down_btn.setEnabled(has_row and self.assignment_list.currentRow() < self.assignment_list.count() - 1)
        self.comment_btn.setEnabled(has_row)
        self.delete_comment_btn.setVisible(has_comment)
        self.delete_comment_btn.setEnabled(has_comment)

    def _sync_assignment_order(self) -> None:
        ordered: list[dict] = []
        for row in range(self.assignment_list.count()):
            item = self.assignment_list.item(row)
            assignment = item.data(Qt.UserRole) if item is not None else None
            normalized = self._normalize_tool(assignment)
            if normalized is not None:
                ordered.append(normalized)
        self._assigned_tools = ordered
        self._store_current_bucket()
        self._rebuild_assignment_list()

    def _add_tools(self, dropped_items: list[dict], insert_row: int | None = None) -> None:
        existing = {self._tool_key(item) for item in self._assigned_tools if self._tool_key(item)}
        insert_at = len(self._assigned_tools) if insert_row is None else max(0, min(insert_row, len(self._assigned_tools)))
        added = False
        for tool in dropped_items or []:
            normalized = self._normalize_tool(tool)
            if normalized is None:
                continue
            key = self._tool_key(normalized)
            if not key or key in existing:
                continue
            self._assigned_tools.insert(insert_at, normalized)
            existing.add(key)
            insert_at += 1
            added = True
        if not added:
            return
        self._store_current_bucket()
        self._rebuild_assignment_list()
        if self.assignment_list.count() > 0:
            self.assignment_list.setCurrentRow(min(insert_at - 1, self.assignment_list.count() - 1))

    def _remove_selected(self) -> None:
        row = self.assignment_list.currentRow()
        if row < 0 or row >= len(self._assigned_tools):
            if self._assigned_tools:
                self._assigned_tools.pop()
                self._store_current_bucket()
                self._rebuild_assignment_list()
            return
        self._assigned_tools.pop(row)
        self._store_current_bucket()
        self._rebuild_assignment_list()
        if self.assignment_list.count() > 0:
            self.assignment_list.setCurrentRow(min(row, self.assignment_list.count() - 1))

    def _remove_by_drop(self, dropped_items: list[dict]) -> None:
        keys = {self._tool_key(self._normalize_tool(item)) for item in (dropped_items or []) if isinstance(item, dict)}
        keys = {k for k in keys if k}
        if not keys:
            return
        self._assigned_tools = [item for item in self._assigned_tools if self._tool_key(item) not in keys]
        self._store_current_bucket()
        self._rebuild_assignment_list()

    def _move_up(self) -> None:
        row = self.assignment_list.currentRow()
        if row <= 0 or row >= len(self._assigned_tools):
            return
        self._assigned_tools[row - 1], self._assigned_tools[row] = self._assigned_tools[row], self._assigned_tools[row - 1]
        self._store_current_bucket()
        self._rebuild_assignment_list()
        self.assignment_list.setCurrentRow(row - 1)

    def _move_down(self) -> None:
        row = self.assignment_list.currentRow()
        if row < 0 or row >= len(self._assigned_tools) - 1:
            return
        self._assigned_tools[row], self._assigned_tools[row + 1] = self._assigned_tools[row + 1], self._assigned_tools[row]
        self._store_current_bucket()
        self._rebuild_assignment_list()
        self.assignment_list.setCurrentRow(row + 1)

    def _add_comment(self) -> None:
        row = self.assignment_list.currentRow()
        if row < 0 or row >= len(self._assigned_tools):
            return
        from PySide6.QtWidgets import QInputDialog

        current = str(self._assigned_tools[row].get('comment') or '').strip()
        text, ok = QInputDialog.getText(
            self,
            self._t('tool_library.selector.add_comment', 'Add Comment'),
            self._t('tool_library.selector.comment_prompt', 'Comment:'),
            text=current,
        )
        if not ok:
            return
        self._assigned_tools[row]['comment'] = text.strip()
        self._store_current_bucket()
        self._rebuild_assignment_list()
        self.assignment_list.setCurrentRow(row)

    def _delete_comment(self) -> None:
        row = self.assignment_list.currentRow()
        if row < 0 or row >= len(self._assigned_tools):
            return
        self._assigned_tools[row].pop('comment', None)
        self._store_current_bucket()
        self._rebuild_assignment_list()
        self.assignment_list.setCurrentRow(row)

    def _toggle_head(self) -> None:
        self._store_current_bucket()
        self._current_head = 'HEAD2' if self._current_head == 'HEAD1' else 'HEAD1'
        self._load_current_bucket()
        self._refresh_catalog()
        self._rebuild_assignment_list()
        self._update_context_header()

    def _toggle_spindle(self) -> None:
        self._store_current_bucket()
        self._current_spindle = 'sub' if self.spindle_btn.isChecked() else 'main'
        self._load_current_bucket()
        self._refresh_catalog()
        self._rebuild_assignment_list()
        self._update_context_header()

    def _update_context_header(self) -> None:
        if bool(getattr(self, '_is_machining_center_selector_mode', False)):
            self.selector_head_value_label.setVisible(False)
            self.selector_spindle_value_label.setVisible(False)
            self.head_btn.setVisible(False)
            self.spindle_btn.setVisible(False)
            self.assignment_frame.setTitle(
                self._t('tool_library.selector.operation_tools', 'Operation tools')
            )
            return

        head_label = (
            self._t('tool_library.selector.head_lower', 'Lower Turret')
            if self._current_head == 'HEAD2'
            else self._t('tool_library.selector.head_upper', 'Upper Spindle')
        )
        spindle_label = (
            self._t('tool_library.nav.sub_spindle', 'Sub Spindle')
            if self._current_spindle == 'sub'
            else self._t('tool_library.nav.main_spindle', 'Main Spindle')
        )
        self.selector_head_value_label.setText(head_label)
        self.selector_spindle_value_label.setText(spindle_label)
        self.head_btn.setText(head_label)
        self.spindle_btn.blockSignals(True)
        self.spindle_btn.setChecked(self._current_spindle == 'sub')
        self.spindle_btn.setText(spindle_label)
        self.spindle_btn.blockSignals(False)
        self.assignment_frame.setTitle(
            self._t('tool_library.selector.spindle_sub_tools', 'Sub Spindle Tools')
            if self._current_spindle == 'sub'
            else self._t('tool_library.selector.spindle_main_tools', 'Main Spindle Tools')
        )

    def _on_catalog_double_clicked(self, _index) -> None:
        indexes = selected_rows_or_current(self.list_view)
        if not indexes:
            return
        dropped_items: list[dict] = []
        for index in indexes:
            tool_data = index.data(ROLE_TOOL_DATA)
            if isinstance(tool_data, dict):
                dropped_items.append(dict(tool_data))
        self._add_tools(dropped_items)

    def _on_tools_dropped(self, dropped_items: list, insert_row: int) -> None:
        self._add_tools(dropped_items if isinstance(dropped_items, list) else [], insert_row)

    # ── Toolbar helpers ─────────────────────────────────────────────────────

    def _toggle_search(self) -> None:
        """Show/hide the search input and rebuild the toolbar row."""
        visible = self.search_toggle.isChecked()
        self.search_input.setVisible(visible)
        if not visible:
            self.search_input.clear()
            self._refresh_catalog()
        rebuild_filter_row(
            self._filter_layout,
            self.search_toggle,
            self.toggle_details_btn,
            self.search_input,
            self.filter_icon,
            [self.type_filter],
            self.preview_window_btn,
            self.detail_header_container,
        )
        if visible:
            self.search_input.setFocus()

    def _clear_search(self) -> None:
        """Reset search text and type filter."""
        self.search_input.clear()
        if self.type_filter.count():
            self.type_filter.setCurrentIndex(0)

    # ── Detail panel toggle ──────────────────────────────────────────────────

    def _toggle_detail_panel(self) -> None:
        """Toggle right panel between selector and tool detail views."""
        if self.detail_card.isVisible():
            self._switch_to_selector_panel()
            return
        indexes = selected_rows_or_current(self.list_view)
        tool_data: dict | None = None
        if indexes:
            tool_data = indexes[0].data(ROLE_TOOL_DATA)
        self._switch_to_detail_panel(tool_data)

    def _switch_to_detail_panel(self, tool_data: dict | None = None) -> None:
        """Show the detail card and populate it with tool_data."""
        self.setUpdatesEnabled(False)
        self.selector_card.setVisible(False)
        self.detail_card.setVisible(True)
        self.detail_header_container.setVisible(True)
        rebuild_filter_row(
            self._filter_layout,
            self.search_toggle,
            self.toggle_details_btn,
            self.search_input,
            self.filter_icon,
            [self.type_filter],
            self.preview_window_btn,
            self.detail_header_container,
        )
        self._populate_tool_detail(tool_data)
        self.setUpdatesEnabled(True)

    def _switch_to_selector_panel(self) -> None:
        """Show the selector card; hide the detail card."""
        self.detail_card.setVisible(False)
        self.selector_card.setVisible(True)
        self.detail_header_container.setVisible(False)
        rebuild_filter_row(
            self._filter_layout,
            self.search_toggle,
            self.toggle_details_btn,
            self.search_input,
            self.filter_icon,
            [self.type_filter],
            self.preview_window_btn,
            self.detail_header_container,
        )

    def _on_catalog_item_clicked(self, index) -> None:
        """When detail panel is active, repopulate it with the clicked tool."""
        tool_data = index.data(ROLE_TOOL_DATA)
        if isinstance(tool_data, dict):
            self.current_tool_id = str(tool_data.get('id') or '').strip() or None
            try:
                self.current_tool_uid = int(tool_data.get('uid') or 0) or None
            except Exception:
                self.current_tool_uid = None
        self._sync_preview_if_open()
        if not self.detail_card.isVisible():
            return
        self._populate_tool_detail(tool_data if isinstance(tool_data, dict) else None)

    def _on_catalog_double_clicked_open_detail(self, index) -> None:
        """Double-click toggles detail panel only (never starts in-place editing)."""
        tool_data = index.data(ROLE_TOOL_DATA)
        if isinstance(tool_data, dict):
            self.current_tool_id = str(tool_data.get('id') or '').strip() or None
            try:
                self.current_tool_uid = int(tool_data.get('uid') or 0) or None
            except Exception:
                self.current_tool_uid = None
        self._sync_preview_if_open()
        if self.detail_card.isVisible():
            self._switch_to_selector_panel()
            return
        self._switch_to_detail_panel(tool_data if isinstance(tool_data, dict) else None)

    def _prime_detail_panel_cache(self) -> None:
        """Pre-render first detail payload so first open is smooth and non-jarring."""
        indexes = selected_rows_or_current(self.list_view)
        if not indexes and self._model.rowCount() > 0:
            first_index = self._model.index(0, 0)
            if first_index.isValid():
                self.list_view.setCurrentIndex(first_index)
                indexes = [first_index]
        if not indexes:
            return
        tool_data = indexes[0].data(ROLE_TOOL_DATA)
        if isinstance(tool_data, dict):
            self.current_tool_id = str(tool_data.get('id') or '').strip() or None
            try:
                self.current_tool_uid = int(tool_data.get('uid') or 0) or None
            except Exception:
                self.current_tool_uid = None
            self._populate_tool_detail(tool_data)

    def _sync_preview_if_open(self) -> None:
        preview_btn = getattr(self, 'preview_window_btn', None)
        if preview_btn is not None and preview_btn.isChecked():
            self._sync_detached_preview(show_errors=False)

    def _populate_tool_detail(self, tool: dict | None) -> None:
        """Clear and rebuild the detail panel content using DetailPanelBuilder."""
        from ui.home_page_support.detail_panel_builder import DetailPanelBuilder
        # Clear existing content
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        builder = DetailPanelBuilder(self)
        builder.populate_details(tool)
