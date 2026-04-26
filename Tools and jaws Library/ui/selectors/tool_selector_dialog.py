from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import QMimeData, QModelIndex, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QDrag, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

try:
    from ...config import ALL_TOOL_TYPES, SHARED_UI_PREFERENCES_PATH, TOOL_ICONS_DIR
except ImportError:
    from config import ALL_TOOL_TYPES, SHARED_UI_PREFERENCES_PATH, TOOL_ICONS_DIR
from shared.ui.helpers.editor_helpers import (
    ResponsiveColumnsHost,
    apply_shared_checkbox_style,
    style_icon_action_button,
    style_move_arrow_button,
    style_panel_action_button,
)
from shared.ui.helpers.icon_loader import icon_from_path
from shared.ui.helpers.page_scaffold_common import apply_catalog_list_view_defaults, build_catalog_list_shell
from shared.ui.helpers.topbar_common import (
    build_detail_header,
    build_details_toggle,
    build_filter_frame,
    build_filter_reset,
    build_preview_toggle,
    build_search_toggle,
    rebuild_filter_row,
)
from shared.ui.theme import apply_top_level_surface_palette
from shared.ui.helpers.window_geometry_memory import restore_window_geometry, save_window_geometry
from shared.ui.selectors import ToolSelectorWidget
from .common import SelectorDialogBase, SelectorWidgetBase
from .detached_preview import (
    load_tool_selector_preview_content,
    sync_tool_selector_detached_preview,
    toggle_tool_selector_preview_window,
)
from .external_preview_ipc import (
    sync_embedded_tool_selector_preview,
    toggle_embedded_tool_selector_preview_window,
)
from .selector_mime import SELECTOR_TOOL_MIME, decode_tool_payload, encode_selector_payload
from .tool_selector_layout import ToolAssignmentDropSection, ToolSelectorLayoutMixin
from .tool_selector_payload import ToolSelectorPayloadMixin
from .tool_selector_state import ToolSelectorStateMixin
from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
from shared.ui.tool_assignment_display import build_badges, compose_title, effective_fields
from ..tool_catalog_delegate import (
    ROLE_TOOL_DATA,
    ROLE_TOOL_ICON,
    ROLE_TOOL_ID,
    ROLE_TOOL_UID,
    ToolCatalogDelegate,
    tool_icon_for_type,
)
from ..home_page_support.retranslate_page import (
    localized_tool_type as _localized_tool_type_impl,
    tool_id_display_value as _tool_id_display_value_impl,
)
from ..home_page_support.selector_widgets import ToolSelectorRemoveDropButton
from ..widgets.common import apply_shared_dropdown_style


class ToolSelectorDialog(
    ToolSelectorLayoutMixin,
    ToolSelectorStateMixin,
    ToolSelectorPayloadMixin,
    SelectorDialogBase,
):
    """Standalone Tool selector hosted in a dialog.

    Owns selector lifecycle (`DONE` / `CANCEL`) without depending on MainWindow page mode.
    """

    def __init__(
        self,
        *,
        tool_service,
        machine_profile,
        translate: Callable[[str, str | None], str],
        selector_head: str,
        selector_spindle: str,
        initial_assignments: list[dict] | None,
        initial_assignment_buckets: dict[str, list[dict]] | None,
        initial_print_pots: bool = False,
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
            window_flags=Qt.Widget if self._embedded_mode else (Qt.Tool | Qt.WindowStaysOnTopHint),
        )
        self.tool_service = tool_service
        self.machine_profile = machine_profile
        self._on_submit = on_submit

        self._current_head = self._normalize_head(selector_head)
        self._current_spindle = self._normalize_spindle(selector_spindle)
        self._print_pots_enabled = bool(initial_print_pots)
        self._assigned_tools: list[dict] = []
        self.current_tool_id: str | None = None
        self.current_tool_uid: int | None = None
        self._assignments_by_target = self._build_initial_buckets(
            initial_assignments,
            initial_assignment_buckets,
        )

        # Detached preview state (toolbar preview toggle parity with HomePage)
        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._close_preview_shortcut = None
        self._measurement_toggle_btn = None
        self._measurement_filter_combo = None
        self._detached_measurements_enabled = True
        self._detached_measurement_filter = None
        self._detached_preview_last_model_key = None
        self._startup_initialized = False

        if not self._embedded_mode and self._use_shared_selector_wrapper():
            self._init_shared_widget_wrapper(
                selector_head=selector_head,
                selector_spindle=selector_spindle,
                initial_assignments=initial_assignments,
                initial_assignment_buckets=initial_assignment_buckets,
            )
            return
        self.setUpdatesEnabled(False)
        try:
            if not self._embedded_mode:
                self.setWindowTitle(self._t('work_editor.selector.tools_dialog_title', 'Työkaluvalitsin'))
                self.setAttribute(Qt.WA_DeleteOnClose, True)
                self.resize(1500, 860)

            inner = self._make_themed_inner_layout()

            self._build_filter_row(inner)
            self._build_content(inner)
            self._build_bottom_bar(inner)
            # Populate catalog and assignment lists while updates are suppressed
            # so the dialog is fully built before the first paint.  Deferring
            # via QTimer caused the empty-state hint to flash briefly in the
            # wrong position before the real content loaded.
            self._run_startup_initialization()
        finally:
            self.setUpdatesEnabled(True)

    def _run_startup_initialization(self) -> None:
        if self._startup_initialized:
            return
        self._startup_initialized = True
        if hasattr(self, 'print_pots_checkbox'):
            self.print_pots_checkbox.blockSignals(True)
            self.print_pots_checkbox.setChecked(bool(getattr(self, '_print_pots_enabled', False)))
            self.print_pots_checkbox.blockSignals(False)
        self._load_current_bucket()
        self._refresh_catalog()
        self._rebuild_assignment_list()
        self._update_context_header()
        self._update_assignment_buttons()

    @staticmethod
    def _use_shared_selector_wrapper() -> bool:
        mode = str(os.environ.get('NTX_SELECTOR_DIALOG_WRAPPER_MODE', 'legacy') or '').strip().lower()
        return mode in {'shared', 'widget', 'wrapper'}

    def _init_shared_widget_wrapper(
        self,
        *,
        selector_head: str,
        selector_spindle: str,
        initial_assignments: list[dict] | None,
        initial_assignment_buckets: dict[str, list[dict]] | None,
    ) -> None:
        if not self._embedded_mode:
            self.setWindowTitle(self._t('work_editor.selector.tools_dialog_title', 'Työkaluvalitsin'))
            self.setAttribute(Qt.WA_DeleteOnClose, True)
            self.resize(1500, 860)
            restore_window_geometry(self, SHARED_UI_PREFERENCES_PATH, 'tool_selector_dialog')

        inner = self._make_themed_inner_layout()

        widget = ToolSelectorWidget(
            translate=self._t,
            selector_head=self._normalize_head(selector_head),
            selector_spindle=self._normalize_spindle(selector_spindle),
            initial_assignments=initial_assignments,
            assignment_buckets_by_target=initial_assignment_buckets,
            parent=self,
        )
        widget.submitted.connect(lambda payload: self._finish_submit(self._on_submit, payload))
        widget.canceled.connect(self._cancel_dialog)
        inner.addWidget(widget, 1)

    # ── Interface required by DetailPanelBuilder ────────────────────────

    def _localized_tool_type(self, tool_type: str) -> str:
        return _localized_tool_type_impl(self, tool_type)

    @staticmethod
    def _tool_id_display_value(value: str) -> str:
        return _tool_id_display_value_impl(value)

    @staticmethod
    def _is_turning_drill_tool_type(tool_type: str) -> bool:
        normalized = str(tool_type or '').strip()
        return normalized in {'Turn Drill', 'Turn Spot Drill', 'Turn Center Drill'}

    def _load_preview_content(self, viewer, stl_path: str | None, *, label: str | None = None) -> bool:
        return load_tool_selector_preview_content(viewer, stl_path, label=label)

    def part_clicked(self, part: dict) -> None:
        # Navigation not applicable in selector context — no-op.
        pass

    # ── Detached preview parity with HomePage toolbar ──────────────────

    def _get_selected_tool(self) -> dict | None:
        index = self.list_view.currentIndex()
        if index.isValid():
            tool = index.data(ROLE_TOOL_DATA)
            if isinstance(tool, dict):
                return tool
        selection_model = self.list_view.selectionModel()
        if selection_model is None:
            return None
        rows = selection_model.selectedRows()
        if not rows:
            return None
        tool = rows[0].data(ROLE_TOOL_DATA)
        return tool if isinstance(tool, dict) else None

    def _sync_detached_preview(self, show_errors: bool = False) -> bool:
        if getattr(self, '_embedded_mode', False):
            return sync_embedded_tool_selector_preview(self, show_errors=show_errors)
        return sync_tool_selector_detached_preview(self, show_errors=show_errors)

    def toggle_preview_window(self) -> None:
        if getattr(self, '_embedded_mode', False):
            toggle_embedded_tool_selector_preview_window(self)
            return
        toggle_tool_selector_preview_window(self)

    def closeEvent(self, event) -> None:
        if not getattr(self, '_embedded_mode', False):
            save_window_geometry(self, SHARED_UI_PREFERENCES_PATH, 'tool_selector_dialog')
        super().closeEvent(event)


class EmbeddedToolCatalogView(QListView):
    """Flash-free catalog view with selector-compatible tool drags."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)

    def startDrag(self, supportedActions):
        selection_model = self.selectionModel()
        indexes = []
        if selection_model is not None:
            indexes = sorted(selection_model.selectedRows(), key=lambda idx: idx.row())
        if not indexes and self.currentIndex().isValid():
            indexes = [self.currentIndex()]
        payload: list[dict] = []
        for index in indexes:
            data = index.data(ROLE_TOOL_DATA)
            if isinstance(data, dict):
                tool_id = str(data.get('id') or data.get('tool_id') or '').strip()
                if tool_id:
                    payload.append(
                        {
                            'tool_id': tool_id,
                            'id': tool_id,
                            'uid': int(data.get('uid') or 0),
                            'tool_type': str(data.get('tool_type') or '').strip(),
                            'description': str(data.get('description') or '').strip(),
                            'default_pot': str(data.get('default_pot') or data.get('pot_number') or '').strip(),
                            'tool_head': str(data.get('tool_head') or '').strip(),
                            'spindle': str(data.get('spindle_orientation') or data.get('spindle') or '').strip(),
                        }
                    )
        if not payload:
            return
        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_TOOL_MIME, payload)
        drag = QDrag(self)
        drag.setMimeData(mime)
        self._apply_catalog_drag_ghost(drag, payload)
        drag.exec(Qt.CopyAction)

    def _apply_catalog_drag_ghost(self, drag: QDrag, payload: list[dict]) -> None:
        from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
        from PySide6.QtCore import QRect, QSize
        first = payload[0]
        tool_id = str(first.get('tool_id') or first.get('id') or '').strip()
        description = str(first.get('description') or '').strip()
        tool_type = str(first.get('tool_type') or '').strip()
        title = f"{tool_id}  -  {description}" if description else tool_id
        W, H = 260, 42
        pixmap = QPixmap(W, H)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(0.75)
        painter.setBrush(QColor('#ffffff'))
        painter.setPen(QColor('#99acbf'))
        painter.drawRoundedRect(1, 1, W - 2, H - 2, 8, 8)
        icon = tool_icon_for_type(tool_type)
        if icon and not icon.isNull():
            icon_pixmap = icon.pixmap(QSize(22, 22))
            if not icon_pixmap.isNull():
                painter.setOpacity(0.75)
                painter.drawPixmap(8, (H - 22) // 2, icon_pixmap)
        painter.setOpacity(1.0)
        font = QFont()
        font.setPointSizeF(10.8)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor('#171a1d'))
        text_x = 38
        painter.drawText(QRect(text_x, 0, W - text_x - 8, H), Qt.AlignVCenter | Qt.TextSingleLine, title)
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())


class EmbeddedToolAssignmentList(QListWidget):
    """Assignment list that supports internal reorder and catalog drops."""

    externalToolsDropped = Signal(list, int)
    orderChanged = Signal()

    def __init__(self, spindle: str, owner, parent=None):
        super().__init__(parent)
        self._spindle = spindle
        self._owner = owner
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setSizeAdjustPolicy(QAbstractItemView.AdjustToContents)

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
            assignment = item.data(Qt.UserRole) if item is not None else None
            if isinstance(assignment, dict):
                payload.append(dict(assignment))
        if not payload:
            return
        from PySide6.QtCore import QMimeData
        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_TOOL_MIME, payload)
        drag = QDrag(self)
        drag.setMimeData(mime)
        preview_item = self.item(indexes[0].row())
        preview_widget = self.itemWidget(preview_item) if preview_item is not None else None
        ghost_applied = False
        if preview_widget is not None:
            from shared.ui.helpers.dragdrop_helpers import build_widget_drag_ghost
            ghost_applied = build_widget_drag_ghost(preview_widget, drag)
        if not ghost_applied:
            from shared.ui.helpers.dragdrop_helpers import build_text_drag_ghost
            label = str(payload[0].get('tool_id') or payload[0].get('id') or '').strip()
            if not label:
                label = f'{len(payload)} tool(s)'
            build_text_drag_ghost(label, drag)
        drag.exec(Qt.MoveAction)

    def _set_external_drag_state(self, active: bool) -> None:
        self.setProperty('catalogDragOver', bool(active))
        self.style().unpolish(self)
        self.style().polish(self)
        self.viewport().update()
        frame = self.parentWidget()
        while frame is not None and not bool(frame.property('selectorAssignmentsFrame')):
            frame = frame.parentWidget()
        if frame is not None:
            frame.setProperty('catalogDragOver', bool(active))
            frame.style().unpolish(frame)
            frame.style().polish(frame)
            frame.update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME):
            if event.source() is not self:
                self._set_external_drag_state(True)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME):
            if event.source() is not self:
                self._set_external_drag_state(True)
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._set_external_drag_state(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME) and event.source() is not self:
            self._set_external_drag_state(False)
            dropped = decode_tool_payload(event.mimeData())
            row = self.indexAt(event.position().toPoint()).row()
            insert_row = self.count() if row < 0 else row
            self.externalToolsDropped.emit(dropped if isinstance(dropped, list) else [], insert_row)
            if dropped:
                event.acceptProposedAction()
                return
        self._set_external_drag_state(False)
        super().dropEvent(event)
        self._owner._sync_assignment_order_for_spindle(self._spindle)
        self.orderChanged.emit()


class EmbeddedToolSelectorWidget(
    ToolSelectorLayoutMixin,
    ToolSelectorStateMixin,
    ToolSelectorPayloadMixin,
    SelectorWidgetBase,
):
    """Work Editor embedded Tool selector built as a QWidget from birth."""

    def __init__(
        self,
        *,
        tool_service,
        machine_profile,
        translate: Callable[[str, str | None], str],
        selector_head: str,
        selector_spindle: str,
        initial_assignments: list[dict] | None,
        initial_assignment_buckets: dict[str, list[dict]] | None,
        initial_print_pots: bool = False,
        on_submit: Callable[[dict], None],
        on_cancel: Callable[[], None],
        parent=None,
    ):
        self._embedded_mode = True
        super().__init__(translate=translate, on_cancel=on_cancel, parent=parent, window_flags=Qt.Widget)
        self.tool_service = tool_service
        self.machine_profile = machine_profile
        self._on_submit = on_submit

        self._current_head = self._normalize_head(selector_head)
        self._current_spindle = self._normalize_spindle(selector_spindle)
        self._print_pots_enabled = bool(initial_print_pots)
        self._assigned_tools: list[dict] = []
        self.current_tool_id: str | None = None
        self.current_tool_uid: int | None = None
        self._assignments_by_target = self._build_initial_buckets(
            initial_assignments,
            initial_assignment_buckets,
        )

        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._close_preview_shortcut = None
        self._measurement_toggle_btn = None
        self._measurement_filter_combo = None
        self._detached_measurements_enabled = True
        self._detached_measurement_filter = None
        self._detached_preview_last_model_key = None

        self._load_current_bucket()
        self._content_materialized = False
        self._materialize_scheduled = False
        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(8, 8, 8, 8)
        self._root_layout.setSpacing(8)
        self.setUpdatesEnabled(False)
        try:
            self._build_embedded_ui()

            if hasattr(self, 'print_pots_checkbox'):
                self.print_pots_checkbox.blockSignals(True)
                self.print_pots_checkbox.setChecked(bool(self._print_pots_enabled))
                self.print_pots_checkbox.blockSignals(False)

            self._refresh_catalog()
            self._rebuild_assignment_list()
            self._update_context_header()
            self._update_assignment_buttons()
            self._content_materialized = True
        finally:
            self.setUpdatesEnabled(True)

    def _build_embedded_ui(self) -> None:
        toolbar, self._filter_layout = build_filter_frame(parent=self)
        toolbar.setProperty('card', False)
        toolbar.setProperty('pageFamilyHost', True)
        apply_top_level_surface_palette(toolbar, role='page_bg')
        self._filter_layout.setContentsMargins(8, 6, 8, 6)

        search_icon = icon_from_path(TOOL_ICONS_DIR / 'search_icon.svg', size=QSize(28, 28))
        self._close_icon = icon_from_path(TOOL_ICONS_DIR / 'close_icon.svg', size=QSize(20, 20))
        self.search_toggle = build_search_toggle(search_icon, self._toggle_search)
        self.toggle_details_btn = build_details_toggle(TOOL_ICONS_DIR, self._toggle_detail_panel)

        self.search_input = QLineEdit(toolbar)
        self.search_input.setPlaceholderText(
            self._t(
                'work_editor.tool_picker.search_placeholder',
                'Hae työkalun ID:tä, nimeä, mittoja, pidintä, inserttiä tai huomioita...',
            )
        )
        self.search_input.textChanged.connect(self._refresh_catalog)
        self.search_input.setVisible(False)

        self.filter_icon = build_filter_reset(TOOL_ICONS_DIR, self._clear_search)

        self.type_filter = QComboBox(toolbar)
        self.type_filter.setObjectName('topTypeFilter')
        self.type_filter.addItem(self._t('tool_library.filter.all', 'All'), 'All')
        for tool_type in ALL_TOOL_TYPES:
            self.type_filter.addItem(self._localized_tool_type(tool_type), tool_type)
        self.type_filter.currentIndexChanged.connect(self._refresh_catalog)

        self.preview_window_btn = build_preview_toggle(
            TOOL_ICONS_DIR,
            self._t('tool_library.preview.toggle', 'Näytä irrotettava 3D-esikatselu'),
            self.toggle_preview_window,
        )
        self.detail_header_container, self.detail_section_label, self.detail_close_btn = build_detail_header(
            self._close_icon,
            self._t('work_editor.selector.assignment.details_title', 'Työkalun tiedot'),
            self._switch_to_selector_panel,
            parent=toolbar,
        )
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
        self._root_layout.addWidget(toolbar, 0)
        self._apply_type_filter_style()

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setObjectName('selectorSplitter')
        splitter.setProperty('pageFamilySplitter', True)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)
        splitter.setAutoFillBackground(False)

        catalog_panel, catalog_layout = build_catalog_list_shell(parent=splitter)
        self.list_view = EmbeddedToolCatalogView(catalog_panel)
        apply_catalog_list_view_defaults(self.list_view)
        self._model = QStandardItemModel(self.list_view)
        self.list_view.setModel(self._model)
        self.list_view.setItemDelegate(ToolCatalogDelegate(parent=self.list_view, view_mode='home', translate=self._t))
        self.list_view.doubleClicked.connect(lambda _index: self._add_selected_tools())
        self.list_view.clicked.connect(self._on_catalog_item_clicked)
        catalog_layout.addWidget(self.list_view, 1)
        splitter.addWidget(catalog_panel)

        right_panel = QWidget(splitter)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self._right_stack = QStackedLayout()
        right_layout.addLayout(self._right_stack)

        self.selector_card = QFrame(right_panel)
        self.selector_card.setProperty('card', True)
        self.selector_card.setProperty('selectorContext', True)
        selector_card_layout = QVBoxLayout(self.selector_card)
        selector_card_layout.setContentsMargins(0, 0, 0, 0)
        selector_card_layout.setSpacing(0)

        selector_scroll = QScrollArea(self.selector_card)
        selector_scroll.setWidgetResizable(True)
        selector_scroll.setFrameShape(QFrame.NoFrame)
        selector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        selector_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        selector_panel = QWidget()
        selector_panel.setProperty('selectorPanel', True)
        selector_panel.setProperty('selectorContext', True)
        selector_panel.setAttribute(Qt.WA_StyledBackground, True)
        selector_panel.setMinimumWidth(0)
        selector_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        selector_scroll.setWidget(selector_panel)
        assignment_layout = QVBoxLayout(selector_panel)
        assignment_layout.setContentsMargins(10, 10, 10, 10)
        assignment_layout.setSpacing(8)
        header = QFrame(selector_panel)
        header.setProperty('selectorInfoHeader', True)
        header.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        header.setMaximumHeight(86)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 10, 14, 8)
        header_layout.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.addStretch(1)
        self.selector_header_title_label = QLabel(self._t('work_editor.selector.tools_dialog_title', 'Tool selector'), header)
        self.selector_header_title_label.setProperty('selectorInfoTitle', True)
        self.selector_header_title_label.setAlignment(Qt.AlignCenter)
        title_row.addWidget(self.selector_header_title_label, 0, Qt.AlignCenter)
        title_row.addStretch(1)
        header_layout.addLayout(title_row)
        badge_row = QHBoxLayout()
        self.selector_spindle_value_label = QLabel('', header)
        self.selector_spindle_value_label.setProperty('toolBadge', True)
        self.selector_head_value_label = QLabel('', header)
        self.selector_head_value_label.setProperty('toolBadge', True)
        badge_row.addWidget(self.selector_spindle_value_label, 0, Qt.AlignLeft)
        badge_row.addStretch(1)
        badge_row.addWidget(self.selector_head_value_label, 0, Qt.AlignRight)
        header_layout.addLayout(badge_row)
        assignment_layout.addWidget(header, 0)

        context_row = QHBoxLayout()
        context_row.addStretch(1)
        self.head_btn = QPushButton(self._t('work_editor.selector.head1', 'HEAD1'), selector_panel)
        self.head_btn.setProperty('panelActionButton', True)
        style_panel_action_button(self.head_btn)
        self.head_btn.setMinimumWidth(280)
        self.head_btn.setMaximumWidth(420)
        self.head_btn.clicked.connect(self._toggle_head)
        context_row.addWidget(self.head_btn, 0)
        context_row.addStretch(1)
        assignment_layout.addLayout(context_row, 0)

        self.assignment_lists = {}
        self.assignment_frames = {}
        self.assignment_title_labels = {}
        self.assignment_hints = {}
        spindle_host = ResponsiveColumnsHost(switch_width=620)
        host_layout = spindle_host.layout()
        if host_layout is not None:
            host_layout.setAlignment(Qt.AlignTop)
        for spindle in ('main', 'sub'):
            lst = EmbeddedToolAssignmentList(spindle, self, selector_panel)
            lst.setObjectName('toolIdsOrderList')
            lst.setProperty('selectorAssignmentList', True)
            lst.setViewportMargins(0, 0, 2, 0)
            lst.setMinimumHeight(56)
            lst.setStyleSheet(
                'QListWidget { background: transparent; border: none; outline: none; padding: 0px; }'
                'QListWidget::item { background-color: transparent; border: none; padding: 0px; margin: 0px; }'
                'QListWidget::item:hover { background-color: transparent; border: none; }'
                'QListWidget::item:selected, QListWidget::item:selected:active, QListWidget::item:selected:!active'
                ' { background-color: transparent; border: none; color: inherit; }'
                'QListWidget::viewport { background: transparent; border: none; }'
            )
            lst.currentRowChanged.connect(lambda _row, sp=spindle: self._remember_active_spindle(sp))
            lst.itemSelectionChanged.connect(lambda sp=spindle: self._on_assignment_selection_changed(sp))
            lst.externalToolsDropped.connect(
                lambda dropped, row, sp=spindle: self._add_tools(dropped, insert_row=row, spindle=sp)
            )
            lst.orderChanged.connect(lambda sp=spindle: self._sync_assignment_order_for_spindle(sp))
            frame = ToolAssignmentDropSection(
                self._selector_spindle_title(spindle),
                lst,
                parent=selector_panel,
            )
            frame.setProperty('toolIdsPanel', True)
            frame.setProperty('selectorAssignmentsFrame', True)
            frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(8, 10, 8, 8)
            frame_layout.setSpacing(4)
            self.assignment_lists[spindle] = lst
            self.assignment_frames[spindle] = frame
            frame_layout.addWidget(lst, 0)
            hint = QLabel(
                self._t(
                    'work_editor.selector.action.drag_hint',
                    'Vedä työkalut tähän kirjastosta. Järjestä ne uudelleen vetämällä listassa.',
                ),
                frame,
            )
            hint.setProperty('detailHint', True)
            hint.setProperty('selectorInlineHint', True)
            hint.setWordWrap(True)
            hint.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            hint.setContentsMargins(2, 0, 2, 0)
            hint.setVisible(False)
            self.assignment_hints[spindle] = hint
            frame_layout.addWidget(hint, 0)
            spindle_host.add_widget(frame, 0)
            if host_layout is not None:
                host_layout.setAlignment(frame, Qt.AlignTop)
        self.assignment_list = self.assignment_lists['main']
        self.assignment_frame = self.assignment_frames['main']
        assignment_layout.addWidget(spindle_host, 0, Qt.AlignTop)

        action_row = QHBoxLayout()
        self.move_up_btn = QPushButton('▲', self.selector_card)
        style_move_arrow_button(self.move_up_btn, '▲', self._t('work_editor.selector.action.move_up', 'Siirrä ylös'))
        self.move_down_btn = QPushButton('▼', self.selector_card)
        style_move_arrow_button(self.move_down_btn, '▼', self._t('work_editor.selector.action.move_down', 'Siirrä alas'))
        self.remove_btn = ToolSelectorRemoveDropButton(self.selector_card)
        style_icon_action_button(self.remove_btn, TOOL_ICONS_DIR / 'delete.svg', self._t('work_editor.selector.action.remove', 'Poista'), danger=True)
        self.remove_btn.toolsDropped.connect(self._remove_by_drop)
        self.edit_btn = QPushButton(self.selector_card)
        style_icon_action_button(self.edit_btn, TOOL_ICONS_DIR / 'edit_arrow.svg', self._t('tool_library.selector.edit_assignment', 'Muokkaa työkaluriviä'))
        self.pot_btn = QPushButton(self.selector_card)
        style_icon_action_button(self.pot_btn, TOOL_ICONS_DIR / 'fine_tune.svg', self._t('tool_library.selector.edit_pots', 'Muokkaa potteja'))
        self.remove_btn.clicked.connect(self._remove_selected)
        self.move_up_btn.clicked.connect(self._move_up)
        self.move_down_btn.clicked.connect(self._move_down)
        self.edit_btn.clicked.connect(self._edit_selected_assignment)
        self.pot_btn.clicked.connect(self._open_pot_editor)
        action_row.addWidget(self.remove_btn)
        action_row.addWidget(self.move_up_btn)
        action_row.addWidget(self.move_down_btn)
        action_row.addWidget(self.edit_btn)
        action_row.addWidget(self.pot_btn)

        self.print_pots_checkbox = QCheckBox(
            self._t('work_editor.tools.print_pot_numbers', 'Print Pot Numbers'),
            self.selector_card,
        )
        apply_shared_checkbox_style(self.print_pots_checkbox, indicator_size=16, min_height=28)
        self.print_pots_checkbox.setVisible(bool(getattr(self.machine_profile, 'supports_print_pots', False)))
        self.print_pots_checkbox.toggled.connect(self._on_print_pots_toggled)
        actions_host = QWidget(self.selector_card)
        actions_host.setObjectName('selectorActionsHost')
        actions_host.setProperty('selectorActionBar', True)
        actions_host.setProperty('hostTransparent', True)
        actions_host_layout = QGridLayout(actions_host)
        actions_host_layout.setContentsMargins(8, 6, 8, 6)
        actions_host_layout.setSpacing(8)
        actions_host_layout.setColumnStretch(0, 1)
        actions_host_layout.setColumnStretch(1, 0)
        actions_host_layout.setColumnStretch(2, 1)
        actions_host_layout.addWidget(self.print_pots_checkbox, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        actions_host_layout.addLayout(action_row, 0, 1, Qt.AlignCenter)
        selector_card_layout.addWidget(selector_scroll, 1)
        selector_card_layout.addWidget(actions_host, 0)
        self._right_stack.addWidget(self.selector_card)

        self.detail_card = QFrame(right_panel)
        self.detail_card.setProperty('selectorAssignmentsFrame', True)
        detail_layout = QVBoxLayout(self.detail_card)
        detail_layout.setContentsMargins(12, 12, 12, 12)
        detail_layout.setSpacing(8)
        self.detail_title = QLabel(self._t('work_editor.selector.assignment.details_title', 'Tool details'), self.detail_card)
        self.detail_title.setProperty('selectorInfoTitle', True)
        self.detail_body = QLabel(self._t('work_editor.selector.detail_empty', 'Select a catalog item to view details.'), self.detail_card)
        self.detail_body.setWordWrap(True)
        close_details = QPushButton(self._t('work_editor.selector.action.back_to_selector', 'Back to selector'), self.detail_card)
        close_details.setProperty('panelActionButton', True)
        close_details.clicked.connect(self._switch_to_selector_panel)
        detail_layout.addWidget(self.detail_title, 0)
        detail_layout.addWidget(self.detail_body, 1, Qt.AlignTop)
        detail_layout.addWidget(close_details, 0)
        self._right_stack.addWidget(self.detail_card)
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 58)
        splitter.setStretchFactor(1, 42)
        self._root_layout.addWidget(splitter, 1)

        bottom_bar = QFrame(self)
        bottom_bar.setProperty('bottomBar', True)
        bottom_row = QHBoxLayout(bottom_bar)
        bottom_row.setContentsMargins(10, 8, 10, 8)
        bottom_row.addStretch(1)
        self.cancel_btn = QPushButton(self._t('work_editor.selector.action.cancel', 'Cancel'), bottom_bar)
        self.done_btn = QPushButton(self._t('work_editor.selector.action.complete', 'Done'), bottom_bar)
        self.cancel_btn.setProperty('panelActionButton', True)
        self.done_btn.setProperty('panelActionButton', True)
        self.done_btn.setProperty('primaryAction', True)
        self.cancel_btn.clicked.connect(self._cancel)
        self.done_btn.clicked.connect(self._send_selector_selection)
        bottom_row.addWidget(self.cancel_btn)
        bottom_row.addWidget(self.done_btn)
        self._root_layout.addWidget(bottom_bar, 0)

    def _remember_active_spindle(self, spindle: str) -> None:
        self._last_active_assignment_spindle = self._normalize_spindle(spindle)
        self._update_assignment_buttons()

    def _active_assignment_spindle(self) -> str:
        remembered = self._normalize_spindle(getattr(self, '_last_active_assignment_spindle', self._current_spindle))
        return remembered if remembered in {'main', 'sub'} else 'main'

    def _assignment_list_for_spindle(self, spindle: str):
        return self.assignment_lists.get(self._normalize_spindle(spindle))

    def _apply_type_filter_style(self) -> None:
        combo = self.type_filter
        arrow_path = (TOOL_ICONS_DIR / 'menu_open.svg').as_posix()
        combo.setStyleSheet(
            'QComboBox {'
            ' background-color: #ffffff;'
            ' border: 1px solid #a0b4c8;'
            ' border-radius: 6px;'
            ' min-height: 0px;'
            ' font-size: 10.5pt;'
            ' font-weight: 400;'
            ' padding: 6px 10px;'
            '}'
            'QComboBox[hovered="true"] {'
            ' background-color: #edf5fc;'
            ' border: 1px solid #c0c4c8;'
            '}'
            'QComboBox::drop-down { width: 28px; border: none; background: transparent; }'
            f'QComboBox::down-arrow {{ image: url("{arrow_path}"); width: 20px; height: 20px; }}'
        )
        apply_shared_dropdown_style(combo)

    def _refresh_catalog(self) -> None:
        if not hasattr(self, 'list_view'):
            return
        search_text = self.search_input.text().strip() if hasattr(self, 'search_input') else ''
        tool_type = self.type_filter.currentData() if hasattr(self, 'type_filter') else 'All'
        tools = self.tool_service.list_tools(
            search_text=search_text,
            tool_type=tool_type or 'All',
            tool_head=self._current_head,
        )
        self._model.clear()
        for tool in tools:
            item = QStandardItem()
            tool_id = str(tool.get('id') or tool.get('tool_id') or '').strip()
            uid = int(tool.get('uid') or 0)
            icon = tool_icon_for_type(str(tool.get('tool_type') or '').strip())
            item.setData(tool_id, ROLE_TOOL_ID)
            item.setData(uid, ROLE_TOOL_UID)
            item.setData(dict(tool), Qt.UserRole)
            item.setData(dict(tool), ROLE_TOOL_DATA)
            item.setData(icon, ROLE_TOOL_ICON)
            self._model.appendRow(item)

    def _rebuild_assignment_list(self, spindle: str | None = None) -> None:
        if not hasattr(self, 'assignment_lists'):
            return
        targets = ('main', 'sub') if spindle is None else (self._normalize_spindle(spindle),)
        for target in targets:
            lst = self.assignment_lists.get(target)
            if lst is None:
                continue
            previous = lst.currentRow()
            lst.blockSignals(True)
            lst.clear()
            for row_index, assignment in enumerate(self._assigned_tools_for_spindle(target)):
                comment = str(assignment.get('comment') or '').strip()
                pot = str(assignment.get('pot') or assignment.get('default_pot') or '').strip()
                effective_tool_id, effective_description, is_edited = effective_fields(assignment)
                item = QListWidgetItem()
                item.setSizeHint(QSize(0, 57 if comment else 49))
                item.setData(Qt.UserRole, dict(assignment))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                lst.addItem(item)

                row_host = QWidget(lst)
                row_host.setAttribute(Qt.WA_StyledBackground, False)
                row_layout = QVBoxLayout(row_host)
                row_layout.setContentsMargins(0, 0, 2, 7)
                row_layout.setSpacing(0)

                card = MiniAssignmentCard(
                    icon=self._assignment_icon_for_spindle(
                        str(assignment.get('tool_type') or '').strip(),
                        target,
                        str(assignment.get('tool_head') or self._current_head),
                    ),
                    title=compose_title(
                        row_index=row_index,
                        tool_id=effective_tool_id,
                        description=effective_description,
                    ),
                    subtitle=comment,
                    badges=build_badges(
                        comment=comment,
                        pot=pot,
                        edited=is_edited,
                        show_pot=bool(getattr(self, '_print_pots_enabled', False)),
                    ),
                    editable=True,
                    compact=True,
                    parent=row_host,
                )
                card.editRequested.connect(lambda sp=target, row=row_index: self._edit_assignment_row(sp, row))
                row_layout.addWidget(card)
                lst.setItemWidget(item, row_host)
            if lst.count():
                lst.setCurrentRow(min(max(previous, 0), lst.count() - 1))
            lst.blockSignals(False)
            self._update_assignment_empty_hint(target)
            self._update_assignment_list_height(target)

    def _sync_assignment_order_for_spindle(self, spindle: str) -> None:
        target = self._normalize_spindle(spindle)
        lst = self.assignment_lists.get(target) if hasattr(self, 'assignment_lists') else None
        if lst is None:
            return
        ordered: list[dict] = []
        for row in range(lst.count()):
            item = lst.item(row)
            normalized = self._normalize_tool(item.data(Qt.UserRole) if item is not None else None)
            if normalized is not None:
                normalized['spindle'] = target
                normalized['spindle_orientation'] = target
                ordered.append(normalized)
        self._assigned_tools_by_spindle[target] = ordered
        self._store_current_bucket()

    def _sync_assignment_order(self) -> None:
        for spindle in ('main', 'sub'):
            self._sync_assignment_order_for_spindle(spindle)

    def _add_selected_tools(self) -> None:
        selected = []
        selection_model = self.list_view.selectionModel()
        indexes = selection_model.selectedRows() if selection_model is not None else []
        if not indexes and self.list_view.currentIndex().isValid():
            indexes = [self.list_view.currentIndex()]
        for index in indexes:
            data = index.data(ROLE_TOOL_DATA)
            if isinstance(data, dict):
                selected.append(data)
        self._add_tools(selected, spindle=self._active_assignment_spindle())

    def _update_context_header(self) -> None:
        if not hasattr(self, 'selector_head_value_label'):
            return
        head_label = (
            self._t('tool_library.selector.head_lower', 'Alarevolveri')
            if self._current_head == 'HEAD2'
            else self._t('tool_library.selector.head_upper', 'Yläkara')
        )
        spindle_label = 'SP2' if self._active_assignment_spindle() == 'sub' else 'SP1'
        self.selector_head_value_label.setText(head_label)
        self.selector_spindle_value_label.setText(spindle_label)
        self.head_btn.setText(head_label)
        for spindle in ('main', 'sub'):
            frame = self.assignment_frames.get(spindle)
            if frame is not None:
                frame.setVisible(not self._has_single_spindle_profile() or spindle == self._current_spindle)
            self._set_assignment_section_title(spindle, self._selector_spindle_title(spindle))

    def _update_assignment_buttons(self) -> None:
        if not hasattr(self, 'remove_btn'):
            return
        self._sync_card_selection_states()
        active_list = self._assignment_list_for_spindle(self._active_assignment_spindle())
        row = active_list.currentRow() if active_list is not None else -1
        has_row = row >= 0
        has_any = any(self._assigned_tools_for_spindle(sp) for sp in ('main', 'sub'))
        self.remove_btn.setEnabled(has_row or has_any)
        self.move_up_btn.setEnabled(has_row and row > 0)
        self.move_down_btn.setEnabled(has_row and active_list is not None and row < active_list.count() - 1)

    def _sync_card_selection_states(self) -> None:
        for assignment_list in getattr(self, 'assignment_lists', {}).values():
            for row in range(assignment_list.count()):
                item = assignment_list.item(row)
                widget = assignment_list.itemWidget(item)
                if isinstance(widget, MiniAssignmentCard):
                    widget.set_selected(item.isSelected())
                elif isinstance(widget, QWidget):
                    card = widget.findChild(MiniAssignmentCard)
                    if isinstance(card, MiniAssignmentCard):
                        card.set_selected(item.isSelected())

    def _on_print_pots_toggled(self, checked: bool) -> None:
        self._print_pots_enabled = bool(checked)
        if self._print_pots_enabled:
            self._populate_default_pots_for_assignments()
            self._store_current_bucket()
        self._rebuild_assignment_list()
        self._update_assignment_buttons()

    def _toggle_search(self, visible: bool) -> None:
        self.search_input.setVisible(bool(visible))
        if not visible:
            self.search_input.clear()
        else:
            self.search_input.setFocus()
        self._rebuild_filter_row()

    def _toggle_detail_panel(self) -> None:
        if self._right_stack.currentWidget() is self.detail_card:
            self._switch_to_selector_panel()
            return
        self._switch_to_detail_panel(self._get_selected_tool())

    def _switch_to_selector_panel(self) -> None:
        self._right_stack.setCurrentWidget(self.selector_card)
        if hasattr(self, 'detail_header_container'):
            self.detail_header_container.setVisible(False)
            self._rebuild_filter_row()

    def _switch_to_detail_panel(self, tool_data: dict | None = None) -> None:
        self._populate_tool_detail(tool_data)
        self._right_stack.setCurrentWidget(self.detail_card)
        if hasattr(self, 'detail_header_container'):
            self.detail_header_container.setVisible(True)
            self._rebuild_filter_row()

    def _rebuild_filter_row(self) -> None:
        if not hasattr(self, '_filter_layout'):
            return
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

    def _populate_tool_detail(self, tool: dict | None) -> None:
        if not isinstance(tool, dict):
            self.detail_body.setText(self._t('work_editor.selector.detail_empty', 'Select a catalog item to view details.'))
            return
        rows = [
            (self._t('tool_library.row.tool_id', 'Tool ID'), str(tool.get('id') or tool.get('tool_id') or '').strip()),
            (self._t('tool_library.row.tool_name', 'Tool name'), str(tool.get('description') or '').strip()),
            (self._t('tool_library.row.tool_type', 'Tool type'), self._localized_tool_type(str(tool.get('tool_type') or '').strip())),
            (self._t('tool_library.field.geom_x', 'Geom X'), str(tool.get('geom_x') or '')),
            (self._t('tool_library.field.geom_z', 'Geom Z'), str(tool.get('geom_z') or '')),
            (self._t('tool_library.field.holder_code', 'Holder'), str(tool.get('holder_code') or '')),
            (self._t('tool_library.field.cutting_code', 'Insert'), str(tool.get('cutting_code') or '')),
            (self._t('tool_library.field.notes', 'Notes'), str(tool.get('notes') or '')),
        ]
        self.detail_body.setText('\n'.join(f'{label}: {value or "-"}' for label, value in rows))

    def _on_catalog_item_clicked(self, index) -> None:
        data = index.data(ROLE_TOOL_DATA)
        if isinstance(data, dict):
            self.current_tool_id = str(data.get('id') or data.get('tool_id') or '').strip() or None
            try:
                self.current_tool_uid = int(data.get('uid') or 0) or None
            except Exception:
                self.current_tool_uid = None
            if self._right_stack.currentWidget() is self.detail_card:
                self._populate_tool_detail(data)
        self._sync_preview_if_open()

    def _toggle_head(self) -> None:
        if self._has_single_head_profile():
            return
        self._store_current_bucket()
        keys = self._profile_head_keys() or ['HEAD1', 'HEAD2']
        idx = keys.index(self._current_head) if self._current_head in keys else 0
        self._current_head = keys[(idx + 1) % len(keys)]
        self._load_current_bucket()
        self._refresh_catalog()
        self._rebuild_assignment_list()
        self._update_context_header()

    def _update_assignment_empty_hint(self, spindle: str) -> None:
        normalized = self._normalize_spindle(spindle)
        hint = getattr(self, 'assignment_hints', {}).get(normalized)
        lst = self._assignment_list_for_spindle(spindle)
        if hint is None or lst is None:
            return
        dismissed = getattr(self, '_assignment_hint_dismissed', {}) or {}
        hint.setVisible(lst.count() == 0 and not bool(dismissed.get(normalized, False)))

    def _update_assignment_list_height(self, spindle: str) -> None:
        from PySide6.QtCore import QTimer
        lst = self._assignment_list_for_spindle(spindle)
        frame = getattr(self, 'assignment_frames', {}).get(self._normalize_spindle(spindle))
        def _apply():
            if lst is None:
                return
            count = lst.count()
            if count <= 0:
                lst.setFixedHeight(56)
            else:
                h = lst.frameWidth() * 2
                for i in range(count):
                    item = lst.item(i)
                    if item is not None:
                        hint_h = item.sizeHint().height()
                        if hint_h > 0:
                            h += hint_h
                            continue
                        widget = lst.itemWidget(item)
                        row_h = (widget.height() if widget is not None and widget.height() > 0
                                 else lst.sizeHintForRow(i))
                        h += max(row_h, 1)
                lst.setFixedHeight(max(h, 56))
            lst.updateGeometry()
            if frame is not None:
                frame.updateGeometry()
        QTimer.singleShot(0, _apply)

    def prepare_for_session(
        self,
        *,
        selector_head: str,
        selector_spindle: str,
        initial_assignments: list[dict] | None,
        initial_assignment_buckets: dict[str, list[dict]] | None,
        initial_print_pots: bool = False,
        on_submit: Callable[[dict], None],
        on_cancel: Callable[[], None],
    ) -> None:
        self.setUpdatesEnabled(False)
        try:
            self._reset_selector_widget_state(on_cancel=on_cancel)
            self._on_submit = on_submit
            self._current_head = self._normalize_head(selector_head)
            self._current_spindle = self._normalize_spindle(selector_spindle)
            self._print_pots_enabled = bool(initial_print_pots)
            self._assigned_tools = []
            self.current_tool_id = None
            self.current_tool_uid = None
            self._assignments_by_target = self._build_initial_buckets(
                initial_assignments,
                initial_assignment_buckets,
            )
            self._assignment_hint_dismissed = {}
            self._load_current_bucket()

            if not self._content_materialized:
                return

            if hasattr(self, 'search_toggle'):
                self.search_toggle.setChecked(False)
            if hasattr(self, 'print_pots_checkbox'):
                self.print_pots_checkbox.blockSignals(True)
                self.print_pots_checkbox.setChecked(bool(self._print_pots_enabled))
                self.print_pots_checkbox.blockSignals(False)
            if hasattr(self, 'search_input'):
                self.search_input.setVisible(False)
                self.search_input.blockSignals(True)
                self.search_input.clear()
                self.search_input.blockSignals(False)
            if hasattr(self, 'type_filter') and self.type_filter.count():
                self._populate_type_filter_items()
                self.type_filter.setCurrentIndex(0)
            if hasattr(self, 'detail_card') and self.detail_card.isVisible():
                self._switch_to_selector_panel()
            if hasattr(self, 'list_view'):
                self.list_view.clearSelection()
                self.list_view.setCurrentIndex(QModelIndex())
            for assignment_list in getattr(self, 'assignment_lists', {}).values():
                assignment_list.clearSelection()
                assignment_list.setCurrentRow(-1)

            self._refresh_catalog()
            self._rebuild_assignment_list()
            self._update_context_header()
            self._update_assignment_buttons()
        finally:
            self.setUpdatesEnabled(True)

    def _localized_tool_type(self, tool_type: str) -> str:
        return _localized_tool_type_impl(self, tool_type)

    @staticmethod
    def _tool_id_display_value(value: str) -> str:
        return _tool_id_display_value_impl(value)

    @staticmethod
    def _is_turning_drill_tool_type(tool_type: str) -> bool:
        normalized = str(tool_type or '').strip()
        return normalized in {'Turn Drill', 'Turn Spot Drill', 'Turn Center Drill'}

    def _load_preview_content(self, viewer, stl_path: str | None, *, label: str | None = None) -> bool:
        return load_tool_selector_preview_content(viewer, stl_path, label=label)

    def part_clicked(self, part: dict) -> None:
        pass

    def _get_selected_tool(self) -> dict | None:
        index = self.list_view.currentIndex()
        if index.isValid():
            tool = index.data(ROLE_TOOL_DATA)
            if isinstance(tool, dict):
                return tool
        selection_model = self.list_view.selectionModel()
        if selection_model is None:
            return None
        rows = selection_model.selectedRows()
        if not rows:
            return None
        tool = rows[0].data(ROLE_TOOL_DATA)
        return tool if isinstance(tool, dict) else None

    def _sync_detached_preview(self, show_errors: bool = False) -> bool:
        if getattr(self, '_embedded_mode', False):
            return sync_embedded_tool_selector_preview(self, show_errors=show_errors)
        return sync_tool_selector_detached_preview(self, show_errors=show_errors)

    def toggle_preview_window(self) -> None:
        if getattr(self, '_embedded_mode', False):
            toggle_embedded_tool_selector_preview_window(self)
            return
        toggle_tool_selector_preview_window(self)

