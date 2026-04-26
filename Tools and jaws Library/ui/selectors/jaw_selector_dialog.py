from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import QMimeData, QModelIndex, QSize, Qt, QTimer
from PySide6.QtGui import QDrag, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

try:
    from ...config import SHARED_UI_PREFERENCES_PATH, TOOL_ICONS_DIR
except ImportError:
    from config import SHARED_UI_PREFERENCES_PATH, TOOL_ICONS_DIR
from shared.ui.helpers.editor_helpers import style_icon_action_button
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
from shared.ui.helpers.window_geometry_memory import restore_window_geometry, save_window_geometry
from shared.ui.theme import apply_top_level_surface_palette
from shared.ui.selectors import JawSelectorWidget
from .selector_ui_helpers import normalize_selector_spindle
from .common import SelectorDialogBase, SelectorWidgetBase
from .detached_preview import (
    load_jaw_selector_preview_content,
    on_jaw_selector_detached_measurements_toggled,
    on_jaw_selector_detached_preview_closed,
    sync_jaw_selector_detached_preview,
    toggle_jaw_selector_preview_window,
)
from .external_preview_ipc import (
    sync_embedded_jaw_selector_preview,
    toggle_embedded_jaw_selector_preview_window,
)
from .selector_mime import SELECTOR_JAW_MIME, decode_jaw_payload, encode_selector_payload, first_dropped_jaw
from .jaw_selector_layout import JawSelectorLayoutMixin
from .jaw_selector_payload import JawSelectorPayloadMixin
from .jaw_selector_state import JawSelectorStateMixin
from ..jaw_catalog_delegate import ROLE_JAW_DATA, ROLE_JAW_ICON, ROLE_JAW_ID, JawCatalogDelegate, jaw_icon_for_row
from ..jaw_page_support.selector_widgets import JawAssignmentSlot, SelectorRemoveDropButton


class JawSelectorDialog(
    JawSelectorLayoutMixin,
    JawSelectorStateMixin,
    JawSelectorPayloadMixin,
    SelectorDialogBase,
):
    """Standalone Jaw selector hosted in a dialog (no JawPage dependency)."""

    def __init__(
        self,
        *,
        jaw_service,
        machine_profile,
        translate: Callable[[str, str | None], str],
        selector_spindle: str,
        initial_assignments: list[dict] | None,
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
        self.jaw_service = jaw_service
        self._on_submit = on_submit
        self.machine_profile = machine_profile

        self._current_spindle = normalize_selector_spindle(selector_spindle)
        self.current_jaw_id: str | None = None
        self._selector_assignments: dict[str, dict | None] = {'main': None, 'sub': None}
        self._selected_slots: set[str] = set()

        # Detached preview state (toolbar preview toggle parity with JawPage)
        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._detached_preview_last_model_key = None
        self._detached_measurements_enabled = True
        self._measurement_toggle_btn = None
        self._close_preview_shortcut = None
        self._startup_initialized = False

        if not self._embedded_mode and self._use_shared_selector_wrapper():
            self._init_shared_widget_wrapper(
                selector_spindle=selector_spindle,
                initial_assignments=initial_assignments,
            )
            return

        self._load_initial_assignments(initial_assignments)
        self.setUpdatesEnabled(False)
        try:
            if not self._embedded_mode:
                self.setWindowTitle(self._t('work_editor.selector.jaws_dialog_title', 'Leukavalitsin'))
                self.setAttribute(Qt.WA_DeleteOnClose, True)
                self.resize(1500, 860)

            inner = self._make_themed_inner_layout()

            self._build_filter_row(inner)
            self._build_content(inner)
            self._build_bottom_bar(inner)
            # Populate catalog and assignment lists while updates are suppressed
            # so the dialog is fully built before the first paint.
            self._run_startup_initialization()
        finally:
            self.setUpdatesEnabled(True)

    def _run_startup_initialization(self) -> None:
        if self._startup_initialized:
            return
        self._startup_initialized = True
        self._refresh_catalog()
        self._refresh_slot_ui()
        self._update_context_header()
        self._update_remove_button()

    @staticmethod
    def _use_shared_selector_wrapper() -> bool:
        mode = str(os.environ.get('NTX_SELECTOR_DIALOG_WRAPPER_MODE', 'legacy') or '').strip().lower()
        return mode in {'shared', 'widget', 'wrapper'}

    def _init_shared_widget_wrapper(
        self,
        *,
        selector_spindle: str,
        initial_assignments: list[dict] | None,
    ) -> None:
        if not self._embedded_mode:
            self.setWindowTitle(self._t('work_editor.selector.jaws_dialog_title', 'Leukavalitsin'))
            self.setAttribute(Qt.WA_DeleteOnClose, True)
            self.resize(1220, 780)
            restore_window_geometry(self, SHARED_UI_PREFERENCES_PATH, 'jaw_selector_dialog')

        inner = self._make_themed_inner_layout()

        widget = JawSelectorWidget(
            translate=self._t,
            selector_spindle=normalize_selector_spindle(selector_spindle),
            initial_assignments=initial_assignments,
            parent=self,
        )
        widget.submitted.connect(lambda payload: self._finish_submit(self._on_submit, payload))
        widget.canceled.connect(self._cancel_dialog)
        inner.addWidget(widget, 1)

    # ── Interface required by populate_detail_panel (jaw detail builder) ─

    def _localized_spindle_side(self, raw_side: str) -> str:
        normalized = (raw_side or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.spindle_side.{normalized}', raw_side)

    def _localized_jaw_type(self, raw_type: str) -> str:
        normalized = (raw_type or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.jaw_type.{normalized}', raw_type)

    def _load_preview_content(self, viewer, jaw: dict, *, label: str | None = None) -> bool:
        return load_jaw_selector_preview_content(self, viewer, jaw, label=label)

    def _preview_model_key(self, jaw: dict) -> str | None:
        """Return a stable dedup key for the jaw 3-D model so the viewer skips redundant reloads."""
        return str(jaw.get('jaw_id') or '').strip() or None

    # ── Detached preview parity with JawPage toolbar ───────────────────

    def _on_detached_measurements_toggled(self, checked: bool) -> None:
        on_jaw_selector_detached_measurements_toggled(self, checked)

    def _on_detached_preview_closed(self, result) -> None:
        on_jaw_selector_detached_preview_closed(self, result)

    def _sync_detached_preview(self, show_errors: bool = False) -> bool:
        if getattr(self, '_embedded_mode', False):
            return sync_embedded_jaw_selector_preview(self, show_errors=show_errors)
        return sync_jaw_selector_detached_preview(self, show_errors)

    def toggle_preview_window(self) -> None:
        if getattr(self, '_embedded_mode', False):
            toggle_embedded_jaw_selector_preview_window(self)
            return
        toggle_jaw_selector_preview_window(self)

    def closeEvent(self, event) -> None:
        if not getattr(self, '_embedded_mode', False):
            save_window_geometry(self, SHARED_UI_PREFERENCES_PATH, 'jaw_selector_dialog')
        super().closeEvent(event)


class EmbeddedJawCatalogView(QListView):
    """Flash-free jaw catalog view with selector-compatible drags."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)

    def startDrag(self, supportedActions):
        selection_model = self.selectionModel()
        indexes = selection_model.selectedRows() if selection_model is not None else []
        if not indexes and self.currentIndex().isValid():
            indexes = [self.currentIndex()]
        payload: list[dict] = []
        for index in indexes:
            jaw = index.data(ROLE_JAW_DATA)
            if isinstance(jaw, dict):
                jaw_id = str(jaw.get('jaw_id') or jaw.get('id') or '').strip()
                if jaw_id:
                    payload.append(
                        {
                            'jaw_id': jaw_id,
                            'jaw_type': str(jaw.get('jaw_type') or '').strip(),
                            'spindle_side': str(jaw.get('spindle_side') or '').strip(),
                        }
                    )
        if not payload:
            return
        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_JAW_MIME, payload)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class EmbeddedJawSlotButton(QPushButton):
    """Native SP1/SP2 drop slot used by the embedded jaw selector."""

    def __init__(self, slot: str, owner, parent=None):
        super().__init__(parent)
        self._slot = normalize_selector_spindle(slot)
        self._owner = owner
        self.setAcceptDrops(True)
        self.setCheckable(True)
        self.setProperty('embeddedSlotCard', True)
        self.setMinimumHeight(74)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_JAW_MIME):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_JAW_MIME):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        jaw = first_dropped_jaw(event.mimeData())
        if isinstance(jaw, dict):
            self._owner._assign_jaw_to_slot(self._slot, jaw)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class EmbeddedJawSelectorWidget(
    JawSelectorLayoutMixin,
    JawSelectorStateMixin,
    JawSelectorPayloadMixin,
    SelectorWidgetBase,
):
    """Work Editor embedded Jaw selector built as a QWidget from birth."""

    def __init__(
        self,
        *,
        jaw_service,
        machine_profile,
        translate: Callable[[str, str | None], str],
        selector_spindle: str,
        initial_assignments: list[dict] | None,
        on_submit: Callable[[dict], None],
        on_cancel: Callable[[], None],
        parent=None,
    ):
        self._embedded_mode = True
        super().__init__(translate=translate, on_cancel=on_cancel, parent=parent, window_flags=Qt.Widget)
        self.jaw_service = jaw_service
        self._on_submit = on_submit
        self.machine_profile = machine_profile

        self._current_spindle = normalize_selector_spindle(selector_spindle)
        self.current_jaw_id: str | None = None
        self._selector_assignments: dict[str, dict | None] = {'main': None, 'sub': None}
        self._selected_slots: set[str] = set()

        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._detached_preview_last_model_key = None
        self._detached_measurements_enabled = True
        self._measurement_toggle_btn = None
        self._close_preview_shortcut = None

        self._load_initial_assignments(initial_assignments)
        self._content_materialized = False
        self._materialize_scheduled = False
        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(8, 8, 8, 8)
        self._root_layout.setSpacing(8)
        self.setUpdatesEnabled(False)
        try:
            self._build_embedded_ui()

            self._refresh_catalog()
            self._refresh_slot_ui()
            self._update_context_header()
            self._update_remove_button()
            self._content_materialized = True
        finally:
            self.setUpdatesEnabled(True)

        self._initialize_preview_infrastructure()

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
                'work_editor.jaw.filter_placeholder',
                'Hae leukien ID:tä, tyyppiä, karaa tai halkaisijaa...',
            )
        )
        self.search_input.textChanged.connect(self._refresh_catalog)
        self.search_input.setVisible(False)

        self.filter_icon = build_filter_reset(TOOL_ICONS_DIR, self._clear_search)

        self.view_filter = QComboBox(toolbar)
        self.view_filter.setObjectName('topTypeFilter')
        self.view_filter.addItem(self._t('tool_library.nav.all_jaws', 'Kaikki leuat'), 'all')
        self.view_filter.addItem(self._t('work_editor.selector.sp1', 'Pääkara'), 'main')
        self.view_filter.addItem(self._t('work_editor.selector.sp2', 'Vastakara'), 'sub')
        self.view_filter.addItem(self._t('jaw_library.nav.soft_jaws', 'Pehmeät leuat'), 'soft')
        self.view_filter.addItem(self._t('jaw_library.nav.hard_group', 'Kovat / teräkäs / erikois'), 'hard_group')
        self.view_filter.currentIndexChanged.connect(self._refresh_catalog)

        self.preview_window_btn = build_preview_toggle(
            TOOL_ICONS_DIR,
            self._t('tool_library.preview.toggle', 'Näytä irrotettava 3D-esikatselu'),
            self.toggle_preview_window,
        )
        self.detail_header_container, self.detail_section_label, self.detail_close_btn = build_detail_header(
            self._close_icon,
            self._t('work_editor.selector.assignment.details_title', 'Leukojen tiedot'),
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
            [self.view_filter],
            self.preview_window_btn,
            self.detail_header_container,
        )
        self._root_layout.addWidget(toolbar, 0)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setObjectName('selectorSplitter')
        splitter.setProperty('pageFamilySplitter', True)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)
        splitter.setAutoFillBackground(False)

        catalog_panel, catalog_layout = build_catalog_list_shell(parent=splitter)
        self.list_view = EmbeddedJawCatalogView(catalog_panel)
        apply_catalog_list_view_defaults(self.list_view)
        self._model = QStandardItemModel(self.list_view)
        self.list_view.setModel(self._model)
        self.list_view.setItemDelegate(JawCatalogDelegate(parent=self.list_view, translate=self._t))
        self.list_view.doubleClicked.connect(lambda _index: self._assign_selected_jaw())
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

        selector_panel = QWidget(self.selector_card)
        selector_panel.setProperty('selectorPanel', True)
        slot_layout = QVBoxLayout(selector_panel)
        slot_layout.setContentsMargins(10, 10, 10, 10)
        slot_layout.setSpacing(8)

        header = QFrame(selector_panel)
        header.setProperty('selectorInfoHeader', True)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 14, 14, 12)
        header_layout.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.addStretch(1)
        self.selector_header_title_label = QLabel(self._t('work_editor.selector.jaws_dialog_title', 'Jaw selector'), header)
        self.selector_header_title_label.setProperty('selectorInfoTitle', True)
        self.selector_header_title_label.setAlignment(Qt.AlignCenter)
        title_row.addWidget(self.selector_header_title_label, 0, Qt.AlignCenter)
        title_row.addStretch(1)
        header_layout.addLayout(title_row)
        badge_row = QHBoxLayout()
        self.selector_spindle_value_label = QLabel('', header)
        self.selector_spindle_value_label.setProperty('toolBadge', True)
        self.selector_module_value_label = QLabel(self._t('work_editor.jaw.main_spindle_jaws', 'Jaws'), header)
        self.selector_module_value_label.setProperty('toolBadge', True)
        badge_row.addWidget(self.selector_spindle_value_label, 0, Qt.AlignLeft)
        badge_row.addStretch(1)
        badge_row.addWidget(self.selector_module_value_label, 0, Qt.AlignRight)
        header_layout.addLayout(badge_row)
        slot_layout.addWidget(header, 0)

        hint = QLabel(self._t('work_editor.selector.action.drag_hint', 'Vedä leuat kirjastosta SP1- tai SP2-paikkaan.'), selector_panel)
        hint.setProperty('selectorInlineHint', True)
        hint.setProperty('detailHint', True)
        hint.setWordWrap(False)
        slot_layout.addWidget(hint, 0)

        self.slot_buttons: dict[str, JawAssignmentSlot] = {}
        for slot, title in (
            ('main', self._t('work_editor.selector.slot.main_jaw', 'SP1-leuka')),
            ('sub', self._t('work_editor.selector.slot.sub_jaw', 'SP2-leuka')),
        ):
            btn = JawAssignmentSlot(
                slot,
                title,
                parent=selector_panel,
                translate=self._t,
            )
            btn.setMinimumHeight(70)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.set_drop_placeholder_text(self._t('work_editor.selector.action.drop_hint', 'Pudota leuka tähän'))
            btn.jawDropped.connect(self._on_slot_dropped)
            btn.slotClicked.connect(self._on_slot_clicked)
            self.slot_buttons[slot] = btn
            slot_layout.addWidget(btn, 0)
        self.slot_main = self.slot_buttons['main']
        self.slot_sub = self.slot_buttons['sub']

        slot_layout.addStretch(1)
        self.remove_btn = SelectorRemoveDropButton(self.selector_card)
        style_icon_action_button(
            self.remove_btn,
            TOOL_ICONS_DIR / 'delete.svg',
            self._t('work_editor.selector.action.remove', 'Poista'),
            danger=True,
        )
        self.remove_btn.clicked.connect(self._remove_selected)
        self.remove_btn.jawsDropped.connect(self._remove_by_ids)

        actions_host = QWidget(self.selector_card)
        actions_host.setObjectName('jawSelectorActionsHost')
        actions_host.setProperty('selectorActionBar', True)
        actions_host.setProperty('hostTransparent', True)
        actions_host_layout = QHBoxLayout(actions_host)
        actions_host_layout.setContentsMargins(8, 6, 8, 6)
        actions_host_layout.setSpacing(4)
        actions_host_layout.addWidget(self.remove_btn, 0, Qt.AlignLeft)
        actions_host_layout.addStretch(1)

        selector_card_layout.addWidget(selector_panel, 1)
        selector_card_layout.addWidget(actions_host, 0)
        self._right_stack.addWidget(self.selector_card)

        self.detail_card = QFrame(right_panel)
        self.detail_card.setProperty('selectorAssignmentsFrame', True)
        detail_layout = QVBoxLayout(self.detail_card)
        detail_layout.setContentsMargins(12, 12, 12, 12)
        detail_layout.setSpacing(8)
        self.detail_title = QLabel(self._t('work_editor.selector.assignment.details_title', 'Jaw details'), self.detail_card)
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

    def _refresh_catalog(self) -> None:
        if not hasattr(self, 'list_view'):
            return
        search_text = self.search_input.text().strip() if hasattr(self, 'search_input') else ''
        view_mode = self.view_filter.currentData() if hasattr(self, 'view_filter') else 'all'
        jaws = self.jaw_service.list_jaws(
            search_text=search_text,
            view_mode=view_mode or 'all',
            jaw_type_filter='All',
        )
        self._model.clear()
        for jaw in jaws:
            item = QStandardItem()
            jaw_id = str(jaw.get('jaw_id') or '').strip()
            item.setData(jaw_id, ROLE_JAW_ID)
            item.setData(dict(jaw), ROLE_JAW_DATA)
            item.setData(jaw_icon_for_row(jaw), ROLE_JAW_ICON)
            item.setData(dict(jaw), Qt.UserRole)
            self._model.appendRow(item)

    def _select_slot(self, slot_key: str) -> None:
        slot = normalize_selector_spindle(slot_key)
        self._selected_slots = {slot}
        self._current_spindle = slot
        self._refresh_slot_ui()

    def _assign_selected_jaw(self) -> None:
        index = self.list_view.currentIndex()
        if not index.isValid():
            return
        data = index.data(ROLE_JAW_DATA)
        normalized = self._normalize_selector_jaw(data if isinstance(data, dict) else None)
        if normalized is None:
            return
        self._assign_jaw_to_slot(self._current_spindle, normalized)

    def _assign_jaw_to_slot(self, slot_key: str, jaw: dict) -> None:
        slot = normalize_selector_spindle(slot_key)
        normalized = self._normalize_selector_jaw(jaw)
        if normalized is None:
            return
        if not self._jaw_supports_slot(normalized, slot):
            return
        self._selector_assignments[slot] = normalized
        self._selected_slots = {slot}
        self._current_spindle = slot
        self._refresh_slot_ui()

    def _refresh_slot_ui(self) -> None:
        if not hasattr(self, 'slot_buttons'):
            return
        for slot, btn in self.slot_buttons.items():
            jaw = self._selector_assignments.get(slot)
            btn.set_assignment(jaw if isinstance(jaw, dict) else None)
            btn.set_selected(slot in self._selected_slots)
        self._update_context_header()
        self._update_remove_button()

    def _update_context_header(self) -> None:
        if hasattr(self, 'selector_spindle_value_label'):
            label = 'SP2' if normalize_selector_spindle(self._current_spindle) == 'sub' else 'SP1'
            self.selector_spindle_value_label.setText(label)

    def _update_remove_button(self) -> None:
        if not hasattr(self, 'remove_btn'):
            return
        has_selected = any(self._selector_assignments.get(slot) is not None for slot in self._selected_slots)
        has_assigned = any(self._selector_assignments.get(slot) is not None for slot in ('main', 'sub'))
        self.remove_btn.setEnabled(has_selected or has_assigned)

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
        self._switch_to_detail_panel(self._get_selected_jaw())

    def _switch_to_selector_panel(self) -> None:
        self._right_stack.setCurrentWidget(self.selector_card)
        if hasattr(self, 'detail_header_container'):
            self.detail_header_container.setVisible(False)
            self._rebuild_filter_row()

    def _switch_to_detail_panel(self, jaw: dict | None = None) -> None:
        self._populate_jaw_detail(jaw)
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
            [self.view_filter],
            self.preview_window_btn,
            self.detail_header_container,
        )

    def _populate_jaw_detail(self, jaw: dict | None) -> None:
        if not isinstance(jaw, dict):
            self.detail_body.setText(self._t('work_editor.selector.detail_empty', 'Select a catalog item to view details.'))
            return
        rows = [
            (self._t('jaw_library.row.jaw_id', 'Jaw ID'), str(jaw.get('jaw_id') or '').strip()),
            (self._t('jaw_library.row.jaw_type', 'Jaw type'), self._localized_jaw_type(str(jaw.get('jaw_type') or '').strip())),
            (self._t('jaw_library.row.spindle', 'Spindle'), self._localized_spindle_side(str(jaw.get('spindle_side') or '').strip())),
            (self._t('jaw_library.row.clamping_diameter_multiline', 'Clamping diameter'), str(jaw.get('clamping_diameter_text') or jaw.get('diameter') or '')),
            (self._t('tool_library.field.notes', 'Notes'), str(jaw.get('notes') or '')),
        ]
        self.detail_body.setText('\n'.join(f'{label}: {value or "-"}' for label, value in rows))

    def _get_selected_jaw(self) -> dict | None:
        index = self.list_view.currentIndex()
        if not index.isValid():
            return None
        jaw = index.data(ROLE_JAW_DATA)
        return jaw if isinstance(jaw, dict) else None

    def _on_catalog_item_clicked(self, index) -> None:
        jaw = index.data(ROLE_JAW_DATA)
        if isinstance(jaw, dict):
            self.current_jaw_id = str(jaw.get('jaw_id') or '').strip() or None
            if self._right_stack.currentWidget() is self.detail_card:
                self._populate_jaw_detail(jaw)
        self._sync_preview_if_open()

    def prepare_for_session(
        self,
        *,
        selector_spindle: str,
        initial_assignments: list[dict] | None,
        on_submit: Callable[[dict], None],
        on_cancel: Callable[[], None],
    ) -> None:
        self.setUpdatesEnabled(False)
        try:
            self._reset_selector_widget_state(on_cancel=on_cancel)
            self._on_submit = on_submit
            self._current_spindle = normalize_selector_spindle(selector_spindle)
            self.current_jaw_id = None
            self._selector_assignments = {'main': None, 'sub': None}
            self._selected_slots = set()
            self._load_initial_assignments(initial_assignments)

            if not self._content_materialized:
                return

            if hasattr(self, 'search_toggle'):
                self.search_toggle.setChecked(False)
            if hasattr(self, 'search_input'):
                self.search_input.setVisible(False)
                self.search_input.blockSignals(True)
                self.search_input.clear()
                self.search_input.blockSignals(False)
            if hasattr(self, 'view_filter') and self.view_filter.count():
                self.view_filter.setCurrentIndex(0)
            if hasattr(self, 'detail_card') and self.detail_card.isVisible():
                self._switch_to_selector_panel()
            if hasattr(self, 'list_view'):
                self.list_view.clearSelection()
                self.list_view.setCurrentIndex(QModelIndex())

            self._refresh_catalog()
            self._refresh_slot_ui()
            self._update_context_header()
            self._update_remove_button()
        finally:
            self.setUpdatesEnabled(True)

    def _localized_spindle_side(self, raw_side: str) -> str:
        normalized = (raw_side or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.spindle_side.{normalized}', raw_side)

    def _localized_jaw_type(self, raw_type: str) -> str:
        normalized = (raw_type or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.jaw_type.{normalized}', raw_type)

    def _load_preview_content(self, viewer, jaw: dict, *, label: str | None = None) -> bool:
        return load_jaw_selector_preview_content(self, viewer, jaw, label=label)

    def _preview_model_key(self, jaw: dict) -> str | None:
        return str(jaw.get('jaw_id') or '').strip() or None

    def _on_detached_measurements_toggled(self, checked: bool) -> None:
        on_jaw_selector_detached_measurements_toggled(self, checked)

    def _on_detached_preview_closed(self, result) -> None:
        on_jaw_selector_detached_preview_closed(self, result)

    def _sync_detached_preview(self, show_errors: bool = False) -> bool:
        if getattr(self, '_embedded_mode', False):
            return sync_embedded_jaw_selector_preview(self, show_errors=show_errors)
        return sync_jaw_selector_detached_preview(self, show_errors)

    def toggle_preview_window(self) -> None:
        if getattr(self, '_embedded_mode', False):
            toggle_embedded_jaw_selector_preview_window(self)
            return
        toggle_jaw_selector_preview_window(self)

