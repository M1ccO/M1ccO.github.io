"""
Abstract base class for catalog item painting and sizing (Phase 3 Platform Layer).

This module provides CatalogDelegate, a QAbstractItemDelegate subclass that
encapsulates common rendering logic for catalog list items across all domains
(TOOLS, JAWS, Fixtures, etc.). Domain-specific subclasses override abstract
methods to customize rendering and sizing behavior.

Design Principles:
  - No embedded row widgets; all rendering via QPainter
  - Deterministic layout computed from paint rect
  - Selection state (normal, hover, selected) handled consistently
  - Abstract methods for domain-specific content rendering
  - Item dict extraction and background color computation shared
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Callable

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemDelegate, QStyle, QStyleOptionViewItem
from shared.ui.platforms.catalog_page_base import CATALOG_ROLE_DATA

__all__ = [
    "CatalogDelegate",
    "resolve_catalog_delegate_theme",
]


def resolve_catalog_delegate_theme(theme, accent: str | None = None) -> dict[str, QColor]:
    """Resolve shared semantic theme colors for delegate-painted catalog cards."""
    if isinstance(theme, dict):
        info_box_bg = str(theme.get("card_bg") or theme.get("info_box_bg") or "#ffffff")
        border = str(theme.get("border_strong") or theme.get("border") or "#3e4a56")
        list_bg = str(theme.get("row_area_bg") or theme.get("surface_bg") or "rgba(205, 212, 238, 0.97)")
        accent = str(theme.get("accent") or accent or "#42a5f5")
    else:
        info_box_bg = str(theme or "#ffffff")
        border = "#3e4a56"
        list_bg = "rgba(205, 212, 238, 0.97)"

    card_bg = QColor(info_box_bg)
    if not card_bg.isValid():
        card_bg = QColor("#ffffff")

    card_border = QColor(border)
    if not card_border.isValid():
        card_border = QColor("#3e4a56")

    row_area_bg = QColor(list_bg)
    if not row_area_bg.isValid():
        row_area_bg = QColor(205, 212, 238, 247)

    selected_border = QColor(accent or "#42a5f5")
    if not selected_border.isValid():
        selected_border = QColor("#42a5f5")

    # Hover cards stay close to the normal card surface, but lighten a touch.
    h, s, l, a = card_bg.getHslF()
    card_hover = QColor.fromHslF(h, max(0.0, s - 0.05), min(1.0, l + 0.04), a)

    return {
        "card_bg": card_bg,
        "card_hover": card_hover,
        "card_border": card_border,
        "selected_border": selected_border,
        "row_area_bg": row_area_bg,
    }


class CatalogDelegate(QAbstractItemDelegate):
    """
    Abstract base class for rendering catalog items in list views.

    Handles common painting logic: background color selection based on state,
    border rendering, and item data extraction. Domain-specific subclasses
    override abstract methods to provide custom rendering.

    Attributes:
        ROW_HEIGHT (int): Default row height in pixels (domain may override).
        CARD_MARGIN_H (int): Horizontal margin between card and list edge.
        CARD_MARGIN_V (int): Vertical margin between cards.
        CARD_PADDING_H (int): Internal horizontal padding.
        CARD_PADDING_V (int): Internal vertical padding.
        CARD_RADIUS (int): Border radius for rounded corners.
        BORDER_INSET (int): Inset space for border to prevent layout shift.
        CLR_CARD_BG (QColor): Normal card background.
        CLR_CARD_HOVER (QColor): Hover state background.
        CLR_CARD_BORDER (QColor): Normal border color.
        CLR_CARD_SELECTED_BORDER (QColor): Selected border color.
    """

    # ── Constants (Override in subclass if needed) ───────────────────────
    ROW_HEIGHT: int = 74
    CARD_MARGIN_H: int = 6
    CARD_MARGIN_V: int = 2
    CARD_PADDING_H: int = 10
    CARD_PADDING_V: int = 1
    CARD_RADIUS: int = 8
    BORDER_INSET: int = 3

    CLR_CARD_BG: QColor = QColor("#ffffff")
    CLR_CARD_HOVER: QColor = QColor("#f7fbff")
    CLR_CARD_BORDER: QColor = QColor("#3e4a56")
    CLR_CARD_SELECTED_BORDER: QColor = QColor("#42a5f5")

    def __init__(self, parent=None):
        """
        Initialize the delegate.

        Args:
            parent: Parent widget (typically a QListView or QTableView).
        """
        super().__init__(parent)

    # ── Abstract Methods (Override in subclass) ──────────────────────────

    @abstractmethod
    def _paint_item_content(
        self, painter: QPainter, option: QStyleOptionViewItem, item_dict: dict
    ) -> None:
        """
        Paint domain-specific item content inside the card.

        This method is called after the card background and border are drawn.
        Subclasses use this to render icons, text columns, metadata, etc.

        Args:
            painter: Active QPainter in save/restore context.
            option: Style option containing rect, state, palette, font, etc.
            item_dict: Item data dict extracted via _get_item_data(index).
                      Contains domain-specific fields (tool_id, description, etc.)

        Raises:
            NotImplementedError: If not overridden by subclass.
        """
        raise NotImplementedError

    @abstractmethod
    def _compute_size(self, option: QStyleOptionViewItem, item_dict: dict) -> QSize:
        """
        Compute row size for the given item.

        This method is called to determine list view row height dynamically based
        on item content. Return consistent QSize.width() (typically option.rect.width())
        and item-specific QSize.height() based on content.

        Args:
            option: Style option containing rect and other view metadata.
            item_dict: Item data dict extracted via _get_item_data(index).

        Returns:
            QSize: Row dimensions (width, height). Width typically matches
                   option.rect.width(); height is computed from content.

        Raises:
            NotImplementedError: If not overridden by subclass.
        """
        raise NotImplementedError

    # ── Concrete Methods (Final implementation) ──────────────────────────

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """
        Render the item in the list view.

        This method:
        1. Saves painter state
        2. Extracts item dict from model
        3. Draws card background and border (with selection/hover styling)
        4. Calls _paint_item_content() for domain-specific rendering
        5. Restores painter state

        Args:
            painter: Active QPainter.
            option: Style option with rect, state, palette, etc.
            index: Model index of the item being painted.
        """
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        item_dict = self._get_item_data(index)

        # ── Card rectangle (with margins) ───────────────────────────────
        full = option.rect
        card = QRect(
            full.x() + self.CARD_MARGIN_H,
            full.y() + self.CARD_MARGIN_V,
            full.width() - self.CARD_MARGIN_H * 2,
            self.ROW_HEIGHT,
        )

        # ── Background and border styling ───────────────────────────────
        bg_color = self._get_background_color(option)
        border_color = self._get_border_color(option)
        border_width = self._get_border_width(option)

        pen = painter.pen()
        pen.setColor(border_color)
        pen.setWidth(border_width)
        painter.setPen(pen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(card, self.CARD_RADIUS, self.CARD_RADIUS)

        # ── Content area (preserve space for border) ────────────────────
        content = card.adjusted(
            self.CARD_PADDING_H + self.BORDER_INSET,
            self.CARD_PADDING_V + self.BORDER_INSET,
            -(self.CARD_PADDING_H + self.BORDER_INSET),
            -(self.CARD_PADDING_V + self.BORDER_INSET),
        )

        # ── Domain-specific content rendering ───────────────────────────
        self._paint_item_content(painter, option, item_dict)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """
        Return the size of the item.

        Calls _compute_size() to allow domain-specific height calculation.

        Args:
            option: Style option with rect (used to determine available width).
            index: Model index of the item.

        Returns:
            QSize: Row dimensions (width, height).
        """
        item_dict = self._get_item_data(index)
        return self._compute_size(option, item_dict)

    # ── Helper Methods ───────────────────────────────────────────────────

    def _get_item_data(self, index: QModelIndex) -> dict:
        """
        Extract item dict from model.

        By convention, item data is stored in the model with role
        Qt.UserRole + 1. Override if using a different role.

        Args:
            index: Model index.

        Returns:
            dict: Item data; empty dict if not found.
        """
        data = index.data(CATALOG_ROLE_DATA)
        if not isinstance(data, dict):
            # Compatibility fallback for legacy delegates/models that used
            # Qt.UserRole + 1 as their dict payload role.
            data = index.data(Qt.UserRole + 1)
        return data if isinstance(data, dict) else {}

    def _get_background_color(self, option: QStyleOptionViewItem) -> QColor:
        """
        Determine card background color based on selection/hover state.

        Returns CLR_CARD_HOVER if hovered (but not selected),
        CLR_CARD_BG otherwise.

        Args:
            option: Style option with state flags.

        Returns:
            QColor: Background color.
        """
        is_hovered = bool(option.state & QStyle.State_MouseOver)
        is_selected = bool(option.state & QStyle.State_Selected)

        if is_hovered and not is_selected:
            return self.CLR_CARD_HOVER
        return self.CLR_CARD_BG

    def _get_border_color(self, option: QStyleOptionViewItem) -> QColor:
        """
        Determine border color based on selection state.

        Returns CLR_CARD_SELECTED_BORDER if selected,
        CLR_CARD_BORDER otherwise.

        Args:
            option: Style option with state flags.

        Returns:
            QColor: Border color.
        """
        is_selected = bool(option.state & QStyle.State_Selected)
        return self.CLR_CARD_SELECTED_BORDER if is_selected else self.CLR_CARD_BORDER

    def _get_border_width(self, option: QStyleOptionViewItem) -> int:
        """
        Determine border width based on selection state.

        Returns 3 if selected, 1 otherwise.

        Args:
            option: Style option with state flags.

        Returns:
            int: Border width in pixels.
        """
        is_selected = bool(option.state & QStyle.State_Selected)
        return 3 if is_selected else 1
