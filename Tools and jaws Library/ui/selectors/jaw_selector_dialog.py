from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QVBoxLayout

try:
    from ...config import SHARED_UI_PREFERENCES_PATH
except ImportError:
    from config import SHARED_UI_PREFERENCES_PATH
from shared.ui.helpers.window_geometry_memory import restore_window_geometry, save_window_geometry
from shared.ui.selectors import JawSelectorWidget
from ..selector_ui_helpers import normalize_selector_spindle
from .common import SelectorDialogBase, SelectorWidgetBase
from .jaw_selector_layout import JawSelectorLayoutMixin
from .jaw_selector_payload import JawSelectorPayloadMixin
from .jaw_selector_state import JawSelectorStateMixin


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
            window_flags=Qt.Widget if self._embedded_mode else Qt.WindowFlags(),
        )
        self.jaw_service = jaw_service
        self._on_submit = on_submit
        self.machine_profile = machine_profile

        self._current_spindle = normalize_selector_spindle(selector_spindle)
        self.current_jaw_id: str | None = None
        self._selector_assignments: dict[str, dict | None] = {'main': None, 'sub': None}
        self._selected_slots: set[str] = set()

        # Required by jaw detail builder (build_jaw_preview_card / _clear_details)
        self._detail_preview_widget = None
        self._detail_preview_model_key = None

        # Detached preview state (toolbar preview toggle parity with JawPage)
        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._detached_preview_last_model_key = None
        self._detached_measurements_enabled = True
        self._measurement_toggle_btn = None
        self._close_preview_shortcut = None

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
                self.resize(1180, 720)
                restore_window_geometry(self, SHARED_UI_PREFERENCES_PATH, 'jaw_selector_dialog')

            inner = self._make_themed_inner_layout()

            self._build_filter_row(inner)
            self._build_content(inner)
            self._build_bottom_bar(inner)

            self._refresh_catalog()
            self._refresh_slot_ui()
            self._update_context_header()
            self._update_remove_button()
            if not self._embedded_mode:
                self._prime_detail_panel_cache()
        finally:
            self.setUpdatesEnabled(True)

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
            self.resize(1180, 720)
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
        """Delegate to the jaw-specific preview loader (signature: page, viewer, jaw_dict)."""
        from ..jaw_page_support.detached_preview import load_preview_content
        return load_preview_content(self, viewer, jaw, label=label)

    def _preview_model_key(self, jaw: dict) -> str | None:
        """Return a stable dedup key for the jaw 3-D model so the viewer skips redundant reloads."""
        return str(jaw.get('jaw_id') or '').strip() or None

    # ── Detached preview parity with JawPage toolbar ───────────────────

    def _on_detached_measurements_toggled(self, checked: bool) -> None:
        from ..jaw_page_support.detached_preview import on_detached_measurements_toggled
        on_detached_measurements_toggled(self, checked)

    def _on_detached_preview_closed(self, result) -> None:
        from ..jaw_page_support.detached_preview import on_detached_preview_closed
        on_detached_preview_closed(self, result)

    def _sync_detached_preview(self, show_errors: bool = False) -> bool:
        from ..jaw_page_support.detached_preview import sync_detached_preview
        return sync_detached_preview(self, show_errors)

    def toggle_preview_window(self) -> None:
        from ..jaw_page_support.detached_preview import toggle_preview_window
        toggle_preview_window(self)

    def closeEvent(self, event) -> None:
        if not getattr(self, '_embedded_mode', False):
            save_window_geometry(self, SHARED_UI_PREFERENCES_PATH, 'jaw_selector_dialog')
        super().closeEvent(event)


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
        super().__init__(translate=translate, on_cancel=on_cancel, parent=parent)
        self.jaw_service = jaw_service
        self._on_submit = on_submit
        self.machine_profile = machine_profile

        self._current_spindle = normalize_selector_spindle(selector_spindle)
        self.current_jaw_id: str | None = None
        self._selector_assignments: dict[str, dict | None] = {'main': None, 'sub': None}
        self._selected_slots: set[str] = set()

        self._detail_preview_widget = None
        self._detail_preview_model_key = None
        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._detached_preview_last_model_key = None
        self._detached_measurements_enabled = True
        self._measurement_toggle_btn = None
        self._close_preview_shortcut = None

        self._load_initial_assignments(initial_assignments)
        self.setUpdatesEnabled(False)
        try:
            root = QVBoxLayout(self)
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(8)

            self._build_filter_row(root)
            self._build_content(root)
            self._build_bottom_bar(root)

            self._refresh_catalog()
            self._refresh_slot_ui()
            self._update_context_header()
            self._update_remove_button()
        finally:
            self.setUpdatesEnabled(True)

        self._initialize_preview_infrastructure()

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
        from ..jaw_page_support.detached_preview import load_preview_content
        return load_preview_content(self, viewer, jaw, label=label)

    def _preview_model_key(self, jaw: dict) -> str | None:
        return str(jaw.get('jaw_id') or '').strip() or None

    def _on_detached_measurements_toggled(self, checked: bool) -> None:
        from ..jaw_page_support.detached_preview import on_detached_measurements_toggled
        on_detached_measurements_toggled(self, checked)

    def _on_detached_preview_closed(self, result) -> None:
        from ..jaw_page_support.detached_preview import on_detached_preview_closed
        on_detached_preview_closed(self, result)

    def _sync_detached_preview(self, show_errors: bool = False) -> bool:
        from ..jaw_page_support.detached_preview import sync_detached_preview
        return sync_detached_preview(self, show_errors)

    def toggle_preview_window(self) -> None:
        from ..jaw_page_support.detached_preview import toggle_preview_window
        toggle_preview_window(self)

