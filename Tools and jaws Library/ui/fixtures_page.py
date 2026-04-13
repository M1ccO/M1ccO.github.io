"""Fixtures catalog page example for Phase 9 domain onboarding template."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QStyleOptionViewItem,
    QWidget,
)

from shared.ui.platforms.catalog_delegate import CatalogDelegate
from shared.ui.platforms.catalog_page_base import CatalogPageBase

__all__ = ['FixturesPage', 'FixtureCatalogDelegate']


class _FixtureFilterPane(QFrame):
    def __init__(self, translate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translate = translate
        self.setObjectName('fixturesFilterPane')

        layout = QFormLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setHorizontalSpacing(8)

        self.category_combo = QComboBox()
        self.category_combo.addItems(['All', 'Chuck', 'Robot', 'Legacy'])
        self.include_archived = QCheckBox(
            self._translate('tool_library.fixtures.filters.include_archived', 'Include archived')
        )

        layout.addRow(
            QLabel(self._translate('tool_library.fixtures.filters.category', 'Category')),
            self.category_combo,
        )
        layout.addRow(QLabel(''), self.include_archived)

    def get_filters(self) -> dict:
        return {
            'category': self.category_combo.currentText() or 'All',
            'include_archived': self.include_archived.isChecked(),
        }


class FixtureCatalogDelegate(CatalogDelegate):
    """Simple card renderer for the Fixtures example page."""

    def _compute_size(self, option: QStyleOptionViewItem, _data: dict) -> QSize:
        return QSize(option.rect.width(), 80)

    def _paint_item_content(self, painter: QPainter, rect: QRectF, data: dict, option: QStyleOptionViewItem) -> None:
        painter.save()
        text_color = QColor('#1F2933') if (option.state & option.State_Enabled) else QColor('#6B7280')
        title_font = QFont(option.font)
        title_font.setBold(True)
        title_font.setPointSize(max(9, option.font.pointSize()))
        body_font = QFont(option.font)
        body_font.setPointSize(max(8, option.font.pointSize() - 1))

        title = str(data.get('id') or data.get('name') or 'Fixture')
        subtitle = f"{data.get('category', 'General')} | {data.get('mount_type', 'Bolt-on')}"
        status = 'ACTIVE' if bool(data.get('is_active', True)) else 'ARCHIVED'

        title_rect = QRectF(rect.left(), rect.top() + 2, rect.width(), 22)
        subtitle_rect = QRectF(rect.left(), rect.top() + 26, rect.width(), 18)
        status_rect = QRectF(rect.left(), rect.top() + 48, rect.width(), 18)

        painter.setPen(text_color)
        painter.setFont(title_font)
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, title)

        painter.setFont(body_font)
        painter.setPen(QColor('#4B5563'))
        painter.drawText(subtitle_rect, Qt.AlignLeft | Qt.AlignVCenter, subtitle)

        painter.setPen(QColor('#0F766E') if status == 'ACTIVE' else QColor('#9A3412'))
        painter.drawText(status_rect, Qt.AlignLeft | Qt.AlignVCenter, status)
        painter.restore()


class FixturesPage(CatalogPageBase):
    """Minimal platform-backed page for the Phase 9 Fixtures example domain."""

    def __init__(self, fixture_service: Any, parent: QWidget | None = None, translate=None) -> None:
        self.fixture_service = fixture_service
        super().__init__(parent=parent, item_service=fixture_service, translate=translate)
        self.setObjectName('fixturesPage')
        self.search_input.setPlaceholderText(
            self._translate('tool_library.fixtures.search.placeholder', 'Search fixtures...')
        )
        self.refresh_catalog()

    def create_delegate(self) -> QAbstractItemDelegate:
        return FixtureCatalogDelegate(self.list_view)

    def get_item_service(self) -> Any:
        return self.fixture_service

    def build_filter_pane(self) -> QWidget:
        return _FixtureFilterPane(self._translate, self)

    def apply_filters(self, filters: dict) -> list[dict]:
        return self.fixture_service.list_fixtures(
            search_text=str(filters.get('search', '')),
            category=str(filters.get('category', 'All')),
            include_archived=bool(filters.get('include_archived', False)),
        )

    # Compatibility helpers so MainWindow can treat this as a lightweight peer.
    def refresh_list(self) -> None:
        self.refresh_catalog()

    def populate_details(self, _fixture_id) -> None:
        return

    def _clear_selection(self) -> None:
        self.list_view.clearSelection()

    def apply_localization(self, translate) -> None:
        self._translate = translate
        self.search_input.setPlaceholderText(
            self._translate('tool_library.fixtures.search.placeholder', 'Search fixtures...')
        )