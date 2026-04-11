import json
import numpy as np
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from typing import Callable

from PySide6.QtCore import QEvent, QModelIndex, QSize, Qt, QMimeData, Signal
from PySide6.QtGui import QColor, QDrag, QIcon, QImage, QPixmap, QStandardItem, QStandardItemModel, QTransform
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import TOOL_ICONS_DIR, SHARED_UI_PREFERENCES_PATH, PROJECTS_DIR
from ui.jaw_catalog_delegate import JawCatalogDelegate, ROLE_JAW_DATA, ROLE_JAW_ICON, ROLE_JAW_ID, jaw_icon_for_row
from ui.jaw_editor_dialog import AddEditJawDialog
from shared.editor_helpers import (
    apply_secondary_button_theme,
    apply_titled_section_style,
    ask_multi_edit_mode,
    build_titled_detail_field,
    build_titled_detail_list_field,
    create_titled_section,
    create_dialog_buttons,
    setup_editor_dialog,
    style_icon_action_button,
    style_panel_action_button,
)


def _load_transparent_icon(path, threshold: int = 220) -> QPixmap:
    """Load a PNG and replace near-white pixels with transparency using numpy."""
    img = QImage(str(path))
    if img.isNull():
        return QPixmap()
    img = img.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), dtype=np.uint8).copy().reshape((h, w, 4))
    # Format_ARGB32 memory layout on little-endian: [B, G, R, A]
    near_white = (arr[:, :, 2] >= threshold) & (arr[:, :, 1] >= threshold) & (arr[:, :, 0] >= threshold)
    arr[near_white, 3] = 0
    out = QImage(arr.tobytes(), w, h, w * 4, QImage.Format_ARGB32)
    return QPixmap.fromImage(out)


_DEFAULT_JAW_ICON = 'hard_jaw.png'


def _jaw_icon_pixmap(jaw: dict, icon_target_size: QSize) -> QPixmap:
    icon_path = TOOL_ICONS_DIR / _DEFAULT_JAW_ICON
    spindle_side = (jaw.get('spindle_side') or '').strip()
    if icon_path.exists():
        pixmap = _load_transparent_icon(icon_path)
        if spindle_side == 'Sub spindle':
            pixmap = pixmap.transformed(QTransform().scale(-1, 1), Qt.SmoothTransformation)
        return pixmap.scaled(icon_target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return QIcon(str(TOOL_ICONS_DIR / 'jaw_icon.png')).pixmap(icon_target_size)
from ui.stl_preview import StlPreviewWidget
from ui.widgets.common import AutoShrinkLabel, add_shadow, apply_shared_dropdown_style, repolish_widget
from shared.mini_assignment_card import MiniAssignmentCard

SELECTOR_JAW_MIME = 'application/x-tool-library-jaw-assignment'


class _JawCatalogListView(QListView):
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
            jaw_id = str(index.data(ROLE_JAW_ID) or '').strip()
            if not jaw_id:
                continue
            jaw_data = index.data(ROLE_JAW_DATA) or {}
            payload.append(
                {
                    'jaw_id': jaw_id,
                    'jaw_type': str(jaw_data.get('jaw_type') if isinstance(jaw_data, dict) else '').strip(),
                }
            )
        if not payload:
            return
        mime = QMimeData()
        mime.setData(SELECTOR_JAW_MIME, json.dumps(payload).encode('utf-8'))
        drag = QDrag(self)
        drag.setMimeData(mime)

        # Build a semi-transparent ghost card showing the first jaw
        first = payload[0]
        ghost_text = first.get('jaw_id', '')
        jaw_type = first.get('jaw_type', '')
        if jaw_type:
            ghost_text = f'{ghost_text} - {jaw_type}'
        if len(payload) > 1:
            ghost_text += f'  (+{len(payload) - 1})'
        from PySide6.QtGui import QFont, QPainter
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
        font = QFont()
        font.setPointSizeF(9.0)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.drawText(10, 4, 200, 32, Qt.AlignVCenter | Qt.TextSingleLine, ghost_text)
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())

        drag.exec(Qt.CopyAction)


class _JawAssignmentSlot(QGroupBox):
    jawDropped = Signal(str, dict)
    slotClicked = Signal(str, bool)

    def __init__(self, slot_key: str, title: str, parent=None):
        super().__init__(parent)
        self._slot_key = slot_key
        self._assignment: dict | None = None
        self._drop_placeholder = 'Drop jaw here'
        self._assignment_card: MiniAssignmentCard | None = None
        self._selected = False
        self._content_height = 38
        self._drag_start_pos = None
        self.setAcceptDrops(True)
        self.setProperty('toolIdsPanel', True)
        apply_titled_section_style(self)
        self.setTitle(title)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(6)

        self.value_label = QLabel('')
        self.value_label.setProperty('detailHint', True)
        self.value_label.setWordWrap(False)
        self.value_label.setFixedHeight(self._content_height)
        self.value_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.value_label)
        self._refresh_ui()

    def set_title(self, title: str):
        self.setTitle(title)

    def set_drop_placeholder_text(self, text: str):
        self._drop_placeholder = str(text or 'Drop jaw here')
        self._refresh_ui()

    def set_selected(self, selected: bool):
        self._selected = bool(selected)
        if self._assignment_card is not None:
            self._assignment_card.set_selected(self._selected)

    def is_selected(self) -> bool:
        return self._selected

    def assignment(self) -> dict | None:
        return dict(self._assignment) if isinstance(self._assignment, dict) else None

    def set_assignment(self, jaw: dict | None):
        normalized = None
        if isinstance(jaw, dict):
            jaw_id = str(jaw.get('jaw_id') or jaw.get('id') or '').strip()
            if jaw_id:
                normalized = {
                    'jaw_id': jaw_id,
                    'jaw_type': str(jaw.get('jaw_type') or '').strip(),
                }
        self._assignment = normalized
        self._refresh_ui()

    def _refresh_ui(self):
        if isinstance(self._assignment, dict):
            jaw_id = str(self._assignment.get('jaw_id') or '').strip()
            jaw_type = str(self._assignment.get('jaw_type') or '').strip()
            title = f'{jaw_id}  -  {jaw_type}' if jaw_type else jaw_id
            if self._assignment_card is None:
                icon = jaw_icon_for_row(self._assignment)
                self._assignment_card = MiniAssignmentCard(
                    icon=icon,
                    title=title,
                    subtitle='',
                    badges=[],
                    editable=False,
                    compact=True,
                    parent=self,
                )
                self._assignment_card.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                self._assignment_card.setFixedHeight(self._content_height)
                self.layout().insertWidget(0, self._assignment_card)
            else:
                icon = jaw_icon_for_row(self._assignment)
                if icon is not None and not icon.isNull():
                    self._assignment_card.icon_label.setPixmap(icon.pixmap(QSize(22, 22)))
                self._assignment_card.title_label.setText(title)
                self._assignment_card.setFixedHeight(self._content_height)
            self._assignment_card.subtitle_label.setVisible(False)
            self._assignment_card.set_badges([])
            self._assignment_card.setVisible(True)
            self._assignment_card.set_selected(self._selected)
            self.value_label.setVisible(False)
            return
        self.value_label.setText(self._drop_placeholder)
        self.value_label.setVisible(True)
        if self._assignment_card is not None:
            self._assignment_card.setVisible(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        ctrl = bool(event.modifiers() & Qt.ControlModifier)
        self.slotClicked.emit(self._slot_key, ctrl)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(event)
        if self._assignment is None or self._drag_start_pos is None:
            return super().mouseMoveEvent(event)
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)

        payload = [dict(self._assignment)]
        mime = QMimeData()
        mime.setData(SELECTOR_JAW_MIME, json.dumps(payload).encode('utf-8'))

        drag = QDrag(self)
        drag.setMimeData(mime)

        ghost_source = self._assignment_card if self._assignment_card is not None else self
        ghost = ghost_source.grab()
        if not ghost.isNull():
            translucent = QPixmap(ghost.size())
            translucent.fill(Qt.transparent)
            painter = QPainter(translucent)
            painter.setOpacity(0.7)
            painter.drawPixmap(0, 0, ghost)
            painter.end()
            drag.setPixmap(translucent)
            drag.setHotSpot(translucent.rect().center())

        drag.exec(Qt.CopyAction)
        self._drag_start_pos = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    @staticmethod
    def _normalized_first_dropped_jaw(mime: QMimeData) -> dict | None:
        if not mime.hasFormat(SELECTOR_JAW_MIME):
            return None
        try:
            payload = json.loads(bytes(mime.data(SELECTOR_JAW_MIME)).decode('utf-8'))
        except Exception:
            payload = []
        if not isinstance(payload, list):
            return None
        for item in payload:
            if not isinstance(item, dict):
                continue
            jaw_id = str(item.get('jaw_id') or item.get('id') or '').strip()
            if not jaw_id:
                continue
            return {
                'jaw_id': jaw_id,
                'jaw_type': str(item.get('jaw_type') or '').strip(),
            }
        return None

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_JAW_MIME):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_JAW_MIME):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        jaw = self._normalized_first_dropped_jaw(event.mimeData())
        if jaw is None:
            event.ignore()
            return
        self.jawDropped.emit(self._slot_key, jaw)
        event.acceptProposedAction()


class _SelectorRemoveDropButton(QPushButton):
    jawsDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    @staticmethod
    def _payload_jaw_ids(mime: QMimeData) -> list[str]:
        if not mime.hasFormat(SELECTOR_JAW_MIME):
            return []
        try:
            payload = json.loads(bytes(mime.data(SELECTOR_JAW_MIME)).decode('utf-8'))
        except Exception:
            payload = []
        if not isinstance(payload, list):
            return []
        jaw_ids: list[str] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            jaw_id = str(item.get('jaw_id') or item.get('id') or '').strip()
            if jaw_id and jaw_id not in jaw_ids:
                jaw_ids.append(jaw_id)
        return jaw_ids

    def dragEnterEvent(self, event):
        if self._payload_jaw_ids(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if self._payload_jaw_ids(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        jaw_ids = self._payload_jaw_ids(event.mimeData())
        if not jaw_ids:
            event.ignore()
            return
        self.jawsDropped.emit(jaw_ids)
        event.acceptProposedAction()


CATALOG_CARD_HEIGHT = 74
CATALOG_ITEM_HEIGHT = 78


def _lookup_setup_db_used_in_works(jaw_id: str) -> str:
    """Return pipe-separated drawing IDs of Setup Manager works that use jaw_id."""
    if not jaw_id:
        return ''
    # Resolve Setup Manager DB path from shared preferences, then fall back to defaults.
    db_path: Path | None = None
    try:
        if SHARED_UI_PREFERENCES_PATH.exists():
            prefs = json.loads(SHARED_UI_PREFERENCES_PATH.read_text(encoding='utf-8'))
            candidate = str((prefs or {}).get('setup_db_path', '') or '').strip()
            if candidate:
                db_path = Path(candidate)
    except Exception:
        pass
    if db_path is None or not db_path.exists():
        # Fallback: sibling 'Setup Manager/databases/setup_manager.db'
        db_path = PROJECTS_DIR / 'Setup Manager' / 'databases' / 'setup_manager.db'
    if not db_path.exists():
        return ''
    try:
        uri = f'file:{db_path.as_posix()}?mode=ro&immutable=1'
        conn = sqlite3.connect(uri, uri=True)
        rows = conn.execute(
            'SELECT DISTINCT drawing_id FROM works '
            'WHERE (main_jaw_id = ? OR sub_jaw_id = ?) AND drawing_id != ""',
            (jaw_id, jaw_id),
        ).fetchall()
        conn.close()
        return ' | '.join(r[0] for r in rows if r[0])
    except Exception:
        return ''


class JawRowWidget(QFrame):
    def __init__(self, jaw: dict, parent=None, translate=None):
        super().__init__(parent)
        self.jaw = jaw
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self.setProperty('toolListCard', True)
        self.setProperty('catalogRowCard', True)
        self.setProperty('selected', False)
        self._val_labels: list[QLabel] = []
        self._head_labels: list[QLabel] = []
        self._col_layouts: list[QVBoxLayout] = []
        self._build_ui()

    def _card_columns(self):
        dash = '-'
        return [
            ('jaw_id', self._t('jaw_library.row.jaw_id', 'Jaw ID'), self.jaw.get('jaw_id', ''), 180),
            (
                'jaw_type',
                self._t('jaw_library.row.jaw_type', 'Jaw type'),
                self._t(
                    f"jaw_library.jaw_type.{(self.jaw.get('jaw_type') or '').strip().lower().replace(' ', '_')}",
                    self.jaw.get('jaw_type', ''),
                ),
                210,
            ),
            ('diameter', self._t('jaw_library.row.clamping_diameter', 'Clamping diameter'), self.jaw.get('clamping_diameter_text', '') or dash, 190),
            ('length', self._t('jaw_library.row.clamping_length', 'Clamping length'), self.jaw.get('clamping_length', '') or dash, 180),
        ]

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _value(self, text: str) -> QLabel:
        lbl = AutoShrinkLabel(text)
        lbl.setProperty('toolCardValue', True)
        lbl.setProperty('catalogRowValue', True)
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setProperty("catalogRowIcon", True)
        icon_target_size = QSize(40, 40)
        pixmap = _jaw_icon_pixmap(self.jaw, icon_target_size)
        icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet('background-color: transparent;')
        layout.addWidget(icon_label, 0, Qt.AlignVCenter)

        for _key, title, value, weight in self._card_columns():
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            self._col_layouts.append(col)

            head = QLabel(title)
            head.setProperty('toolCardHeader', True)
            head.setProperty('catalogRowHeader', True)
            head.setAlignment(Qt.AlignCenter)
            head.setWordWrap(True)

            val = self._value(value)

            wrap = QWidget()
            wrap.setProperty('toolCardColumn', True)
            wrap.setStyleSheet('background: transparent;')
            wrap.setLayout(col)
            wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

            col.addWidget(head)
            col.addWidget(val)
            layout.addWidget(wrap, weight, Qt.AlignVCenter)

            self._head_labels.append(head)
            self._val_labels.append(val)

        layout.addStretch(1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = event.size().width()
        lay = self.layout()
        if lay is None:
            return
        if w < 560:
            lay.setContentsMargins(7, 2, 7, 2)
            lay.setSpacing(7)
            v_size, h_size, col_spacing = 11.5, 8.6, 0
        else:
            lay.setContentsMargins(10, 2, 10, 2)
            lay.setSpacing(10)
            v_size, h_size, col_spacing = 12.8, 9.4, 0
        for col in self._col_layouts:
            col.setSpacing(col_spacing)
        for lbl in self._val_labels:
            f = lbl.font()
            f.setPointSizeF(v_size)
            lbl.setFont(f)
        for lbl in self._head_labels:
            f = lbl.font()
            f.setPointSizeF(h_size)
            lbl.setFont(f)


class ResponsiveJawRowWidget(QFrame):
    def __init__(self, jaw: dict, parent=None, translate=None):
        super().__init__(parent)
        self.jaw = jaw
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self.setProperty('toolListCard', True)
        self.setProperty('catalogRowCard', True)
        self.setProperty('selected', False)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._val_labels: list[QLabel] = []
        self._head_labels: list[QLabel] = []
        self._col_layouts: list[QVBoxLayout] = []
        self._column_wraps: dict[str, QWidget] = {}
        self._column_values: dict[str, QLabel] = {}
        self._column_texts: dict[str, str] = {}
        self._compact_breakpoint = 620
        self._reduced_breakpoint = 560
        self._single_column_breakpoint = 345
        self._icon_only_breakpoint = 220
        self._icon_label = None
        self._icon_wrap = None
        self._details_open_context = False
        self._build_ui()

    def _card_columns(self):
        dash = '-'
        jaw_type_text = self._t(
            f"jaw_library.jaw_type.{(self.jaw.get('jaw_type') or '').strip().lower().replace(' ', '_')}",
            self.jaw.get('jaw_type', ''),
        )
        return [
            ('jaw_id', self._t('jaw_library.row.jaw_id', 'Jaw ID'), self.jaw.get('jaw_id', ''), 180),
            ('jaw_type', self._t('jaw_library.row.jaw_type', 'Jaw type'), jaw_type_text, 210),
            ('diameter', self._t('jaw_library.row.clamping_diameter_multiline', 'Clamping\ndiameter'), self.jaw.get('clamping_diameter_text', '') or dash, 190),
            ('length', self._t('jaw_library.row.clamping_length_multiline', 'Clamping\nlength'), self.jaw.get('clamping_length', '') or dash, 180),
        ]

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _value(self, text: str) -> QLabel:
        lbl = AutoShrinkLabel(text)
        lbl.setProperty('toolCardValue', True)
        lbl.setProperty('catalogRowValue', True)
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    @staticmethod
    def _split_responsive_token(text: str) -> str:
        value = (text or '').strip()
        if not value or len(value) <= 8:
            return value
        if '-' in value:
            pivot = value.find('-') + 1
            if 1 < pivot < len(value):
                return f"{value[:pivot]}\n{value[pivot:]}"
        pivot = max(4, len(value) // 2)
        return f"{value[:pivot]}\n{value[pivot:]}"

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setProperty("catalogRowIcon", True)
        icon_target_size = QSize(40, 40)
        pixmap = _jaw_icon_pixmap(self.jaw, icon_target_size)
        icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet('background-color: transparent;')
        self._icon_label = icon_label
        icon_wrap = QWidget()
        icon_wrap.setStyleSheet('background-color: transparent;')
        icon_wrap_layout = QHBoxLayout(icon_wrap)
        icon_wrap_layout.setContentsMargins(0, 0, 0, 0)
        icon_wrap_layout.setSpacing(0)
        icon_wrap_layout.addStretch(1)
        icon_wrap_layout.addWidget(icon_label, 0, Qt.AlignVCenter)
        icon_wrap_layout.addStretch(1)
        icon_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self._icon_wrap = icon_wrap
        layout.addWidget(icon_wrap, 0, Qt.AlignVCenter)

        for key, title, value, weight in self._card_columns():
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(-2)
            self._col_layouts.append(col)

            head = QLabel(title)
            head.setProperty('toolCardHeader', True)
            head.setProperty('catalogRowHeader', True)
            head.setWordWrap(True)
            if key in {'diameter', 'length'}:
                head.setProperty('catalogRowHeaderWrap', True)
                head.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            else:
                head.setAlignment(Qt.AlignCenter)

            val = self._value(value)

            wrap = QWidget()
            wrap.setProperty('toolCardColumn', True)
            wrap.setStyleSheet('background: transparent;')
            wrap.setLayout(col)
            wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self._column_wraps[key] = wrap
            self._column_values[key] = val
            self._column_texts[key] = value

            col.addWidget(head)
            col.addWidget(val)
            layout.addWidget(wrap, weight, Qt.AlignVCenter)

            self._head_labels.append(head)
            self._val_labels.append(val)

        layout.addStretch(1)

    def _apply_column_visibility(self, width: int):
        if width <= 1:
            visible_keys = {'jaw_id', 'jaw_type', 'diameter', 'length'}
        elif width < self._single_column_breakpoint:
            visible_keys = {'jaw_id'}
        elif width < self._reduced_breakpoint:
            visible_keys = {'jaw_id', 'jaw_type', 'diameter'}
        else:
            visible_keys = {'jaw_id', 'jaw_type', 'diameter', 'length'}

        for key, wrap in self._column_wraps.items():
            wrap.setVisible(key in visible_keys)

    def _set_row_responsive_properties(self, narrow: bool, tight: bool, tiny: bool):
        changed = False
        for key, value in (('rowNarrow', narrow), ('rowTight', tight), ('rowTiny', tiny)):
            if bool(self.property(key)) != bool(value):
                self.setProperty(key, bool(value))
                changed = True
        if changed:
            repolish_widget(self)
            for lbl in self._val_labels + self._head_labels:
                repolish_widget(lbl)

    def _apply_responsive_layout(self, width: int):
        lay = self.layout()
        if lay is None:
            return

        single_column_mode = width < self._single_column_breakpoint
        icon_only_mode = width < self._icon_only_breakpoint
        jaw_id_wrap_mode = (width < 260) and not icon_only_mode
        row_narrow = width < 560
        row_tight = width < 430
        row_tiny = width < 330
        self._set_row_responsive_properties(row_narrow, row_tight, row_tiny)

        if single_column_mode:
            lay.setContentsMargins(8, 2, 8, 2)
            lay.setSpacing(4)
            col_spacing = 0
        elif width < 520:
            lay.setContentsMargins(7, 2, 7, 2)
            lay.setSpacing(7)
            col_spacing = 0
        else:
            lay.setContentsMargins(10, 2, 10, 2)
            lay.setSpacing(10)
            col_spacing = 0

        self._apply_column_visibility(width)

        jaw_id = self._column_values.get('jaw_id')
        jaw_id_wrap = self._column_wraps.get('jaw_id')
        jaw_id_visible = bool(jaw_id_wrap.isVisible()) if jaw_id_wrap is not None else False
        if jaw_id is not None and jaw_id_visible:
            jaw_id.setText(self._split_responsive_token(self._column_texts.get('jaw_id', '')) if jaw_id_wrap_mode else self._column_texts.get('jaw_id', ''))
            jaw_id.setWordWrap(jaw_id_wrap_mode)
            jaw_id.setMinimumHeight(36 if jaw_id_wrap_mode else 28)
            jaw_id.setMaximumHeight(36 if jaw_id_wrap_mode else 28)
            wrap_changed = bool(jaw_id.property('nameWrap')) != bool(jaw_id_wrap_mode)
            tiny_changed = bool(jaw_id.property('nameTiny')) != bool(jaw_id_wrap_mode)
            if wrap_changed:
                jaw_id.setProperty('nameWrap', bool(jaw_id_wrap_mode))
            if tiny_changed:
                jaw_id.setProperty('nameTiny', bool(jaw_id_wrap_mode))
            if wrap_changed or tiny_changed:
                repolish_widget(jaw_id)
        elif jaw_id is not None:
            jaw_id.setText(self._column_texts.get('jaw_id', ''))
            jaw_id.setWordWrap(False)
            if bool(jaw_id.property('nameWrap')) or bool(jaw_id.property('nameTiny')):
                jaw_id.setProperty('nameWrap', False)
                jaw_id.setProperty('nameTiny', False)
                repolish_widget(jaw_id)

        for col in self._col_layouts:
            col.setSpacing(col_spacing)

        if self._icon_label is not None:
            if icon_only_mode:
                self._icon_label.setFixedSize(36, 36)
            else:
                self._icon_label.setFixedSize(40, 40)

        if self._icon_wrap is not None:
            if icon_only_mode:
                self._icon_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                self._icon_wrap.setMinimumWidth(0)
                self._icon_wrap.setMaximumWidth(16777215)
            else:
                self._icon_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
                self._icon_wrap.setFixedWidth(48)

    def set_detail_context(self, details_hidden: bool):
        self._details_open_context = not bool(details_hidden)
        self._apply_responsive_layout(max(1, self.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())


class JawPage(QWidget):
    NAV_MODES = [
        ('all', 'all'),
        ('main', 'main'),
        ('sub', 'sub'),
        ('soft', 'soft'),
        ('hard_group', 'hard_group'),
    ]

    def __init__(
        self,
        jaw_service,
        parent=None,
        show_sidebar: bool = True,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self.jaw_service = jaw_service
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self.show_sidebar = show_sidebar
        self.current_jaw_id = None
        self.current_view_mode = 'all'
        self._details_hidden = True
        self._last_splitter_sizes = None
        self._module_switch_callback = None
        self._master_filter_ids: set[str] = set()
        self._master_filter_active = False
        self._type_filter_values = ['all', 'soft', 'hard_group', 'special']
        self._selector_active = False
        self._selector_spindle = ''
        self._selector_panel_mode = 'details'
        self._selector_assignments: dict[str, dict | None] = {'main': None, 'sub': None}
        self._selector_selected_slots: set[str] = set()
        self._selector_saved_details_hidden = True
        self._build_ui()
        self.refresh_list()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _localized_jaw_type(self, raw_type: str) -> str:
        normalized = (raw_type or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.jaw_type.{normalized}', raw_type)

    def _localized_spindle_side(self, raw_side: str) -> str:
        normalized = (raw_side or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.spindle_side.{normalized}', raw_side)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        filter_frame = QFrame()
        self.filter_frame = filter_frame
        filter_frame.setObjectName('filterFrame')
        filter_frame.setProperty('card', True)
        self.filter_layout = QHBoxLayout(filter_frame)
        self.filter_layout.setContentsMargins(56, 6, 0, 6)
        self.filter_layout.setSpacing(4)

        self.toolbar_title_label = QLabel(self._t('tool_library.rail_title.jaws', 'Jaws Library'))
        self.toolbar_title_label.setProperty('pageTitle', True)
        self.toolbar_title_label.setStyleSheet('padding-left: 0px; padding-right: 20px;')

        self.search_toggle = QToolButton()
        self.search_icon = QIcon(str(TOOL_ICONS_DIR / 'search_icon.svg'))
        self.close_icon = QIcon(str(TOOL_ICONS_DIR / 'close_icon.svg'))
        self.search_toggle.setIcon(self.search_icon)
        self.search_toggle.setIconSize(QSize(28, 28))
        self.search_toggle.setCheckable(True)
        self.search_toggle.setAutoRaise(True)
        self.search_toggle.setProperty('topBarIconButton', True)
        self.search_toggle.setFixedSize(36, 36)
        self.search_toggle.clicked.connect(self._toggle_search)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            self._t('jaw_library.search.placeholder', 'Search jaw ID, type, spindle, diameter, work, washer or notes')
        )
        self.search.setVisible(False)
        self.search.textChanged.connect(self.refresh_list)

        self.toggle_details_btn = QToolButton()
        self.toggle_details_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / 'tooltip.svg')))
        self.toggle_details_btn.setIconSize(QSize(28, 28))
        self.toggle_details_btn.setAutoRaise(True)
        self.toggle_details_btn.setProperty('topBarIconButton', True)
        self.toggle_details_btn.setProperty('secondaryAction', True)
        self.toggle_details_btn.setFixedSize(36, 36)
        self.toggle_details_btn.clicked.connect(self.toggle_details)

        self.detail_header_container = QWidget()
        detail_top = QHBoxLayout(self.detail_header_container)
        detail_top.setContentsMargins(0, 0, 0, 0)
        detail_top.setSpacing(6)
        self.detail_section_label = QLabel(self._t('jaw_library.section.details', 'Jaw details'))
        self.detail_section_label.setProperty('detailSectionTitle', True)
        self.detail_section_label.setStyleSheet('padding: 0 2px 0 0; font-size: 18px;')
        detail_top.addWidget(self.detail_section_label)

        detail_top.addStretch(1)

        self.detail_close_btn = QToolButton()
        self.detail_close_btn.setIcon(self.close_icon)
        self.detail_close_btn.setIconSize(QSize(20, 20))
        self.detail_close_btn.setAutoRaise(True)
        self.detail_close_btn.setProperty('topBarIconButton', True)
        self.detail_close_btn.setFixedSize(32, 32)
        self.detail_close_btn.clicked.connect(self.hide_details)
        detail_top.addWidget(self.detail_close_btn)

        self.filter_icon = QToolButton()
        self.filter_icon.setIcon(QIcon(str(TOOL_ICONS_DIR / 'filter_arrow_right.svg')))
        self.filter_icon.setIconSize(QSize(28, 28))
        self.filter_icon.setAutoRaise(True)
        self.filter_icon.setProperty('topBarIconButton', True)
        self.filter_icon.setFixedSize(36, 36)
        self.filter_icon.clicked.connect(self._clear_type_filter)

        self.jaw_type_filter = QComboBox()
        self.jaw_type_filter.setObjectName('topTypeFilter')
        self._build_type_filter_items()
        self.jaw_type_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.jaw_type_filter.setMinimumWidth(60)
        self.jaw_type_filter.currentIndexChanged.connect(self._on_type_filter_changed)
        add_shadow(self.jaw_type_filter)
        apply_shared_dropdown_style(self.jaw_type_filter)
        self.jaw_type_filter.installEventFilter(self)
        self.jaw_type_filter.view().installEventFilter(self)

        self._rebuild_filter_row()
        root.addWidget(filter_frame)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(10)

        self.view_buttons = []
        if self.show_sidebar:
            self.sidebar = QFrame()
            self.sidebar.setProperty('card', True)
            self.sidebar.setFixedWidth(188)
            side_layout = QVBoxLayout(self.sidebar)
            side_layout.setContentsMargins(10, 12, 10, 12)
            side_layout.setSpacing(6)

            side_title = QLabel(self._t('jaw_library.section.views', 'Jaw Views'))
            side_title.setProperty('detailSectionTitle', True)
            side_layout.addWidget(side_title)

            for _title, mode in self.NAV_MODES:
                btn = QPushButton(self._nav_mode_title(mode))
                btn.setProperty('panelActionButton', True)
                btn.clicked.connect(lambda _checked=False, m=mode: self._set_view_mode(m))
                side_layout.addWidget(btn)
                self.view_buttons.append((mode, btn))

            side_layout.addStretch(1)
            content.addWidget(self.sidebar, 0)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)

        list_card = QFrame()
        list_card.setProperty('catalogShell', True)
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(10)

        self.jaw_list = _JawCatalogListView()
        self.jaw_list.setObjectName('toolCatalog')
        self.jaw_list.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.jaw_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.jaw_list.setSelectionMode(QListView.ExtendedSelection)
        self.jaw_list.setDragEnabled(True)
        self.jaw_list.setMouseTracking(True)
        self.jaw_list.setStyleSheet(
            "QListView#toolCatalog { border: none; outline: none; padding: 8px; }"
            " QListView#toolCatalog::item { background: transparent; border: none; }"
        )
        self.jaw_list.setSpacing(4)
        self._jaw_model = QStandardItemModel(self)
        self.jaw_list.setModel(self._jaw_model)
        self._jaw_delegate = JawCatalogDelegate(parent=self.jaw_list, translate=self._t)
        self.jaw_list.setItemDelegate(self._jaw_delegate)
        self.jaw_list.installEventFilter(self)
        self.jaw_list.viewport().installEventFilter(self)
        self.jaw_list.selectionModel().currentChanged.connect(self.on_current_item_changed)
        self.jaw_list.selectionModel().selectionChanged.connect(self._on_multi_selection_changed)
        self.jaw_list.doubleClicked.connect(self.on_item_double_clicked)
        list_layout.addWidget(self.jaw_list, 1)

        self.splitter.addWidget(list_card)

        self.detail_container = QWidget()
        self.detail_container.setMinimumWidth(280)
        detail_layout = QVBoxLayout(self.detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(0)

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
        self.detail_layout = QVBoxLayout(self.detail_panel)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(10)
        self.detail_scroll.setWidget(self.detail_panel)
        self.populate_details(None)

        detail_card_layout.addWidget(self.detail_scroll, 1)
        detail_layout.addWidget(self.detail_card, 1)

        self.selector_card = QFrame()
        self.selector_card.setProperty('card', True)
        self.selector_card.setProperty('selectorContext', True)
        self.selector_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.selector_card.setVisible(False)
        selector_card_layout = QVBoxLayout(self.selector_card)
        selector_card_layout.setContentsMargins(0, 0, 0, 0)
        selector_card_layout.setSpacing(0)

        self.selector_scroll = QScrollArea()
        self.selector_scroll.setWidgetResizable(True)
        self.selector_scroll.setFrameShape(QFrame.NoFrame)
        self.selector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.selector_panel = QWidget()
        self.selector_panel.setProperty('selectorPanel', True)
        self.selector_panel.setMinimumWidth(0)
        self.selector_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        selector_layout = QVBoxLayout(self.selector_panel)
        selector_layout.setContentsMargins(10, 10, 10, 10)
        selector_layout.setSpacing(6)

        self.selector_info_header = QFrame()
        self.selector_info_header.setProperty('detailHeader', True)
        self.selector_info_header.setProperty('selectorInfoHeader', True)
        self.selector_info_header.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        selector_info_layout = QVBoxLayout(self.selector_info_header)
        selector_info_layout.setContentsMargins(14, 14, 14, 12)
        selector_info_layout.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(0)
        title_row.addStretch(1)
        self.selector_header_title_label = QLabel(self._t('jaw_library.selector.header_title', 'Jaw Selector'))
        self.selector_header_title_label.setProperty('selectorInfoTitle', True)
        self.selector_header_title_label.setAlignment(Qt.AlignCenter)
        title_row.addWidget(self.selector_header_title_label, 0, Qt.AlignCenter)
        title_row.addStretch(1)
        selector_info_layout.addLayout(title_row)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(10)
        self.selector_spindle_value_label = QLabel('SP1')
        self.selector_spindle_value_label.setProperty('toolBadge', True)
        badge_row.addWidget(self.selector_spindle_value_label, 0, Qt.AlignLeft)
        badge_row.addStretch(1)
        self.selector_module_value_label = QLabel(self._t('tool_library.selector.jaws', 'Jaws'))
        self.selector_module_value_label.setProperty('toolBadge', True)
        badge_row.addWidget(self.selector_module_value_label, 0, Qt.AlignRight)
        selector_info_layout.addLayout(badge_row)
        selector_layout.addWidget(self.selector_info_header, 0)

        # ── Toggle button (SELECTOR / DETAILS) — above the subheading ──
        ctx_row = QHBoxLayout()
        ctx_row.setContentsMargins(0, 0, 0, 0)
        ctx_row.setSpacing(10)
        ctx_row.addStretch(1)

        self.selector_toggle_btn = QPushButton(self._t('tool_library.selector.mode_details', 'DETAILS'))
        self.selector_toggle_btn.setProperty('panelActionButton', True)
        self.selector_toggle_btn.setFixedHeight(30)
        self.selector_toggle_btn.setMinimumWidth(120)
        self.selector_toggle_btn.setMaximumWidth(140)
        self.selector_toggle_btn.setCheckable(True)
        self.selector_toggle_btn.setChecked(True)
        self.selector_toggle_btn.setVisible(False)
        self.selector_toggle_btn.clicked.connect(self._on_selector_toggle_clicked)
        style_panel_action_button(self.selector_toggle_btn)
        ctx_row.addWidget(self.selector_toggle_btn, 0)
        ctx_row.addStretch(1)
        selector_layout.addLayout(ctx_row)

        self.selector_hint_label = QLabel(
            self._t('tool_library.selector.jaw_hint', 'Drag jaws from the catalog to SP1 or SP2.')
        )
        self.selector_hint_label.setWordWrap(False)
        self.selector_hint_label.setProperty('detailHint', True)
        self.selector_hint_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.selector_hint_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.selector_hint_label.setFixedHeight(24)
        self.selector_hint_label.setStyleSheet('margin: 0px; padding: 0px; background: transparent;')
        selector_layout.addWidget(self.selector_hint_label, 0)

        self.selector_sp1_slot = _JawAssignmentSlot('main', self._t('jaw_library.selector.sp1_slot', 'SP1 jaw'))
        self.selector_sp2_slot = _JawAssignmentSlot('sub', self._t('jaw_library.selector.sp2_slot', 'SP2 jaw'))
        self.selector_sp1_slot.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.selector_sp2_slot.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.selector_sp1_slot.set_drop_placeholder_text(self._t('jaw_library.selector.drop_here', 'Drop jaw here'))
        self.selector_sp2_slot.set_drop_placeholder_text(self._t('jaw_library.selector.drop_here', 'Drop jaw here'))
        self.selector_sp1_slot.jawDropped.connect(self._on_selector_jaw_dropped)
        self.selector_sp2_slot.jawDropped.connect(self._on_selector_jaw_dropped)
        self.selector_sp1_slot.slotClicked.connect(self._on_selector_slot_clicked)
        self.selector_sp2_slot.slotClicked.connect(self._on_selector_slot_clicked)
        selector_layout.addWidget(self.selector_sp1_slot)
        selector_layout.addWidget(self.selector_sp2_slot)

        self.selector_remove_btn = _SelectorRemoveDropButton()
        style_icon_action_button(
            self.selector_remove_btn,
            TOOL_ICONS_DIR / 'delete.svg',
            self._t('tool_library.selector.remove', 'Remove'),
            danger=True,
        )
        self.selector_remove_btn.clicked.connect(self._remove_selected_selector_jaws)
        self.selector_remove_btn.jawsDropped.connect(self._on_selector_remove_drop)
        selector_layout.addWidget(self.selector_remove_btn, 0, Qt.AlignLeft)
        selector_layout.addStretch(1)

        self.selector_scroll.setWidget(self.selector_panel)
        selector_card_layout.addWidget(self.selector_scroll, 1)
        detail_layout.addWidget(self.selector_card, 1)

        self.splitter.addWidget(self.detail_container)

        self.detail_container.hide()
        self.detail_header_container.hide()
        self.splitter.setSizes([1, 0])

        content.addWidget(self.splitter, 1)
        root.addLayout(content, 1)

        self.button_bar = QFrame()
        self.button_bar.setProperty('bottomBar', True)
        actions = QHBoxLayout(self.button_bar)
        actions.setContentsMargins(10, 8, 10, 8)
        actions.setSpacing(8)

        self.edit_btn = QPushButton(self._t('jaw_library.action.edit_jaw_button', 'EDIT JAW'))
        self.delete_btn = QPushButton(self._t('jaw_library.action.delete_jaw_button', 'DELETE JAW'))
        self.add_btn = QPushButton(self._t('jaw_library.action.add_jaw_button', 'ADD JAW'))
        self.copy_btn = QPushButton(self._t('jaw_library.action.copy_jaw_button', 'COPY JAW'))
        for btn in [self.edit_btn, self.delete_btn, self.add_btn, self.copy_btn]:
            btn.setProperty('panelActionButton', True)
        self.delete_btn.setProperty('dangerAction', True)
        self.add_btn.setProperty('primaryAction', True)

        self.edit_btn.clicked.connect(self.edit_jaw)
        self.delete_btn.clicked.connect(self.delete_jaw)
        self.add_btn.clicked.connect(self.add_jaw)
        self.copy_btn.clicked.connect(self.copy_jaw)

        self.module_switch_label = QLabel(self._t('tool_library.module.switch_to', 'Switch to'))
        self.module_switch_label.setProperty('pageSubtitle', True)
        self.module_toggle_btn = QPushButton(self._t('tool_library.module.tools', 'TOOLS'))
        self.module_toggle_btn.setProperty('panelActionButton', True)
        self.module_toggle_btn.setFixedHeight(28)
        self.module_toggle_btn.clicked.connect(self._on_module_switch_clicked)

        actions.addWidget(self.module_switch_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        actions.addWidget(self.module_toggle_btn, 0, Qt.AlignLeft | Qt.AlignVCenter)
        actions.addStretch(1)
        self.selection_count_label = QLabel('')
        self.selection_count_label.setProperty('detailHint', True)
        self.selection_count_label.setStyleSheet('background: transparent; border: none;')
        self.selection_count_label.hide()
        actions.addWidget(self.selection_count_label, 0, Qt.AlignBottom)
        actions.addWidget(self.add_btn)
        actions.addWidget(self.edit_btn)
        actions.addWidget(self.delete_btn)
        actions.addWidget(self.copy_btn)
        root.addWidget(self.button_bar)

        # ── Selector bottom bar (VALMIS / PERUUTA) — shown in selector mode ──
        self.selector_bottom_bar = QFrame()
        self.selector_bottom_bar.setProperty('bottomBar', True)
        self.selector_bottom_bar.setVisible(False)
        sel_bar_layout = QHBoxLayout(self.selector_bottom_bar)
        sel_bar_layout.setContentsMargins(10, 8, 10, 8)
        sel_bar_layout.setSpacing(8)
        sel_bar_layout.addStretch(1)

        self.selector_cancel_btn = QPushButton(self._t('tool_library.selector.cancel', 'CANCEL'))
        self.selector_cancel_btn.setProperty('panelActionButton', True)
        self.selector_cancel_btn.clicked.connect(self._on_selector_cancel)
        sel_bar_layout.addWidget(self.selector_cancel_btn)

        self.selector_done_btn = QPushButton(self._t('tool_library.selector.done', 'DONE'))
        self.selector_done_btn.setProperty('panelActionButton', True)
        self.selector_done_btn.setProperty('primaryAction', True)
        self.selector_done_btn.clicked.connect(self._on_selector_done)
        sel_bar_layout.addWidget(self.selector_done_btn)
        root.addWidget(self.selector_bottom_bar)

        self._set_view_mode('all', refresh=False)
        self._refresh_selector_slots()
        self._update_selector_remove_button()

        self.selector_card.installEventFilter(self)
        self.selector_scroll.viewport().installEventFilter(self)
        self.selector_panel.installEventFilter(self)
        self.detail_container.installEventFilter(self)
        self.splitter.installEventFilter(self)
        filter_frame.installEventFilter(self)
        self.button_bar.installEventFilter(self)
        self.selector_bottom_bar.installEventFilter(self)
        self.detail_header_container.installEventFilter(self)

    def _on_module_switch_clicked(self):
        if callable(self._module_switch_callback):
            self._module_switch_callback()

    def set_module_switch_handler(self, callback):
        self._module_switch_callback = callback

    def set_module_switch_target(self, target: str):
        target_text = (target or '').strip().upper() or 'TOOLS'
        display = self._t('tool_library.module.tools', 'TOOLS') if target_text == 'TOOLS' else self._t('tool_library.module.jaws', 'JAWS')
        self.module_toggle_btn.setText(display)
        self.module_toggle_btn.setToolTip(self._t('tool_library.module.switch_to_target', 'Switch to {target} module', target=display))

    def set_master_filter(self, jaw_ids, active: bool):
        self._master_filter_ids = {str(j).strip() for j in (jaw_ids or []) if str(j).strip()}
        self._master_filter_active = bool(active) and bool(self._master_filter_ids)
        self.refresh_list()

    @staticmethod
    def _normalize_selector_spindle(value: str | None) -> str:
        return 'sub' if str(value or '').strip().lower() == 'sub' else 'main'

    @staticmethod
    def _selector_spindle_label(spindle: str) -> str:
        return 'SP2' if str(spindle or '').strip().lower() == 'sub' else 'SP1'

    @staticmethod
    def _normalize_selector_jaw(jaw: dict | None) -> dict | None:
        if not isinstance(jaw, dict):
            return None
        jaw_id = str(jaw.get('jaw_id') or jaw.get('id') or '').strip()
        if not jaw_id:
            return None
        return {
            'jaw_id': jaw_id,
            'jaw_type': str(jaw.get('jaw_type') or '').strip(),
        }

    def _selector_context_text(self) -> str:
        active_spindle = self._selector_spindle_label(self._selector_spindle)
        return self._t(
            'tool_library.selector.jaw_context',
            'Drop jaws to SP1 and SP2 slots. Active spindle: {spindle}',
            spindle=active_spindle,
        )

    def _update_selector_spindle_ui(self):
        spindle = self._normalize_selector_spindle(self._selector_spindle)
        if hasattr(self, 'selector_spindle_btn'):
            self.selector_spindle_btn.setProperty('spindle', spindle)
            self.selector_spindle_btn.setChecked(spindle == 'sub')
            self.selector_spindle_btn.setText(self._selector_spindle_label(spindle))
        if hasattr(self, 'selector_spindle_value_label'):
            self.selector_spindle_value_label.setText(self._selector_spindle_label(spindle))

    def _toggle_selector_spindle(self):
        if not self._selector_active or not hasattr(self, 'selector_spindle_btn'):
            return
        self._selector_spindle = 'sub' if self.selector_spindle_btn.isChecked() else 'main'
        self._update_selector_spindle_ui()

    def _refresh_selector_slots(self):
        if not hasattr(self, 'selector_sp1_slot'):
            return
        self.selector_sp1_slot.set_assignment(self._selector_assignments.get('main'))
        self.selector_sp2_slot.set_assignment(self._selector_assignments.get('sub'))
        self._selector_selected_slots = {
            slot for slot in self._selector_selected_slots
            if self._selector_assignments.get(slot) is not None
        }
        self._apply_selector_slot_selection()
        self._update_selector_remove_button()

    def _apply_selector_slot_selection(self):
        if hasattr(self, 'selector_sp1_slot'):
            self.selector_sp1_slot.set_selected('main' in self._selector_selected_slots)
        if hasattr(self, 'selector_sp2_slot'):
            self.selector_sp2_slot.set_selected('sub' in self._selector_selected_slots)

    def _on_selector_slot_clicked(self, slot_key: str, ctrl_pressed: bool):
        slot = self._normalize_selector_spindle(slot_key)
        has_assignment = self._selector_assignments.get(slot) is not None
        if not has_assignment:
            if not ctrl_pressed:
                self._selector_selected_slots.clear()
            self._apply_selector_slot_selection()
            self._update_selector_remove_button()
            return

        if ctrl_pressed:
            if slot in self._selector_selected_slots:
                self._selector_selected_slots.remove(slot)
            else:
                self._selector_selected_slots.add(slot)
        else:
            self._selector_selected_slots = {slot}

        self._apply_selector_slot_selection()
        self._update_selector_remove_button()

    def _update_selector_remove_button(self):
        if not hasattr(self, 'selector_remove_btn'):
            return
        has_selected = any(self._selector_assignments.get(slot) is not None for slot in self._selector_selected_slots)
        has_assigned = any(self._selector_assignments.get(slot) is not None for slot in ('main', 'sub'))
        enabled = has_selected or has_assigned
        self.selector_remove_btn.setEnabled(enabled)

    def _on_selector_jaw_dropped(self, slot_key: str, jaw: dict):
        normalized_slot = self._normalize_selector_spindle(slot_key)
        normalized_jaw = self._normalize_selector_jaw(jaw)
        self._selector_assignments[normalized_slot] = normalized_jaw
        self._selector_selected_slots = {normalized_slot} if normalized_jaw is not None else set()
        self._refresh_selector_slots()

    def _clear_selector_assignments(self):
        self._selector_assignments = {'main': None, 'sub': None}
        self._selector_selected_slots.clear()
        self._refresh_selector_slots()

    def _remove_selected_selector_jaws(self):
        if not self._selector_selected_slots:
            return
        for slot in list(self._selector_selected_slots):
            self._selector_assignments[slot] = None
        self._selector_selected_slots.clear()
        self._refresh_selector_slots()

    def _remove_selector_jaws_by_ids(self, jaw_ids: list[str]):
        targets = {str(jaw_id).strip() for jaw_id in jaw_ids if str(jaw_id).strip()}
        if not targets:
            return
        changed = False
        for slot_key in ('main', 'sub'):
            jaw = self._selector_assignments.get(slot_key)
            jaw_id = str((jaw or {}).get('jaw_id') or '').strip() if isinstance(jaw, dict) else ''
            if jaw_id and jaw_id in targets:
                self._selector_assignments[slot_key] = None
                changed = True
        if changed:
            self._selector_selected_slots.clear()
            self._refresh_selector_slots()

    def _on_selector_remove_drop(self, jaw_ids: list[str]):
        self._remove_selector_jaws_by_ids(jaw_ids)

    def _on_selector_cancel(self):
        """Cancel selector — notify main window to clear the session."""
        main_win = self.window()
        if hasattr(main_win, '_clear_selector_session'):
            main_win._clear_selector_session()
        if hasattr(main_win, '_back_to_setup_manager'):
            main_win._back_to_setup_manager()

    def _on_selector_done(self):
        """Send selection — delegate to main window."""
        main_win = self.window()
        if hasattr(main_win, '_send_selector_selection'):
            main_win._send_selector_selection()

    def _on_selector_toggle_clicked(self):
        if not self._selector_active:
            return
        if self.selector_toggle_btn.isChecked():
            self._set_selector_panel_mode('selector')
        else:
            self._set_selector_panel_mode('details')

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

        target_mode = 'details' if str(mode or '').strip().lower() == 'details' else 'selector'
        self._selector_panel_mode = target_mode
        self._details_hidden = False
        self.detail_container.show()
        self.detail_header_container.show()
        if not self._last_splitter_sizes:
            total = max(600, self.splitter.width())
            self._last_splitter_sizes = [int(total * 0.62), int(total * 0.38)]
        self.splitter.setSizes(self._last_splitter_sizes)

        if target_mode == 'details':
            self.detail_card.setVisible(True)
            self.selector_card.setVisible(False)
            self.detail_section_label.setText(self._t('jaw_library.section.details', 'Jaw details'))
            self.selector_toggle_btn.setChecked(False)
            self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_selector', 'SELECTOR'))
        else:
            self.detail_card.setVisible(False)
            self.selector_card.setVisible(True)
            self.detail_section_label.setText(self._t('tool_library.selector.selection_title', 'Selection'))
            self.selector_toggle_btn.setChecked(True)
            self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_details', 'DETAILS'))

    def set_selector_context(self, active: bool, spindle: str = '') -> None:
        was_active = self._selector_active
        self._selector_active = bool(active)
        self._selector_spindle = self._normalize_selector_spindle(spindle)
        self._update_selector_spindle_ui()
        self.selector_toggle_btn.setVisible(self._selector_active)
        self.toggle_details_btn.setEnabled(not self._selector_active)

        # Toggle bottom bars
        self.button_bar.setVisible(not self._selector_active)
        self.selector_bottom_bar.setVisible(self._selector_active)

        if self._selector_active:
            if not was_active:
                self._selector_saved_details_hidden = self._details_hidden
            self._selector_assignments = {'main': None, 'sub': None}
            self._selector_selected_slots.clear()
            self._refresh_selector_slots()
            self._set_selector_panel_mode('selector')
            return

        self._details_hidden = self._selector_saved_details_hidden
        self._selector_assignments = {'main': None, 'sub': None}
        self._selector_selected_slots.clear()
        self._refresh_selector_slots()
        self._set_selector_panel_mode('details')
        self.detail_section_label.setText(self._t('jaw_library.section.details', 'Jaw details'))
        if self._details_hidden:
            self.detail_container.hide()
            self.detail_header_container.hide()
            self.splitter.setSizes([1, 0])
        else:
            self.detail_container.show()
            self.detail_header_container.show()
            if not self._last_splitter_sizes:
                total = max(600, self.splitter.width())
                self._last_splitter_sizes = [int(total * 0.62), int(total * 0.38)]
            self.splitter.setSizes(self._last_splitter_sizes)

    def selector_assigned_jaws_for_setup_assignment(self) -> list[dict]:
        payload: list[dict] = []
        for slot in ('main', 'sub'):
            jaw = self._normalize_selector_jaw(self._selector_assignments.get(slot))
            if jaw is not None:
                payload.append(jaw)
        return payload

    def _toggle_search(self):
        show = self.search_toggle.isChecked()
        self.jaw_type_filter.hide()
        self.search.setVisible(show)
        self.search_toggle.setIcon(self.close_icon if show else self.search_icon)
        if not show:
            self.search.clear()
            self.refresh_list()
        self._rebuild_filter_row()
        self.jaw_type_filter.hidePopup()
        self._suppress_combo = True
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: setattr(self, '_suppress_combo', False))
        self.jaw_type_filter.setEnabled(False)
        QTimer.singleShot(0, lambda: self.jaw_type_filter.setEnabled(True))
        self.jaw_type_filter.show()
        if show:
            QTimer.singleShot(0, self.search.setFocus)

    def _set_view_mode(self, mode: str, refresh: bool = True):
        self.current_view_mode = mode
        for btn_mode, btn in self.view_buttons:
            btn.setProperty('primaryAction', btn_mode == mode)
            style = btn.style()
            style.unpolish(btn)
            style.polish(btn)
            btn.update()
        if refresh:
            self.refresh_list()

    def set_view_mode(self, mode: str):
        self._set_view_mode(mode, refresh=True)

    def _nav_mode_title(self, mode: str) -> str:
        mapping = {
            'all': self._t('tool_library.nav.all_jaws', 'All Jaws'),
            'main': self._t('tool_library.nav.main_spindle', 'Main Spindle'),
            'sub': self._t('tool_library.nav.sub_spindle', 'Sub Spindle'),
            'soft': self._t('jaw_library.nav.soft_jaws', 'Soft Jaws'),
            'hard_group': self._t('jaw_library.nav.hard_group', 'Hard / Spiked / Special'),
        }
        return mapping.get(mode, mode)

    def _set_type_filter_value(self, value: str):
        target = (value or 'all').strip()
        for idx in range(self.jaw_type_filter.count()):
            if self.jaw_type_filter.itemData(idx) == target:
                self.jaw_type_filter.setCurrentIndex(idx)
                return
        if self.jaw_type_filter.count():
            self.jaw_type_filter.setCurrentIndex(0)

    def _build_type_filter_items(self):
        if not hasattr(self, 'jaw_type_filter'):
            return
        current = self.jaw_type_filter.currentData() if self.jaw_type_filter.count() else 'all'
        self.jaw_type_filter.blockSignals(True)
        self.jaw_type_filter.clear()
        self.jaw_type_filter.addItem(self._t('jaw_library.filter.all', 'All'), 'all')
        self.jaw_type_filter.addItem(self._t('jaw_library.filter.soft_jaws', 'Soft Jaws'), 'soft')
        self.jaw_type_filter.addItem(self._t('jaw_library.filter.hard_spiked', 'Spike/Hard Jaws'), 'hard_group')
        self.jaw_type_filter.addItem(self._t('jaw_library.filter.special_jaws', 'Special Jaws'), 'special')
        self._set_type_filter_value(current if current in self._type_filter_values else 'all')
        self.jaw_type_filter.blockSignals(False)

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
        self.filter_layout.addWidget(self.jaw_type_filter)
        self.filter_layout.addStretch(1)
        self.filter_layout.addWidget(self.detail_header_container)

    def _on_type_filter_changed(self, _index: int):
        active = (self.jaw_type_filter.currentData() or 'all') != 'all'
        icon_name = 'filter_off.svg' if active else 'filter_arrow_right.svg'
        self.filter_icon.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
        self.refresh_list()

    def _clear_type_filter(self):
        self._set_type_filter_value('all')

    def eventFilter(self, obj, event):
        if obj is getattr(self, 'jaw_type_filter', None) or (
                getattr(self, 'jaw_type_filter', None) and obj is self.jaw_type_filter.view()):
            if getattr(self, '_suppress_combo', False) and event.type() in (QEvent.Show, QEvent.ShowToParent):
                return True
        selector_click_targets = {
            getattr(self, 'selector_card', None),
            getattr(self, 'selector_panel', None),
            getattr(self, 'detail_container', None),
            getattr(self, 'splitter', None),
            getattr(self, 'button_bar', None),
            getattr(self, 'selector_bottom_bar', None),
            getattr(self, 'filter_frame', None),
            getattr(self, 'detail_header_container', None),
            getattr(self, 'selector_scroll', None) and self.selector_scroll.viewport(),
        }
        if (
            self._selector_active
            and event.type() == QEvent.MouseButtonPress
            and obj in selector_click_targets
            and hasattr(event, 'pos')
        ):
            global_pos = obj.mapToGlobal(event.pos())
            on_slot = False
            for slot_widget in (getattr(self, 'selector_sp1_slot', None), getattr(self, 'selector_sp2_slot', None)):
                if slot_widget is None:
                    continue
                local_pos = slot_widget.mapFromGlobal(global_pos)
                if slot_widget.rect().contains(local_pos):
                    on_slot = True
                    break
            if not on_slot and hasattr(self, 'selector_remove_btn'):
                remove_local = self.selector_remove_btn.mapFromGlobal(global_pos)
                if self.selector_remove_btn.rect().contains(remove_local):
                    on_slot = True
            if not on_slot and self._selector_selected_slots:
                self._selector_selected_slots.clear()
                self._apply_selector_slot_selection()
                self._update_selector_remove_button()
        if obj in (getattr(self, 'jaw_list', None),
                   getattr(self, 'jaw_list', None) and self.jaw_list.viewport()):
            if event.type() == QEvent.MouseButtonPress:
                if not self.jaw_list.indexAt(event.pos()).isValid():
                    self._clear_selection()
        return super().eventFilter(obj, event)

    def _clear_selection(self):
        details_were_open = not self._details_hidden
        if hasattr(self, 'jaw_list'):
            self.jaw_list.selectionModel().clearSelection()
            self.jaw_list.setCurrentIndex(QModelIndex())
        self.current_jaw_id = None
        self._update_selection_count_label()
        self.populate_details(None)
        if details_were_open:
            self.hide_details()

    def _selected_jaw_ids(self) -> list[str]:
        model = self.jaw_list.selectionModel()
        if model is None:
            return []
        indexes = sorted(model.selectedIndexes(), key=lambda idx: idx.row())
        jaw_ids: list[str] = []
        for index in indexes:
            jaw_id = (index.data(ROLE_JAW_ID) or '').strip()
            if jaw_id and jaw_id not in jaw_ids:
                jaw_ids.append(jaw_id)
        return jaw_ids

    def selected_jaws_for_setup_assignment(self) -> list[dict]:
        model = self.jaw_list.selectionModel()
        if model is None:
            return []
        indexes = sorted(model.selectedIndexes(), key=lambda idx: idx.row())
        payload: list[dict] = []
        for index in indexes:
            jaw_id = str(index.data(ROLE_JAW_ID) or '').strip()
            jaw_data = index.data(ROLE_JAW_DATA) or {}
            jaw_type = str((jaw_data.get('jaw_type') if isinstance(jaw_data, dict) else None) or '').strip()
            payload.append({
                'jaw_id': jaw_id,
                'jaw_type': jaw_type,
            })
        return payload

    def _on_multi_selection_changed(self, _selected, _deselected):
        self._update_selection_count_label()

    def _update_selection_count_label(self):
        count = len(self._selected_jaw_ids())
        if count > 1:
            self.selection_count_label.setText(
                self._t('jaw_library.selection.count', '{count} selected', count=count)
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
        db_path = Path(self.jaw_service.db.path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = db_path.parent / f"{db_path.stem}_{tag}_{timestamp}.bak"
        shutil.copy2(db_path, backup_path)
        self._prune_backups(db_path, tag)
        return backup_path

    def _prompt_batch_cancel_behavior(self) -> str:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(self._t('jaw_library.batch.cancel.title', 'Batch edit cancelled'))
        box.setText(
            self._t(
                'jaw_library.batch.cancel.body',
                'You stopped editing partway through the batch. Do you want to keep the changes you\'ve already saved, or undo all of them?',
            )
        )
        keep_btn = box.addButton(
            self._t('jaw_library.batch.cancel.keep', 'Keep'),
            QMessageBox.AcceptRole,
        )
        undo_btn = box.addButton(
            self._t('jaw_library.batch.cancel.undo', 'Undo'),
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

    def _batch_edit_jaws(self, jaw_ids: list[str]):
        saved_before: list[dict] = []
        total = len(jaw_ids)
        for idx, jaw_id in enumerate(jaw_ids, 1):
            jaw = self.jaw_service.get_jaw(jaw_id)
            if not jaw:
                continue
            dlg = AddEditJawDialog(
                self,
                jaw=jaw,
                translate=self._t,
                batch_label=f"{idx}/{total}",
            )
            if dlg.exec() != QDialog.Accepted:
                if saved_before:
                    action = self._prompt_batch_cancel_behavior()
                    if action == 'undo':
                        for previous in reversed(saved_before):
                            self.jaw_service.save_jaw(previous)
                self.refresh_list()
                return
            saved_before.append(dict(jaw))
            self.jaw_service.save_jaw(dlg.get_jaw_data())
        self.refresh_list()

    def _group_edit_jaws(self, jaw_ids: list[str]):
        dlg = AddEditJawDialog(
            self,
            translate=self._t,
            group_edit_mode=True,
            group_count=len(jaw_ids),
        )
        baseline = dlg.get_jaw_data()
        if dlg.exec() != QDialog.Accepted:
            return
        edited_data = dlg.get_jaw_data()
        changed_fields = {
            key: value
            for key, value in edited_data.items()
            if value != baseline.get(key)
        }
        changed_fields.pop('jaw_id', None)
        if not changed_fields:
            QMessageBox.information(
                self,
                self._t('jaw_library.group_edit.no_changes_title', 'No changes'),
                self._t('jaw_library.group_edit.no_changes_body', 'No fields were changed.'),
            )
            return

        self._create_db_backup('group_edit')
        for jaw_id in jaw_ids:
            jaw = self.jaw_service.get_jaw(jaw_id)
            if not jaw:
                continue
            updated = dict(jaw)
            updated.update(changed_fields)
            updated['jaw_id'] = jaw_id
            self.jaw_service.save_jaw(updated)
        self.refresh_list()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._clear_selection()
            return
        super().keyPressEvent(event)

    def _clear_details(self):
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _split_used_in_works(self, value: str) -> list[str]:
        return [p.strip() for p in (value or '').split('|') if p.strip()]

    def populate_details(self, jaw):
        self._clear_details()

        if not jaw:
            card = QFrame()
            card.setProperty('subCard', True)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(14, 14, 14, 14)
            layout.setSpacing(10)
            title = QLabel(self._t('jaw_library.section.details', 'Jaw details'))
            title.setProperty('detailSectionTitle', True)
            hint = QLabel(self._t('jaw_library.message.select_jaw_for_details', 'Select a jaw to view details.'))
            hint.setProperty('detailHint', True)
            hint.setWordWrap(True)
            layout.addWidget(title)
            layout.addWidget(hint)
            placeholder = QFrame()
            placeholder.setProperty('diagramPanel', True)
            p = QVBoxLayout(placeholder)
            p.setContentsMargins(12, 12, 12, 12)
            p.addStretch(1)
            p.addStretch(1)
            layout.addWidget(placeholder)
            self.detail_layout.addWidget(card)
            self.detail_layout.addStretch(1)
            return

        card = QFrame()
        card.setProperty('subCard', True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header
        header = QFrame()
        header.setProperty('detailHeader', True)
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(14, 14, 14, 12)
        h_layout.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        jaw_id_lbl = QLabel(jaw.get('jaw_id', ''))
        jaw_id_lbl.setProperty('detailHeroTitle', True)
        jaw_id_lbl.setWordWrap(True)
        diam_lbl = QLabel(jaw.get('clamping_diameter_text', '') or '')
        diam_lbl.setProperty('detailHeroTitle', True)
        diam_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title_row.addWidget(jaw_id_lbl, 1)
        title_row.addWidget(diam_lbl, 0, Qt.AlignRight)
        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge = QLabel(self._localized_jaw_type(jaw.get('jaw_type', '')))
        badge.setProperty('toolBadge', True)
        badge_row.addWidget(badge, 0, Qt.AlignLeft)
        badge_row.addStretch(1)
        h_layout.addLayout(title_row)
        h_layout.addLayout(badge_row)
        layout.addWidget(header)

        # Use the same shared titled-field style as Tool Library detail panel.
        def build_field(label_text: str, value_text: str):
            return build_titled_detail_field(label_text, '' if value_text is None else str(value_text))

        def build_used_in_works_field(value_text: str):
            return build_titled_detail_list_field(
                self._t('jaw_library.field.used_in_works', 'Used in works:'),
                self._split_used_in_works(value_text),
            )

        # Explicit 2-column row layout.
        is_spiked = 'spiked' in (jaw.get('jaw_type') or '').lower()

        info = QGridLayout()
        info.setHorizontalSpacing(14)
        info.setVerticalSpacing(8)

        # Row 0: Leuka ID | Kara
        info.addWidget(
            build_field(self._t('jaw_library.field.jaw_id', 'Jaw ID'), jaw.get('jaw_id', '')),
            0, 0, 1, 2, Qt.AlignTop,
        )
        info.addWidget(
            build_field(
                self._t('jaw_library.field.spindle_side', 'Spindle side'),
                self._localized_spindle_side(jaw.get('spindle_side', '')),
            ),
            0, 2, 1, 2, Qt.AlignTop,
        )

        # Row 1: Kiinnityshalkaisija | Kiinnityspituus
        info.addWidget(
            build_field(self._t('jaw_library.field.clamping_diameter', 'Clamping diameter'), jaw.get('clamping_diameter_text', '')),
            1, 0, 1, 2, Qt.AlignTop,
        )
        info.addWidget(
            build_field(self._t('jaw_library.field.clamping_length', 'Clamping length'), jaw.get('clamping_length', '')),
            1, 2, 1, 2, Qt.AlignTop,
        )

        # Row 2: Sorvausrengas | Viimeksi muokattu (hidden for spiked jaws)
        if is_spiked:
            info.addWidget(
                build_field(self._t('jaw_library.field.turning_ring', 'Turning ring'), jaw.get('turning_washer', '')),
                2, 0, 1, 4, Qt.AlignTop,
            )
        else:
            info.addWidget(
                build_field(self._t('jaw_library.field.turning_ring', 'Turning ring'), jaw.get('turning_washer', '')),
                2, 0, 1, 2, Qt.AlignTop,
            )
            info.addWidget(
                build_field(self._t('jaw_library.field.last_modified', 'Last modified'), jaw.get('last_modified', '')),
                2, 2, 1, 2, Qt.AlignTop,
            )

        next_row = 3

        used_in_works_value = _lookup_setup_db_used_in_works(jaw.get('jaw_id', ''))
        used_in_works_field = build_used_in_works_field(used_in_works_value)
        info.addWidget(used_in_works_field, next_row, 0, 1, 4, Qt.AlignTop)

        notes_text = (jaw.get('notes', '') or '').strip()
        if notes_text:
            notes_field = build_titled_detail_field(
                self._t('jaw_library.field.notes', 'Notes'),
                notes_text,
                multiline=True,
            )
            info.addWidget(notes_field, next_row + 1, 0, 1, 4, Qt.AlignTop)

        layout.addLayout(info)

        # Preview panel — mirrored wrapper structure from Tool Library.
        preview_card = create_titled_section(self._t('tool_library.section.preview', 'Preview'))
        preview_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        p_layout = QVBoxLayout(preview_card)
        p_layout.setSpacing(10)
        p_layout.setContentsMargins(6, 4, 6, 6)

        diagram = QWidget()
        diagram.setObjectName('detailPreviewGradientHost')
        diagram.setAttribute(Qt.WA_StyledBackground, True)
        diagram.setStyleSheet(
            'QWidget#detailPreviewGradientHost {'
            '  background-color: #d6d9de;'
            '  border: none;'
            '  border-radius: 6px;'
            '}'
        )
        diagram.setMinimumHeight(300)
        diagram.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        d_layout = QVBoxLayout(diagram)
        d_layout.setContentsMargins(6, 6, 6, 6)
        d_layout.setSpacing(0)

        stl_path = (jaw.get('stl_path', '') or '').strip()
        viewer = None
        loaded = False
        if stl_path:
            viewer = StlPreviewWidget()
            viewer.setStyleSheet('background: transparent; border: none;')
            viewer.set_control_hint_text(
                self._t(
                    'tool_editor.hint.rotate_pan_zoom',
                    'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
                )
            )
            loaded = bool(
                viewer.load_stl(
                    stl_path,
                    label=jaw.get('jaw_id', self._t('jaw_library.preview.jaw_label', 'Jaw')),
                )
            )
            if loaded:
                plane = (jaw.get('preview_plane', '') or 'XZ').strip()
                if plane not in ('XZ', 'XY', 'YZ'):
                    plane = 'XZ'
                viewer.set_alignment_plane(plane)
                for axis, key in (('x', 'preview_rot_x'), ('y', 'preview_rot_y'), ('z', 'preview_rot_z')):
                    deg = int(jaw.get(key, 0) or 0) % 360
                    if deg:
                        viewer.rotate_model(axis, deg)
                viewer.setMinimumHeight(260)
                d_layout.addWidget(viewer, 1)

        if not loaded:
            txt = QLabel(
                self._t('tool_library.preview.invalid_data', 'No valid 3D model data found.')
                if stl_path else
                self._t('tool_library.preview.none_assigned', 'No 3D model assigned.')
            )
            txt.setProperty('detailHint', True)
            txt.setWordWrap(True)
            txt.setAlignment(Qt.AlignCenter)
            d_layout.addStretch(1)
            d_layout.addWidget(txt)
            d_layout.addStretch(1)

        p_layout.addWidget(diagram, 1)
        layout.addWidget(preview_card)
        layout.addStretch(1)
        self.detail_layout.addWidget(card)

    def _refresh_row_style(self, widget):
        if widget is None:
            return
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    def select_jaw_by_id(self, jaw_id: str):
        """Navigate the list to the jaw with the given jaw_id."""
        self.current_jaw_id = jaw_id.strip()
        self.refresh_list()
        for row in range(self._jaw_model.rowCount()):
            idx = self._jaw_model.index(row, 0)
            if idx.data(ROLE_JAW_ID) == self.current_jaw_id:
                self.jaw_list.setCurrentIndex(idx)
                self.jaw_list.scrollTo(idx)
                break

    def refresh_list(self):
        type_filter = self.jaw_type_filter.currentData() if hasattr(self, 'jaw_type_filter') else 'all'
        jaws = self.jaw_service.list_jaws(self.search.text(), self.current_view_mode, type_filter)
        if self._master_filter_active:
            jaws = [jaw for jaw in jaws if str(jaw.get('jaw_id', '')).strip() in self._master_filter_ids]
        self._jaw_model.blockSignals(True)
        self._jaw_model.clear()
        for jaw in jaws:
            item = QStandardItem()
            jaw_id = jaw.get('jaw_id', '')
            item.setData(jaw_id, ROLE_JAW_ID)
            item.setData(jaw, ROLE_JAW_DATA)
            item.setData(jaw_icon_for_row(jaw), ROLE_JAW_ICON)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            self._jaw_model.appendRow(item)
        self._jaw_model.blockSignals(False)

        if self.current_jaw_id:
            for row in range(self._jaw_model.rowCount()):
                idx = self._jaw_model.index(row, 0)
                if idx.data(ROLE_JAW_ID) == self.current_jaw_id:
                    self.jaw_list.setCurrentIndex(idx)
                    self.jaw_list.scrollTo(idx)
                    break

        self.jaw_list.doItemsLayout()
        self.jaw_list.viewport().update()
        self.jaw_list.viewport().repaint()

    def toggle_details(self):
        if self._details_hidden:
            if not self.current_jaw_id:
                QMessageBox.information(
                    self,
                    self._t('jaw_library.message.show_details', 'Show details'),
                    self._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
                )
                return
            jaw = self.jaw_service.get_jaw(self.current_jaw_id)
            self.populate_details(jaw)
            self.show_details()
            return
        self.hide_details()

    def show_details(self):
        if self._selector_active:
            self._set_selector_panel_mode('details')
            return
        self._details_hidden = False
        self.detail_container.show()
        self.detail_header_container.show()
        if not self._last_splitter_sizes:
            total = max(600, self.splitter.width())
            self._last_splitter_sizes = [int(total * 0.62), int(total * 0.38)]
        self.splitter.setSizes(self._last_splitter_sizes)
        self.refresh_list()

    def hide_details(self):
        if self._selector_active:
            self._set_selector_panel_mode('selector')
            return
        self._details_hidden = True
        if self.detail_container.isVisible():
            self._last_splitter_sizes = self.splitter.sizes()
        self.detail_container.hide()
        self.detail_header_container.hide()
        self.splitter.setSizes([1, 0])
        self.refresh_list()

    def on_current_item_changed(self, current: QModelIndex, previous: QModelIndex):
        if not current.isValid():
            self.current_jaw_id = None
            self._update_selection_count_label()
            self.populate_details(None)
            return

        self.current_jaw_id = current.data(ROLE_JAW_ID)
        self._update_selection_count_label()

        if not self._details_hidden:
            jaw = self.jaw_service.get_jaw(self.current_jaw_id)
            self.populate_details(jaw)

    def on_item_double_clicked(self, index: QModelIndex):
        self.current_jaw_id = index.data(ROLE_JAW_ID)
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.edit_jaw()
            return
        if self._details_hidden:
            self.populate_details(self.jaw_service.get_jaw(self.current_jaw_id))
            self.show_details()
        else:
            self.hide_details()

    def _save_from_dialog(self, dlg, original_jaw_id: str | None = None):
        try:
            data = dlg.get_jaw_data()
            self.jaw_service.save_jaw(data)
            new_jaw_id = data['jaw_id']
            # If the Jaw ID was renamed during edit, remove the old record.
            if original_jaw_id and original_jaw_id != new_jaw_id:
                self.jaw_service.delete_jaw(original_jaw_id)
            self.current_jaw_id = new_jaw_id
            self.refresh_list()
            self.populate_details(self.jaw_service.get_jaw(self.current_jaw_id))
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))

    def add_jaw(self):
        dlg = AddEditJawDialog(self, translate=self._t)
        if dlg.exec() == QDialog.Accepted:
            self._save_from_dialog(dlg)

    def edit_jaw(self):
        selected_ids = self._selected_jaw_ids()
        if not selected_ids:
            QMessageBox.information(
                self,
                self._t('jaw_library.action.edit_jaw', 'Edit jaw'),
                self._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
            )
            return
        if len(selected_ids) > 1:
            mode = ask_multi_edit_mode(self, len(selected_ids), self._t)
            if mode == 'batch':
                self._batch_edit_jaws(selected_ids)
            elif mode == 'group':
                self._group_edit_jaws(selected_ids)
            return
        jaw = self.jaw_service.get_jaw(selected_ids[0])
        dlg = AddEditJawDialog(self, jaw=jaw, translate=self._t)
        if dlg.exec() == QDialog.Accepted:
            self._save_from_dialog(dlg, original_jaw_id=jaw.get('jaw_id', ''))

    def delete_jaw(self):
        if not self.current_jaw_id:
            QMessageBox.information(
                self,
                self._t('jaw_library.action.delete_jaw', 'Delete jaw'),
                self._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
            )
            return
        box = QMessageBox(self)
        setup_editor_dialog(box)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(self._t('jaw_library.action.delete_jaw', 'Delete jaw'))
        box.setText(self._t('jaw_library.message.delete_jaw_prompt', 'Delete jaw {jaw_id}?', jaw_id=self.current_jaw_id))
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        yes_btn = box.button(QMessageBox.Yes)
        no_btn = box.button(QMessageBox.No)
        if yes_btn is not None:
            yes_btn.setText(self._t('common.yes', 'Yes'))
            yes_btn.setProperty('panelActionButton', True)
            yes_btn.setProperty('dangerAction', True)
        if no_btn is not None:
            no_btn.setText(self._t('common.no', 'No'))
            no_btn.setProperty('panelActionButton', True)
            no_btn.setProperty('secondaryAction', True)

        if box.exec() != QMessageBox.Yes:
            return
        self.jaw_service.delete_jaw(self.current_jaw_id)
        self.current_jaw_id = None
        self.refresh_list()
        self.populate_details(None)

    def copy_jaw(self):
        if not self.current_jaw_id:
            QMessageBox.information(
                self,
                self._t('jaw_library.action.copy_jaw', 'Copy jaw'),
                self._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
            )
            return

        jaw = self.jaw_service.get_jaw(self.current_jaw_id)
        if not jaw:
            return

        new_id, ok = self._prompt_text(
            self._t('jaw_library.action.copy_jaw', 'Copy jaw'),
            self._t('jaw_library.prompt.new_jaw_id', 'New Jaw ID:'),
        )
        if not ok or not new_id.strip():
            return

        copied = dict(jaw)
        copied['jaw_id'] = new_id.strip()
        try:
            self.jaw_service.save_jaw(copied)
            self.current_jaw_id = copied['jaw_id']
            self.refresh_list()
            self.populate_details(self.jaw_service.get_jaw(self.current_jaw_id))
        except ValueError as exc:
            QMessageBox.warning(self, self._t('jaw_library.action.copy_jaw', 'Copy jaw'), str(exc))

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

    def apply_localization(self, translate: Callable[[str, str | None], str] | None = None):
        if translate is not None:
            self._translate = translate
        if hasattr(self, 'toolbar_title_label'):
            self.toolbar_title_label.setText(self._t('tool_library.module.jaws', 'JAWS'))
        if hasattr(self, 'search'):
            self.search.setPlaceholderText(
                self._t('jaw_library.search.placeholder', 'Search jaw ID, type, spindle, diameter, work, washer or notes')
            )
        if hasattr(self, 'detail_section_label'):
            self.detail_section_label.setText(self._t('jaw_library.section.details', 'Jaw details'))
        if hasattr(self, 'selector_toggle_btn'):
            if self._selector_active and self._selector_panel_mode == 'selector':
                self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_details', 'DETAILS'))
            else:
                self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_selector', 'SELECTOR'))
        if hasattr(self, 'selector_hint_label'):
            self.selector_hint_label.setText(
                self._t('tool_library.selector.jaw_hint', 'Drag jaws from the catalog to SP1 or SP2.')
            )
        if hasattr(self, 'selector_header_title_label'):
            self.selector_header_title_label.setText(self._t('jaw_library.selector.header_title', 'Jaw Selector'))
        if hasattr(self, 'selector_module_value_label'):
            self.selector_module_value_label.setText(self._t('tool_library.selector.jaws', 'Jaws'))
        if hasattr(self, 'selector_sp1_slot'):
            self.selector_sp1_slot.set_title(self._t('jaw_library.selector.sp1_slot', 'SP1 jaw'))
            self.selector_sp1_slot.set_drop_placeholder_text(self._t('jaw_library.selector.drop_here', 'Drop jaw here'))
        if hasattr(self, 'selector_sp2_slot'):
            self.selector_sp2_slot.set_title(self._t('jaw_library.selector.sp2_slot', 'SP2 jaw'))
            self.selector_sp2_slot.set_drop_placeholder_text(self._t('jaw_library.selector.drop_here', 'Drop jaw here'))
        if hasattr(self, 'selector_remove_btn'):
            self.selector_remove_btn.setToolTip(self._t('tool_library.selector.remove', 'Remove'))
        if hasattr(self, 'selector_done_btn'):
            self.selector_done_btn.setText(self._t('tool_library.selector.done', 'DONE'))
        if hasattr(self, 'selector_cancel_btn'):
            self.selector_cancel_btn.setText(self._t('tool_library.selector.cancel', 'CANCEL'))
        self._update_selector_spindle_ui()
        if hasattr(self, 'edit_btn'):
            self.edit_btn.setText(self._t('jaw_library.action.edit_jaw_button', 'EDIT JAW'))
        if hasattr(self, 'delete_btn'):
            self.delete_btn.setText(self._t('jaw_library.action.delete_jaw_button', 'DELETE JAW'))
        if hasattr(self, 'add_btn'):
            self.add_btn.setText(self._t('jaw_library.action.add_jaw_button', 'ADD JAW'))
        if hasattr(self, 'copy_btn'):
            self.copy_btn.setText(self._t('jaw_library.action.copy_jaw_button', 'COPY JAW'))
        if hasattr(self, 'module_switch_label'):
            self.module_switch_label.setText(self._t('tool_library.module.switch_to', 'Switch to'))
        if hasattr(self, 'module_toggle_btn'):
            target = (self.module_toggle_btn.text() or '').strip().upper()
            self.set_module_switch_target('tools' if target == self._t('tool_library.module.tools', 'TOOLS') else target)
        self._build_type_filter_items()
        for mode, btn in self.view_buttons:
            btn.setText(self._nav_mode_title(mode))
        self._refresh_selector_slots()
        self._update_selection_count_label()
        self.refresh_list()
        if self.current_jaw_id:
            self.populate_details(self.jaw_service.get_jaw(self.current_jaw_id))
        else:
            self.populate_details(None)

