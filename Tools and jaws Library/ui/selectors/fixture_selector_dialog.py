from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from config import SHARED_UI_PREFERENCES_PATH
from shared.ui.helpers.editor_helpers import create_titled_section
from shared.ui.helpers.page_scaffold_common import build_catalog_list_shell
from shared.ui.helpers.topbar_common import build_filter_frame
from shared.ui.helpers.window_geometry_memory import restore_window_geometry, save_window_geometry
from ui.selectors.common import SelectorDialogBase, build_selector_bottom_bar


class FixtureSelectorDialog(SelectorDialogBase):
    """Standalone multi-select fixture selector hosted in a dialog."""

    def __init__(
        self,
        *,
        fixture_service,
        translate: Callable[[str, str | None], str],
        initial_assignments: list[dict] | None,
        on_submit: Callable[[dict], None],
        on_cancel: Callable[[], None],
        parent=None,
    ):
        super().__init__(translate=translate, on_cancel=on_cancel, parent=parent)
        self.fixture_service = fixture_service
        self._on_submit = on_submit
        self._selected_items_by_id: dict[str, dict] = {}
        self.current_fixture_id: str | None = None

        for item in initial_assignments or []:
            if not isinstance(item, dict):
                continue
            fixture_id = str(item.get("fixture_id") or item.get("id") or "").strip()
            if not fixture_id:
                continue
            self._selected_items_by_id[fixture_id] = {
                "fixture_id": fixture_id,
                "fixture_type": str(item.get("fixture_type") or "").strip(),
                "fixture_kind": str(item.get("fixture_kind") or "").strip(),
            }

        self.setWindowTitle(self._t("fixture_library.selector.header_title", "Fixture Selector"))
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.resize(1120, 720)
        restore_window_geometry(self, SHARED_UI_PREFERENCES_PATH, 'fixture_selector_dialog')

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self._build_toolbar(root)
        self._build_content(root)
        self._build_bottom_bar(root)

        self._refresh_catalog()
        self._refresh_selected_list()

    def closeEvent(self, event) -> None:
        save_window_geometry(self, SHARED_UI_PREFERENCES_PATH, 'fixture_selector_dialog')
        super().closeEvent(event)

    def _build_toolbar(self, root: QVBoxLayout) -> None:
        frame, layout = build_filter_frame()
        frame.setObjectName('')
        layout.setContentsMargins(8, 6, 8, 6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            self._t('fixture_library.search.placeholder', 'Search fixture ID, type, kind, diameter, work or notes')
        )
        self.search_input.textChanged.connect(self._refresh_catalog)
        layout.addWidget(self.search_input, 1)

        self.kind_filter = QComboBox()
        self.kind_filter.addItem(self._t('tool_library.nav.all_fixtures', 'All Fixtures'), 'all')
        self.kind_filter.addItem(self._t('tool_library.nav.fixture_parts', 'Parts'), 'parts')
        self.kind_filter.addItem(self._t('tool_library.nav.fixture_assemblies', 'Assemblies'), 'assemblies')
        self.kind_filter.currentIndexChanged.connect(self._refresh_catalog)
        layout.addWidget(self.kind_filter, 0)

        root.addWidget(frame, 0)

    def _build_content(self, root: QVBoxLayout) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)

        list_card, list_layout = build_catalog_list_shell()
        self.catalog_list = QListWidget()
        self.catalog_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.catalog_list.itemDoubleClicked.connect(self._toggle_item_selection)
        self.catalog_list.itemSelectionChanged.connect(self._on_catalog_selection_changed)
        list_layout.addWidget(self.catalog_list, 1)
        splitter.addWidget(list_card)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        header = QFrame()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(4)
        title = QLabel(self._t('fixture_library.selector.selection_title', 'Selected fixtures'))
        title.setProperty('detailSectionTitle', True)
        hint = QLabel(self._t('fixture_library.selector.hint', 'Double-click fixtures to add or remove them from the selection.'))
        hint.setWordWrap(True)
        hint.setProperty('detailHint', True)
        header_layout.addWidget(title)
        header_layout.addWidget(hint)
        right_layout.addWidget(header, 0)

        self.selected_list_card = create_titled_section(self._t('fixture_library.selector.selection_title', 'Selected fixtures'))
        self.selected_list = QListWidget()
        self.selected_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.selected_list.itemDoubleClicked.connect(self._remove_selected_from_panel)
        selected_layout = QVBoxLayout(self.selected_list_card)
        selected_layout.setContentsMargins(8, 6, 8, 8)
        selected_layout.addWidget(self.selected_list, 1)
        right_layout.addWidget(self.selected_list_card, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        self.add_btn = QPushButton(self._t('common.add', 'Add').upper())
        self.add_btn.setProperty('panelActionButton', True)
        self.add_btn.clicked.connect(self._add_current_selection)
        actions.addWidget(self.add_btn)
        self.remove_btn = QPushButton(self._t('common.remove', 'Remove').upper())
        self.remove_btn.setProperty('panelActionButton', True)
        self.remove_btn.clicked.connect(self._remove_selected_from_panel)
        actions.addWidget(self.remove_btn)
        actions.addStretch(1)
        right_layout.addLayout(actions)

        splitter.addWidget(right_panel)
        splitter.setSizes([650, 470])
        root.addWidget(splitter, 1)

    def _build_bottom_bar(self, root: QVBoxLayout) -> None:
        build_selector_bottom_bar(
            root,
            translate=self._translate,
            on_cancel=self._cancel,
            on_done=self._send_selector_selection,
        )

    def _refresh_catalog(self) -> None:
        search_text = self.search_input.text().strip()
        view_mode = str(self.kind_filter.currentData() or 'all')
        fixtures = self.fixture_service.list_fixtures(search_text=search_text, view_mode=view_mode)

        self.catalog_list.blockSignals(True)
        self.catalog_list.clear()
        for fixture in fixtures:
            fixture_id = str(fixture.get('fixture_id') or '').strip()
            if not fixture_id:
                continue
            fixture_type = str(fixture.get('fixture_type') or '').strip()
            fixture_kind = str(fixture.get('fixture_kind') or '').strip()
            parts = [fixture_id]
            if fixture_type:
                parts.append(fixture_type)
            if fixture_kind:
                parts.append(f"[{fixture_kind}]")
            item = QListWidgetItem('  '.join(parts))
            item.setData(Qt.UserRole, {
                'fixture_id': fixture_id,
                'fixture_type': fixture_type,
                'fixture_kind': fixture_kind,
            })
            if fixture_id in self._selected_items_by_id:
                item.setSelected(True)
            self.catalog_list.addItem(item)
        self.catalog_list.blockSignals(False)

    def _on_catalog_selection_changed(self) -> None:
        selected = self.catalog_list.selectedItems()
        self.add_btn.setEnabled(bool(selected))

    def _toggle_item_selection(self, item: QListWidgetItem) -> None:
        if item is None:
            return
        data = item.data(Qt.UserRole) or {}
        fixture_id = str(data.get('fixture_id') or '').strip()
        if not fixture_id:
            return
        if fixture_id in self._selected_items_by_id:
            self._selected_items_by_id.pop(fixture_id, None)
        else:
            self._selected_items_by_id[fixture_id] = dict(data)
        self._refresh_catalog()
        self._refresh_selected_list()

    def _add_current_selection(self) -> None:
        for item in self.catalog_list.selectedItems():
            data = item.data(Qt.UserRole) or {}
            fixture_id = str(data.get('fixture_id') or '').strip()
            if fixture_id:
                self._selected_items_by_id[fixture_id] = dict(data)
        self._refresh_catalog()
        self._refresh_selected_list()

    def _remove_selected_from_panel(self, _item: QListWidgetItem | None = None) -> None:
        for item in self.selected_list.selectedItems():
            data = item.data(Qt.UserRole) or {}
            fixture_id = str(data.get('fixture_id') or '').strip()
            if fixture_id:
                self._selected_items_by_id.pop(fixture_id, None)
        self._refresh_catalog()
        self._refresh_selected_list()

    def _build_selector_payload(self) -> dict:
        selected_items = [
            dict(item)
            for _, item in sorted(self._selected_items_by_id.items(), key=lambda pair: pair[0])
        ]
        return {
            'kind': 'fixtures',
            'selected_items': selected_items,
        }

    def _refresh_selected_list(self) -> None:
        self.selected_list.clear()
        for fixture_id, data in sorted(self._selected_items_by_id.items()):
            fixture_type = str(data.get('fixture_type') or '').strip()
            fixture_kind = str(data.get('fixture_kind') or '').strip()
            parts = [fixture_id]
            if fixture_type:
                parts.append(fixture_type)
            if fixture_kind:
                parts.append(f"[{fixture_kind}]")
            item = QListWidgetItem('  '.join(parts))
            item.setData(Qt.UserRole, dict(data))
            self.selected_list.addItem(item)
        self.remove_btn.setEnabled(self.selected_list.count() > 0)

    def _cancel(self) -> None:
        self._cancel_dialog()

    def _send_selector_selection(self) -> None:
        payload = self._build_selector_payload()
        self._finish_submit(self._on_submit, payload)