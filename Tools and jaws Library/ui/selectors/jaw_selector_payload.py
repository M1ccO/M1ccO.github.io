from __future__ import annotations

from typing import Callable

from .selector_ui_helpers import normalize_selector_spindle


class JawSelectorPayloadMixin:
    def _cancel(self) -> None:
        self._cancel_dialog()

    def reset_for_session(
        self,
        *,
        selector_spindle: str,
        initial_assignments: list[dict] | None,
        on_submit: Callable[[dict], None],
        on_cancel: Callable[[], None],
    ) -> None:
        """Reconfigure this dialog for a new selector session without rebuilding
        the widget tree or re-querying the catalog."""
        self._submitted = False
        self._cancel_notified = False
        self._on_submit = on_submit
        self._on_cancel = on_cancel
        self._current_spindle = normalize_selector_spindle(selector_spindle)
        self._selector_assignments = {'main': None, 'sub': None}
        self._selected_slots = set()
        self._load_initial_assignments(initial_assignments)
        self._refresh_slot_ui()
        self._update_context_header()

    def _build_selector_payload(self) -> dict:
        payload_items: list[dict] = []
        for slot in ('main', 'sub'):
            jaw = self._normalize_selector_jaw(self._selector_assignments.get(slot))
            if jaw is None:
                continue
            payload_items.append({**jaw, 'slot': slot})

        return {
            'kind': 'jaws',
            'selected_items': payload_items,
        }

    def _send_selector_selection(self) -> None:
        payload = self._build_selector_payload()
        self._finish_submit(self._on_submit, payload)
