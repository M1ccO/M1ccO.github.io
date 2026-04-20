from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import QModelIndex, QTimer, Qt
from PySide6.QtWidgets import QVBoxLayout

try:
    from ...config import SHARED_UI_PREFERENCES_PATH
except ImportError:
    from config import SHARED_UI_PREFERENCES_PATH
from shared.ui.helpers.window_geometry_memory import restore_window_geometry, save_window_geometry
from shared.ui.selectors import ToolSelectorWidget
from .common import SelectorDialogBase, SelectorWidgetBase
from .tool_selector_layout import ToolSelectorLayoutMixin
from .tool_selector_payload import ToolSelectorPayloadMixin
from .tool_selector_state import ToolSelectorStateMixin
from ..tool_catalog_delegate import ROLE_TOOL_DATA
from ..home_page_support.retranslate_page import (
    localized_tool_type as _localized_tool_type_impl,
    tool_id_display_value as _tool_id_display_value_impl,
)


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
            window_flags=Qt.Widget if self._embedded_mode else Qt.WindowFlags(),
        )
        self.tool_service = tool_service
        self.machine_profile = machine_profile
        self._on_submit = on_submit

        self._current_head = self._normalize_head(selector_head)
        self._current_spindle = self._normalize_spindle(selector_spindle)
        self._assigned_tools: list[dict] = []
        self.current_tool_id: str | None = None
        self.current_tool_uid: int | None = None
        self._assignments_by_target = self._build_initial_buckets(
            initial_assignments,
            initial_assignment_buckets,
        )

        # Required by detail panel builder (detail_panel_builder.py / _clear_details)
        self._detail_preview_widget = None
        self._detail_preview_model_key = None

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
                self.resize(1180, 720)
                restore_window_geometry(self, SHARED_UI_PREFERENCES_PATH, 'tool_selector_dialog')

            inner = self._make_themed_inner_layout()

            self._build_filter_row(inner)
            self._build_content(inner)
            self._build_bottom_bar(inner)
        finally:
            self.setUpdatesEnabled(True)

        if self._embedded_mode:
            self._run_startup_initialization()
        else:
            # Let the dialog paint first; defer heavier data population to avoid
            # first-show stalls and compositor flicker during selector handoff.
            QTimer.singleShot(0, self._run_startup_initialization)

    def _run_startup_initialization(self) -> None:
        if self._startup_initialized:
            return
        self._startup_initialized = True
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
            self.resize(1180, 720)
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
        from ..home_page_support.detached_preview import load_preview_content
        return load_preview_content(viewer, stl_path, label=label)

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
            preview_btn = getattr(self, 'preview_window_btn', None)
            if preview_btn is not None:
                preview_btn.setChecked(False)
            return False
        from ..home_page_support.detached_preview import sync_detached_preview
        return sync_detached_preview(self, show_errors=show_errors)

    def toggle_preview_window(self) -> None:
        if getattr(self, '_embedded_mode', False):
            preview_btn = getattr(self, 'preview_window_btn', None)
            if preview_btn is not None:
                preview_btn.setChecked(False)
            return
        from ..home_page_support.detached_preview import toggle_preview_window
        toggle_preview_window(self)

    def closeEvent(self, event) -> None:
        if not getattr(self, '_embedded_mode', False):
            save_window_geometry(self, SHARED_UI_PREFERENCES_PATH, 'tool_selector_dialog')
        super().closeEvent(event)


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
        on_submit: Callable[[dict], None],
        on_cancel: Callable[[], None],
        parent=None,
    ):
        self._embedded_mode = True
        super().__init__(translate=translate, on_cancel=on_cancel, parent=parent)
        self.tool_service = tool_service
        self.machine_profile = machine_profile
        self._on_submit = on_submit

        self._current_head = self._normalize_head(selector_head)
        self._current_spindle = self._normalize_spindle(selector_spindle)
        self._assigned_tools: list[dict] = []
        self.current_tool_id: str | None = None
        self.current_tool_uid: int | None = None
        self._assignments_by_target = self._build_initial_buckets(
            initial_assignments,
            initial_assignment_buckets,
        )

        self._detail_preview_widget = None
        self._detail_preview_model_key = None
        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._close_preview_shortcut = None
        self._measurement_toggle_btn = None
        self._measurement_filter_combo = None
        self._detached_measurements_enabled = True
        self._detached_measurement_filter = None
        self._detached_preview_last_model_key = None

        self.setUpdatesEnabled(False)
        try:
            root = QVBoxLayout(self)
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(8)

            self._build_filter_row(root)
            self._build_content(root)
            self._build_bottom_bar(root)

            self._load_current_bucket()
            self._refresh_catalog()
            self._rebuild_assignment_list()
            self._update_context_header()
            self._update_assignment_buttons()
        finally:
            self.setUpdatesEnabled(True)

        self._initialize_preview_infrastructure()

    def prepare_for_session(
        self,
        *,
        selector_head: str,
        selector_spindle: str,
        initial_assignments: list[dict] | None,
        initial_assignment_buckets: dict[str, list[dict]] | None,
        on_submit: Callable[[dict], None],
        on_cancel: Callable[[], None],
    ) -> None:
        self.setUpdatesEnabled(False)
        try:
            self._reset_selector_widget_state(on_cancel=on_cancel)
            self._on_submit = on_submit
            self._current_head = self._normalize_head(selector_head)
            self._current_spindle = self._normalize_spindle(selector_spindle)
            self._assigned_tools = []
            self.current_tool_id = None
            self.current_tool_uid = None
            self._assignments_by_target = self._build_initial_buckets(
                initial_assignments,
                initial_assignment_buckets,
            )
            self._assignment_hint_dismissed = {}

            if hasattr(self, 'search_toggle'):
                self.search_toggle.setChecked(False)
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

            self._load_current_bucket()
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
        from ..home_page_support.detached_preview import load_preview_content
        return load_preview_content(viewer, stl_path, label=label)

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
            preview_btn = getattr(self, 'preview_window_btn', None)
            if preview_btn is not None:
                preview_btn.setChecked(False)
            return False
        from ..home_page_support.detached_preview import sync_detached_preview
        return sync_detached_preview(self, show_errors=show_errors)

    def toggle_preview_window(self) -> None:
        if getattr(self, '_embedded_mode', False):
            preview_btn = getattr(self, 'preview_window_btn', None)
            if preview_btn is not None:
                preview_btn.setChecked(False)
            return
        from ..home_page_support.detached_preview import toggle_preview_window
        toggle_preview_window(self)

