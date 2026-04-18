from __future__ import annotations

import json
import os
from typing import Callable

from PySide6.QtCore import QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QDrag, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

try:
    from ...config import SHARED_UI_PREFERENCES_PATH, TOOL_ICONS_DIR
except ImportError:
    from config import SHARED_UI_PREFERENCES_PATH, TOOL_ICONS_DIR
from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
from shared.ui.helpers.dragdrop_helpers import (
    build_text_drag_ghost,
    build_widget_drag_ghost,
    clear_selection_on_blank_click,
)
from shared.ui.helpers.editor_helpers import (
    create_titled_section,
    style_icon_action_button,
    style_move_arrow_button,
)
from shared.ui.helpers.icon_loader import icon_from_path
from shared.ui.helpers.page_scaffold_common import (
    apply_catalog_list_view_defaults,
    build_catalog_list_shell,
    build_detail_container_shell,
)
from shared.ui.helpers.topbar_common import (
    build_detail_header,
    build_details_toggle,
    build_filter_frame,
    build_filter_reset,
    build_preview_toggle,
    build_search_toggle,
    rebuild_filter_row,
)
from shared.ui.helpers.window_geometry_memory import restore_window_geometry, save_window_geometry
from shared.ui.selectors import FixtureSelectorWidget
from ..fixture_catalog_delegate import (
    ROLE_FIXTURE_DATA,
    ROLE_FIXTURE_ICON,
    ROLE_FIXTURE_ID,
    FixtureCatalogDelegate,
    fixture_icon_for_row,
)
from ..selector_mime import (
    SELECTOR_JAW_MIME,
    decode_jaw_payload,
    encode_selector_payload,
    jaw_payload_ids,
)
from .common import SelectorDialogBase, build_selector_bottom_bar, selected_rows_or_current
from ..shared.selector_panel_builders import (
    build_selector_actions_row,
    build_selector_card_shell,
    build_selector_hint_label,
    build_selector_info_header,
)


class FixtureCatalogListView(QListView):
    """QListView that starts selector-compatible fixture drags."""

    def startDrag(self, supportedActions):
        selection_model = self.selectionModel()
        if selection_model is None:
            return
        indexes = sorted(selection_model.selectedRows(), key=lambda idx: idx.row())
        if not indexes:
            current = self.currentIndex()
            if current.isValid():
                indexes = [current]
        if not indexes:
            return

        payload: list[dict] = []
        for index in indexes:
            fixture = index.data(ROLE_FIXTURE_DATA)
            if not isinstance(fixture, dict):
                continue
            fixture_id = str(fixture.get('fixture_id') or fixture.get('id') or '').strip()
            if not fixture_id:
                continue
            payload.append(
                {
                    'fixture_id': fixture_id,
                    'id': fixture_id,
                    'jaw_id': fixture_id,
                    'fixture_type': str(fixture.get('fixture_type') or '').strip(),
                    'fixture_kind': str(fixture.get('fixture_kind') or '').strip(),
                }
            )
        if not payload:
            return

        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_JAW_MIME, payload)

        drag = QDrag(self)
        drag.setMimeData(mime)

        first = payload[0]
        ghost_text = str(first.get('fixture_id') or '').strip()
        fixture_type = str(first.get('fixture_type') or '').strip()
        if fixture_type:
            ghost_text = f'{ghost_text} - {fixture_type}'
        if len(payload) > 1:
            ghost_text += f'  (+{len(payload) - 1})'
        build_text_drag_ghost(ghost_text, drag)
        drag.exec(Qt.CopyAction)


class FixtureAssignmentListWidget(QListWidget):
    """Drop target + reorderable list for selector-assigned fixtures."""

    externalFixturesDropped = Signal(list, int)
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

        payload: list[dict] = []
        for index in indexes:
            item = self.item(index.row())
            if item is None:
                continue
            assignment = item.data(Qt.UserRole)
            if isinstance(assignment, dict):
                payload.append(dict(assignment))
        if not payload:
            return

        mime = self.model().mimeData(indexes)
        if mime is None:
            mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_JAW_MIME, payload)

        drag = QDrag(self)
        drag.setMimeData(mime)

        preview_item = self.item(indexes[0].row())
        preview_widget = self.itemWidget(preview_item) if preview_item is not None else None
        ghost_applied = False
        if preview_widget is not None:
            ghost_applied = build_widget_drag_ghost(preview_widget, drag)
        if not ghost_applied:
            first_payload = payload[0] if payload else {}
            label = str(first_payload.get('fixture_id') or first_payload.get('id') or '').strip()
            if not label:
                label = f"{len(payload)} fixture(s)"
            build_text_drag_ghost(label, drag)

        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_JAW_MIME):
            event.acceptProposedAction()
            return
        if event.source() is self:
            super().dragEnterEvent(event)
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_JAW_MIME):
            event.acceptProposedAction()
            return
        if event.source() is self:
            super().dragMoveEvent(event)
            return
        event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_JAW_MIME) and event.source() is not self:
            dropped = decode_jaw_payload(event.mimeData())
            point = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            row = self.indexAt(point).row()
            if row < 0:
                row = self.count()
            self.externalFixturesDropped.emit(dropped if isinstance(dropped, list) else [], row)
            event.acceptProposedAction()
            return

        super().dropEvent(event)
        if event.source() is self:
            self.orderChanged.emit()

    def mousePressEvent(self, event):
        clear_selection_on_blank_click(self, event)
        super().mousePressEvent(event)


class FixtureSelectorRemoveDropButton(QPushButton):
    """Remove button that accepts dropped selector fixtures."""

    fixturesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if jaw_payload_ids(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if jaw_payload_ids(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        dropped = decode_jaw_payload(event.mimeData())
        if not dropped:
            event.ignore()
            return
        self.fixturesDropped.emit(dropped)
        event.acceptProposedAction()


class FixtureSelectorDialog(SelectorDialogBase):
    """Standalone fixture selector with ToolSelector-identical UI shell."""

    def __init__(
        self,
        *,
        fixture_service,
        translate: Callable[[str, str | None], str],
        initial_assignments: list[dict] | None,
        initial_assignment_buckets: dict[str, list[dict]] | None = None,
        initial_target_key: str = '',
        on_submit: Callable[[dict], None],
        on_cancel: Callable[[], None],
        parent=None,
        embedded_mode: bool = False,
    ):
        self._embedded_mode = bool(embedded_mode)
        super().__init__(
            translate=translate,
            on_cancel=on_cancel,
            parent=parent,
            window_flags=Qt.Widget if self._embedded_mode else Qt.WindowFlags(),
        )
        self.fixture_service = fixture_service
        self._on_submit = on_submit

        if not self._embedded_mode and self._use_shared_selector_wrapper():
            self._init_shared_widget_wrapper(
                initial_assignments=initial_assignments,
                initial_assignment_buckets=initial_assignment_buckets,
                initial_target_key=initial_target_key,
            )
            return

        self._selected_items: list[dict] = []
        self._selected_ids: set[str] = set()
        self._assignment_buckets_by_target: dict[str, list[dict]] = {}

        if isinstance(initial_assignment_buckets, dict):
            for raw_key, raw_items in initial_assignment_buckets.items():
                target_key = str(raw_key or '').strip()
                if not target_key or not isinstance(raw_items, list):
                    continue
                bucket_items: list[dict] = []
                bucket_seen: set[str] = set()
                for item in raw_items:
                    normalized = self._normalize_fixture(item)
                    if normalized is None:
                        continue
                    fixture_key = self._fixture_key(normalized)
                    if not fixture_key or fixture_key in bucket_seen:
                        continue
                    bucket_seen.add(fixture_key)
                    bucket_items.append(normalized)
                self._assignment_buckets_by_target[target_key] = bucket_items

        if not self._assignment_buckets_by_target:
            fallback_items: list[dict] = []
            fallback_seen: set[str] = set()
            for item in initial_assignments or []:
                normalized = self._normalize_fixture(item)
                if normalized is None:
                    continue
                fixture_key = self._fixture_key(normalized)
                if not fixture_key or fixture_key in fallback_seen:
                    continue
                fallback_seen.add(fixture_key)
                fallback_items.append(normalized)
            self._assignment_buckets_by_target['OP10'] = fallback_items

        self._target_keys = list(self._assignment_buckets_by_target.keys())
        resolved_target = str(initial_target_key or '').strip()
        if resolved_target not in self._target_keys:
            resolved_target = self._target_keys[0] if self._target_keys else ''
        self._active_target_key = resolved_target

        self._selected_items = [
            dict(item)
            for item in self._assignment_buckets_by_target.get(self._active_target_key, [])
            if isinstance(item, dict)
        ]
        self._selected_ids = {self._fixture_key(item) for item in self._selected_items if self._fixture_key(item)}

        self.setUpdatesEnabled(False)
        try:
            if not self._embedded_mode:
                self.setWindowTitle(self._t('fixture_library.selector.header_title', 'Fixture Selector'))
                self.setAttribute(Qt.WA_DeleteOnClose, True)
                self.resize(1180, 720)
                restore_window_geometry(self, SHARED_UI_PREFERENCES_PATH, 'fixture_selector_dialog')

            root = QVBoxLayout(self)
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(8)

            self._build_toolbar(root)
            self._build_content(root)
            self._build_bottom_bar(root)

            self._switch_to_selector_panel()
            self._refresh_catalog()
            self._rebuild_assignment_list()
            self._update_assignment_buttons()
        finally:
            self.setUpdatesEnabled(True)

    @staticmethod
    def _use_shared_selector_wrapper() -> bool:
        mode = str(os.environ.get('NTX_SELECTOR_DIALOG_WRAPPER_MODE', 'legacy') or '').strip().lower()
        return mode in {'shared', 'widget', 'wrapper'}

    def _init_shared_widget_wrapper(
        self,
        *,
        initial_assignments: list[dict] | None,
        initial_assignment_buckets: dict[str, list[dict]] | None,
        initial_target_key: str,
    ) -> None:
        if not self._embedded_mode:
            self.setWindowTitle(self._t('fixture_library.selector.header_title', 'Fixture Selector'))
            self.setAttribute(Qt.WA_DeleteOnClose, True)
            self.resize(1180, 720)
            restore_window_geometry(self, SHARED_UI_PREFERENCES_PATH, 'fixture_selector_dialog')

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        widget = FixtureSelectorWidget(
            translate=self._t,
            target_key=str(initial_target_key or '').strip(),
            initial_assignments=initial_assignments,
            assignment_buckets_by_target=initial_assignment_buckets,
            parent=self,
        )
        widget.submitted.connect(lambda payload: self._finish_submit(self._on_submit, payload))
        widget.canceled.connect(self._cancel_dialog)
        root.addWidget(widget, 1)

    def closeEvent(self, event) -> None:
        if not getattr(self, '_embedded_mode', False):
            save_window_geometry(self, SHARED_UI_PREFERENCES_PATH, 'fixture_selector_dialog')
        super().closeEvent(event)

    def _build_toolbar(self, root: QVBoxLayout) -> None:
        frame, self._filter_layout = build_filter_frame(parent=self)
        frame.setObjectName('')
        self._filter_layout.setContentsMargins(8, 6, 8, 6)

        search_icon = icon_from_path(TOOL_ICONS_DIR / 'search_icon.svg', size=QSize(28, 28))
        close_icon = icon_from_path(TOOL_ICONS_DIR / 'close_icon.svg', size=QSize(20, 20))

        self.search_toggle = build_search_toggle(search_icon, self._toggle_search)
        self.toggle_details_btn = build_details_toggle(TOOL_ICONS_DIR, self._toggle_detail_panel)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            self._t(
                'fixture_library.search.placeholder',
                'Search fixture ID, type, kind, diameter, work or notes',
            )
        )
        self.search_input.textChanged.connect(self._refresh_catalog)
        self.search_input.setVisible(False)

        self.filter_icon = build_filter_reset(TOOL_ICONS_DIR, self._clear_search)

        self.view_filter = QComboBox()
        self.view_filter.setObjectName('topTypeFilter')
        self.view_filter.addItem(self._t('tool_library.nav.all_fixtures', 'All Fixtures'), 'all')
        self.view_filter.addItem(self._t('tool_library.nav.fixture_parts', 'Parts'), 'parts')
        self.view_filter.addItem(self._t('tool_library.nav.fixture_assemblies', 'Assemblies'), 'assemblies')
        self.view_filter.currentIndexChanged.connect(self._refresh_catalog)

        self.target_filter = QComboBox()
        self.target_filter.setObjectName('topTypeFilter')
        for target_key in self._target_keys:
            self.target_filter.addItem(target_key, target_key)
        target_index = self.target_filter.findData(self._active_target_key)
        if target_index >= 0:
            self.target_filter.setCurrentIndex(target_index)
        self.target_filter.currentIndexChanged.connect(self._on_target_changed)

        self.preview_window_btn = build_preview_toggle(
            TOOL_ICONS_DIR,
            self._t('tool_library.preview.toggle', 'Toggle detached 3D preview'),
            self.toggle_preview_window,
        )
        self.preview_window_btn.setVisible(True)

        self.detail_header_container, self.detail_section_label, self.detail_close_btn = build_detail_header(
            close_icon,
            self._t('fixture_library.section.fixture_details', 'Fixture details'),
            self._switch_to_selector_panel,
            parent=frame,
        )
        self.detail_header_container.setVisible(False)

        rebuild_filter_row(
            self._filter_layout,
            self.search_toggle,
            self.toggle_details_btn,
            self.search_input,
            self.filter_icon,
                [self.view_filter, self.target_filter],  # Updated to include target filter
            self.preview_window_btn,
            self.detail_header_container,
        )
        root.addWidget(frame, 0)

    def _build_content(self, root: QVBoxLayout) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        list_card, list_layout = build_catalog_list_shell(parent=splitter)
        self.list_view = FixtureCatalogListView()
        apply_catalog_list_view_defaults(self.list_view)
        self._model = QStandardItemModel(self.list_view)
        self.list_view.setModel(self._model)
        self.list_view.setItemDelegate(FixtureCatalogDelegate(parent=self.list_view, translate=self._t))
        self.list_view.doubleClicked.connect(self._on_catalog_double_clicked)
        self.list_view.clicked.connect(self._on_catalog_item_clicked)
        list_layout.addWidget(self.list_view, 1)
        splitter.addWidget(list_card)

        right_panel = QWidget(splitter)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._build_selector_card(parent=right_panel), 1)
        right_layout.addWidget(self._build_detail_card(parent=right_panel), 1)
        splitter.addWidget(right_panel)

        splitter.setSizes([int(self.width() * 0.58), int(self.width() * 0.42)])
        root.addWidget(splitter, 1)

    def _build_detail_card(self, parent: QWidget | None = None) -> QWidget:
        (
            detail_container,
            _outer_layout,
            _card,
            _scroll,
            _panel,
            self.detail_layout,
        ) = build_detail_container_shell(min_width=300, parent=parent)
        self.detail_card = detail_container
        self.detail_card.setVisible(False)
        return self.detail_card

    def _build_selector_card(self, parent: QWidget | None = None) -> QWidget:
        selector_card, selector_scroll, selector_panel, selector_layout = build_selector_card_shell(
            spacing=8,
            parent=parent,
        )
        selector_card.setVisible(True)
        self.selector_card = selector_card
        selector_card_layout = QVBoxLayout(selector_card)
        selector_card_layout.setContentsMargins(0, 0, 0, 0)
        selector_card_layout.setSpacing(0)

        (
            self.selector_info_header,
            self.selector_header_title_label,
            self.selector_spindle_value_label,
            self.selector_head_value_label,
        ) = build_selector_info_header(
            title_text=self._t('fixture_library.selector.header_title', 'Fixture Selector'),
            left_badge_text='',
            right_badge_text='',
            fixed_height_policy=True,
            parent=selector_panel,
        )
        self.selector_spindle_value_label.setVisible(False)
        self.selector_head_value_label.setVisible(False)
        selector_layout.addWidget(self.selector_info_header, 0)

        hint = build_selector_hint_label(
            text=self._t(
                'fixture_library.selector.hint',
                'Drag fixtures from the catalog to this list and reorder them by dragging.',
            ),
            multiline=False,
            parent=selector_panel,
        )
        selector_layout.addWidget(hint, 0)

        self.assignment_list = FixtureAssignmentListWidget()
        self.assignment_list.setObjectName('toolIdsOrderList')
        self.assignment_list.setStyleSheet(
            '#toolIdsOrderList { background: transparent; border: none; }'
            '#toolIdsOrderList::viewport { background: transparent; border: none; }'
            '#toolIdsOrderList::item { background: transparent; border: none; }'
        )
        self.assignment_list.externalFixturesDropped.connect(self._on_fixtures_dropped)
        self.assignment_list.orderChanged.connect(self._sync_assignment_order)
        self.assignment_list.itemSelectionChanged.connect(self._sync_card_selection_states)
        self.assignment_list.itemSelectionChanged.connect(self._update_assignment_buttons)

        self.assignment_frame = create_titled_section(
            self._t('fixture_library.selector.selection_title', 'Selected fixtures'),
            parent=selector_panel,
        )
        self.assignment_frame.setProperty('selectorAssignmentsFrame', True)
        self.assignment_frame.setProperty('toolIdsPanel', True)
        self.assignment_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        assignment_layout = QVBoxLayout(self.assignment_frame)
        assignment_layout.setContentsMargins(8, 6, 8, 8)
        assignment_layout.setSpacing(0)
        assignment_layout.addWidget(self.assignment_list, 1)
        selector_layout.addWidget(self.assignment_frame, 1)

        actions = build_selector_actions_row(spacing=4)

        self.move_up_btn = QPushButton('▲')
        style_move_arrow_button(self.move_up_btn, '▲', self._t('tool_library.selector.move_up', 'Move Up'))
        self.move_up_btn.clicked.connect(self._move_up)
        actions.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton('▼')
        style_move_arrow_button(self.move_down_btn, '▼', self._t('tool_library.selector.move_down', 'Move Down'))
        self.move_down_btn.clicked.connect(self._move_down)
        actions.addWidget(self.move_down_btn)

        self.remove_btn = FixtureSelectorRemoveDropButton()
        style_icon_action_button(self.remove_btn, TOOL_ICONS_DIR / 'delete.svg', self._t('tool_library.selector.remove', 'Remove'), danger=True)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.remove_btn.fixturesDropped.connect(self._remove_by_drop)
        actions.addWidget(self.remove_btn)

        self.comment_btn = QPushButton()
        style_icon_action_button(self.comment_btn, TOOL_ICONS_DIR / 'comment.svg', self._t('tool_library.selector.add_comment', 'Add Comment'))
        self.comment_btn.clicked.connect(self._add_comment)
        actions.addWidget(self.comment_btn)

        self.delete_comment_btn = QPushButton()
        style_icon_action_button(self.delete_comment_btn, TOOL_ICONS_DIR / 'comment_disable.svg', self._t('tool_library.selector.delete_comment', 'Delete Comment'))
        self.delete_comment_btn.clicked.connect(self._delete_comment)
        actions.addWidget(self.delete_comment_btn)

        actions.addStretch(1)
        selector_layout.addLayout(actions)

        selector_card_layout.addWidget(selector_scroll, 1)
        return selector_card

    def _build_bottom_bar(self, root: QVBoxLayout) -> None:
        build_selector_bottom_bar(
            root,
            translate=self._translate,
            on_cancel=self._cancel,
            on_done=self._send_selector_selection,
            parent=self,
        )

    def _toggle_search(self) -> None:
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
            [self.view_filter, self.target_filter],
            self.preview_window_btn,
            self.detail_header_container,
        )
        if visible:
            self.search_input.setFocus()

    def _clear_search(self) -> None:
        self.search_input.clear()
        if self.view_filter.count():
            self.view_filter.setCurrentIndex(0)

    def _toggle_detail_panel(self) -> None:
        if self.detail_card.isVisible():
            self._switch_to_selector_panel()
            return
        indexes = selected_rows_or_current(self.list_view)
        fixture_data = indexes[0].data(ROLE_FIXTURE_DATA) if indexes else None
        self._switch_to_detail_panel(fixture_data if isinstance(fixture_data, dict) else None)

    def _switch_to_detail_panel(self, fixture_data: dict | None = None) -> None:
        self.selector_card.setVisible(False)
        self.detail_card.setVisible(True)
        self.detail_header_container.setVisible(True)
        rebuild_filter_row(
            self._filter_layout,
            self.search_toggle,
            self.toggle_details_btn,
            self.search_input,
            self.filter_icon,
            [self.view_filter, self.target_filter],
            self.preview_window_btn,
            self.detail_header_container,
        )
        self.toggle_details_btn.setChecked(True)
        self._render_detail_panel(fixture_data)

    def _switch_to_selector_panel(self) -> None:
        self.detail_card.setVisible(False)
        self.selector_card.setVisible(True)
        self.detail_header_container.setVisible(False)
        rebuild_filter_row(
            self._filter_layout,
            self.search_toggle,
            self.toggle_details_btn,
            self.search_input,
            self.filter_icon,
                [self.view_filter, self.target_filter],  # Updated to include target filter
            self.preview_window_btn,
            self.detail_header_container,
        )
        self.toggle_details_btn.setChecked(False)

    def _render_detail_panel(self, fixture: dict | None) -> None:
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        card = QFrame()
        card.setProperty('card', True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        if not isinstance(fixture, dict):
            empty = QLabel(self._t('fixture_library.message.select_fixture_for_details', 'Select a fixture to view details.'))
            empty.setProperty('detailHint', True)
            empty.setWordWrap(True)
            card_layout.addWidget(empty)
        else:
            for key, fallback in [
                ('fixture_id', 'Fixture ID'),
                ('fixture_type', 'Fixture type'),
                ('fixture_kind', 'Fixture kind'),
            ]:
                row = QHBoxLayout()
                label = QLabel(self._t(f'fixture_library.field.{key}', fallback))
                label.setProperty('detailFieldKey', True)
                value = QLabel(str(fixture.get(key) or '-'))
                row.addWidget(label)
                row.addWidget(value, 1)
                card_layout.addLayout(row)

        card_layout.addStretch(1)
        self.detail_layout.addWidget(card)
        self.detail_layout.addStretch(1)

    def toggle_preview_window(self) -> None:
        self.preview_window_btn.setChecked(False)

    @staticmethod
    def _normalize_part_ids(raw) -> list[str]:
        if isinstance(raw, list):
            values = raw
        else:
            text = str(raw or '').strip()
            if not text:
                values = []
            else:
                try:
                    parsed = json.loads(text)
                except Exception:
                    parsed = []
                values = parsed if isinstance(parsed, list) else []
        result: list[str] = []
        for item in values:
            value = str(item or '').strip()
            if value and value not in result:
                result.append(value)
        return result

    def _normalize_fixture(self, item: dict | None) -> dict | None:
        if not isinstance(item, dict):
            return None
        fixture_id = str(item.get('fixture_id') or item.get('id') or item.get('jaw_id') or '').strip()
        if not fixture_id:
            return None
        return {
            'fixture_id': fixture_id,
            'id': fixture_id,
            'jaw_id': fixture_id,
            'fixture_type': str(item.get('fixture_type') or item.get('jaw_type') or '').strip(),
            'fixture_kind': str(item.get('fixture_kind') or '').strip(),
            'assembly_part_ids': self._normalize_part_ids(item.get('assembly_part_ids')),
            'comment': str(item.get('comment') or '').strip(),
        }

    @staticmethod
    def _fixture_key(item: dict | None) -> str:
        if not isinstance(item, dict):
            return ''
        return str(item.get('fixture_id') or item.get('id') or '').strip()

    def _refresh_catalog(self) -> None:
        search_text = self.search_input.text().strip()
        view_mode = str(self.view_filter.currentData() or 'all')
        fixtures = self.fixture_service.list_fixtures(search_text=search_text, view_mode=view_mode)

        self._model.clear()
        for fixture in fixtures:
            normalized = self._normalize_fixture(fixture)
            if normalized is None:
                continue
            # Keep extra fields for detail panel rendering.
            normalized['notes'] = str(fixture.get('notes') or '').strip()
            item = QStandardItem()
            item.setData(normalized['fixture_id'], ROLE_FIXTURE_ID)
            item.setData(dict(normalized), ROLE_FIXTURE_DATA)
            item.setData(fixture_icon_for_row(normalized), ROLE_FIXTURE_ICON)
            self._model.appendRow(item)

    def _rebuild_assignment_list(self) -> None:
        current_row = self.assignment_list.currentRow()
        self.assignment_list.blockSignals(True)
        self.assignment_list.clear()

        for row, assignment in enumerate(self._selected_items):
            fixture_id = str(assignment.get('fixture_id') or '').strip()
            fixture_type = str(assignment.get('fixture_type') or '').strip()
            fixture_kind = str(assignment.get('fixture_kind') or '').strip()
            comment = str(assignment.get('comment') or '').strip()

            title = f'{row + 1}. {fixture_id}' if fixture_id else f'{row + 1}.'
            if fixture_type:
                title = f'{title}  -  {fixture_type}'

            badges: list[str] = []
            if fixture_kind:
                badges.append(f'[{fixture_kind}]')
            if comment:
                badges.append('C')

            item = QListWidgetItem()
            item.setData(Qt.UserRole, dict(assignment))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            item.setSizeHint(QSize(0, 50 if comment else 42))
            self.assignment_list.addItem(item)

            card = MiniAssignmentCard(
                icon=fixture_icon_for_row(assignment),
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
            card = widget.findChild(MiniAssignmentCard) if isinstance(widget, QWidget) else None
            if isinstance(card, MiniAssignmentCard):
                card.set_selected(item.isSelected())

    def _update_assignment_buttons(self) -> None:
        has_row = self.assignment_list.currentRow() >= 0
        has_assignments = bool(self._selected_items)
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
            normalized = self._normalize_fixture(assignment)
            if normalized is not None:
                normalized['comment'] = str((assignment or {}).get('comment') or '').strip() if isinstance(assignment, dict) else ''
                ordered.append(normalized)
        self._selected_items = ordered
        self._selected_ids = {self._fixture_key(item) for item in self._selected_items if self._fixture_key(item)}
        self._rebuild_assignment_list()

    def _add_fixtures(self, dropped_items: list[dict], insert_row: int | None = None) -> None:
        existing = {self._fixture_key(item) for item in self._selected_items if self._fixture_key(item)}
        insert_at = len(self._selected_items) if insert_row is None else max(0, min(insert_row, len(self._selected_items)))
        added = False
        for fixture in dropped_items or []:
            normalized = self._normalize_fixture(fixture)
            if normalized is None:
                continue
            key = self._fixture_key(normalized)
            if not key or key in existing:
                continue
            self._selected_items.insert(insert_at, normalized)
            existing.add(key)
            insert_at += 1
            added = True
        if not added:
            return
        self._selected_ids = existing
        if self._active_target_key:
            self._assignment_buckets_by_target[self._active_target_key] = [dict(item) for item in self._selected_items]
        self._rebuild_assignment_list()
        if self.assignment_list.count() > 0:
            self.assignment_list.setCurrentRow(min(insert_at - 1, self.assignment_list.count() - 1))

    def _remove_selected(self) -> None:
        row = self.assignment_list.currentRow()
        if row < 0 or row >= len(self._selected_items):
            if self._selected_items:
                self._selected_items.pop()
                self._selected_ids = {self._fixture_key(item) for item in self._selected_items if self._fixture_key(item)}
                self._rebuild_assignment_list()
            return
        self._selected_items.pop(row)
        self._selected_ids = {self._fixture_key(item) for item in self._selected_items if self._fixture_key(item)}
        if self._active_target_key:
            self._assignment_buckets_by_target[self._active_target_key] = [dict(item) for item in self._selected_items]
        self._rebuild_assignment_list()
        if self.assignment_list.count() > 0:
            self.assignment_list.setCurrentRow(min(row, self.assignment_list.count() - 1))

    def _remove_by_drop(self, dropped_items: list[dict]) -> None:
        keys = {
            self._fixture_key(self._normalize_fixture(item))
            for item in (dropped_items or [])
            if isinstance(item, dict)
        }
        keys = {k for k in keys if k}
        if not keys:
            return
        self._selected_items = [item for item in self._selected_items if self._fixture_key(item) not in keys]
        self._selected_ids = {self._fixture_key(item) for item in self._selected_items if self._fixture_key(item)}
        if self._active_target_key:
            self._assignment_buckets_by_target[self._active_target_key] = [dict(item) for item in self._selected_items]
        self._rebuild_assignment_list()

    def _move_up(self) -> None:
        row = self.assignment_list.currentRow()
        if row <= 0 or row >= len(self._selected_items):
            return
        self._selected_items[row - 1], self._selected_items[row] = self._selected_items[row], self._selected_items[row - 1]
        if self._active_target_key:
            self._assignment_buckets_by_target[self._active_target_key] = [dict(item) for item in self._selected_items]
        self._rebuild_assignment_list()
        self.assignment_list.setCurrentRow(row - 1)

    def _move_down(self) -> None:
        row = self.assignment_list.currentRow()
        if row < 0 or row >= len(self._selected_items) - 1:
            return
        self._selected_items[row], self._selected_items[row + 1] = self._selected_items[row + 1], self._selected_items[row]
        if self._active_target_key:
            self._assignment_buckets_by_target[self._active_target_key] = [dict(item) for item in self._selected_items]
        self._rebuild_assignment_list()
        self.assignment_list.setCurrentRow(row + 1)

    def _add_comment(self) -> None:
        row = self.assignment_list.currentRow()
        if row < 0 or row >= len(self._selected_items):
            return
        current = str(self._selected_items[row].get('comment') or '').strip()
        text, ok = QInputDialog.getText(
            self,
            self._t('tool_library.selector.add_comment', 'Add Comment'),
            self._t('tool_library.selector.comment_prompt', 'Comment:'),
            text=current,
        )
        if not ok:
            return
        self._selected_items[row]['comment'] = text.strip()
        if self._active_target_key:
            self._assignment_buckets_by_target[self._active_target_key] = [dict(item) for item in self._selected_items]
        self._rebuild_assignment_list()
        self.assignment_list.setCurrentRow(row)

    def _delete_comment(self) -> None:
        row = self.assignment_list.currentRow()
        if row < 0 or row >= len(self._selected_items):
            return
        self._selected_items[row].pop('comment', None)
        if self._active_target_key:
            self._assignment_buckets_by_target[self._active_target_key] = [dict(item) for item in self._selected_items]
        self._rebuild_assignment_list()
        self.assignment_list.setCurrentRow(row)

    def _on_target_changed(self, _index: int) -> None:
        if self._active_target_key:
            self._assignment_buckets_by_target[self._active_target_key] = [dict(item) for item in self._selected_items]
        self._active_target_key = str(self.target_filter.currentData() or '').strip()
        self._selected_items = [
            dict(item)
            for item in self._assignment_buckets_by_target.get(self._active_target_key, [])
            if isinstance(item, dict)
        ]
        self._selected_ids = {self._fixture_key(item) for item in self._selected_items if self._fixture_key(item)}
        self._rebuild_assignment_list()

    def _on_catalog_item_clicked(self, index) -> None:
        if not self.detail_card.isVisible() or not index.isValid():
            return
        fixture = index.data(ROLE_FIXTURE_DATA)
        self._render_detail_panel(fixture if isinstance(fixture, dict) else None)

    def _on_catalog_double_clicked(self, _index) -> None:
        indexes = selected_rows_or_current(self.list_view)
        if not indexes:
            return
        dropped_items: list[dict] = []
        for index in indexes:
            fixture = index.data(ROLE_FIXTURE_DATA)
            if isinstance(fixture, dict):
                dropped_items.append(dict(fixture))
        self._add_fixtures(dropped_items)

    def _on_fixtures_dropped(self, dropped_items: list, insert_row: int) -> None:
        self._add_fixtures(dropped_items if isinstance(dropped_items, list) else [], insert_row)

    def _build_selector_payload(self) -> dict:
        if self._active_target_key:
            self._assignment_buckets_by_target[self._active_target_key] = [dict(item) for item in self._selected_items]
        return {
            'kind': 'fixtures',
            'selected_items': [dict(item) for item in self._selected_items],
            'target_key': self._active_target_key,
            'assignment_buckets_by_target': {
                str(key): [dict(item) for item in value if isinstance(item, dict)]
                for key, value in self._assignment_buckets_by_target.items()
                if isinstance(value, list)
            },
        }

    def _cancel(self) -> None:
        self._cancel_dialog()

    def _send_selector_selection(self) -> None:
        payload = self._build_selector_payload()
        self._finish_submit(self._on_submit, payload)
