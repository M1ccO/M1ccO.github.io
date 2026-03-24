"""
Custom QStyledItemDelegate for painting tool catalog rows.

All layout is computed from the paint rect — no child widgets, no nested layouts,
no QSS-driven size negotiation.  The icon is always painted at a fixed position,
and text columns are measured / elided deterministically with QFontMetrics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from config import DEFAULT_TOOL_ICON, TOOL_ICONS_DIR, TOOL_TYPE_TO_ICON

# ── Data roles stored in the model ──────────────────────────────────────
ROLE_TOOL_ID = Qt.UserRole
ROLE_TOOL_DATA = Qt.UserRole + 1
ROLE_TOOL_ICON = Qt.UserRole + 2

# ── Layout constants ────────────────────────────────────────────────────
ROW_HEIGHT = 74
ICON_SIZE = 40
ICON_SLOT_W = 48
ICON_VISUAL_OFFSET_Y = 3
CARD_RADIUS = 8
CARD_MARGIN_H = 6          # horizontal gap between cards and list edge
CARD_MARGIN_V = 2           # vertical gap between cards
CARD_PADDING_H = 10         # inner horizontal padding inside the card
CARD_PADDING_V = 2          # inner vertical padding inside the card
COL_SPACING = 10            # gap between text columns
HEADER_VALUE_GAP = 1        # vertical gap between header and value text
BORDER_INSET = 3            # always reserve space for thickest border so selection doesn't shift
WRAPPED_LINE_STEP_FACTOR = 0.82

# ── Responsive stage breakpoints ────────────────────────────────────────
BP_FULL = 620               # card_width >= this → full (all columns)
BP_REDUCED = 390            # card_width >= this → reduced (id + name)
BP_NAME_ONLY = 180          # card_width >= this → name only
# below BP_NAME_ONLY → icon only

# ── Colours ─────────────────────────────────────────────────────────────
CLR_CARD_BG = QColor('#ffffff')
CLR_CARD_HOVER = QColor('#f7fbff')
CLR_CARD_BORDER = QColor('#3e4a56')
CLR_CARD_SELECTED_BORDER = QColor('#42a5f5')
CLR_HEADER_TEXT = QColor('#2b3136')
CLR_VALUE_TEXT = QColor('#171a1d')
CLR_LIST_BG = QColor(205, 212, 238, 247)  # rgba(205,212,238,0.97)


# ── Fonts (built once, reused) ──────────────────────────────────────────
def _header_font() -> QFont:
    f = QFont()
    f.setPointSizeF(10.0)
    f.setWeight(QFont.DemiBold)
    return f


def _value_font(pt: float = 14.5) -> QFont:
    f = QFont()
    f.setPointSizeF(pt)
    f.setWeight(QFont.DemiBold)
    return f


def _safe_float(value) -> str:
    try:
        return f'{float(value or 0):.3f}'
    except Exception:
        return '0.000'


def _parse_json_list(value):
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def tool_icon_for_type(tool_type: str) -> QIcon:
    filename = TOOL_TYPE_TO_ICON.get(tool_type, DEFAULT_TOOL_ICON)
    path = TOOL_ICONS_DIR / filename
    if not path.exists():
        path = TOOL_ICONS_DIR / DEFAULT_TOOL_ICON
    return QIcon(str(path)) if path.exists() else QIcon()


# ── Column definitions per view mode ────────────────────────────────────

def _home_columns(tool: dict, t: Callable) -> list[tuple[str, str, str, int]]:
    """Return (key, header, value, weight) tuples for the home/tools view."""
    desc = (tool.get('description', '') or '').strip() or t('tool_library.common.no_description', 'No description')
    return [
        ('tool_id', t('tool_library.row.tool_id', 'Tool ID'), tool.get('id', ''), 100),
        ('tool_name', t('tool_library.row.tool_name', 'Tool name'), desc, 270),
        ('geom_x', t('tool_library.field.geom_x', 'Geom X'), _safe_float(tool.get('geom_x', 0)), 110),
        ('geom_z', t('tool_library.field.geom_z', 'Geom Z'), _safe_float(tool.get('geom_z', 0)), 110),
        ('radius', t('tool_library.field.radius', 'Radius'), _safe_float(tool.get('radius', 0)), 95),
        ('nose_corner_radius', t('tool_library.field.nose_corner_radius_multiline', 'Nose /\nCorner R'), _safe_float(tool.get('nose_corner_radius', 0)), 145),
    ]


def _holders_columns(tool: dict, t: Callable) -> list[tuple[str, str, str, int]]:
    desc = (tool.get('description', '') or '').strip() or t('tool_library.common.no_description', 'No description')
    return [
        ('tool_id', t('tool_library.row.tool_id', 'Tool ID'), tool.get('id', ''), 100),
        ('holder_name', t('tool_library.row.holder_name', 'Holder name'), (tool.get('holder_code', '') or '').strip() or '-', 220),
        ('tool_name', t('tool_library.row.tool_name', 'Tool name'), desc, 320),
    ]


def _inserts_columns(tool: dict, t: Callable) -> list[tuple[str, str, str, int]]:
    desc = (tool.get('description', '') or '').strip() or t('tool_library.common.no_description', 'No description')
    return [
        ('tool_id', t('tool_library.row.tool_id', 'Tool ID'), tool.get('id', ''), 100),
        ('insert_name', t('tool_library.row.insert_name', 'Insert name'), (tool.get('cutting_code', '') or '').strip() or '-', 250),
        ('tool_name', t('tool_library.row.tool_name', 'Tool name'), desc, 320),
    ]


def _assemblies_columns(tool: dict, t: Callable) -> list[tuple[str, str, str, int]]:
    desc = (tool.get('description', '') or '').strip() or t('tool_library.common.no_description', 'No description')
    support_parts = _parse_json_list(tool.get('support_parts'))
    stl_parts = _parse_json_list(tool.get('stl_path'))
    return [
        ('tool_id', t('tool_library.row.tool_id', 'Tool ID'), tool.get('id', ''), 100),
        ('tool_name', t('tool_library.row.assembly_name', 'Assembly name'), desc, 260),
        ('support_parts', t('tool_library.row.support_parts', 'Support parts'), str(len(support_parts)), 130),
        ('model_parts', t('tool_library.row.model_parts', '3D parts'), str(len(stl_parts) if stl_parts else 0), 120),
    ]


COLUMNS_BY_MODE = {
    'home': _home_columns,
    'holders': _holders_columns,
    'inserts': _inserts_columns,
    'assemblies': _assemblies_columns,
}


# ── Delegate ────────────────────────────────────────────────────────────

class ToolCatalogDelegate(QStyledItemDelegate):
    """Paints each tool row as a rounded card with deterministic layout."""

    def __init__(self, parent=None, view_mode: str = 'home',
                 translate: Callable | None = None):
        super().__init__(parent)
        self._view_mode = (view_mode or 'home').lower()
        self._translate = translate or (lambda k, d=None, **kw: d or '')
        # pre-build fonts
        self._header_font = _header_font()
        self._value_font_full = _value_font(14.5)
        self._value_font_narrow = _value_font(13.0)
        self._value_font_tight = _value_font(12.0)
        self._value_font_tiny = _value_font(11.0)
        # icon pixmap cache  {tool_type: QPixmap}
        self._icon_cache: dict[str, QPixmap] = {}

    # ── public helpers ──────────────────────────────────────────────────

    def set_view_mode(self, mode: str):
        self._view_mode = (mode or 'home').lower()

    def set_translate(self, translate: Callable):
        self._translate = translate

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _description_line_count(self, fm: QFontMetrics, text: str, width: int, stage: str) -> int:
        raw = (text or '').strip()
        if not raw or stage == 'icon-only' or width < 16:
            return 1
        breakable = ' ' in raw or '-' in raw or '/' in raw
        if stage == 'name-only' and breakable:
            return 2
        if fm.horizontalAdvance(raw) <= width:
            return 1
        if not breakable:
            return 1
        return 2

    # ── sizing ──────────────────────────────────────────────────────────

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        width = option.rect.width() if option.rect.width() > 0 else 600
        return QSize(width, ROW_HEIGHT + CARD_MARGIN_V * 2)

    # ── painting ────────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        tool: dict = index.data(ROLE_TOOL_DATA) or {}
        tool_id: str = index.data(ROLE_TOOL_ID) or ''
        icon: QIcon | None = index.data(ROLE_TOOL_ICON)

        # ── card rectangle ──────────────────────────────────────────────
        full = option.rect
        card = QRect(
            full.x() + CARD_MARGIN_H,
            full.y() + CARD_MARGIN_V,
            full.width() - CARD_MARGIN_H * 2,
            ROW_HEIGHT,
        )
        card_w = card.width()

        # ── determine responsive stage ──────────────────────────────────
        if card_w >= BP_FULL:
            stage = 'full'
        elif card_w >= BP_REDUCED:
            stage = 'reduced'
        elif card_w >= BP_NAME_ONLY:
            stage = 'name-only'
        else:
            stage = 'icon-only'

        # ── background + border ─────────────────────────────────────────
        hovered = bool(option.state & QStyle.State_MouseOver)
        selected = bool(option.state & QStyle.State_Selected)

        bg = CLR_CARD_HOVER if hovered and not selected else CLR_CARD_BG
        border_color = CLR_CARD_SELECTED_BORDER if selected else CLR_CARD_BORDER
        border_width = 3 if selected else 1

        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(bg)
        painter.drawRoundedRect(card, CARD_RADIUS, CARD_RADIUS)

        # ── content rect (inside card padding) ─────────────────────────
        # Always use the same inset so content never shifts on selection.
        content = card.adjusted(
            CARD_PADDING_H + BORDER_INSET,
            CARD_PADDING_V + BORDER_INSET,
            -(CARD_PADDING_H + BORDER_INSET),
            -(CARD_PADDING_V + BORDER_INSET),
        )

        # ── icon ────────────────────────────────────────────────────────
        icon_rect = QRect(content.x(), content.y() + (content.height() - ICON_SIZE) // 2 + ICON_VISUAL_OFFSET_Y,
                          ICON_SLOT_W, ICON_SIZE)
        if icon is not None:
            pm = self._cached_pixmap(icon, tool.get('tool_type', ''))
            if pm and not pm.isNull():
                px = icon_rect.x() + (ICON_SLOT_W - pm.width()) // 2
                py = icon_rect.y() + (ICON_SIZE - pm.height()) // 2
                painter.drawPixmap(px, py, pm)

        if stage == 'icon-only':
            painter.restore()
            return

        # ── decide which columns to paint ───────────────────────────────
        col_fn = COLUMNS_BY_MODE.get(self._view_mode, _home_columns)
        all_cols = col_fn(tool, self._t)

        if stage == 'name-only':
            cols = [c for c in all_cols if c[0] == 'tool_name']
        elif stage == 'reduced':
            cols = [c for c in all_cols if c[0] in ('tool_id', 'tool_name')]
        else:
            cols = all_cols

        # ── choose value font based on stage ────────────────────────────
        if stage == 'name-only':
            if card_w < 300:
                vfont = self._value_font_tight
            else:
                vfont = self._value_font_narrow
        elif stage == 'reduced':
            vfont = self._value_font_full
        elif card_w < 500:
            vfont = self._value_font_tight
        elif card_w < 620:
            vfont = self._value_font_narrow
        else:
            vfont = self._value_font_full

        hfont = self._header_font
        hfm = QFontMetrics(hfont)
        vfm = QFontMetrics(vfont)

        # ── compute column rects ────────────────────────────────────────
        text_left = content.x() + ICON_SLOT_W + COL_SPACING
        text_width = content.width() - ICON_SLOT_W - COL_SPACING
        if text_width < 10:
            painter.restore()
            return

        total_weight = sum(c[3] for c in cols) or 1
        col_rects: list[tuple[str, str, str, QRect]] = []
        x = text_left
        for i, (key, header, value, weight) in enumerate(cols):
            if i == len(cols) - 1:
                w = text_left + text_width - x
            else:
                w = int(text_width * weight / total_weight)
            col_rects.append((key, header, value, QRect(x, content.y(), w, content.height())))
            x += w + (COL_SPACING if i < len(cols) - 1 else 0)

        # ── paint each column ───────────────────────────────────────────
        single_header_h = hfm.height()
        value_line_h = vfm.height()
        for key, header, value, rect in col_rects:
            if rect.width() < 8:
                continue

            # determine if header is multi-line
            header_lines = header.split('\n') if '\n' in header else [header]
            header_h = single_header_h * len(header_lines) + 2

            # compute block height and vertical offset to center it
            line_count = (
                self._description_line_count(vfm, value, rect.width(), stage)
                if key == 'tool_name' else 1
            )
            wrapped = line_count == 2 and key == 'tool_name'
            effective_value_h = int(round(value_line_h * WRAPPED_LINE_STEP_FACTOR)) if wrapped else value_line_h
            value_h = value_line_h + effective_value_h if wrapped else value_line_h * line_count
            block_h = header_h + HEADER_VALUE_GAP + value_h
            y_off = max(0, (rect.height() - block_h) // 2)

            # header
            painter.setFont(hfont)
            painter.setPen(CLR_HEADER_TEXT)
            if len(header_lines) > 1:
                for ln_i, ln_text in enumerate(header_lines):
                    ln_rect = QRect(rect.x(), rect.y() + y_off + single_header_h * ln_i,
                                    rect.width(), single_header_h)
                    elided_ln = hfm.elidedText(ln_text.strip(), Qt.ElideRight, rect.width())
                    painter.drawText(ln_rect, Qt.AlignHCenter | Qt.AlignBottom, elided_ln)
            else:
                header_rect = QRect(rect.x(), rect.y() + y_off, rect.width(), header_h)
                elided_header = hfm.elidedText(header_lines[0], Qt.ElideRight, rect.width())
                painter.drawText(header_rect, Qt.AlignHCenter | Qt.AlignBottom, elided_header)

            # value
            value_rect = QRect(rect.x(), rect.y() + y_off + header_h + HEADER_VALUE_GAP,
                               rect.width(), rect.height() - y_off - header_h - HEADER_VALUE_GAP)
            painter.setFont(vfont)
            painter.setPen(CLR_VALUE_TEXT)

            if key == 'tool_name':
                self._paint_description(painter, value, value_rect, stage)
            else:
                elided = vfm.elidedText(value, Qt.ElideRight, value_rect.width())
                painter.drawText(value_rect, Qt.AlignHCenter | Qt.AlignTop, elided)

        painter.restore()

    # ── description painting (two-line fitting) ─────────────────────────

    def _paint_description(self, painter: QPainter, text: str, rect: QRect, stage: str):
        """Paint the tool description, splitting into two lines when it no longer fits."""
        fm = QFontMetrics(painter.font())
        raw = (text or '').strip()
        if not raw:
            return

        w = rect.width()
        two_lines = self._description_line_count(fm, raw, w, stage) == 2
        line_h = fm.height()
        line_step = max(1, int(round(line_h * WRAPPED_LINE_STEP_FACTOR))) if two_lines else line_h

        if not two_lines or fm.horizontalAdvance(raw) <= w:
            elided = fm.elidedText(raw, Qt.ElideRight, w)
            painter.drawText(rect, Qt.AlignHCenter | Qt.AlignTop, elided)
            return

        # try to split at ' - ' first
        if ' - ' in raw:
            left, right = raw.split(' - ', 1)
            left = left.strip()
            right = f'- {right.strip()}'
            if left and fm.horizontalAdvance(left) <= w:
                painter.drawText(QRect(rect.x(), rect.y(), w, line_h),
                                 Qt.AlignHCenter | Qt.AlignTop, left)
                elided2 = fm.elidedText(right, Qt.ElideRight, w)
                painter.drawText(QRect(rect.x(), rect.y() + line_step, w, line_h),
                                 Qt.AlignHCenter | Qt.AlignTop, elided2)
                return

        # word-wrap fitting
        tokens = raw.split()
        first_tokens: list[str] = []
        rest = tokens[:]
        while rest:
            candidate = ' '.join(first_tokens + [rest[0]])
            if not first_tokens or fm.horizontalAdvance(candidate) <= w:
                first_tokens.append(rest.pop(0))
            else:
                break

        line1 = ' '.join(first_tokens)
        if not rest:
            elided1 = fm.elidedText(line1, Qt.ElideRight, w)
            painter.drawText(rect, Qt.AlignHCenter | Qt.AlignTop, elided1)
            return

        painter.drawText(QRect(rect.x(), rect.y(), w, line_h),
                         Qt.AlignHCenter | Qt.AlignTop, fm.elidedText(line1, Qt.ElideRight, w))
        line2 = fm.elidedText(' '.join(rest), Qt.ElideRight, w)
        painter.drawText(QRect(rect.x(), rect.y() + line_step, w, line_h),
                         Qt.AlignHCenter | Qt.AlignTop, line2)

    # ── icon cache ──────────────────────────────────────────────────────

    def _cached_pixmap(self, icon: QIcon, tool_type: str) -> QPixmap | None:
        key = tool_type or '__default__'
        if key not in self._icon_cache:
            pm = icon.pixmap(QSize(ICON_SIZE, ICON_SIZE))
            pm = self._normalized_icon_pixmap(pm)
            self._icon_cache[key] = pm
        return self._icon_cache.get(key)

    @staticmethod
    def _normalized_icon_pixmap(pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull():
            return pixmap

        image = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
        left = image.width()
        top = image.height()
        right = -1
        bottom = -1

        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() > 6:
                    left = min(left, x)
                    top = min(top, y)
                    right = max(right, x)
                    bottom = max(bottom, y)

        if right < left or bottom < top:
            return pixmap

        cropped = image.copy(left, top, right - left + 1, bottom - top + 1)
        normalized = QPixmap.fromImage(
            cropped.scaled(QSize(ICON_SIZE, ICON_SIZE), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        return normalized if not normalized.isNull() else pixmap
