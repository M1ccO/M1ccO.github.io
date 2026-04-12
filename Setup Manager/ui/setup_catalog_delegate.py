from __future__ import annotations

from typing import Mapping

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem


ROLE_WORK_ID = Qt.UserRole
ROLE_WORK_DATA = Qt.UserRole + 1

ROW_HEIGHT = 74
ROW_HEIGHT_COMPACT = 74
CARD_MARGIN_H = 6
CARD_MARGIN_V = 6
CARD_RADIUS = 8
CARD_PADDING_H = 10
CARD_PADDING_V = 2
CARD_TRAILING_PAD = 0
COL_SPACING = 8
HEADER_VALUE_GAP = 1
BORDER_INSET = 3
WRAPPED_LINE_STEP_FACTOR = 0.82

BP_FULL_NARROW = 560
BP_COMPACT_WRAP = 430
BP_COMPACT_ID_ONLY = 350

CLR_CARD_BG = QColor("#ffffff")
CLR_CARD_HOVER = QColor("#f7fbff")
CLR_CARD_BORDER = QColor("#3e4a56")
CLR_CARD_SELECTED_BORDER = QColor("#42a5f5")
CLR_HEADER_TEXT = QColor("#2b3136")
CLR_VALUE_TEXT = QColor("#171a1d")


def _font(point_size: float, weight: int = QFont.DemiBold) -> QFont:
    font = QFont()
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    return font


class SetupCatalogDelegate(QStyledItemDelegate):
    def __init__(
        self,
        parent=None,
        headers: Mapping[str, str] | None = None,
        compact_mode: bool = False,
    ):
        super().__init__(parent)
        self._headers = dict(headers or {})
        self._compact_mode = bool(compact_mode)

    def set_headers(self, headers: Mapping[str, str] | None):
        self._headers = dict(headers or {})

    def set_compact_mode(self, compact_mode: bool):
        self._compact_mode = bool(compact_mode)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        width = option.rect.width()
        if width <= 0:
            width = 620 if self._compact_mode else 600
        row_height = ROW_HEIGHT_COMPACT if self._compact_mode else ROW_HEIGHT
        return QSize(width, row_height + CARD_MARGIN_V * 2)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        row = index.data(ROLE_WORK_DATA) or {}
        work_id = str(index.data(ROLE_WORK_ID) or row.get("work_id") or "").strip() or "-"
        drawing_id = str(row.get("drawing_id") or "").strip() or "-"
        description = str(row.get("description") or "").strip() or "-"
        last_run = str(row.get("latest_text") or "").strip() or "-"

        full = option.rect
        card = QRect(
            full.x() + CARD_MARGIN_H,
            full.y() + CARD_MARGIN_V,
            max(0, full.width() - CARD_MARGIN_H * 2),
            ROW_HEIGHT,
        )

        hovered = bool(option.state & QStyle.State_MouseOver)
        selected = bool(option.state & QStyle.State_Selected)

        bg = CLR_CARD_HOVER if hovered and not selected else CLR_CARD_BG
        border_color = CLR_CARD_SELECTED_BORDER if selected else CLR_CARD_BORDER
        border_width = 3 if selected else 1

        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(bg)
        painter.drawRoundedRect(card, CARD_RADIUS, CARD_RADIUS)

        content = card.adjusted(
            CARD_PADDING_H + BORDER_INSET,
            CARD_PADDING_V + BORDER_INSET,
            -(CARD_PADDING_H + BORDER_INSET + CARD_TRAILING_PAD),
            -(CARD_PADDING_V + BORDER_INSET),
        )

        card_width = card.width()
        if card_width >= BP_FULL_NARROW:
            stage = "full"
        elif card_width >= BP_COMPACT_WRAP:
            stage = "compact"
        elif card_width >= BP_COMPACT_ID_ONLY:
            stage = "compact-wrap"
        else:
            stage = "id-only"

        if stage == "full":
            header_font = _font(10.0)
            value_font = _font(14.5)
            description_font = value_font
            columns = [
                ("work_id", self._headers.get("work_id", "Work ID"), work_id, 175),
                ("drawing", self._headers.get("drawing", "Drawing"), drawing_id, 180),
                ("description", self._headers.get("description", "Description"), description, 235),
                ("last_run", self._headers.get("last_run", "Last run"), last_run, 225),
            ]
        elif stage == "compact":
            header_font = _font(10.0)
            value_font = _font(14.5)
            description_font = value_font
            columns = [
                ("work_id", self._headers.get("work_id", "Work ID"), work_id, 180),
                ("description", self._headers.get("description", "Description"), description, 220),
            ]
        elif stage == "compact-wrap":
            header_font = _font(10.0)
            value_font = _font(14.5)
            description_font = value_font
            columns = [
                ("work_id", self._headers.get("work_id", "Work ID"), work_id, 180),
                ("description", self._headers.get("description", "Description"), description, 220),
            ]
        else:
            header_font = _font(10.0)
            value_font = _font(14.5)
            description_font = value_font
            columns = [
                ("work_id", self._headers.get("work_id", "Work ID"), work_id, 1),
            ]

        col_rects = self._column_rects(content, columns)
        for rect, (key, header, value, _weight) in zip(col_rects, columns):
            value_font_for_col = description_font if key == "description" else value_font
            self._paint_column(
                painter,
                rect,
                header,
                value,
                header_font,
                value_font_for_col,
                wrap_value=(stage == "compact-wrap" and key == "description"),
            )

        painter.restore()

    def _column_rects(
        self,
        content: QRect,
        columns: list[tuple[str, str, str, int]],
    ) -> list[QRect]:
        if not columns:
            return []
        spacing_total = COL_SPACING * (len(columns) - 1)
        available = max(0, content.width() - spacing_total)
        total_weight = max(1, sum(max(0, column[3]) for column in columns))
        rects: list[QRect] = []
        x = content.x()
        remaining_width = available
        remaining_weight = total_weight
        for idx, column in enumerate(columns):
            weight = max(0, column[3])
            if idx == len(columns) - 1 or remaining_weight <= 0:
                width = remaining_width
            else:
                width = round(remaining_width * weight / remaining_weight)
            width = max(0, width)
            rects.append(QRect(x, content.y(), width, content.height()))
            x += width + COL_SPACING
            remaining_width = max(0, available - (x - content.x() - COL_SPACING * (idx + 1)))
            remaining_weight = max(0, remaining_weight - weight)
        return rects

    def _paint_column(
        self,
        painter: QPainter,
        rect: QRect,
        header: str,
        value: str,
        header_font: QFont,
        value_font: QFont,
        wrap_value: bool = False,
    ):
        painter.setPen(CLR_HEADER_TEXT)
        painter.setFont(header_font)
        header_metrics = QFontMetrics(header_font)
        header_height = max(
            header_metrics.height(),
            header_metrics.boundingRect(
                QRect(0, 0, max(1, rect.width()), rect.height()),
                Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                header,
            ).height(),
        )

        painter.setPen(CLR_VALUE_TEXT)
        painter.setFont(value_font)
        value_metrics = QFontMetrics(value_font)
        value_width = max(1, rect.width())
        lines = self._wrapped_lines(value_metrics, value, value_width) if wrap_value else [value_metrics.elidedText(value, Qt.ElideRight, value_width)]
        line_height = value_metrics.height()
        if wrap_value and len(lines) > 1:
            value_height = max(line_height, round(line_height * WRAPPED_LINE_STEP_FACTOR) * len(lines))
        else:
            value_height = line_height

        total_height = header_height + HEADER_VALUE_GAP + value_height
        top = rect.y() + max(0, (rect.height() - total_height) // 2)

        painter.setPen(CLR_HEADER_TEXT)
        painter.setFont(header_font)
        header_rect = QRect(rect.x(), top, rect.width(), header_height)
        painter.drawText(header_rect, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, header)

        painter.setPen(CLR_VALUE_TEXT)
        painter.setFont(value_font)
        value_top = header_rect.bottom() + 1 + HEADER_VALUE_GAP
        if wrap_value and len(lines) > 1:
            step = max(1, round(line_height * WRAPPED_LINE_STEP_FACTOR))
            block_height = step * (len(lines) - 1) + line_height
            start_y = value_top + max(0, (value_height - block_height) // 2)
            for idx, line in enumerate(lines):
                line_rect = QRect(rect.x(), start_y + idx * step, rect.width(), line_height)
                painter.drawText(line_rect, Qt.AlignHCenter | Qt.AlignVCenter, line)
        else:
            value_rect = QRect(rect.x(), value_top, rect.width(), value_height)
            painter.drawText(value_rect, Qt.AlignHCenter | Qt.AlignVCenter, lines[0] if lines else "")

    @staticmethod
    def _wrapped_lines(metrics: QFontMetrics, text: str, width: int) -> list[str]:
        raw = (text or "").strip()
        if not raw:
            return [""]
        if metrics.horizontalAdvance(raw) <= width:
            return [raw]

        words = raw.split()
        if len(words) <= 1:
            return [metrics.elidedText(raw, Qt.ElideRight, width)]

        line1 = ""
        consumed = -1
        for idx, word in enumerate(words):
            candidate = word if not line1 else f"{line1} {word}"
            if metrics.horizontalAdvance(candidate) <= width:
                line1 = candidate
                consumed = idx
                continue
            break

        if not line1:
            return [metrics.elidedText(raw, Qt.ElideRight, width)]

        remainder_words = words[consumed + 1 :]
        if not remainder_words:
            return [line1]
        line2 = metrics.elidedText(" ".join(remainder_words), Qt.ElideRight, width)
        return [line1, line2]
