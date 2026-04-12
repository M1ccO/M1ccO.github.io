
import json
import shutil
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QUrl, QTimer, QModelIndex, QMimeData, Signal
from PySide6.QtGui import QDrag, QIcon, QDesktopServices, QFontMetrics, QKeySequence, QShortcut, QStandardItemModel, QStandardItem, QColor, QPainter, QPixmap, QTransform
# import QtSvg so that SVG image support is initialized early
import PySide6.QtSvg  # noqa: F401
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QDialogButtonBox, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QSplitter, QVBoxLayout, QWidget, QSizePolicy, QToolButton
)
from config import (
    EXPORT_DEFAULT_PATH,
    ALL_TOOL_TYPES,
    MILLING_TOOL_TYPES,
    TURNING_TOOL_TYPES,
    TOOL_TYPE_TO_ICON,
    TOOL_ICONS_DIR,
    DEFAULT_TOOL_ICON,
)
from ui.tool_editor_dialog import AddEditToolDialog
from ui.tool_catalog_delegate import (
    ToolCatalogDelegate, tool_icon_for_type,
    ROLE_TOOL_ID, ROLE_TOOL_DATA, ROLE_TOOL_ICON, ROLE_TOOL_UID,
)
from shared.editor_helpers import (
    apply_secondary_button_theme,
    ask_multi_edit_mode,
    create_dialog_buttons,
    setup_editor_dialog,
)
from shared.mini_assignment_card import MiniAssignmentCard

from ui.stl_preview import StlPreviewWidget
from ui.selector_mime import SELECTOR_TOOL_MIME, decode_tool_payload, encode_selector_payload, tool_payload_keys
from ui.selector_state_helpers import (
    default_selector_splitter_sizes,
    normalize_selector_mode,
)
from ui.selector_ui_helpers import normalize_selector_spindle, selector_spindle_label
from ui.home_page_support import (
    SelectorAssignmentState,
    sync_selector_assignment_order,
    sync_selector_card_selection_states,
    update_selector_assignment_buttons,
    add_three_box_row as build_three_box_row,
    add_two_box_row as build_two_box_row,
    apply_tool_detail_layout_rules,
    build_catalog_list_panel,
    build_bottom_bars,
    build_detail_field as build_detail_field_widget,
    build_filter_toolbar,
    build_components_panel,
    build_preview_panel,
    build_selector_card,
)


class _ToolCatalogListView(QListView):
    def startDrag(self, supportedActions):
        selection_model = self.selectionModel()
        if selection_model is None:
            return
        indexes = sorted(selection_model.selectedRows(), key=lambda idx: idx.row())
        if not indexes:
            index = self.currentIndex()
            if index.isValid():
                indexes = [index]
        if not indexes:
            return

        payload: list[dict] = []
        for index in indexes:
            tool_id = str(index.data(ROLE_TOOL_ID) or '').strip()
            if not tool_id:
                continue
            entry: dict = {'tool_id': tool_id}
            tool_uid = index.data(ROLE_TOOL_UID)
            try:
                parsed_uid = int(tool_uid) if tool_uid is not None and str(tool_uid).strip() else None
            except Exception:
                parsed_uid = None
            if parsed_uid is not None:
                entry['tool_uid'] = parsed_uid
            tool_data = index.data(ROLE_TOOL_DATA)
            if isinstance(tool_data, dict):
                entry['description'] = str(tool_data.get('description') or '').strip()
                entry['tool_type'] = str(tool_data.get('tool_type') or '').strip()
                entry['default_pot'] = str(tool_data.get('default_pot') or '').strip()
            payload.append(entry)

        if not payload:
            return

        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_TOOL_MIME, payload)
        drag = QDrag(self)
        drag.setMimeData(mime)

        # Build a semi-transparent ghost card showing the first tool
        first = payload[0]
        ghost_text = first.get('tool_id', '')
        desc = first.get('description', '')
        if desc:
            ghost_text = f'{ghost_text} - {desc}'
        if len(payload) > 1:
            ghost_text += f'  (+{len(payload) - 1})'
        pixmap = QPixmap(220, 40)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(0.75)
        painter.setBrush(QColor('#f0f6fc'))
        painter.setPen(QColor('#637282'))
        painter.drawRoundedRect(1, 1, 218, 38, 6, 6)
        painter.setOpacity(1.0)
        painter.setPen(QColor('#22303c'))
        from PySide6.QtGui import QFont
        font = QFont()
        font.setPointSizeF(9.0)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.drawText(10, 4, 200, 32, Qt.AlignVCenter | Qt.TextSingleLine, ghost_text)
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())

        drag.exec(Qt.CopyAction)


class _ToolAssignmentListWidget(QListWidget):
    externalToolsDropped = Signal(list, int)
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

        mime = self.model().mimeData(indexes)
        if mime is None:
            mime = QMimeData()

        payload: list[dict] = []
        for index in indexes:
            item = self.item(index.row())
            if item is None:
                continue
            assignment = item.data(Qt.UserRole)
            if isinstance(assignment, dict):
                payload.append(dict(assignment))
        encode_selector_payload(mime, SELECTOR_TOOL_MIME, payload)

        drag = QDrag(self)
        drag.setMimeData(mime)

        first_row = indexes[0].row()
        ghost_item = self.item(first_row)
        ghost_widget = self.itemWidget(ghost_item) if ghost_item is not None else None
        if isinstance(ghost_widget, QWidget):
            card_widget = ghost_widget.findChild(MiniAssignmentCard)
            preview_widget = card_widget if isinstance(card_widget, QWidget) else ghost_widget
            grabbed = preview_widget.grab()
            if not grabbed.isNull():
                translucent = QPixmap(grabbed.size())
                translucent.fill(Qt.transparent)
                painter = QPainter(translucent)
                painter.setOpacity(0.7)
                painter.drawPixmap(0, 0, grabbed)
                painter.end()
                drag.setPixmap(translucent)
                drag.setHotSpot(translucent.rect().center())

        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME):
            event.acceptProposedAction()
            return
        if event.source() is self:
            super().dragEnterEvent(event)
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME):
            event.acceptProposedAction()
            return
        if event.source() is self:
            super().dragMoveEvent(event)
            return
        event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME) and event.source() is not self:
            dropped = decode_tool_payload(event.mimeData())
            point = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            row = self.indexAt(point).row()
            if row < 0:
                row = self.count()
            self.externalToolsDropped.emit(dropped if isinstance(dropped, list) else [], row)
            event.acceptProposedAction()
            return
        super().dropEvent(event)
        if event.source() is self:
            self.orderChanged.emit()

    def mousePressEvent(self, event):
        point = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        if self.itemAt(point) is None:
            self.clearSelection()
            self.setCurrentRow(-1)
        super().mousePressEvent(event)


class _SelectorToolRemoveDropButton(QPushButton):
    toolsDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    @staticmethod
    def _payload_tool_keys(mime: QMimeData) -> list[tuple[str, str | None]]:
        return tool_payload_keys(mime)

    def dragEnterEvent(self, event):
        if self._payload_tool_keys(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if self._payload_tool_keys(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        tool_keys = self._payload_tool_keys(event.mimeData())
        if not tool_keys:
            event.ignore()
            return
        self.toolsDropped.emit(tool_keys)
        event.acceptProposedAction()


class _SelectorAssignmentRowWidget(MiniAssignmentCard):
    def __init__(
        self,
        icon: QIcon,
        text: str,
        subtitle: str = '',
        comment: str = '',
        pot: str = '',
        parent=None,
    ):
        badges: list[str] = []
        if pot:
            badges.append(f'P:{pot}')
        if comment:
            badges.append('C')
        super().__init__(
            icon=icon,
            title=text,
            subtitle=subtitle,
            badges=badges,
            editable=True,
            compact=True,
            parent=parent,
        )
        self.setObjectName('selectorAssignmentRowCard')
        self._apply_visual_style(False)

    def _apply_visual_style(self, selected: bool) -> None:
        background = '#ffffff'
        border = '#00C8FF' if selected else '#99acbf'
        border_width = '2px' if selected else '1px'
        padding = '0px' if selected else '1px'
        title_color = '#24303c' if selected else '#171a1d'
        meta_color = '#2b3136'
        hint_color = '#617180'
        self.setStyleSheet(
            'QFrame#selectorAssignmentRowCard {'
            f'  background-color: {background};'
            f'  border: {border_width} solid {border};'
            '  border-radius: 8px;'
            f'  padding: {padding};'
            '}'
            'QFrame#selectorAssignmentRowCard QLabel {'
            '  background-color: transparent;'
            '  border: none;'
            '}'
            'QFrame#selectorAssignmentRowCard QLabel[miniAssignmentTitle="true"] {'
            f'  color: {title_color};'
            '}'
            'QFrame#selectorAssignmentRowCard QLabel[miniAssignmentMeta="true"] {'
            f'  color: {meta_color};'
            '}'
            'QFrame#selectorAssignmentRowCard QLabel[miniAssignmentHint="true"] {'
            f'  color: {hint_color};'
            '}'
        )

    def set_selected(self, selected: bool):
        super().set_selected(selected)
        self._apply_visual_style(bool(selected))


# ==============================
# Home Page Shell
# ==============================
class HomePage(QWidget):
    def __init__(
        self,
        tool_service,
        export_service,
        settings_service,
        parent=None,
        page_title: str = 'Tool Library',
        view_mode: str = 'home',
        translate=None,
    ):
        super().__init__(parent)
        self.tool_service = tool_service
        self.export_service = export_service
        self.settings_service = settings_service
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self.page_title = page_title
        self.view_mode = (view_mode or 'home').lower()
        self.current_tool_id = None
        self.current_tool_uid = None
        self._details_hidden = True
        self._last_splitter_sizes = None
        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._close_preview_shortcut = None
        self._measurement_toggle_btn = None
        self._measurement_filter_combo = None
        self._detached_measurements_enabled = True
        self._detached_measurement_filter = None
        self._detached_preview_last_model_key = None
        self._inline_preview_warmup = None
        self._active_db_name = ''
        self._module_switch_callback = None
        self._external_head_filter = None
        self._head_filter_value = 'HEAD1/2'
        self._master_filter_ids: set[str] = set()
        self._master_filter_active = False
        self._selector_active = False
        self._selector_head = ''
        self._selector_spindle = ''
        self._selector_panel_mode = 'details'
        self._selector_assigned_tools: list[dict] = []
        self._selector_assignments_by_target: dict[str, list[dict]] = {}
        self._selector_saved_details_hidden = True
        self._selector_assignment_state = SelectorAssignmentState(
            normalize_head=self._normalize_selector_head_value,
        )
        self._build_ui()
        self._warmup_preview_engine()
        self.refresh_list()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    @staticmethod
    def _strip_tool_id_prefix(value: str) -> str:
        raw = str(value or '').strip()
        if raw.lower().startswith('t'):
            raw = raw[1:].strip()
        return ''.join(ch for ch in raw if ch.isdigit())

    @classmethod
    def _tool_id_storage_value(cls, value: str) -> str:
        stripped = cls._strip_tool_id_prefix(value)
        return f'T{stripped}' if stripped else ''

    @classmethod
    def _tool_id_display_value(cls, value: str) -> str:
        return cls._tool_id_storage_value(value)

    def _warmup_preview_engine(self):
        """Pre-create a hidden preview widget so first detail-open doesn't flash."""
        if StlPreviewWidget is None:
            return
        self._inline_preview_warmup = StlPreviewWidget(parent=self)
        self._inline_preview_warmup.set_control_hint_text(
            self._t(
                'tool_editor.hint.rotate_pan_zoom',
                'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
            )
        )
        self._inline_preview_warmup.hide()

        def _drop_warmup():
            if self._inline_preview_warmup is not None:
                self._inline_preview_warmup.deleteLater()
                self._inline_preview_warmup = None

        # Keep warmup alive long enough for first user interactions.
        QTimer.singleShot(10000, _drop_warmup)

    def _update_row_type_visibility(self, show: bool):
        """Called when the detail panel opens/closes.
        With the delegate-based list, we just need to trigger a repaint.
        """
        self.tool_list.viewport().update()

    def _build_type_filter_widget(self) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName('topTypeFilter')
        self.type_filter = combo
        self._build_tool_type_filter_items()
        combo.setMaxVisibleItems(8)
        type_popup_view = combo.view()
        type_popup_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        type_popup_view.setMinimumHeight(0)
        type_popup_view.setMaximumHeight(8 * 40)
        type_popup_view.window().setMinimumHeight(0)
        type_popup_view.window().setMaximumHeight(8 * 40 + 8)
        combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        combo.setMinimumWidth(60)
        combo.currentIndexChanged.connect(self._on_type_changed)
        return combo

    # ==============================
    # Home Page Layout
    # ==============================
    def _build_ui(self):
        root = QVBoxLayout(self)
        # Set all margins to 0 for flush alignment
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        filter_frame = build_filter_toolbar(self, tool_icons_dir=TOOL_ICONS_DIR)
        root.addWidget(filter_frame)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)

        # catalogue and detail panes
        left_card = build_catalog_list_panel(
            self,
            tool_list_cls=_ToolCatalogListView,
            tool_model_cls=QStandardItemModel,
            tool_delegate_cls=ToolCatalogDelegate,
        )
        self.splitter.addWidget(left_card)

        self.detail_container = QWidget()
        self.detail_container.setContentsMargins(0, 0, 0, 0)
        self.detail_container.setMinimumWidth(220)
        self.detail_container.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        dc_layout = QVBoxLayout(self.detail_container)
        dc_layout.setContentsMargins(0, 0, 0, 0)
        dc_layout.setSpacing(2)

        self.detail_card = QFrame()
        self.detail_card.setProperty('card', True)
        detail_card_layout = QVBoxLayout(self.detail_card)
        detail_card_layout.setContentsMargins(0, 0, 0, 0)
        detail_card_layout.setSpacing(0)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName('detailScrollArea')
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail_panel = QWidget()
        self.detail_panel.setObjectName('detailPanel')
        self.detail_panel.setMinimumWidth(0)
        self.detail_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.detail_layout = QVBoxLayout(self.detail_panel)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(10)
        self.detail_scroll.setWidget(self.detail_panel)
        self.detail_layout.addWidget(self._build_placeholder_details())
        detail_card_layout.addWidget(self.detail_scroll, 1)
        dc_layout.addWidget(self.detail_card, 1)

        build_selector_card(
            self,
            dc_layout=dc_layout,
            assignment_list_cls=_ToolAssignmentListWidget,
            remove_drop_button_cls=_SelectorToolRemoveDropButton,
            tool_icons_dir=TOOL_ICONS_DIR,
        )

        self.splitter.addWidget(self.detail_container)
        root.addWidget(self.splitter, 1)

        self.detail_container.hide()
        self.detail_header_container.hide()
        self.splitter.setSizes([1, 0])

        build_bottom_bars(self, root=root)

    def set_module_switch_handler(self, callback):
        self._module_switch_callback = callback

    def set_page_title(self, title: str):
        self.page_title = str(title or '')
        if hasattr(self, 'toolbar_title_label'):
            self.toolbar_title_label.setText(self.page_title)

    def set_module_switch_target(self, target: str):
        target_text = (target or '').strip().upper() or 'JAWS'
        display = self._t('tool_library.module.tools', 'TOOLS') if target_text == 'TOOLS' else self._t('tool_library.module.jaws', 'JAWS')
        self.module_toggle_btn.setText(display)
        self.module_toggle_btn.setToolTip(self._t('tool_library.module.switch_to_target', 'Switch to {target} module', target=display))

    def set_master_filter(self, tool_ids, active: bool):
        self._master_filter_ids = {str(t).strip() for t in (tool_ids or []) if str(t).strip()}
        self._master_filter_active = bool(active) and bool(self._master_filter_ids)
        self.refresh_list()

    def _selector_tool_key(self, tool: dict | None) -> str:
        return self._selector_assignment_state.selector_tool_key(tool)

    def _normalize_selector_tool(self, tool: dict | None) -> dict | None:
        return self._selector_assignment_state.normalize_selector_tool(tool)

    @staticmethod
    def _selector_spindle_label(spindle: str) -> str:
        return selector_spindle_label(spindle)

    @staticmethod
    def _normalize_selector_head_value(head: str) -> str:
        return 'HEAD2' if str(head or '').strip().upper() == 'HEAD2' else 'HEAD1'

    @staticmethod
    def _normalize_selector_spindle_value(spindle: str) -> str:
        return normalize_selector_spindle(spindle)

    @staticmethod
    def _normalize_tool_spindle_orientation(value: str | None) -> str:
        raw = str(value or '').strip().lower().replace('_', ' ')
        if not raw:
            return 'main'
        if 'both' in raw:
            return 'both'
        if raw in {'sub', 'sub spindle', 'subspindle', 'counter spindle'}:
            return 'sub'
        return 'main'

    def _tool_matches_selector_spindle(self, tool: dict) -> bool:
        if not self._selector_active:
            return True
        if self._normalize_selector_head_value(self._selector_head or 'HEAD1') != 'HEAD2':
            # HEAD1 tools are valid for both spindles on this machine profile.
            return True
        target = self._current_selector_spindle_value()
        orientation = self._normalize_tool_spindle_orientation(tool.get('spindle_orientation'))
        return orientation in {target, 'both'}

    def _selector_assignment_icon(self, assignment: dict) -> QIcon:
        icon = tool_icon_for_type(str(assignment.get('tool_type') or '').strip())
        tool_type = str(assignment.get('tool_type') or '').strip()
        is_turning = tool_type in TURNING_TOOL_TYPES
        if icon.isNull() or self._current_selector_spindle_value() != 'sub' or not is_turning:
            return icon
        pixmap = icon.pixmap(QSize(32, 32))
        if pixmap.isNull():
            return icon
        mirrored = pixmap.transformed(QTransform().scale(-1, 1), Qt.SmoothTransformation)
        return QIcon(mirrored)

    def _selector_target_key(self, head: str, spindle: str) -> str:
        return self._selector_assignment_state.selector_target_key(head, spindle)

    def _selector_current_target_key(self) -> str:
        return self._selector_assignment_state.current_target_key(
            self._selector_head or 'HEAD1',
            self._current_selector_spindle_value(),
        )

    def _store_selector_bucket_for_current_target(self) -> None:
        self._selector_assignment_state.store_bucket_for_target(
            self._selector_assignments_by_target,
            self._selector_assigned_tools,
            head=self._selector_head or 'HEAD1',
            spindle=self._current_selector_spindle_value(),
        )

    def _load_selector_bucket_for_current_target(self) -> None:
        self._selector_assigned_tools = self._selector_assignment_state.load_bucket_for_target(
            self._selector_assignments_by_target,
            head=self._selector_head or 'HEAD1',
            spindle=self._current_selector_spindle_value(),
        )

    def _current_selector_spindle_value(self) -> str:
        if hasattr(self, 'selector_spindle_btn'):
            return 'sub' if self.selector_spindle_btn.property('spindle') == 'sub' else 'main'
        return 'sub' if str(self._selector_spindle or '').strip().lower() == 'sub' else 'main'

    def _update_selector_spindle_button_text(self):
        if not hasattr(self, 'selector_spindle_btn'):
            return
        spindle = self._current_selector_spindle_value()
        self.selector_spindle_btn.setText(self._selector_spindle_label(spindle))
        self.selector_spindle_btn.setChecked(spindle == 'sub')
        if hasattr(self, 'selector_spindle_value_label'):
            self.selector_spindle_value_label.setText(self._selector_spindle_label(spindle))

    def _update_selector_context_header(self) -> None:
        head = self._normalize_selector_head_value(self._selector_head or 'HEAD1')
        spindle = self._current_selector_spindle_value()
        if hasattr(self, 'selector_head_value_label'):
            self.selector_head_value_label.setText(head)
        if hasattr(self, 'selector_spindle_value_label'):
            self.selector_spindle_value_label.setText(self._selector_spindle_label(spindle))

    def _set_selector_spindle_value(self, spindle: str):
        normalized = normalize_selector_spindle(spindle)
        self._selector_spindle = normalized
        if hasattr(self, 'selector_spindle_btn'):
            self.selector_spindle_btn.setProperty('spindle', normalized)
            self._update_selector_spindle_button_text()

    def _selector_assignments_section_title(self) -> str:
        if self._normalize_selector_head_value(self._selector_head or 'HEAD1') == 'HEAD2':
            return self._t('tool_library.selector.head2_tools', 'Head 2 Tools')
        return self._t('tool_library.selector.head1_tools', 'Head 1 Tools')

    def _update_selector_assignments_section_title(self) -> None:
        if hasattr(self, 'selector_assignments_frame') and hasattr(self.selector_assignments_frame, 'setTitle'):
            self.selector_assignments_frame.setTitle(self._selector_assignments_section_title())

    def _selector_selected_rows(self) -> list[int]:
        if not hasattr(self, 'selector_assignment_list'):
            return []
        rows = sorted({index.row() for index in self.selector_assignment_list.selectedIndexes()})
        return [row for row in rows if 0 <= row < len(self._selector_assigned_tools)]

    def _refresh_selector_assignment_rows(self):
        if not hasattr(self, 'selector_assignment_list'):
            return
        self._rebuild_selector_assignment_list()

    def _rebuild_selector_assignment_list(self):
        if not hasattr(self, 'selector_assignment_list'):
            return
        current = self.selector_assignment_list.currentRow()
        selected_rows = self._selector_selected_rows()
        self.selector_assignment_list.blockSignals(True)
        self.selector_assignment_list.clear()
        for row, assignment in enumerate(self._selector_assigned_tools):
            tool_id = str(assignment.get('tool_id') or '').strip()
            description = str(assignment.get('description') or '').strip()
            comment = str(assignment.get('comment') or '').strip()
            pot = str(assignment.get('default_pot') or '').strip()
            title = f'{row + 1}. {tool_id}'
            if description:
                title = f'{title}  -  {description}'
            subtitle = comment
            badges: list[str] = []
            if pot:
                badges.append(f'P:{pot}')
            if comment:
                badges.append('C')
            icon = self._selector_assignment_icon(assignment)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, dict(assignment))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            item.setSizeHint(QSize(0, 50 if comment else 42))
            self.selector_assignment_list.addItem(item)
            card = _SelectorAssignmentRowWidget(
                icon=icon,
                text=title,
                subtitle=subtitle,
                comment=assignment.get('comment', ''),
                pot=pot,
                parent=self.selector_assignment_list,
            )
            card.setProperty('hasComment', bool(comment))
            card.editRequested.connect(lambda r=row: self._inline_edit_selector_row(r))
            row_host = QWidget(self.selector_assignment_list)
            row_host.setProperty('editorTransparentPanel', True)
            row_host.setAttribute(Qt.WA_StyledBackground, False)
            row_host.setStyleSheet('background: transparent; border: none;')
            row_layout = QVBoxLayout(row_host)
            row_layout.setContentsMargins(0, 0, 0, 7)
            row_layout.setSpacing(0)
            row_layout.addWidget(card)
            self.selector_assignment_list.setItemWidget(item, row_host)
        self.selector_assignment_list.blockSignals(False)
        for row in selected_rows:
            if 0 <= row < self.selector_assignment_list.count():
                item = self.selector_assignment_list.item(row)
                if item is not None:
                    item.setSelected(True)
        if current >= 0 and current < self.selector_assignment_list.count():
            self.selector_assignment_list.setCurrentRow(current)
        sync_selector_card_selection_states(self)
        update_selector_assignment_buttons(self)


    def _inline_edit_selector_row(self, row: int):
        if row < 0 or row >= len(self._selector_assigned_tools):
            return
        assignment = self._selector_assigned_tools[row]
        tool_id = str(assignment.get('tool_id') or '').strip()
        description = str(assignment.get('description') or '').strip()
        pot = str(assignment.get('default_pot') or '').strip()
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self,
            self._t('tool_library.selector.edit_assignment', 'Edit Assignment'),
            f'T-code / Description / Pot  (current: {tool_id})',
            text=f'{tool_id}  |  {description}  |  {pot}',
        )
        if not ok:
            return
        parts = [p.strip() for p in text.split('|')]
        if parts:
            assignment['tool_id'] = parts[0] or tool_id
        if len(parts) > 1:
            assignment['description'] = parts[1]
        if len(parts) > 2:
            assignment['default_pot'] = parts[2]
        self._rebuild_selector_assignment_list()
        self.selector_assignment_list.setCurrentRow(row)

    def _toggle_selector_spindle(self):
        if not self._selector_active or not hasattr(self, 'selector_spindle_btn'):
            return
        self._store_selector_bucket_for_current_target()
        target = 'sub' if self.selector_spindle_btn.isChecked() else 'main'
        self._set_selector_spindle_value(target)
        self._load_selector_bucket_for_current_target()
        self._update_selector_context_header()
        self._update_selector_assignments_section_title()
        self.refresh_list()
        self._rebuild_selector_assignment_list()

    def _set_selector_panel_mode(self, mode: str):
        if not self._selector_active:
            self._selector_panel_mode = 'details'
            if hasattr(self, 'selector_toggle_btn'):
                self.selector_toggle_btn.setChecked(False)
            if hasattr(self, 'selector_card'):
                self.selector_card.setVisible(False)
            if hasattr(self, 'detail_card'):
                self.detail_card.setVisible(True)
            return

        target_mode = normalize_selector_mode(mode)
        self._selector_panel_mode = target_mode
        self._details_hidden = False
        self.detail_container.show()
        self.detail_header_container.show()
        if not self._last_splitter_sizes:
            self._last_splitter_sizes = default_selector_splitter_sizes(self.splitter.width())
        self.splitter.setSizes(self._last_splitter_sizes)

        if target_mode == 'details':
            self.detail_card.setVisible(True)
            self.selector_card.setVisible(False)
            self.detail_section_label.setText(self._t('tool_library.section.tool_details', 'Tool details'))
            self.toggle_details_btn.setText(self._t('tool_library.details.hide', 'HIDE DETAILS'))
            self._update_row_type_visibility(False)
            self.selector_toggle_btn.setChecked(False)
            self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_selector', 'SELECTOR'))
        else:
            self.detail_card.setVisible(False)
            self.selector_card.setVisible(True)
            self.detail_section_label.setText(self._t('tool_library.selector.selection_title', 'Selection'))
            self.toggle_details_btn.setText(self._t('tool_library.details.show', 'SHOW DETAILS'))
            self._update_row_type_visibility(True)
            self.selector_toggle_btn.setChecked(True)
            self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_details', 'DETAILS'))
            # Keep selector rows resilient after UI mode/header refactors.
            self._load_selector_bucket_for_current_target()
            self._rebuild_selector_assignment_list()

    def set_selector_context(
        self,
        active: bool,
        head: str = '',
        spindle: str = '',
        initial_assignments: list[dict] | None = None,
        initial_assignment_buckets: dict[str, list[dict]] | None = None,
    ) -> None:
        was_active = self._selector_active
        self._selector_active = bool(active)
        self.selector_toggle_btn.setVisible(self._selector_active)
        self.toggle_details_btn.setEnabled(not self._selector_active)

        # Toggle bottom bars
        self.button_bar.setVisible(not self._selector_active)
        self.selector_bottom_bar.setVisible(self._selector_active)

        if self._selector_active:
            if not was_active:
                self._selector_saved_details_hidden = self._details_hidden
            context = self._selector_assignment_state.prepare_context(
                head=str(head or '').strip().upper(),
                spindle=str(spindle or '').strip().lower(),
                initial_assignments=initial_assignments,
                initial_assignment_buckets=initial_assignment_buckets,
            )
            self._selector_head = context.head
            self._set_selector_spindle_value(context.spindle)
            self._selector_assignments_by_target = context.buckets
            self._selector_assigned_tools = context.assignments
            self._update_selector_spindle_button_text()
            self._update_selector_context_header()
            self._update_selector_assignments_section_title()
            self.refresh_list()
            self._rebuild_selector_assignment_list()
            self._set_selector_panel_mode('selector')
            return

        self._selector_head = self._normalize_selector_head_value(str(head or '').strip().upper())
        self._set_selector_spindle_value(str(spindle or '').strip().lower())
        self._details_hidden = self._selector_saved_details_hidden
        self._selector_assigned_tools = []
        self._selector_assignments_by_target = {}
        if hasattr(self, 'selector_assignment_list'):
            self.selector_assignment_list.clear()
        self.refresh_list()
        self._update_selector_context_header()
        self._set_selector_panel_mode('details')
        self.detail_section_label.setText(self._t('tool_library.section.tool_details', 'Tool details'))
        if self._details_hidden:
            self.detail_container.hide()
            self.detail_header_container.hide()
            self.splitter.setSizes([1, 0])
            self._update_row_type_visibility(True)
        else:
            self.detail_container.show()
            self.detail_header_container.show()
            if not self._last_splitter_sizes:
                self._last_splitter_sizes = default_selector_splitter_sizes(self.splitter.width())
            self.splitter.setSizes(self._last_splitter_sizes)
            self._update_row_type_visibility(False)

    def selector_assigned_tools_for_setup_assignment(self) -> list[dict]:
        # Sync the active bucket from the UI and persist it before reading all buckets.
        sync_selector_assignment_order(self)
        self._store_selector_bucket_for_current_target()
        return self._selector_assignment_state.setup_assignment_payload(
            self._selector_assignments_by_target,
            head=self._selector_head or 'HEAD1',
        )

    def selector_assignment_buckets_for_setup_assignment(self) -> dict[str, list[dict]]:
        """Return per-target buckets (already persisted by selector_assigned_tools_for_setup_assignment)."""
        return self._selector_assignment_state.setup_assignment_buckets(
            self._selector_assignments_by_target,
            head=self._selector_head or 'HEAD1',
        )

    def update_selector_head(self, head: str) -> None:
        """Update the selector HEAD target (called when the HEAD dropdown changes)."""
        if not self._selector_active:
            return
        self._store_selector_bucket_for_current_target()
        self._selector_head = self._normalize_selector_head_value(head)
        self._load_selector_bucket_for_current_target()
        self._update_selector_context_header()
        self._update_selector_assignments_section_title()
        self._rebuild_selector_assignment_list()

    def selector_current_target_for_setup_assignment(self) -> dict:
        return {
            'head': self._normalize_selector_head_value(self._selector_head or 'HEAD1'),
            'spindle': self._normalize_selector_spindle_value(self._current_selector_spindle_value()),
        }

    def _rebuild_filter_row(self):
        while self.filter_layout.count():
            item = self.filter_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        self.filter_layout.addWidget(self.search_toggle)
        self.filter_layout.addWidget(self.toggle_details_btn)
        if self.search.isVisible():
            self.filter_layout.addWidget(self.search, 1)
        self.filter_layout.addWidget(self.filter_icon)
        self.filter_layout.addWidget(self.type_filter)
        self.filter_layout.addWidget(self.preview_window_btn)
        self.filter_layout.addStretch(1)
        self.filter_layout.addWidget(self.detail_header_container)

    def set_active_database_name(self, db_name: str):
        self._active_db_name = (db_name or '').strip()

    # ==============================
    # Home Page Filters + List State
    # ==============================
    def _toggle_search(self):
        """Show or hide the search field and update widget order."""
        show = self.search_toggle.isChecked()
        # hide the combo entirely while we rearrange; this prevents it from briefly
        # popping up in its own window when its geometry shifts under the cursor.
        self.type_filter.hide()
        self.search.setVisible(show)
        self.search_toggle.setIcon(self.search_icon if not show else self.close_icon)
        if not show:
            # clear search when closed
            self.search.clear()
            self.refresh_list()
        self._rebuild_filter_row()
        # hide any open popup that might have been triggered by the mouse
        self.type_filter.hidePopup()
        # set a flag so eventFilter can swallow any upcoming show events
        self._suppress_combo = True
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: setattr(self, '_suppress_combo', False))
        # briefly disable the combo so stray press/release events can't open it
        self.type_filter.setEnabled(False)
        QTimer.singleShot(0, lambda: self.type_filter.setEnabled(True))
        # show combo once layout has been rebuilt
        self.type_filter.show()
        if show:
            # delay focusing the search field until after the layout settles
            QTimer.singleShot(0, self.search.setFocus)

    def _tool_icon(self, tool_type: str) -> QIcon:
        filename = TOOL_TYPE_TO_ICON.get(tool_type, DEFAULT_TOOL_ICON)
        path = TOOL_ICONS_DIR / filename
        if not path.exists():
            path = TOOL_ICONS_DIR / DEFAULT_TOOL_ICON
        return QIcon(str(path)) if path.exists() else QIcon()

    def _load_preview_content(self, viewer, stl_path: str | None, label: str | None = None) -> bool:
        if StlPreviewWidget is None or viewer is None or not stl_path:
            return False

        try:
            parsed = json.loads(stl_path)

            if isinstance(parsed, list):
                viewer.load_parts(parsed)
                return True

            if isinstance(parsed, str) and parsed.strip():
                viewer.load_stl(parsed, label=label)
                return True
        except Exception:
            viewer.load_stl(stl_path, label=label)
            return True

        return False

    def _set_preview_button_checked(self, checked: bool):
        self.preview_window_btn.blockSignals(True)
        self.preview_window_btn.setChecked(checked)
        self.preview_window_btn.blockSignals(False)

    def _ensure_detached_preview_dialog(self):
        if self._detached_preview_dialog is not None:
            return

        dialog = QDialog(self)
        dialog.setProperty('detachedPreviewDialog', True)
        dialog.setWindowTitle(self._t('tool_library.preview.window_title', '3D Preview'))
        dialog.resize(620, 820)
        dialog.finished.connect(self._on_detached_preview_closed)
        self._close_preview_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), dialog)
        self._close_preview_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._close_preview_shortcut.activated.connect(dialog.close)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        controls_host = QWidget(dialog)
        controls_host.setProperty('detachedPreviewToolbar', True)
        controls_host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        controls_layout = QHBoxLayout(controls_host)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        controls_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self._measurement_toggle_btn = QToolButton(controls_host)
        self._measurement_toggle_btn.setCheckable(True)
        self._measurement_toggle_btn.setChecked(self._detached_measurements_enabled)
        self._measurement_toggle_btn.setIconSize(QSize(28, 28))
        self._measurement_toggle_btn.setAutoRaise(True)
        self._measurement_toggle_btn.setProperty('topBarIconButton', True)
        self._measurement_toggle_btn.setFixedSize(36, 36)
        self._update_detached_measurement_toggle_icon(self._measurement_toggle_btn.isChecked())
        self._measurement_toggle_btn.clicked.connect(self._on_detached_measurements_toggled)
        controls_layout.addWidget(self._measurement_toggle_btn)

        measurements_label = QLabel(self._t('tool_library.preview.measurements_label', 'Mittaukset'))
        measurements_label.setProperty('detailHint', True)
        measurements_label.setProperty('detachedPreviewToolbarLabel', True)
        measurements_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        controls_layout.addWidget(measurements_label)

        self._measurement_filter_combo = None
        controls_layout.addStretch(1)
        layout.addWidget(controls_host)

        if StlPreviewWidget is not None:
            self._detached_preview_widget = StlPreviewWidget()
            self._detached_preview_widget.set_control_hint_text(
                self._t(
                    'tool_editor.hint.rotate_pan_zoom',
                    'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
                )
            )
            self._detached_preview_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self._detached_preview_widget, 1)
        else:
            fallback = QLabel(self._t('tool_library.preview.unavailable', 'Preview component not available.'))
            fallback.setWordWrap(True)
            fallback.setAlignment(Qt.AlignCenter)
            self._detached_preview_widget = None
            fallback.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(fallback, 1)

        self._detached_preview_dialog = dialog
        self._refresh_detached_measurement_controls([])

    def _apply_detached_preview_default_bounds(self):
        if self._detached_preview_dialog is None:
            return
        host_window = self.window()
        if host_window is None:
            return

        host_frame = host_window.frameGeometry()
        if host_frame.width() <= 0 or host_frame.height() <= 0:
            return

        width = max(520, int(host_frame.width() * 0.37))
        width = min(width, 700)
        max_height = max(420, host_frame.height() - 30)
        height = max(600, int(host_frame.height() * 0.86))
        height = min(height, max_height)

        x = host_frame.right() - width + 1
        y = host_frame.bottom() - height + 1
        min_y = host_frame.top() + 30
        if y < min_y:
            y = min_y

        self._detached_preview_dialog.setGeometry(x, y, width, height)

    def _update_detached_measurement_toggle_icon(self, enabled: bool):
        if self._measurement_toggle_btn is None:
            return
        is_enabled = bool(enabled)
        icon_name = 'comment_disable.svg' if is_enabled else 'comment.svg'
        self._measurement_toggle_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
        tooltip = self._t(
            'tool_library.preview.measurements_hide' if is_enabled else 'tool_library.preview.measurements_show',
            'Piilota mittaukset' if is_enabled else 'Näytä mittaukset',
        )
        self._measurement_toggle_btn.setToolTip(tooltip)

    def _on_detached_preview_closed(self, _result):
        if self._detached_preview_widget is not None:
            self._detached_preview_widget.set_measurement_focus_index(-1)
        self._detached_preview_last_model_key = None
        self._set_preview_button_checked(False)

    def _refresh_detached_measurement_controls(self, overlays):
        if self._measurement_toggle_btn is None:
            return

        names = []
        seen = set()
        for overlay in overlays or []:
            if not isinstance(overlay, dict):
                continue
            name = str(overlay.get('name') or '').strip()
            if not name or name in seen:
                continue
            names.append(name)
            seen.add(name)

        has_measurements = bool(names)
        self._measurement_toggle_btn.setEnabled(has_measurements)

        self._measurement_toggle_btn.blockSignals(True)
        self._measurement_toggle_btn.setChecked(self._detached_measurements_enabled and has_measurements)
        self._measurement_toggle_btn.blockSignals(False)
        self._update_detached_measurement_toggle_icon(self._measurement_toggle_btn.isChecked())
        self._detached_measurement_filter = None

    def _apply_detached_measurement_state(self, overlays):
        if self._detached_preview_widget is None:
            return
        self._detached_preview_widget.set_measurement_overlays(overlays or [])
        self._detached_preview_widget.set_measurements_visible(
            bool(overlays) and self._detached_measurements_enabled
        )
        self._detached_preview_widget.set_measurement_filter(self._detached_measurement_filter)

    def _on_detached_measurements_toggled(self, checked: bool):
        self._detached_measurements_enabled = bool(checked)
        self._update_detached_measurement_toggle_icon(self._detached_measurements_enabled)
        if self._detached_preview_widget is not None:
            self._detached_preview_widget.set_measurements_visible(self._detached_measurements_enabled)

    def _close_detached_preview(self):
        if self._detached_preview_dialog is not None:
            self._detached_preview_dialog.close()
        else:
            self._set_preview_button_checked(False)

    def _sync_detached_preview(self, show_errors: bool = False) -> bool:
        if not self.preview_window_btn.isChecked():
            return False

        if not self.current_tool_id:
            self._close_detached_preview()
            return False

        tool = self._get_selected_tool()
        if not tool:
            self._close_detached_preview()
            return False

        stl_path = tool.get('stl_path')
        if not stl_path:
            if show_errors:
                QMessageBox.information(
                    self,
                    self._t('tool_library.preview.window_title', '3D Preview'),
                    self._t('tool_library.preview.none_assigned_selected', 'The selected tool has no 3D model assigned.'),
                )
            self._close_detached_preview()
            return False

        self._ensure_detached_preview_dialog()
        was_visible = bool(self._detached_preview_dialog and self._detached_preview_dialog.isVisible())
        label = tool.get('description', '').strip() or tool.get('id', '3D Preview')
        raw_model_key = stl_path if isinstance(stl_path, str) else json.dumps(stl_path, ensure_ascii=False, sort_keys=True)
        model_key = (
            int(tool.get('uid')) if str(tool.get('uid', '')).strip().isdigit() else str(tool.get('id') or '').strip(),
            str(raw_model_key or ''),
        )
        loaded = True
        if self._detached_preview_last_model_key != model_key:
            loaded = self._load_preview_content(self._detached_preview_widget, stl_path, label=label)
            if loaded:
                self._detached_preview_last_model_key = model_key
            else:
                self._detached_preview_last_model_key = None
        if not loaded:
            if show_errors:
                QMessageBox.information(
                    self,
                    self._t('tool_library.preview.window_title', '3D Preview'),
                    self._t('tool_library.preview.no_valid_selected', 'No valid 3D model data found for the selected tool.'),
                )
            self._close_detached_preview()
            return False

        overlays = tool.get('measurement_overlays', []) if isinstance(tool, dict) else []
        self._refresh_detached_measurement_controls(overlays)
        self._apply_detached_measurement_state(overlays)

        tool_id = self._tool_id_display_value(tool.get('id', ''))
        self._detached_preview_dialog.setWindowTitle(
            self._t('tool_library.preview.window_title_tool', '3D Preview - {tool_id}', tool_id=tool_id).rstrip(' -')
        )
        if not was_visible:
            self._apply_detached_preview_default_bounds()
            self._detached_preview_dialog.show()
            self._detached_preview_dialog.raise_()
            self._detached_preview_dialog.activateWindow()
        self._set_preview_button_checked(True)
        return True

    def toggle_preview_window(self):
        if self.preview_window_btn.isChecked():
            if not self._sync_detached_preview(show_errors=True):
                self._set_preview_button_checked(False)
            return

        self._close_detached_preview()

    def select_tool_by_id(self, tool_id: str):
        """Navigate the list to the tool with the given id."""
        self.current_tool_id = tool_id.strip()
        self.current_tool_uid = None
        self.refresh_list()
        for row in range(self._tool_model.rowCount()):
            idx = self._tool_model.index(row, 0)
            if idx.data(ROLE_TOOL_ID) == self.current_tool_id:
                self.tool_list.setCurrentIndex(idx)
                self.tool_list.scrollTo(idx)
                break

    def _get_selected_tool(self):
        if self.current_tool_uid is not None:
            tool = self.tool_service.get_tool_by_uid(self.current_tool_uid)
            if tool:
                return tool
        if self.current_tool_id:
            return self.tool_service.get_tool(self.current_tool_id)
        return None

    def refresh_list(self):
        # bail if UI hasn't been built yet
        if not hasattr(self, 'tool_list'):
            return
        tools = self.tool_service.list_tools(
            self.search.text(),
            self.type_filter.currentData() or 'All',
            self._selected_head_filter(),
        )
        if self._selector_active:
            tools = [tool for tool in tools if self._tool_matches_selector_spindle(tool)]
        if self._master_filter_active:
            tools = [tool for tool in tools if str(tool.get('id', '')).strip() in self._master_filter_ids]
        tools = [tool for tool in tools if self._view_match(tool)]
        self._tool_model.blockSignals(True)
        self._tool_model.clear()
        for tool in tools:
            item = QStandardItem()
            tool_id = tool.get('id', '')
            tool_uid = tool.get('uid')
            item.setData(tool_id, ROLE_TOOL_ID)
            item.setData(tool_uid, ROLE_TOOL_UID)
            item.setData(tool, ROLE_TOOL_DATA)
            item.setData(tool_icon_for_type(tool.get('tool_type', '')), ROLE_TOOL_ICON)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            self._tool_model.appendRow(item)
        self._tool_model.blockSignals(False)
        # restore selection
        if self.current_tool_uid is not None:
            for row in range(self._tool_model.rowCount()):
                idx = self._tool_model.index(row, 0)
                if idx.data(ROLE_TOOL_UID) == self.current_tool_uid:
                    self.tool_list.setCurrentIndex(idx)
                    self.tool_list.scrollTo(idx)
                    break
        elif self.current_tool_id:
            for row in range(self._tool_model.rowCount()):
                idx = self._tool_model.index(row, 0)
                if idx.data(ROLE_TOOL_ID) == self.current_tool_id:
                    self.tool_list.setCurrentIndex(idx)
                    self.tool_list.scrollTo(idx)
                    break

        # Force immediate relayout/repaint so head-filter changes are visible
        # without requiring a hover/mouse-move over the list viewport.
        self.tool_list.doItemsLayout()
        self.tool_list.viewport().update()
        self.tool_list.viewport().repaint()

    def _view_match(self, tool: dict) -> bool:
        if self.view_mode == 'holders':
            return bool((tool.get('holder_code', '') or '').strip())

        if self.view_mode == 'inserts':
            return bool((tool.get('cutting_code', '') or '').strip())

        if self.view_mode == 'assemblies':
            support_parts = tool.get('support_parts', [])
            if isinstance(support_parts, str):
                try:
                    support_parts = json.loads(support_parts or '[]')
                except Exception:
                    support_parts = []

            stl_parts = []
            stl_data = tool.get('stl_path', '')
            if isinstance(stl_data, str) and stl_data.strip():
                try:
                    parsed = json.loads(stl_data)
                    stl_parts = parsed if isinstance(parsed, list) else []
                except Exception:
                    stl_parts = []

            return len(support_parts) > 0 or len(stl_parts) > 1

        # home/tools/export pages use full list
        return True

    def toggle_details(self):
        if self._details_hidden:
            if not self.current_tool_id:
                QMessageBox.information(self, self._t('tool_library.message.show_details', 'Show details'), self._t('tool_library.message.select_tool_first', 'Select a tool first.'))
                return
            tool = self._get_selected_tool()
            self.populate_details(tool)
            self.show_details()
        else:
            self.hide_details()

    def show_details(self):
        if self._selector_active:
            self._set_selector_panel_mode('details')
            return
        self._details_hidden = False
        self.detail_container.show()
        self.detail_header_container.show()
        self.toggle_details_btn.setText(self._t('tool_library.details.hide', 'HIDE DETAILS'))
        if not self._last_splitter_sizes:
            total = max(600, self.splitter.width())
            self._last_splitter_sizes = [int(total * 0.62), int(total * 0.38)]
        self.splitter.setSizes(self._last_splitter_sizes)
        self._update_row_type_visibility(False)

    def hide_details(self):
        if self._selector_active:
            self._set_selector_panel_mode('selector')
            return
        self._details_hidden = True
        if self.detail_container.isVisible():
            self._last_splitter_sizes = self.splitter.sizes()
        self.detail_container.hide()
        self.detail_header_container.hide()
        self.toggle_details_btn.setText(self._t('tool_library.details.show', 'SHOW DETAILS'))
        self.splitter.setSizes([1, 0])
        self._update_row_type_visibility(True)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if getattr(obj, 'property', None) and obj.property('elideGroupTitle'):
            if event.type() in (QEvent.Resize, QEvent.Show, QEvent.FontChange):
                self._refresh_elided_group_title(obj)
        if obj is getattr(self, 'type_filter', None) or (
                getattr(self, 'type_filter', None) and obj is self.type_filter.view()):
            # if we are currently suppressing, swallow any show events
            if getattr(self, '_suppress_combo', False) and event.type() in (QEvent.Show, QEvent.ShowToParent):
                return True
        # clear selection when clicking on empty area of the tool list or its viewport
        if obj in (getattr(self, 'tool_list', None),
                   getattr(self, 'tool_list', None) and self.tool_list.viewport()):
            if event.type() == QEvent.MouseButtonPress:
                # coordinate is in viewport space either way
                if not self.tool_list.indexAt(event.pos()).isValid():
                    self._clear_selection()
        return super().eventFilter(obj, event)

    def _refresh_elided_group_title(self, group):
        if group is None or not hasattr(group, 'setTitle'):
            return
        full_title = str(group.property('fullGroupTitle') or group.title() or '').strip()
        if not full_title:
            return
        available = max(12, group.width() - 30)
        elided = QFontMetrics(group.font()).elidedText(full_title, Qt.ElideRight, available)
        group.setTitle(elided)
        group.setToolTip(full_title)

    def _clear_selection(self):
        """Internal helper to clear row selection and reset details."""
        details_were_open = not self._details_hidden
        if hasattr(self, 'tool_list'):
            self.tool_list.selectionModel().clearSelection()
            self.tool_list.setCurrentIndex(QModelIndex())
        self.current_tool_id = None
        self.current_tool_uid = None
        self._update_selection_count_label()
        self.populate_details(None)
        if details_were_open:
            self.hide_details()
        if hasattr(self, 'preview_window_btn') and self.preview_window_btn.isChecked():
            self._close_detached_preview()

    def _selected_tool_uids(self) -> list[int]:
        model = self.tool_list.selectionModel()
        if model is None:
            return []
        indexes = sorted(model.selectedIndexes(), key=lambda idx: idx.row())
        uids: list[int] = []
        for index in indexes:
            uid = index.data(ROLE_TOOL_UID)
            if uid is None:
                continue
            try:
                parsed = int(uid)
            except Exception:
                continue
            if parsed not in uids:
                uids.append(parsed)
        return uids

    def selected_tools_for_setup_assignment(self) -> list[dict]:
        model = self.tool_list.selectionModel()
        if model is None:
            return []
        indexes = sorted(model.selectedIndexes(), key=lambda idx: idx.row())
        payload: list[dict] = []
        for index in indexes:
            tool_id = str(index.data(ROLE_TOOL_ID) or '').strip()
            tool_uid = index.data(ROLE_TOOL_UID)
            try:
                parsed_uid = int(tool_uid) if tool_uid is not None else None
            except Exception:
                parsed_uid = None
            payload.append({
                'tool_id': tool_id,
                'tool_uid': parsed_uid,
            })
        return payload

    def _on_multi_selection_changed(self, _selected, _deselected):
        self._update_selection_count_label()

    def _update_selection_count_label(self):
        count = len(self._selected_tool_uids())
        if count > 1:
            self.selection_count_label.setText(
                self._t('tool_library.selection.count', '{count} selected', count=count)
            )
            self.selection_count_label.show()
            return
        self.selection_count_label.hide()

    @staticmethod
    def _prune_backups(db_path: Path, tag: str, keep: int = 5):
        prefix = f"{db_path.stem}_{tag}_"
        backups = sorted(
            db_path.parent.glob(f"{prefix}*.bak"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for stale in backups[keep:]:
            try:
                stale.unlink()
            except Exception:
                pass

    def _create_db_backup(self, tag: str) -> Path:
        db_path = Path(self.tool_service.db.path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = db_path.parent / f"{db_path.stem}_{tag}_{timestamp}.bak"
        shutil.copy2(db_path, backup_path)
        self._prune_backups(db_path, tag)
        return backup_path

    def _prompt_batch_cancel_behavior(self) -> str:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(self._t('tool_library.batch.cancel.title', 'Batch edit cancelled'))
        box.setText(
            self._t(
                'tool_library.batch.cancel.body',
                'You stopped editing partway through the batch. Do you want to keep the changes you\'ve already saved, or undo all of them?',
            )
        )
        keep_btn = box.addButton(
            self._t('tool_library.batch.cancel.keep', 'Keep'),
            QMessageBox.AcceptRole,
        )
        undo_btn = box.addButton(
            self._t('tool_library.batch.cancel.undo', 'Undo'),
            QMessageBox.DestructiveRole,
        )
        box.addButton(self._t('common.cancel', 'Cancel'), QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is undo_btn:
            return 'undo'
        if clicked is keep_btn:
            return 'keep'
        return 'keep'

    def _batch_edit_tools(self, uids: list[int]):
        saved_before: list[dict] = []
        total = len(uids)
        for idx, uid in enumerate(uids, 1):
            tool = self.tool_service.get_tool_by_uid(uid)
            if not tool:
                continue
            draft_tool = dict(tool)
            while True:
                dlg = AddEditToolDialog(
                    self,
                    tool=draft_tool,
                    tool_service=self.tool_service,
                    translate=self._t,
                    batch_label=f"{idx}/{total}",
                )
                if dlg.exec() != QDialog.Accepted:
                    if saved_before:
                        action = self._prompt_batch_cancel_behavior()
                        if action == 'undo':
                            for previous in reversed(saved_before):
                                self.tool_service.save_tool(previous, allow_duplicate=True)
                    self.refresh_list()
                    return
                result = self._save_from_dialog(dlg)
                if result == 'saved':
                    saved_before.append(tool)
                    break
                if result == 'retry':
                    draft_tool = dlg.get_tool_data()
                    draft_tool['uid'] = uid
                    continue
                self.refresh_list()
                return
        self.refresh_list()

    def _group_edit_tools(self, uids: list[int]):
        dlg = AddEditToolDialog(
            self,
            tool_service=self.tool_service,
            translate=self._t,
            group_edit_mode=True,
            group_count=len(uids),
        )
        baseline = dlg.get_tool_data()
        if dlg.exec() != QDialog.Accepted:
            return
        edited_data = dlg.get_tool_data()
        changed_fields = {
            key: value
            for key, value in edited_data.items()
            if value != baseline.get(key)
        }
        if not changed_fields:
            QMessageBox.information(
                self,
                self._t('tool_library.group_edit.no_changes_title', 'No changes'),
                self._t('tool_library.group_edit.no_changes_body', 'No fields were changed.'),
            )
            return

        self._create_db_backup('group_edit')
        for uid in uids:
            existing = self.tool_service.get_tool_by_uid(uid)
            if not existing:
                continue
            merged = dict(existing)
            merged.update(changed_fields)
            merged['uid'] = uid
            self.tool_service.save_tool(merged, allow_duplicate=True)
        self.refresh_list()

    def keyPressEvent(self, event):
        """Handle escape key to deselect any selected tool row."""
        from PySide6.QtCore import Qt as _Qt
        if event.key() == _Qt.Key_Escape:
            self._clear_selection()
            return
        super().keyPressEvent(event)

    def _on_type_changed(self, _index):
        # update filter icon based on whether a real filter is active
        active = (self.type_filter.currentData() or 'All') != 'All'
        icon_name = 'filter_off.svg' if active else 'filter_arrow_right.svg'
        self.filter_icon.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
        if active:
            # apply filter immediately
            self.refresh_list()
        else:
            # if filter cleared programmatically, restore list
            self.refresh_list()

    def _selected_head_filter(self) -> str:
        if self._external_head_filter is not None:
            raw = self._external_head_filter.currentData()
            if raw is not None:
                return str(raw)
            return self._external_head_filter.currentText()
        return self._head_filter_value

    def _localized_tool_type(self, raw_tool_type: str) -> str:
        key = f"tool_library.tool_type.{(raw_tool_type or '').strip().lower().replace('.', '_').replace('/', '_').replace(' ', '_')}"
        return self._t(key, raw_tool_type)

    def _localized_cutting_type(self, raw_cutting_type: str) -> str:
        key = f"tool_library.cutting_type.{(raw_cutting_type or '').strip().lower().replace(' ', '_')}"
        return self._t(key, raw_cutting_type)

    @staticmethod
    def _is_turning_drill_tool_type(raw_tool_type: str) -> bool:
        normalized = (raw_tool_type or '').strip().lower()
        return normalized in {'turn drill', 'turn spot drill', 'turn center drill'}

    @staticmethod
    def _is_mill_tool_type(raw_tool_type: str) -> bool:
        return (raw_tool_type or '').strip() in MILLING_TOOL_TYPES

    def _build_tool_type_filter_items(self):
        current_raw = self.type_filter.currentData() if hasattr(self, 'type_filter') and self.type_filter.count() else 'All'
        if not hasattr(self, 'type_filter'):
            return
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem(self._t('tool_library.filter.all', 'All'), 'All')
        for raw_type in ALL_TOOL_TYPES:
            self.type_filter.addItem(self._localized_tool_type(raw_type), raw_type)
        for idx in range(self.type_filter.count()):
            if self.type_filter.itemData(idx) == current_raw:
                self.type_filter.setCurrentIndex(idx)
                break
        if self.type_filter.count() and self.type_filter.currentIndex() < 0:
            self.type_filter.setCurrentIndex(0)
        self.type_filter.blockSignals(False)

    def bind_external_head_filter(self, combo: QWidget | None):
        self._external_head_filter = combo
        self.refresh_list()

    def set_head_filter_value(self, value: str, refresh: bool = True):
        normalized = (value or 'HEAD1/2').strip().upper()
        if normalized not in {'HEAD1/2', 'HEAD1', 'HEAD2'}:
            normalized = 'HEAD1/2'
        self._head_filter_value = normalized
        if refresh:
            self.refresh_list()

    def _clear_filter(self):
        # clicked the icon when filter active -> set back to All
        for idx in range(self.type_filter.count()):
            if self.type_filter.itemData(idx) == 'All':
                self.type_filter.setCurrentIndex(idx)
                break

    def _on_current_changed(self, current: QModelIndex, previous: QModelIndex):
        if not current.isValid():
            self.current_tool_id = None
            self.current_tool_uid = None
            self._update_selection_count_label()
            self.populate_details(None)
            if self.preview_window_btn.isChecked():
                self._close_detached_preview()
            return
        self.current_tool_id = current.data(ROLE_TOOL_ID)
        self.current_tool_uid = current.data(ROLE_TOOL_UID)
        self._update_selection_count_label()
        # if details pane is already visible, refresh its contents
        if not self._details_hidden:
            tool = self._get_selected_tool()
            self.populate_details(tool)
        if self.preview_window_btn.isChecked():
            self._sync_detached_preview(show_errors=False)

    def _on_double_clicked(self, index: QModelIndex):
        self.current_tool_id = index.data(ROLE_TOOL_ID)
        self.current_tool_uid = index.data(ROLE_TOOL_UID)
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.edit_tool()
            return
        # if detail window already open, close it; otherwise open/update
        if not self._details_hidden:
            self.hide_details()
        else:
            self.populate_details(self._get_selected_tool())
            self.show_details()

    # ==============================
    # Detail Panel Construction
    # ==============================
    def _clear_details(self):
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _build_placeholder_details(self):
        card = QFrame()
        card.setProperty('subCard', True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        title = QLabel(self._t('tool_library.section.tool_details', 'Tool details'))
        title.setProperty('detailSectionTitle', True)
        layout.addWidget(title)
        info = QLabel(self._t('tool_library.message.select_tool_for_details', 'Select a tool to view details.'))
        info.setProperty('detailHint', True)
        info.setWordWrap(True)
        layout.addWidget(info)
        preview = QFrame()
        preview.setProperty('diagramPanel', True)
        p = QVBoxLayout(preview)
        p.setContentsMargins(12, 12, 12, 12)
        p.addStretch(1)
        p.addStretch(1)
        layout.addWidget(preview)
        return card

    def populate_details(self, tool):
        self._clear_details()
        if not tool:
            self.detail_layout.addWidget(self._build_placeholder_details())
            return

        support_parts = tool.get('support_parts', []) if isinstance(tool.get('support_parts'), list) else json.loads(tool.get('support_parts', '[]') or '[]')

        card = QFrame()
        card.setProperty('subCard', True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QFrame()
        header.setProperty('detailHeader', True)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 14, 14, 12)
        header_layout.setSpacing(4)

        name_label = QLabel(tool.get('description', '').strip() or self._t('tool_library.common.no_description', 'No description'))
        name_label.setProperty('detailHeroTitle', True)
        name_label.setWordWrap(True)
        name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        tool_id_text = self._tool_id_display_value(tool.get('id', '')) or '-'
        id_label = QLabel(tool_id_text)
        id_label.setProperty('detailHeroTitle', True)
        id_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        title_row.addWidget(name_label, 1)
        title_row.addWidget(id_label, 0, Qt.AlignRight)

        meta_row = QHBoxLayout()
        badge = QLabel(self._localized_tool_type(tool.get('tool_type', '')))
        badge.setProperty('toolBadge', True)
        meta_row.addWidget(badge, 0, Qt.AlignLeft)
        tool_head = (tool.get('tool_head', 'HEAD1') or 'HEAD1').strip().upper()
        head_badge = QLabel(tool_head)
        head_badge.setProperty('toolBadge', True)
        meta_row.addStretch(1)
        meta_row.addWidget(head_badge, 0, Qt.AlignRight)
        header_layout.addLayout(title_row)
        header_layout.addLayout(meta_row)
        layout.addWidget(header)

        raw_cutting_type = tool.get('cutting_type', 'Insert')
        raw_tool_type = tool.get('tool_type', '')
        turning_drill_type = self._is_turning_drill_tool_type(raw_tool_type)

        # Build the information grid using 6 equal columns.
        # Two-box rows use 3+3 spans; three-box rows use 2+2+2 spans.
        info = QGridLayout()
        info.setHorizontalSpacing(6)
        info.setVerticalSpacing(8)
        info.setColumnStretch(0, 1)
        info.setColumnStretch(1, 1)
        info.setColumnStretch(2, 1)
        info.setColumnStretch(3, 1)

        info.setColumnStretch(4, 1)
        info.setColumnStretch(5, 1)

        angle_value = str(tool.get('drill_nose_angle', ''))
        if not angle_value.strip():
            # Backward compatibility: older records may store point angle in nose_corner_radius.
            angle_value = str(tool.get('nose_corner_radius', ''))

        def _fallback_pair_row(left_label: str, left_value: str, right_label: str, right_value: str) -> None:
            info.addWidget(self._build_detail_field(left_label, left_value), 1, 0, 1, 3, Qt.AlignTop)
            info.addWidget(self._build_detail_field(right_label, right_value), 1, 3, 1, 3, Qt.AlignTop)

        full_row = apply_tool_detail_layout_rules(
            tool=tool,
            tool_head=tool_head,
            raw_tool_type=raw_tool_type,
            raw_cutting_type=raw_cutting_type,
            turning_drill_type=turning_drill_type,
            angle_value=angle_value,
            milling_tool_types=MILLING_TOOL_TYPES,
            turning_tool_types=TURNING_TOOL_TYPES,
            add_two_box_row=lambda row, ll, lv, rl, rv: self._add_two_box_row(info, row, ll, lv, rl, rv),
            add_three_box_row=lambda row, l1, v1, l2, v2, l3, v3: self._add_three_box_row(
                info, row, l1, v1, l2, v2, l3, v3
            ),
            add_fallback_pair_row=_fallback_pair_row,
            translate=self._t,
        )

        # notes field - spans full width
        notes_text = tool.get('notes', tool.get('spare_parts', ''))
        if notes_text:
            notes_field = self._build_detail_field(self._t('tool_library.field.notes', 'Notes'), notes_text, multiline=True)
            info.addWidget(notes_field, full_row, 0, 1, 6)
        layout.addLayout(info)
        layout.addWidget(self._build_components_panel(tool, support_parts))
        layout.addWidget(self._build_preview_panel(tool.get('stl_path')))
        layout.addStretch(1)
        self.detail_layout.addWidget(card)

    def _build_detail_field(self, label_text: str, value_text: str, multiline: bool = False) -> QWidget:
        return build_detail_field_widget(
            page=self,
            label_text=label_text,
            value_text=value_text,
            multiline=multiline,
        )

    def _add_two_box_row(
        self,
        info: QGridLayout,
        row: int,
        left_label: str,
        left_value: str,
        right_label: str,
        right_value: str,
    ) -> None:
        build_two_box_row(
            info=info,
            row=row,
            left_label=left_label,
            left_value=left_value,
            right_label=right_label,
            right_value=right_value,
            build_field=lambda label, value: self._build_detail_field(label, value),
        )

    def _add_three_box_row(
        self,
        info: QGridLayout,
        row: int,
        first_label: str,
        first_value: str,
        second_label: str,
        second_value: str,
        third_label: str,
        third_value: str,
    ) -> None:
        build_three_box_row(
            info=info,
            row=row,
            first_label=first_label,
            first_value=first_value,
            second_label=second_label,
            second_value=second_value,
            third_label=third_label,
            third_value=third_value,
            build_field=lambda label, value: self._build_detail_field(label, value),
        )

    # ==============================
    # Detail Panel Sections
    # ==============================
    def _build_components_panel(self, tool, support_parts):
        return build_components_panel(self, tool, support_parts)

    def _build_preview_panel(self, stl_path: str | None = None):
        return build_preview_panel(
            page=self,
            stl_path=stl_path,
            stl_preview_widget_cls=StlPreviewWidget,
            load_preview_content=self._load_preview_content,
        )


    # ==============================
    # Dialogs + CRUD Actions
    # ==============================
    def part_clicked(self, part):
        link = (part.get('link', '') or '').strip()
        if not link:
            QMessageBox.information(
                self,
                self._t('tool_library.part.title', 'Tool component'),
                self._t('tool_library.part.no_link', 'No link set for: {name}', name=part.get('name', self._t('tool_library.field.part', 'Part'))),
            )
            return

        url = QUrl.fromUserInput(link)
        if not url.isValid() or not url.scheme():
            QMessageBox.warning(
                self,
                self._t('tool_library.part.title', 'Tool component'),
                self._t('tool_library.part.invalid_link', 'Invalid link: {link}', link=link),
            )
            return
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(
                self,
                self._t('tool_library.part.title', 'Tool component'),
                self._t('tool_library.part.open_failed', 'Unable to open link: {link}', link=link),
            )

    def _save_from_dialog(self, dlg):
        try:
            data = dlg.get_tool_data()
            source_uid = data.get('uid')
            is_new_tool = source_uid is None

            if is_new_tool and self.tool_service.tcode_exists(data['id'], exclude_uid=data.get('uid')):
                confirm_text = (
                    self._t(
                        'tool_library.warning.duplicate_tcode',
                        'This T-code already exists, want to save the tool anyway?\n\n'
                        'This does not overwrite or replace the existing tool.',
                    )
                )
                if not self._confirm_yes_no(
                    self._t('tool_library.warning.duplicate_tcode_title', 'Duplicate T-code'),
                    confirm_text,
                    danger=False,
                ):
                    return 'retry'

            saved_uid = self.tool_service.save_tool(data, allow_duplicate=True)
            saved_tool = self.tool_service.get_tool_by_uid(saved_uid)
            self.current_tool_uid = saved_uid
            self.current_tool_id = (saved_tool or {}).get('id', data['id'])
            self.refresh_list()
            self.populate_details(saved_tool)
            if self.preview_window_btn.isChecked():
                self._sync_detached_preview(show_errors=False)
            return 'saved'
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))
            return 'error'

    def _open_tool_editor(self, tool=None):
        draft_tool = tool
        while True:
            dlg = AddEditToolDialog(self, tool=draft_tool, tool_service=self.tool_service, translate=self._t)
            if dlg.exec() != QDialog.Accepted:
                return
            result = self._save_from_dialog(dlg)
            if result == 'saved':
                return
            if result == 'retry':
                draft_tool = dlg.get_tool_data()
                draft_tool.pop('uid', None)
                continue
            return

    def add_tool(self):
        self._open_tool_editor()

    def edit_tool(self):
        selected_uids = self._selected_tool_uids()
        if not selected_uids:
            QMessageBox.information(
                self,
                self._t('tool_library.action.edit_tool_title', 'Edit tool'),
                self._t('tool_library.message.select_tool_first', 'Select a tool first.'),
            )
            return
        if len(selected_uids) > 1:
            mode = ask_multi_edit_mode(self, len(selected_uids), self._t)
            if mode == 'batch':
                self._batch_edit_tools(selected_uids)
            elif mode == 'group':
                self._group_edit_tools(selected_uids)
            return
        tool = self.tool_service.get_tool_by_uid(selected_uids[0])
        self._open_tool_editor(tool=tool)

    def apply_localization(self, translate=None):
        if translate is not None:
            self._translate = translate
        if hasattr(self, 'toolbar_title_label'):
            self.toolbar_title_label.setText(self.page_title)
        if hasattr(self, 'search'):
            self.search.setPlaceholderText(self._t('tool_library.search.placeholder', 'Tool ID, description, holder or cutting code'))
        if hasattr(self, 'detail_section_label'):
            self.detail_section_label.setText(self._t('tool_library.section.tool_details', 'Tool details'))
        if hasattr(self, 'selector_toggle_btn'):
            if self._selector_active and self._selector_panel_mode == 'selector':
                self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_details', 'DETAILS'))
            else:
                self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_selector', 'SELECTOR'))
        if hasattr(self, 'selector_drop_hint'):
            self.selector_drop_hint.setText(
                self._t(
                    'tool_library.selector.drop_hint',
                    'Drag tools from the catalog to this list and reorder them by dragging.',
                )
            )
        if hasattr(self, 'selector_header_title_label'):
            self.selector_header_title_label.setText(self._t('tool_library.selector.header_title', 'Tool Selector'))
        self._update_selector_context_header()
        self._update_selector_assignments_section_title()
        if hasattr(self, 'module_switch_label'):
            self.module_switch_label.setText(self._t('tool_library.module.switch_to', 'Switch to'))
        if hasattr(self, 'copy_btn'):
            self.copy_btn.setText(self._t('tool_library.action.copy_tool', 'COPY TOOL'))
        if hasattr(self, 'edit_btn'):
            self.edit_btn.setText(self._t('tool_library.action.edit_tool', 'EDIT TOOL'))
        if hasattr(self, 'delete_btn'):
            self.delete_btn.setText(self._t('tool_library.action.delete_tool', 'DELETE TOOL'))
        if hasattr(self, 'add_btn'):
            self.add_btn.setText(self._t('tool_library.action.add_tool', 'ADD TOOL'))
        if hasattr(self, 'preview_window_btn'):
            self.preview_window_btn.setToolTip(self._t('tool_library.preview.toggle', 'Toggle detached 3D preview'))
        if hasattr(self, 'type_filter'):
            self._build_tool_type_filter_items()
        if hasattr(self, 'selector_clear_btn'):
            self.selector_clear_btn.setText(self._t('tool_library.selector.clear', 'Clear'))
        if hasattr(self, 'selector_done_btn'):
            self.selector_done_btn.setText(self._t('tool_library.selector.done', 'DONE'))
        if hasattr(self, 'selector_cancel_btn'):
            self.selector_cancel_btn.setText(self._t('tool_library.selector.cancel', 'CANCEL'))
        if hasattr(self, 'selector_move_up_btn'):
            self.selector_move_up_btn.setToolTip(self._t('tool_library.selector.move_up', 'Move Up'))
        if hasattr(self, 'selector_move_down_btn'):
            self.selector_move_down_btn.setToolTip(self._t('tool_library.selector.move_down', 'Move Down'))
        if hasattr(self, 'selector_remove_btn'):
            self.selector_remove_btn.setToolTip(self._t('tool_library.selector.remove', 'Remove'))
        if hasattr(self, 'selector_comment_btn'):
            self.selector_comment_btn.setToolTip(self._t('tool_library.selector.add_comment', 'Add Comment'))
        if hasattr(self, 'selector_delete_comment_btn'):
            self.selector_delete_comment_btn.setToolTip(self._t('tool_library.selector.delete_comment', 'Delete Comment'))
        self._update_selection_count_label()
        self._refresh_selector_assignment_rows()
        update_selector_assignment_buttons(self)
        self.refresh_list()
        if self.current_tool_id or self.current_tool_uid is not None:
            self.populate_details(self._get_selected_tool())
        else:
            self.populate_details(None)

    def copy_tool(self):
        if not self.current_tool_id:
            QMessageBox.information(
                self,
                self._t('tool_library.action.copy_tool_title', 'Copy tool'),
                self._t('tool_library.message.select_tool_first', 'Select a tool first.'),
            )
            return
        new_id, ok = self._prompt_text(
            self._t('tool_library.action.copy_tool_title', 'Copy tool'),
            self._t('tool_library.prompt.new_tool_id', 'New Tool ID:'),
        )
        if not ok or not new_id.strip():
            return
        new_id_storage = self._tool_id_storage_value(new_id)
        if not new_id_storage:
            QMessageBox.warning(
                self,
                self._t('tool_library.action.copy_tool_title', 'Copy tool'),
                self._t('tool_editor.error.tool_id_required', 'Tool ID is required.'),
            )
            return
        new_desc, _ = self._prompt_text(
            self._t('tool_library.action.copy_tool_title', 'Copy tool'),
            self._t('tool_library.prompt.new_description_optional', 'New description (optional):'),
        )
        allow_duplicate = False
        if self.tool_service.tcode_exists(new_id_storage):
            confirm_text = self._t(
                'tool_library.warning.duplicate_tcode',
                'This T-code already exists, want to save the tool anyway?\n\n'
                'This does not overwrite or replace the existing tool.',
            )
            if not self._confirm_yes_no(
                self._t('tool_library.warning.duplicate_tcode_title', 'Duplicate T-code'),
                confirm_text,
                danger=False,
            ):
                return
            allow_duplicate = True
        try:
            if self.current_tool_uid is not None:
                copied = self.tool_service.copy_tool_by_uid(
                    self.current_tool_uid,
                    new_id_storage,
                    new_desc,
                    allow_duplicate=allow_duplicate,
                )
            else:
                copied = self.tool_service.copy_tool(
                    self.current_tool_id,
                    new_id_storage,
                    new_desc,
                    allow_duplicate=allow_duplicate,
                )
            self.current_tool_uid = copied.get('uid') if isinstance(copied, dict) else None
            self.current_tool_id = (copied.get('id') if isinstance(copied, dict) else '') or new_id_storage
            self.refresh_list()
            self.populate_details(self._get_selected_tool())
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.action.copy_tool_title', 'Copy tool'), str(exc))

    def _prompt_text(self, title: str, label: str, initial: str = '') -> tuple[str, bool]:
        dlg = QDialog(self)
        setup_editor_dialog(dlg)
        dlg.setWindowTitle(title)
        dlg.setModal(True)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        prompt = QLabel(label)
        prompt.setProperty('detailFieldKey', True)
        prompt.setWordWrap(True)
        root.addWidget(prompt)

        editor = QLineEdit()
        editor.setText(initial)
        root.addWidget(editor)

        buttons = create_dialog_buttons(
            dlg,
            save_text=self._t('common.ok', 'OK'),
            cancel_text=self._t('common.cancel', 'Cancel'),
            on_save=dlg.accept,
            on_cancel=dlg.reject,
        )
        root.addWidget(buttons)

        apply_secondary_button_theme(dlg, buttons.button(QDialogButtonBox.Save))
        editor.setFocus()
        editor.selectAll()

        accepted = dlg.exec() == QDialog.Accepted
        return editor.text(), accepted

    def _confirm_yes_no(self, title: str, text: str, *, danger: bool) -> bool:
        box = QMessageBox(self)
        setup_editor_dialog(box)
        box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
        box.setWindowTitle(title)
        main_text = text
        info_text = ''
        if '\n\n' in text:
            main_text, info_text = text.split('\n\n', 1)
        box.setText(main_text)
        if info_text:
            box.setInformativeText(info_text)
            # Style only the secondary line to be subtler.
            box.setStyleSheet(
                '#qt_msgbox_informativelabel { font-style: italic; font-weight: 400; color: #5f6a74; }'
            )
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        yes_btn = box.button(QMessageBox.Yes)
        no_btn = box.button(QMessageBox.No)
        if yes_btn is not None:
            yes_btn.setText(self._t('common.yes', 'Yes'))
            yes_btn.setProperty('panelActionButton', True)
            yes_btn.setProperty('dangerAction', bool(danger))
            yes_btn.setProperty('primaryAction', not danger)
        if no_btn is not None:
            no_btn.setText(self._t('common.no', 'No'))
            no_btn.setProperty('panelActionButton', True)
            no_btn.setProperty('secondaryAction', True)

        return box.exec() == QMessageBox.Yes

    def delete_tool(self):
        if not self.current_tool_id:
            QMessageBox.information(
                self,
                self._t('tool_library.action.delete_tool_title', 'Delete tool'),
                self._t('tool_library.message.select_tool_first', 'Select a tool first.'),
            )
            return
        if self._confirm_yes_no(
            self._t('tool_library.action.delete_tool_title', 'Delete tool'),
            self._t('tool_library.prompt.delete_tool', 'Delete tool {tool_id}?', tool_id=self.current_tool_id),
            danger=True,
        ):
            if self.current_tool_uid is not None:
                self.tool_service.delete_tool_by_uid(self.current_tool_uid)
            else:
                self.tool_service.delete_tool(self.current_tool_id)
            self.current_tool_id = None
            self.current_tool_uid = None
            self.refresh_list()
            self.populate_details(None)
            if self.preview_window_btn.isChecked():
                self._close_detached_preview()

    def export_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._t('tool_library.export.title', 'Export to Excel'),
            str(EXPORT_DEFAULT_PATH),
            self._t('tool_library.export.filter_excel', 'Excel (*.xlsx)'),
        )
        if not path:
            return
        try:
            self.export_service.export_tools(path, self.tool_service.list_tools())
            QMessageBox.information(
                self,
                self._t('tool_library.export.done_title', 'Export'),
                self._t('tool_library.export.done_body', 'Exported to\n{path}', path=path),
            )
        except Exception as exc:
            QMessageBox.critical(self, self._t('tool_library.export.failed_title', 'Export failed'), str(exc))

