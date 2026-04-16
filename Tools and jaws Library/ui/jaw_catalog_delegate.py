"""Jaw catalog delegate implemented on the platform CatalogDelegate."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

try:
    from ..config import TOOL_ICONS_DIR
except ImportError:
    from config import TOOL_ICONS_DIR
from shared.ui.platforms.catalog_delegate import CatalogDelegate
from shared.ui.platforms.catalog_page_base import (
    CATALOG_ROLE_DATA,
    CATALOG_ROLE_ICON,
    CATALOG_ROLE_ID,
)

__all__ = ['JawCatalogDelegate', 'ROLE_JAW_DATA', 'ROLE_JAW_ICON', 'ROLE_JAW_ID', 'jaw_icon_for_row']

ROLE_JAW_ID = CATALOG_ROLE_ID
ROLE_JAW_DATA = CATALOG_ROLE_DATA
ROLE_JAW_ICON = CATALOG_ROLE_ICON

ICON_SIZE = 48
ICON_SLOT_W = 52
COL_SPACING = 10
BP_FULL = 620
BP_REDUCED = 390
BP_NAME_ONLY = 180

CLR_HEADER_TEXT = QColor('#2b3136')
CLR_VALUE_TEXT = QColor('#171a1d')

_ICON_OBJECT_CACHE: dict[str, QIcon] = {}


def _header_font() -> QFont:
    font = QFont()
    font.setPointSizeF(9.0)
    font.setWeight(QFont.DemiBold)
    return font


def _value_font(point_size: float) -> QFont:
    font = QFont()
    font.setPointSizeF(point_size)
    font.setWeight(QFont.DemiBold)
    return font


def jaw_icon_for_row(jaw: dict) -> QIcon:
    path = TOOL_ICONS_DIR / 'jaw_main.png'
    if not path.exists():
        fallback = TOOL_ICONS_DIR / 'jaw_icon.png'
        path = fallback if fallback.exists() else path
    if not path.exists():
        return QIcon()
    cache_key = str(path).lower()
    if cache_key not in _ICON_OBJECT_CACHE:
        _ICON_OBJECT_CACHE[cache_key] = QIcon(str(path))
    return _ICON_OBJECT_CACHE[cache_key]


def _is_sub_spindle_jaw(jaw: dict) -> bool:
    spindle_side = str(jaw.get('spindle_side') or '').strip().lower()
    return ('sub' in spindle_side or 'vasta' in spindle_side or 'ala' in spindle_side)


def _normalize_spindle_side_key(value: str) -> str:
    text = str(value or '').strip().lower().replace('_', ' ')
    if not text:
        return ''
    if text in {'both', 'molemmat'}:
        return 'both'
    if text in {'main spindle', 'main', 'head1', 'sp1'}:
        return 'main_spindle'
    if text in {'sub spindle', 'sub', 'counter spindle', 'head2', 'sp2'}:
        return 'sub_spindle'
    if 'pää' in text or 'yla' in text or 'ylä' in text:
        return 'main_spindle'
    if 'vasta' in text or 'ala' in text:
        return 'sub_spindle'
    return text.replace(' ', '_')


class JawCatalogDelegate(CatalogDelegate):
    def __init__(self, parent=None, translate: Callable | None = None):
        super().__init__(parent)
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self._header_font = _header_font()
        self._value_font_full = _value_font(13.4)
        self._value_font_narrow = _value_font(12.4)
        self._value_font_tight = _value_font(11.4)

    def set_translate(self, translate: Callable) -> None:
        self._translate = translate

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _compute_size(self, option: QStyleOptionViewItem, item_dict: dict) -> QSize:
        width = option.rect.width() if option.rect.width() > 0 else 600
        return QSize(width, self.ROW_HEIGHT + self.CARD_MARGIN_V * 2)

    def _paint_item_content(self, painter: QPainter, option: QStyleOptionViewItem, item_dict: dict) -> None:
        full = option.rect
        card = QRect(
            full.x() + self.CARD_MARGIN_H,
            full.y() + self.CARD_MARGIN_V,
            full.width() - self.CARD_MARGIN_H * 2,
            self.ROW_HEIGHT,
        )
        content = card.adjusted(
            self.CARD_PADDING_H + self.BORDER_INSET,
            self.CARD_PADDING_V + self.BORDER_INSET,
            -(self.CARD_PADDING_H + self.BORDER_INSET),
            -(self.CARD_PADDING_V + self.BORDER_INSET),
        )

        jaw = item_dict.get('_raw', item_dict)
        card_width = card.width()
        if card_width >= BP_FULL:
            stage = 'full'
        elif card_width >= BP_REDUCED:
            stage = 'reduced'
        elif card_width >= BP_NAME_ONLY:
            stage = 'name-only'
        else:
            stage = 'icon-only'

        icon_rect = QRect(content.x(), content.y() + (content.height() - ICON_SIZE) // 2, ICON_SLOT_W, ICON_SIZE)
        icon = jaw_icon_for_row(jaw)
        pixmap = icon.pixmap(QSize(ICON_SIZE, ICON_SIZE)) if not icon.isNull() else QPixmap()
        if not pixmap.isNull() and _is_sub_spindle_jaw(jaw):
            pixmap = pixmap.transformed(QTransform().scale(-1, 1))
        if not pixmap.isNull():
            px = icon_rect.x() + (ICON_SLOT_W - pixmap.width()) // 2
            py = icon_rect.y() + (ICON_SIZE - pixmap.height()) // 2
            painter.drawPixmap(px, py, pixmap)

        if stage == 'icon-only':
            return

        text_rect = QRect(
            icon_rect.right() + COL_SPACING,
            content.y(),
            max(40, content.right() - (icon_rect.right() + COL_SPACING)),
            content.height(),
        )
        columns = self._columns(jaw, stage)

        if stage == 'name-only':
            value_font = self._value_font_narrow if card_width >= 300 else self._value_font_tight
        elif stage == 'reduced':
            value_font = self._value_font_full
        elif card_width < 500:
            value_font = self._value_font_tight
        elif card_width < 620:
            value_font = self._value_font_narrow
        else:
            value_font = self._value_font_full

        header_metrics = QFontMetrics(self._header_font)
        value_metrics = QFontMetrics(value_font)
        total_weight = sum(weight for _key, _header, _value, weight in columns) or 1
        x_pos = text_rect.x()

        for index, (_key, header, value, weight) in enumerate(columns):
            remaining = text_rect.right() - x_pos
            if index == len(columns) - 1:
                column_width = remaining
            else:
                column_width = max(80, int(text_rect.width() * (weight / total_weight)))
            column_rect = QRect(x_pos, text_rect.y(), column_width, text_rect.height())

            painter.setFont(self._header_font)
            painter.setPen(QPen(CLR_HEADER_TEXT))
            painter.drawText(
                QRect(column_rect.x(), column_rect.y() + 6, column_rect.width(), 18),
                Qt.AlignLeft | Qt.AlignTop,
                self._elide(header_metrics, header, column_rect.width()),
            )

            painter.setFont(value_font)
            painter.setPen(QPen(CLR_VALUE_TEXT))
            painter.drawText(
                QRect(column_rect.x(), column_rect.y() + 26, column_rect.width(), 28),
                Qt.AlignLeft | Qt.AlignVCenter,
                self._elide(value_metrics, value, column_rect.width()),
            )
            x_pos += column_width + COL_SPACING

        # Jaw type badge is intentionally shown only in detail panel.
        # Keep row cards text-only for parity with expected JAWS list view.

    def _columns(self, jaw: dict, stage: str) -> list[tuple[str, str, str, int]]:
        dash = '-'
        jaw_type = self._t(
            f"jaw_library.jaw_type.{(jaw.get('jaw_type') or '').strip().lower().replace(' ', '_')}",
            jaw.get('jaw_type', ''),
        )
        spindle_key = _normalize_spindle_side_key(jaw.get('spindle_side', ''))
        spindle = self._t(
            f"jaw_library.spindle_side.{spindle_key}",
            jaw.get('spindle_side', ''),
        )
        all_columns = [
            ('jaw_id', self._t('jaw_library.row.jaw_id', 'Jaw ID'), str(jaw.get('jaw_id') or dash), 180),
            ('jaw_type', self._t('jaw_library.row.jaw_type', 'Jaw type'), jaw_type or dash, 190),
            ('spindle', self._t('jaw_library.row.spindle', 'Spindle'), spindle or dash, 170),
            (
                'diameter',
                self._t('jaw_library.row.clamping_diameter_multiline', 'Clamping diameter'),
                str(jaw.get('clamping_diameter_text') or dash),
                170,
            ),
        ]
        if stage == 'name-only':
            return [all_columns[0]]
        if stage == 'reduced':
            return all_columns[:2]
        return all_columns

    def _paint_badges(self, painter: QPainter, text_rect: QRect, jaw: dict, option: QStyleOptionViewItem) -> None:
        badge_text = self._t(
            f"jaw_library.jaw_type.{(jaw.get('jaw_type') or '').strip().lower().replace(' ', '_')}",
            jaw.get('jaw_type', ''),
        )
        if not badge_text:
            return
        badge_rect = QRect(text_rect.right() - 120, text_rect.y() + 6, 110, 22)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#dfeef9') if not (option.state & QStyle.State_Selected) else QColor('#c5e0f4'))
        painter.drawRoundedRect(badge_rect, 11, 11)

        badge_font = QFont(self._header_font)
        badge_font.setPointSizeF(8.5)
        painter.setFont(badge_font)
        painter.setPen(QPen(QColor('#204864')))
        painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

    @staticmethod
    def _elide(metrics: QFontMetrics, text: str, width: int) -> str:
        return metrics.elidedText(str(text or ''), Qt.ElideRight, max(10, width - 4))
