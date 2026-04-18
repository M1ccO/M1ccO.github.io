from __future__ import annotations

import logging
import re
from time import perf_counter

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QStandardItem, QTransform
from PySide6.QtWidgets import QListWidgetItem, QVBoxLayout, QWidget

from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
from shared.ui.helpers.topbar_common import rebuild_filter_row
from ..selector_ui_helpers import selector_spindle_label
from .common import selected_rows_or_current
from ..tool_catalog_delegate import (
    ROLE_TOOL_DATA,
    ROLE_TOOL_ID,
    ROLE_TOOL_ICON,
    ROLE_TOOL_UID,
    tool_icon_for_type,
)


_LOGGER = logging.getLogger(__name__)


class ToolSelectorStateMixin:
    _ASSIGNMENT_TAIL_DROP_ZONE_PX = 0

    def _trace_selector_state(self, event: str, **fields) -> None:
        payload = {
            'event': event,
            'embedded_mode': bool(getattr(self, '_embedded_mode', False)),
        }
        payload.update(fields)
        _LOGGER.info('tool_selector.trace %s', payload)

    def _profile_head_keys(self) -> list[str]:
        profile = getattr(self, 'machine_profile', None)
        if profile is None:
            return ['HEAD1', 'HEAD2']
        if hasattr(profile, 'head_keys'):
            try:
                keys = [str(item).strip().upper() for item in profile.head_keys() if str(item).strip()]
                if keys:
                    return keys
            except Exception:
                pass
        heads = getattr(profile, 'heads', ()) or ()
        fallback = [str(getattr(head, 'key', '')).strip().upper() for head in heads if str(getattr(head, 'key', '')).strip()]
        return fallback or ['HEAD1', 'HEAD2']

    def _has_single_head_profile(self) -> bool:
        return len(self._profile_head_keys()) <= 1

    def _has_single_spindle_profile(self) -> bool:
        profile = getattr(self, 'machine_profile', None)
        if profile is None:
            return False
        if hasattr(profile, 'has_multiple_spindles'):
            try:
                return not bool(profile.has_multiple_spindles())
            except Exception:
                pass
        spindle_keys = getattr(profile, 'spindle_keys', ('main', 'sub')) or ('main', 'sub')
        return len(tuple(spindle_keys)) <= 1

    def _uses_op_terminology(self) -> bool:
        profile = getattr(self, 'machine_profile', None)
        return bool(getattr(profile, 'use_op_terminology', False))

    def _selector_spindle_title(self, spindle: str) -> str:
        normalized = self._normalize_spindle(spindle)
        if self._uses_op_terminology():
            return self._t(
                'tool_library.selector.spindle_op20_tools' if normalized == 'sub' else 'tool_library.selector.spindle_op10_tools',
                'OP20-työkalut' if normalized == 'sub' else 'OP10-työkalut',
            )
        return self._t(
            'tool_library.selector.spindle_sub_tools' if normalized == 'sub' else 'tool_library.selector.spindle_main_tools',
            'Vastakaran työkalut' if normalized == 'sub' else 'Pääkaran työkalut',
        )

    def _set_assignment_section_title(self, spindle: str, title: str) -> None:
        key = self._normalize_spindle(spindle)
        labels = getattr(self, 'assignment_title_labels', {}) or {}
        label = labels.get(key)
        if label is not None:
            label.setText(title)
            return
        frames = getattr(self, 'assignment_frames', {}) or {}
        frame = frames.get(key)
        if frame is not None and hasattr(frame, 'setTitle'):
            frame.setTitle(title)

    @staticmethod
    def _normalize_head(value: str) -> str:
        normalized = str(value or 'HEAD1').strip().upper()
        return normalized if normalized in {'HEAD1', 'HEAD2', 'HEAD3'} else 'HEAD1'

    @staticmethod
    def _normalize_spindle(value: str) -> str:
        normalized = str(value or '').strip().lower()
        return 'sub' if normalized in {'sub', 'sp2', '2'} else 'main'

    @classmethod
    def _target_key(cls, head: str, spindle: str) -> str:
        return f'{cls._normalize_head(head)}:{cls._normalize_spindle(spindle)}'

    def _parse_target_key_hints(self, raw_key: str) -> tuple[str | None, str | None]:
        text = str(raw_key or '').strip()
        if not text:
            return None, None

        lowered = text.lower()
        tokens = [tok for tok in re.split(r'[^a-z0-9]+', lowered) if tok]

        head_hint: str | None = None
        spindle_hint: str | None = None

        if 'head2' in tokens or 'h2' in tokens or 'lower' in tokens:
            head_hint = 'HEAD2'
        elif 'head1' in tokens or 'h1' in tokens or 'upper' in tokens:
            head_hint = 'HEAD1'

        if (
            'sub' in tokens
            or 'sp2' in tokens
            or 'counter' in tokens
            or 'secondary' in tokens
            or 'subspindle' in tokens
        ):
            spindle_hint = 'sub'
        elif 'main' in tokens or 'sp1' in tokens or 'primary' in tokens or 'mainspindle' in tokens:
            spindle_hint = 'main'

        if head_hint is None and spindle_hint is None and (':' in text or '/' in text):
            sep = ':' if ':' in text else '/'
            first, second = text.split(sep, 1)
            first_head = self._normalize_head(first)
            second_head = self._normalize_head(second)
            first_spindle = self._normalize_spindle(first)
            second_spindle = self._normalize_spindle(second)

            if str(first or '').strip().upper() in {'HEAD1', 'HEAD2'}:
                head_hint = first_head
            elif str(second or '').strip().upper() in {'HEAD1', 'HEAD2'}:
                head_hint = second_head

            if str(first or '').strip().lower() in {'main', 'sub', 'sp1', 'sp2', '1', '2'}:
                spindle_hint = first_spindle
            elif str(second or '').strip().lower() in {'main', 'sub', 'sp1', 'sp2', '1', '2'}:
                spindle_hint = second_spindle

        return head_hint, spindle_hint

    def _current_target_key(self, spindle: str | None = None) -> str:
        active_spindle = self._normalize_spindle(spindle or self._current_spindle)
        return self._target_key(self._current_head, active_spindle)

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

        spindle = self._normalize_spindle(item.get('spindle') or item.get('spindle_orientation') or 'main')
        head = self._normalize_head(item.get('tool_head') or item.get('head') or self._current_head)

        normalized = dict(item)
        normalized['tool_id'] = tool_id
        normalized['id'] = tool_id
        normalized['uid'] = uid
        normalized['tool_head'] = head
        normalized['spindle'] = spindle
        normalized['spindle_orientation'] = spindle
        self._enrich_tool_metadata(normalized)
        return normalized

    def _resolve_tool_reference(self, item: dict | None) -> dict | None:
        if not isinstance(item, dict):
            return None
        service = getattr(self, 'tool_service', None)
        if service is None:
            return None

        uid_value = item.get('uid', item.get('tool_uid'))
        try:
            uid = int(uid_value) if uid_value is not None and str(uid_value).strip() else None
        except Exception:
            uid = None
        if uid is not None and hasattr(service, 'get_tool_by_uid'):
            try:
                ref = service.get_tool_by_uid(uid)
            except Exception:
                ref = None
            if isinstance(ref, dict):
                return dict(ref)

        tool_id = str(item.get('tool_id') or item.get('id') or '').strip()
        if tool_id and hasattr(service, 'get_tool'):
            try:
                ref = service.get_tool(tool_id)
            except Exception:
                ref = None
            if isinstance(ref, dict):
                return dict(ref)
        return None

    def _enrich_tool_metadata(self, item: dict | None) -> dict | None:
        if not isinstance(item, dict):
            return None
        needs_ref = not any(
            str(item.get(field) or '').strip()
            for field in ('description', 'tool_type', 'default_pot')
        )
        if not needs_ref:
            return item
        ref = self._resolve_tool_reference(item)
        if not isinstance(ref, dict):
            return item
        for field in ('description', 'tool_type', 'default_pot'):
            value = str(ref.get(field) or '').strip()
            if value and not str(item.get(field) or '').strip():
                item[field] = value
        return item

    def _normalize_tool_for_target(self, item: dict | None, head: str, spindle: str) -> dict | None:
        normalized = self._normalize_tool(item)
        if normalized is None:
            return None
        forced_head = self._normalize_head(head)
        forced_spindle = self._normalize_spindle(spindle)
        normalized['tool_head'] = forced_head
        normalized['head'] = forced_head
        normalized['spindle'] = forced_spindle
        normalized['spindle_orientation'] = forced_spindle
        return normalized

    def _tool_key(self, item: dict | None) -> str:
        if not isinstance(item, dict):
            return ''
        tool_id = str(item.get('tool_id') or item.get('id') or '').strip()
        uid = str(item.get('uid') or '').strip()
        head = self._normalize_head(item.get('tool_head') or item.get('head') or self._current_head)
        spindle = self._normalize_spindle(item.get('spindle') or item.get('spindle_orientation') or 'main')
        if tool_id:
            return f'{head}:{spindle}:{tool_id}'
        if uid:
            return f'{head}:{spindle}:uid:{uid}'
        return ''

    def _normalize_bucket(self, items: list[dict] | None, *, head: str, spindle: str) -> list[dict]:
        normalized_items: list[dict] = []
        seen: set[str] = set()
        for item in items or []:
            normalized = self._normalize_tool_for_target(item, head, spindle)
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
                key_head_hint, key_spindle_hint = self._parse_target_key_hints(str(raw_key or ''))
                for raw_item in raw_items:
                    normalized = self._normalize_tool(raw_item)
                    if normalized is None:
                        continue
                    item_head = self._normalize_head(normalized.get('tool_head') or normalized.get('head') or self._current_head)
                    item_spindle = self._normalize_spindle(
                        normalized.get('spindle') or normalized.get('spindle_orientation') or 'main'
                    )
                    final_head = key_head_hint or item_head
                    final_spindle = key_spindle_hint or item_spindle
                    forced = self._normalize_tool_for_target(raw_item, final_head, final_spindle)
                    if forced is None:
                        continue
                    target = self._target_key(final_head, final_spindle)
                    if target not in buckets:
                        buckets[target] = []
                    key = self._tool_key(forced)
                    if key and any(self._tool_key(existing) == key for existing in buckets[target]):
                        continue
                    buckets[target].append(forced)

        if not buckets and isinstance(initial_assignments, list):
            buckets[self._current_target_key('main')] = self._normalize_bucket(
                initial_assignments,
                head=self._current_head,
                spindle='main',
            )

        # Always keep both spindle buckets available for the active head.
        for spindle in ('main', 'sub'):
            key = self._current_target_key(spindle)
            if key not in buckets:
                buckets[key] = []
        return buckets

    def _store_current_bucket(self) -> None:
        for spindle in ('main', 'sub'):
            key = self._current_target_key(spindle)
            values = self._assigned_tools_by_spindle.get(spindle, [])
            self._assignments_by_target[key] = [dict(item) for item in values if isinstance(item, dict)]

    def _load_current_bucket(self) -> None:
        self._assigned_tools_by_spindle = {}
        for spindle in ('main', 'sub'):
            key = self._current_target_key(spindle)
            self._assigned_tools_by_spindle[spindle] = self._normalize_bucket(
                self._assignments_by_target.get(key, []),
                head=self._current_head,
                spindle=spindle,
            )
        self._assigned_tools = self._assigned_tools_by_spindle.get('main', [])

    def _assignment_icon_for_spindle(self, tool_type: str, spindle: str) -> QIcon:
        icon = tool_icon_for_type(str(tool_type or '').strip())
        if self._normalize_spindle(spindle) != 'sub' or icon.isNull():
            return icon
        pixmap = icon.pixmap(QSize(22, 22))
        if pixmap.isNull():
            return icon
        mirrored = pixmap.transformed(QTransform().scale(-1, 1), Qt.SmoothTransformation)
        return QIcon(mirrored)

    def _assignment_list_for_spindle(self, spindle: str):
        return self.assignment_lists.get(self._normalize_spindle(spindle), self.assignment_list)

    def _assigned_tools_for_spindle(self, spindle: str) -> list[dict]:
        key = self._normalize_spindle(spindle)
        return self._assigned_tools_by_spindle.setdefault(key, [])

    def _update_assignment_list_height(self, spindle: str) -> None:
        assignment_list = self._assignment_list_for_spindle(spindle)
        if bool(getattr(self, '_embedded_mode', False)):
            return
        row_count = assignment_list.count()
        if row_count <= 0:
            assignment_list.setFixedHeight(56 + self._ASSIGNMENT_TAIL_DROP_ZONE_PX)
            return
        total_rows_height = 0
        fallback_row_height = 44
        for row in range(row_count):
            row_height = assignment_list.sizeHintForRow(row)
            total_rows_height += row_height if row_height > 0 else fallback_row_height
        frame_height = assignment_list.frameWidth() * 2
        assignment_list.setFixedHeight(total_rows_height + frame_height + 6 + self._ASSIGNMENT_TAIL_DROP_ZONE_PX)

    def _update_assignment_empty_hint(self, spindle: str) -> None:
        hints = getattr(self, 'assignment_hints', {}) or {}
        target_spindle = self._normalize_spindle(spindle)
        hint = hints.get(target_spindle)
        if hint is None:
            return
        dismissed = getattr(self, '_assignment_hint_dismissed', {}) or {}
        hint.setVisible(not bool(dismissed.get(target_spindle, False)))

    def _active_assignment_spindle(self) -> str:
        if self._has_single_spindle_profile():
            return self._normalize_spindle(self._current_spindle)
        for spindle in ('main', 'sub'):
            lst = self.assignment_lists.get(spindle)
            if lst is not None and lst.currentRow() >= 0:
                return spindle
        for spindle in ('main', 'sub'):
            lst = self.assignment_lists.get(spindle)
            if lst is not None and lst.hasFocus():
                return spindle
        return 'main'

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
        started = perf_counter()
        search_text = self.search_input.text().strip()
        tool_type = self.type_filter.currentData() or 'All'
        delegate = self.list_view.itemDelegate()

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
            icon = tool_icon_for_type(str(tool.get('tool_type') or '').strip())
            item.setData(tool_id, ROLE_TOOL_ID)
            item.setData(uid, ROLE_TOOL_UID)
            item.setData(dict(tool), ROLE_TOOL_DATA)
            item.setData(icon, ROLE_TOOL_ICON)
            prewarm_icon = getattr(delegate, 'prewarm_icon_pixmap', None)
            if callable(prewarm_icon):
                prewarm_icon(
                    icon,
                    str(tool.get('tool_type') or '').strip(),
                    mirrored=self._normalize_spindle(tool.get('spindle_orientation') or tool.get('spindle') or 'main') == 'sub',
                )
            self._model.appendRow(item)
        self._trace_selector_state(
            'catalog.refresh',
            search_text=search_text,
            tool_type=tool_type,
            head=self._current_head,
            row_count=self._model.rowCount(),
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )

    def _rebuild_assignment_list(self, spindle: str | None = None) -> None:
        started = perf_counter()
        targets = ('main', 'sub') if spindle is None else (self._normalize_spindle(spindle),)
        row_counts: dict[str, int] = {}
        for target_spindle in targets:
            assignment_list = self._assignment_list_for_spindle(target_spindle)
            current_row = assignment_list.currentRow()
            assignment_list.blockSignals(True)
            assignment_list.clear()
            assignments = self._assigned_tools_for_spindle(target_spindle)
            row_counts[target_spindle] = len(assignments)

            for row, assignment in enumerate(assignments):
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
                assignment_list.addItem(item)

                row_host = QWidget(assignment_list)
                row_host.setAttribute(Qt.WA_StyledBackground, False)
                row_layout = QVBoxLayout(row_host)
                row_layout.setContentsMargins(0, 0, 2, 7)
                row_layout.setSpacing(0)

                card = MiniAssignmentCard(
                    icon=self._assignment_icon_for_spindle(
                        str(assignment.get('tool_type') or '').strip(),
                        target_spindle,
                    ),
                    title=title,
                    subtitle=comment,
                    badges=badges,
                    editable=False,
                    compact=True,
                    parent=row_host,
                )
                row_layout.addWidget(card)
                assignment_list.setItemWidget(item, row_host)

            assignment_list.blockSignals(False)
            if current_row >= 0 and current_row < assignment_list.count():
                assignment_list.setCurrentRow(current_row)
            assignment_list.scrollToTop()
            self._update_assignment_list_height(target_spindle)
            self._update_assignment_empty_hint(target_spindle)
        self._sync_card_selection_states()
        self._update_assignment_buttons()
        self._trace_selector_state(
            'assignment_list.rebuild',
            targets=list(targets),
            row_counts=row_counts,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )

    def _sync_card_selection_states(self) -> None:
        for assignment_list in self.assignment_lists.values():
            for row in range(assignment_list.count()):
                item = assignment_list.item(row)
                widget = assignment_list.itemWidget(item)
                if isinstance(widget, MiniAssignmentCard):
                    widget.set_selected(item.isSelected())
                    continue
                card = widget.findChild(MiniAssignmentCard) if isinstance(widget, QWidget) else None
                if isinstance(card, MiniAssignmentCard):
                    card.set_selected(item.isSelected())

    def _on_assignment_selection_changed(self, spindle: str) -> None:
        target_list = self._assignment_list_for_spindle(spindle)
        for other_spindle, other_list in self.assignment_lists.items():
            if other_list is target_list:
                continue
            other_list.blockSignals(True)
            other_list.clearSelection()
            other_list.setCurrentRow(-1)
            other_list.blockSignals(False)
        self._sync_card_selection_states()
        self._update_assignment_buttons()

    def _update_assignment_buttons(self) -> None:
        active_spindle = self._active_assignment_spindle()
        active_list = self._assignment_list_for_spindle(active_spindle)
        active_assignments = self._assigned_tools_for_spindle(active_spindle)
        has_row = active_list.currentRow() >= 0
        has_assignments = any(self._assigned_tools_for_spindle(sp) for sp in ('main', 'sub'))
        has_comment = False
        if has_row:
            item = active_list.item(active_list.currentRow())
            payload = item.data(Qt.UserRole) if item is not None else None
            has_comment = bool(str((payload or {}).get('comment') or '').strip()) if isinstance(payload, dict) else False
        self.remove_btn.setEnabled(has_row or has_assignments)
        self.move_up_btn.setEnabled(has_row and active_list.currentRow() > 0)
        self.move_down_btn.setEnabled(has_row and active_list.currentRow() < active_list.count() - 1)
        self.comment_btn.setEnabled(has_row)
        self.delete_comment_btn.setVisible(has_comment)
        self.delete_comment_btn.setEnabled(has_comment)

    def _sync_assignment_order_for_spindle(self, spindle: str) -> None:
        target_spindle = self._normalize_spindle(spindle)
        assignment_list = self._assignment_list_for_spindle(target_spindle)
        ordered: list[dict] = []
        for row in range(assignment_list.count()):
            item = assignment_list.item(row)
            assignment = item.data(Qt.UserRole) if item is not None else None
            normalized = self._normalize_tool(assignment)
            if normalized is not None:
                normalized['spindle'] = target_spindle
                normalized['spindle_orientation'] = target_spindle
                ordered.append(normalized)
        self._assigned_tools_by_spindle[target_spindle] = ordered
        self._store_current_bucket()
        self._rebuild_assignment_list(target_spindle)

    def _sync_assignment_order(self) -> None:
        for spindle in ('main', 'sub'):
            self._sync_assignment_order_for_spindle(spindle)

    def _add_tools(self, dropped_items: list[dict], insert_row: int | None = None, spindle: str | None = None) -> bool:
        target_spindle = self._normalize_spindle(spindle or self._active_assignment_spindle())
        target_assignments = self._assigned_tools_for_spindle(target_spindle)
        existing = {self._tool_key(item) for item in target_assignments if self._tool_key(item)}
        insert_at = len(target_assignments) if insert_row is None else max(0, min(insert_row, len(target_assignments)))
        added = False
        for tool in dropped_items or []:
            normalized = self._normalize_tool(tool)
            if normalized is None:
                continue
            normalized['spindle'] = target_spindle
            normalized['spindle_orientation'] = target_spindle
            key = self._tool_key(normalized)
            if not key or key in existing:
                continue
            target_assignments.insert(insert_at, normalized)
            existing.add(key)
            insert_at += 1
            added = True
        if not added:
            return False
        self._store_current_bucket()
        self._rebuild_assignment_list(target_spindle)
        target_list = self._assignment_list_for_spindle(target_spindle)
        if target_list.count() > 0:
            target_list.setCurrentRow(min(insert_at - 1, target_list.count() - 1))
        return True

    def _remove_selected(self) -> None:
        spindle = self._active_assignment_spindle()
        target_list = self._assignment_list_for_spindle(spindle)
        target_assignments = self._assigned_tools_for_spindle(spindle)
        row = target_list.currentRow()
        if row < 0 or row >= len(target_assignments):
            if target_assignments:
                target_assignments.pop()
                self._store_current_bucket()
                self._rebuild_assignment_list(spindle)
            return
        target_assignments.pop(row)
        self._store_current_bucket()
        self._rebuild_assignment_list(spindle)
        if target_list.count() > 0:
            target_list.setCurrentRow(min(row, target_list.count() - 1))

    def _remove_by_drop(self, dropped_items: list[dict]) -> None:
        keys = {self._tool_key(self._normalize_tool(item)) for item in (dropped_items or []) if isinstance(item, dict)}
        keys = {k for k in keys if k}
        if not keys:
            return
        for spindle in ('main', 'sub'):
            self._assigned_tools_by_spindle[spindle] = [
                item for item in self._assigned_tools_for_spindle(spindle) if self._tool_key(item) not in keys
            ]
        self._store_current_bucket()
        self._rebuild_assignment_list()

    def _move_up(self) -> None:
        spindle = self._active_assignment_spindle()
        target_list = self._assignment_list_for_spindle(spindle)
        target_assignments = self._assigned_tools_for_spindle(spindle)
        row = target_list.currentRow()
        if row <= 0 or row >= len(target_assignments):
            return
        target_assignments[row - 1], target_assignments[row] = target_assignments[row], target_assignments[row - 1]
        self._store_current_bucket()
        self._rebuild_assignment_list(spindle)
        target_list.setCurrentRow(row - 1)

    def _move_down(self) -> None:
        spindle = self._active_assignment_spindle()
        target_list = self._assignment_list_for_spindle(spindle)
        target_assignments = self._assigned_tools_for_spindle(spindle)
        row = target_list.currentRow()
        if row < 0 or row >= len(target_assignments) - 1:
            return
        target_assignments[row], target_assignments[row + 1] = target_assignments[row + 1], target_assignments[row]
        self._store_current_bucket()
        self._rebuild_assignment_list(spindle)
        target_list.setCurrentRow(row + 1)

    def _add_comment(self) -> None:
        spindle = self._active_assignment_spindle()
        target_list = self._assignment_list_for_spindle(spindle)
        target_assignments = self._assigned_tools_for_spindle(spindle)
        row = target_list.currentRow()
        if row < 0 or row >= len(target_assignments):
            return
        from PySide6.QtWidgets import QInputDialog

        current = str(target_assignments[row].get('comment') or '').strip()
        text, ok = QInputDialog.getText(
            self,
            self._t('tool_library.selector.add_comment', 'Lisää kommentti'),
            self._t('tool_library.selector.comment_prompt', 'Kommentti:'),
            text=current,
        )
        if not ok:
            return
        target_assignments[row]['comment'] = text.strip()
        self._store_current_bucket()
        self._rebuild_assignment_list(spindle)
        target_list.setCurrentRow(row)

    def _delete_comment(self) -> None:
        spindle = self._active_assignment_spindle()
        target_list = self._assignment_list_for_spindle(spindle)
        target_assignments = self._assigned_tools_for_spindle(spindle)
        row = target_list.currentRow()
        if row < 0 or row >= len(target_assignments):
            return
        target_assignments[row].pop('comment', None)
        self._store_current_bucket()
        self._rebuild_assignment_list(spindle)
        target_list.setCurrentRow(row)

    def _toggle_head(self) -> None:
        if self._has_single_head_profile():
            return
        self._store_current_bucket()
        keys = self._profile_head_keys()
        if not keys:
            return
        if self._current_head not in keys:
            self._current_head = keys[0]
        else:
            idx = keys.index(self._current_head)
            self._current_head = keys[(idx + 1) % len(keys)]
        self._load_current_bucket()
        self._refresh_catalog()
        self._rebuild_assignment_list()
        self._update_context_header()

    def _update_context_header(self) -> None:
        single_head = self._has_single_head_profile()
        single_spindle = self._has_single_spindle_profile()
        if bool(getattr(self, '_is_machining_center_selector_mode', False)):
            self.selector_head_value_label.setVisible(False)
            self.selector_spindle_value_label.setVisible(False)
            self.head_btn.setVisible(False)
            if 'main' in self.assignment_frames:
                self.assignment_frames['main'].setVisible(True)
            if 'sub' in self.assignment_frames:
                self.assignment_frames['sub'].setVisible(False)
            if 'main' in self.assignment_frames:
                self._set_assignment_section_title('main', self._selector_spindle_title('main'))
            return

        head_label = (
            self._t('tool_library.selector.head_lower', 'Alarevolveri')
            if self._current_head == 'HEAD2'
            else self._t('tool_library.selector.head_upper', 'Yläkara')
        )
        self.selector_head_value_label.setText(head_label)
        if single_spindle and self._uses_op_terminology():
            self.selector_spindle_value_label.setText(
                self._t(
                    'tool_library.selector.op20' if self._normalize_spindle(self._current_spindle) == 'sub' else 'tool_library.selector.op10',
                    'OP20' if self._normalize_spindle(self._current_spindle) == 'sub' else 'OP10',
                )
            )
        else:
            self.selector_spindle_value_label.setText(
                self._t('tool_library.selector.main_sub', 'Pääkara / Vastakara')
            )
        self.head_btn.setText(head_label)
        self.selector_spindle_value_label.setVisible(True)
        self.selector_head_value_label.setVisible(not single_head)
        self.head_btn.setVisible(not single_head)
        if 'main' in self.assignment_frames:
            self.assignment_frames['main'].setVisible((not single_spindle) or self._normalize_spindle(self._current_spindle) == 'main')
        if 'sub' in self.assignment_frames:
            self.assignment_frames['sub'].setVisible((not single_spindle) or self._normalize_spindle(self._current_spindle) == 'sub')
        if 'main' in self.assignment_frames:
            self._set_assignment_section_title('main', self._selector_spindle_title('main'))
        if 'sub' in self.assignment_frames:
            self._set_assignment_section_title('sub', self._selector_spindle_title('sub'))

    def _on_catalog_double_clicked(self, _index) -> None:
        indexes = selected_rows_or_current(self.list_view)
        if not indexes:
            return
        dropped_items: list[dict] = []
        for index in indexes:
            tool_data = index.data(ROLE_TOOL_DATA)
            if isinstance(tool_data, dict):
                dropped_items.append(dict(tool_data))
        self._add_tools(dropped_items, spindle=self._active_assignment_spindle())

    def _on_tools_dropped_for_spindle(self, spindle: str, dropped_items: list, insert_row: int) -> None:
        added = self._add_tools(
            dropped_items if isinstance(dropped_items, list) else [],
            None,
            spindle=spindle,
        )
        if not added:
            return
        target_spindle = self._normalize_spindle(spindle)
        dismissed = getattr(self, '_assignment_hint_dismissed', None)
        if not isinstance(dismissed, dict):
            dismissed = {}
        dismissed[target_spindle] = True
        self._assignment_hint_dismissed = dismissed
        self._update_assignment_empty_hint(target_spindle)

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
        ensure_detail_card_built = getattr(self, '_ensure_detail_card_built', None)
        if callable(ensure_detail_card_built):
            ensure_detail_card_built()
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
        started = perf_counter()
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
        self._trace_selector_state(
            'detail.prime_cache',
            has_index=bool(indexes),
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )

    def _sync_preview_if_open(self) -> None:
        preview_btn = getattr(self, 'preview_window_btn', None)
        if preview_btn is not None and preview_btn.isChecked():
            self._sync_detached_preview(show_errors=False)

    def _populate_tool_detail(self, tool: dict | None) -> None:
        """Clear and rebuild the detail panel content using DetailPanelBuilder."""
        started = perf_counter()
        ensure_detail_card_built = getattr(self, '_ensure_detail_card_built', None)
        if callable(ensure_detail_card_built):
            ensure_detail_card_built()
        from ..home_page_support.detail_panel_builder import DetailPanelBuilder
        
        # Clear existing content
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        builder = DetailPanelBuilder(self)
        builder.populate_details(tool)
        self._trace_selector_state(
            'detail.populate',
            tool_id=str((tool or {}).get('id') or '').strip() or None,
            has_tool=bool(tool),
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
