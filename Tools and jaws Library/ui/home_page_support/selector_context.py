"""Selector context helpers for HomePage.

Extracted from home_page.py (Phase 10 Pass 5).
Manages Setup Manager integration: selector state, spindle/head constraints,
assignment buckets, and normalization helpers.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QListWidgetItem, QInputDialog, QVBoxLayout, QWidget

from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
from ui.selector_state_helpers import (
    default_selector_splitter_sizes,
    normalize_selector_bucket,
    selector_assignments_for_target,
    selector_bucket_map,
)
from ui.selector_ui_helpers import normalize_selector_spindle, selector_spindle_label
from ui.tool_catalog_delegate import tool_icon_for_type

__all__ = [
    "normalize_selector_tool",
    "selector_tool_key",
    "selector_target_key",
    "selector_current_target_key",
    "tool_matches_selector_spindle",
    "selected_tools_for_setup_assignment",
    "selector_assignment_buckets_for_setup_assignment",
    "selector_current_target_for_setup_assignment",
    "set_selector_context",
    "selector_assigned_tools_for_setup_assignment",
    "on_selector_toggle_clicked",
    "toggle_selector_spindle",
    "on_selector_tools_dropped",
    "sync_selector_assignment_order",
    "remove_selector_assignment",
    "remove_selector_assignments_by_drop",
    "move_selector_up",
    "move_selector_down",
    "add_selector_comment",
    "delete_selector_comment",
    "sync_selector_card_selection_states",
    "update_selector_assignment_buttons",
    "on_selector_cancel",
    "on_selector_done",
]


def _normalize_selector_head_value(value: str) -> str:
    normalized = str(value or 'HEAD1').strip().upper()
    return normalized if normalized in {'HEAD1', 'HEAD2'} else 'HEAD1'


def _selector_assignments_section_title(page) -> str:
    if _normalize_selector_head_value(page._selector_head) == 'HEAD2':
        return page._t('tool_library.selector.head2_tools', 'Head 2 Tools')
    return page._t('tool_library.selector.head1_tools', 'Head 1 Tools')


def _update_selector_assignments_section_title(page) -> None:
    if hasattr(page, 'selector_assignments_frame') and hasattr(page.selector_assignments_frame, 'setTitle'):
        page.selector_assignments_frame.setTitle(_selector_assignments_section_title(page))


def _update_selector_context_header(page) -> None:
    if hasattr(page, 'selector_spindle_value_label'):
        page.selector_spindle_value_label.setText(selector_spindle_label(page._selector_spindle))
    if hasattr(page, 'selector_head_value_label'):
        page.selector_head_value_label.setText(_normalize_selector_head_value(page._selector_head))
    if hasattr(page, 'selector_spindle_btn'):
        is_sub = normalize_selector_spindle(page._selector_spindle) == 'sub'
        page.selector_spindle_btn.blockSignals(True)
        page.selector_spindle_btn.setChecked(is_sub)
        page.selector_spindle_btn.setProperty('spindle', 'sub' if is_sub else 'main')
        page.selector_spindle_btn.setText(selector_spindle_label(page._selector_spindle))
        page.selector_spindle_btn.blockSignals(False)


def _set_selector_panel_mode(page, mode: str) -> None:
    if not page._selector_active:
        page._selector_panel_mode = 'details'
        if hasattr(page, 'selector_toggle_btn'):
            page.selector_toggle_btn.setChecked(False)
        if hasattr(page, 'selector_card'):
            page.selector_card.setVisible(False)
        if hasattr(page, 'detail_card'):
            page.detail_card.setVisible(True)
        return

    target_mode = 'details' if str(mode or '').strip().lower() == 'details' else 'selector'
    page._selector_panel_mode = target_mode
    page._details_hidden = False
    page.detail_container.show()
    page.detail_header_container.show()
    if not page._last_splitter_sizes:
        page._last_splitter_sizes = default_selector_splitter_sizes(page.splitter.width())
    page.splitter.setSizes(page._last_splitter_sizes)

    if target_mode == 'details':
        page.detail_card.setVisible(True)
        page.selector_card.setVisible(False)
        page.detail_section_label.setText(page._t('tool_library.section.tool_details', 'Tool details'))
        if hasattr(page, 'toggle_details_btn'):
            page.toggle_details_btn.setText(page._t('tool_library.details.hide', 'HIDE DETAILS'))
        if hasattr(page, 'selector_toggle_btn'):
            page.selector_toggle_btn.setChecked(False)
            page.selector_toggle_btn.setText(page._t('tool_library.selector.mode_selector', 'SELECTOR'))
        return

    page.detail_card.setVisible(False)
    page.selector_card.setVisible(True)
    page.detail_section_label.setText(page._t('tool_library.selector.selection_title', 'Selection'))
    if hasattr(page, 'toggle_details_btn'):
        page.toggle_details_btn.setText(page._t('tool_library.details.show', 'SHOW DETAILS'))
    if hasattr(page, 'selector_toggle_btn'):
        page.selector_toggle_btn.setChecked(True)
        page.selector_toggle_btn.setText(page._t('tool_library.selector.mode_details', 'DETAILS'))
    _load_selector_bucket_for_current_target(page)
    _rebuild_selector_assignment_list(page)


def _load_selector_bucket_for_current_target(page) -> None:
    target_key = selector_current_target_key(page)
    page._selector_assigned_tools = selector_assignments_for_target(
        page._selector_assignments_by_target,
        target_key,
    )


def _store_selector_bucket_for_current_target(page) -> None:
    target_key = selector_current_target_key(page)
    page._selector_assignments_by_target[target_key] = [
        dict(item)
        for item in page._selector_assigned_tools
        if isinstance(item, dict)
    ]


def _rebuild_selector_assignment_list(page) -> None:
    if not hasattr(page, 'selector_assignment_list'):
        return

    current = page.selector_assignment_list.currentRow()
    page.selector_assignment_list.blockSignals(True)
    page.selector_assignment_list.clear()
    for row, assignment in enumerate(page._selector_assigned_tools):
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
        page.selector_assignment_list.addItem(item)

        card = MiniAssignmentCard(
            icon=tool_icon_for_type(str(assignment.get('tool_type') or '').strip()),
            title=title,
            subtitle=comment,
            badges=badges,
            editable=False,
            compact=True,
            parent=page.selector_assignment_list,
        )
        card.setProperty('hasComment', bool(comment))

        # Keep row-host margins consistent with Work Editor list cards.
        row_host = QWidget(page.selector_assignment_list)
        row_host.setAttribute(Qt.WA_StyledBackground, False)
        row_layout = QVBoxLayout(row_host)
        row_layout.setContentsMargins(0, 0, 0, 7)
        row_layout.setSpacing(0)
        row_layout.addWidget(card)
        page.selector_assignment_list.setItemWidget(item, row_host)

    page.selector_assignment_list.blockSignals(False)
    if current >= 0 and current < page.selector_assignment_list.count():
        page.selector_assignment_list.setCurrentRow(current)

    sync_selector_card_selection_states(page)
    update_selector_assignment_buttons(page)


def sync_selector_card_selection_states(page) -> None:
    if not hasattr(page, 'selector_assignment_list'):
        return
    for row in range(page.selector_assignment_list.count()):
        item = page.selector_assignment_list.item(row)
        widget = page.selector_assignment_list.itemWidget(item)
        if isinstance(widget, MiniAssignmentCard):
            widget.set_selected(item.isSelected())
            continue
        card = widget.findChild(MiniAssignmentCard) if isinstance(widget, QWidget) else None
        if isinstance(card, MiniAssignmentCard):
            card.set_selected(item.isSelected())


def update_selector_assignment_buttons(page) -> None:
    if not hasattr(page, 'selector_remove_btn'):
        return
    has_row = bool(hasattr(page, 'selector_assignment_list') and page.selector_assignment_list.currentRow() >= 0)
    has_comment = False
    if has_row and hasattr(page, 'selector_assignment_list'):
        row = page.selector_assignment_list.currentRow()
        item = page.selector_assignment_list.item(row)
        assignment = item.data(Qt.UserRole) if item is not None else None
        has_comment = bool(str((assignment or {}).get('comment') or '').strip()) if isinstance(assignment, dict) else False

    page.selector_remove_btn.setEnabled(has_row)
    page.selector_move_up_btn.setEnabled(
        has_row and page.selector_assignment_list.currentRow() > 0
    )
    page.selector_move_down_btn.setEnabled(
        has_row and page.selector_assignment_list.currentRow() < page.selector_assignment_list.count() - 1
    )
    page.selector_comment_btn.setEnabled(has_row)
    page.selector_delete_comment_btn.setVisible(has_comment)
    page.selector_delete_comment_btn.setEnabled(has_comment)


def sync_selector_assignment_order(page) -> None:
    if not hasattr(page, 'selector_assignment_list'):
        return
    ordered: list[dict] = []
    for row in range(page.selector_assignment_list.count()):
        item = page.selector_assignment_list.item(row)
        assignment = item.data(Qt.UserRole)
        normalized = normalize_selector_tool(page, assignment)
        if normalized is not None:
            ordered.append(normalized)
    page._selector_assigned_tools = ordered
    _store_selector_bucket_for_current_target(page)
    _rebuild_selector_assignment_list(page)


def on_selector_tools_dropped(page, dropped_items: list, insert_row: int) -> None:
    if not isinstance(dropped_items, list):
        return

    existing_keys = {
        selector_tool_key(item)
        for item in page._selector_assigned_tools
        if selector_tool_key(item)
    }
    insert_at = insert_row if isinstance(insert_row, int) and insert_row >= 0 else len(page._selector_assigned_tools)
    insert_at = min(insert_at, len(page._selector_assigned_tools))
    added = False

    for tool in dropped_items:
        normalized = normalize_selector_tool(page, tool)
        if normalized is None:
            continue
        key = selector_tool_key(normalized)
        if not key or key in existing_keys:
            continue
        page._selector_assigned_tools.insert(insert_at, normalized)
        existing_keys.add(key)
        insert_at += 1
        added = True

    if not added:
        return

    _store_selector_bucket_for_current_target(page)
    _rebuild_selector_assignment_list(page)
    if hasattr(page, 'selector_assignment_list') and page.selector_assignment_list.count() > 0:
        page.selector_assignment_list.setCurrentRow(min(insert_at - 1, page.selector_assignment_list.count() - 1))


def remove_selector_assignments_by_drop(page, dropped_items: list) -> None:
    targets: set[str] = set()
    for item in dropped_items or []:
        if not isinstance(item, dict):
            continue
        key = selector_tool_key(normalize_selector_tool(page, item))
        if key:
            targets.add(key)
    if not targets:
        return

    page._selector_assigned_tools = [
        item
        for item in page._selector_assigned_tools
        if selector_tool_key(item) not in targets
    ]
    _store_selector_bucket_for_current_target(page)
    _rebuild_selector_assignment_list(page)


def remove_selector_assignment(page) -> None:
    if not hasattr(page, 'selector_assignment_list'):
        return
    row = page.selector_assignment_list.currentRow()
    if row < 0 or row >= len(page._selector_assigned_tools):
        return
    page._selector_assigned_tools.pop(row)
    _store_selector_bucket_for_current_target(page)
    _rebuild_selector_assignment_list(page)
    if page.selector_assignment_list.count() > 0:
        page.selector_assignment_list.setCurrentRow(min(row, page.selector_assignment_list.count() - 1))


def move_selector_up(page) -> None:
    if not hasattr(page, 'selector_assignment_list'):
        return
    row = page.selector_assignment_list.currentRow()
    if row <= 0 or row >= len(page._selector_assigned_tools):
        return
    page._selector_assigned_tools[row - 1], page._selector_assigned_tools[row] = (
        page._selector_assigned_tools[row],
        page._selector_assigned_tools[row - 1],
    )
    _store_selector_bucket_for_current_target(page)
    _rebuild_selector_assignment_list(page)
    page.selector_assignment_list.setCurrentRow(row - 1)


def move_selector_down(page) -> None:
    if not hasattr(page, 'selector_assignment_list'):
        return
    row = page.selector_assignment_list.currentRow()
    if row < 0 or row >= len(page._selector_assigned_tools) - 1:
        return
    page._selector_assigned_tools[row], page._selector_assigned_tools[row + 1] = (
        page._selector_assigned_tools[row + 1],
        page._selector_assigned_tools[row],
    )
    _store_selector_bucket_for_current_target(page)
    _rebuild_selector_assignment_list(page)
    page.selector_assignment_list.setCurrentRow(row + 1)


def add_selector_comment(page) -> None:
    if not hasattr(page, 'selector_assignment_list'):
        return
    row = page.selector_assignment_list.currentRow()
    if row < 0 or row >= len(page._selector_assigned_tools):
        return
    current = str(page._selector_assigned_tools[row].get('comment') or '').strip()
    text, ok = QInputDialog.getText(
        page,
        page._t('tool_library.selector.add_comment', 'Add Comment'),
        page._t('tool_library.selector.comment_prompt', 'Comment:'),
        text=current,
    )
    if not ok:
        return
    page._selector_assigned_tools[row]['comment'] = text.strip()
    _store_selector_bucket_for_current_target(page)
    _rebuild_selector_assignment_list(page)
    page.selector_assignment_list.setCurrentRow(row)


def delete_selector_comment(page) -> None:
    if not hasattr(page, 'selector_assignment_list'):
        return
    row = page.selector_assignment_list.currentRow()
    if row < 0 or row >= len(page._selector_assigned_tools):
        return
    page._selector_assigned_tools[row].pop('comment', None)
    _store_selector_bucket_for_current_target(page)
    _rebuild_selector_assignment_list(page)
    page.selector_assignment_list.setCurrentRow(row)


def toggle_selector_spindle(page) -> None:
    if not page._selector_active or not hasattr(page, 'selector_spindle_btn'):
        return
    _store_selector_bucket_for_current_target(page)
    target = 'sub' if page.selector_spindle_btn.isChecked() else 'main'
    page._selector_spindle = normalize_selector_spindle(target)
    _load_selector_bucket_for_current_target(page)
    _update_selector_context_header(page)
    _update_selector_assignments_section_title(page)
    _rebuild_selector_assignment_list(page)


def on_selector_toggle_clicked(page) -> None:
    if not page._selector_active:
        return
    if hasattr(page, 'selector_toggle_btn') and page.selector_toggle_btn.isChecked():
        _set_selector_panel_mode(page, 'selector')
        return
    _set_selector_panel_mode(page, 'details')


def on_selector_cancel(page) -> None:
    main_win = page.window()
    if hasattr(main_win, '_clear_selector_session'):
        main_win._clear_selector_session()
    if hasattr(main_win, '_back_to_setup_manager'):
        main_win._back_to_setup_manager()


def on_selector_done(page) -> None:
    main_win = page.window()
    if hasattr(main_win, '_send_selector_selection'):
        main_win._send_selector_selection()


def normalize_selector_tool(page, item: dict | None) -> dict | None:
    """Normalize a tool dict for use in selector context."""
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

    head = str(item.get('tool_head') or item.get('head') or page._selector_head or 'HEAD1').strip().upper()
    if head not in {'HEAD1', 'HEAD2'}:
        head = 'HEAD1'

    spindle = str(item.get('spindle') or item.get('spindle_orientation') or page._selector_spindle or 'main').strip().lower()
    if spindle not in {'main', 'sub'}:
        spindle = 'main'

    normalized = dict(item)
    normalized['tool_id'] = tool_id
    normalized['id'] = tool_id
    normalized['uid'] = uid
    normalized['tool_head'] = head
    normalized['spindle'] = spindle
    normalized['spindle_orientation'] = spindle
    return normalized


def selector_tool_key(item: dict | None) -> str:
    """Generate a unique key for a tool dict in selector context."""
    if not isinstance(item, dict):
        return ''
    tool_id = str(item.get('tool_id') or item.get('id') or '').strip()
    uid = str(item.get('uid') or '').strip()
    head = str(item.get('tool_head') or item.get('head') or '').strip().upper()
    spindle = str(item.get('spindle') or item.get('spindle_orientation') or '').strip().lower()
    if tool_id:
        return f'{head}:{spindle}:{tool_id}'
    if uid:
        return f'{head}:{spindle}:uid:{uid}'
    return ''


def selector_target_key(head: str, spindle: str) -> str:
    """Generate a head:spindle target key."""
    normalized_head = str(head or 'HEAD1').strip().upper()
    if normalized_head not in {'HEAD1', 'HEAD2'}:
        normalized_head = 'HEAD1'
    normalized_spindle = str(spindle or 'main').strip().lower()
    if normalized_spindle not in {'main', 'sub'}:
        normalized_spindle = 'main'
    return f'{normalized_head}:{normalized_spindle}'


def selector_current_target_key(page) -> str:
    """Return the target key for the page's current head and spindle."""
    return selector_target_key(page._selector_head, page._selector_spindle)


def tool_matches_selector_spindle(page, tool: dict) -> bool:
    """Return True if the tool is compatible with the selector spindle constraint."""
    if not page._selector_active:
        return True

    spindle = str(
        tool.get('spindle_orientation')
        or tool.get('spindle')
        or tool.get('spindle_side')
        or ''
    ).strip().lower()
    if not spindle:
        return True
    if page._selector_spindle == 'main':
        return spindle in {'main', 'both', 'all'}
    if page._selector_spindle == 'sub':
        return spindle in {'sub', 'both', 'all'}
    return True


def selected_tools_for_setup_assignment(page) -> list[dict]:
    """Return selected tools normalized for setup assignment."""
    selected_items = page.get_selected_items()
    payload: list[dict] = []
    for item in selected_items:
        normalized = normalize_selector_tool(page, item)
        if normalized is None:
            continue
        payload.append(normalized)
    return payload


def selector_assignment_buckets_for_setup_assignment(page) -> dict[str, list[dict]]:
    """Return a copy of all assignment buckets by target key."""
    return {
        key: [dict(item) for item in items if isinstance(item, dict)]
        for key, items in page._selector_assignments_by_target.items()
    }


def selector_current_target_for_setup_assignment(page) -> dict:
    """Return the current target as a head/spindle dict."""
    return {
        'head': page._selector_head,
        'spindle': page._selector_spindle,
    }


def set_selector_context(
    page,
    active: bool,
    head: str = '',
    spindle: str = '',
    initial_assignments: list[dict] | None = None,
    initial_assignment_buckets: dict[str, list[dict]] | None = None,
) -> None:
    """
    Activate or deactivate selector mode.

    Called by Setup Manager when opening tool selector context.

    Args:
        page: HomePage instance
        active: Selector active flag
        head: Target HEAD ('HEAD1', 'HEAD2')
        spindle: Target spindle ('main', 'sub')
        initial_assignments: Initial tool list
        initial_assignment_buckets: Persisted tool buckets by head/spindle
    """
    was_active = page._selector_active
    page._selector_active = bool(active)
    page._selector_head = _normalize_selector_head_value(str(head or 'HEAD1').strip().upper())
    page._selector_spindle = normalize_selector_spindle(str(spindle or 'main').strip().lower())

    page._selector_assigned_tools = normalize_selector_bucket(
        initial_assignments,
        lambda item: normalize_selector_tool(page, item),
        selector_tool_key,
    )

    page._selector_assignments_by_target = selector_bucket_map(
        initial_assignment_buckets,
        lambda item: normalize_selector_tool(page, item),
        selector_tool_key,
        selector_target_key,
    )

    target_key = selector_current_target_key(page)
    existing = selector_assignments_for_target(
        page._selector_assignments_by_target,
        target_key,
    )
    if existing:
        page._selector_assigned_tools = existing

    page._selector_assignments_by_target[target_key] = [
        dict(item)
        for item in page._selector_assigned_tools
        if isinstance(item, dict)
    ]

    if hasattr(page, 'selector_bottom_bar') and hasattr(page, 'button_bar'):
        page.selector_bottom_bar.setVisible(page._selector_active)
        page.button_bar.setVisible(not page._selector_active)
    if hasattr(page, 'selector_toggle_btn'):
        page.selector_toggle_btn.setVisible(page._selector_active)
    if hasattr(page, 'toggle_details_btn'):
        page.toggle_details_btn.setEnabled(not page._selector_active)

    _update_selector_context_header(page)
    _update_selector_assignments_section_title(page)

    if page._selector_active:
        if not was_active:
            page._selector_saved_details_hidden = page._details_hidden
        _load_selector_bucket_for_current_target(page)
        _rebuild_selector_assignment_list(page)
        _set_selector_panel_mode(page, 'selector')
    else:
        page._details_hidden = page._selector_saved_details_hidden
        page._selector_assigned_tools = []
        page._selector_assignments_by_target = {}
        if hasattr(page, 'selector_assignment_list'):
            page.selector_assignment_list.clear()
        _set_selector_panel_mode(page, 'details')

    page.refresh_list()


def selector_assigned_tools_for_setup_assignment(page) -> list[dict]:
    """Return persisted tools with head/spindle metadata for setup assignment."""
    sync_selector_assignment_order(page)
    target_key = selector_current_target_key(page)
    if page._selector_active:
        page._selector_assignments_by_target[target_key] = [
            dict(item)
            for item in page._selector_assigned_tools
            if isinstance(item, dict)
        ]

    persisted = selector_assignments_for_target(
        page._selector_assignments_by_target,
        target_key,
    )
    return persisted if persisted else selected_tools_for_setup_assignment(page)
