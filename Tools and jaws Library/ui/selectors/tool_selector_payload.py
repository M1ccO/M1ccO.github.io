from __future__ import annotations

from typing import Callable


class ToolSelectorPayloadMixin:
    def _cancel(self) -> None:
        self._cancel_dialog()

    def reset_for_session(
        self,
        *,
        selector_head: str,
        selector_spindle: str,
        initial_assignments: list[dict] | None,
        initial_assignment_buckets: dict[str, list[dict]] | None,
        initial_print_pots: bool = False,
        on_submit: Callable[[dict], None],
        on_cancel: Callable[[], None],
    ) -> None:
        """Reconfigure this dialog for a new selector session without rebuilding
        the widget tree or re-querying the catalog.  Mirrors the Work Editor
        shared-dialog ``reset_for_reuse`` / ``populate_dialog`` pattern."""
        # Reset base-class lifecycle flags so DONE/CANCEL fire exactly once.
        self._submitted = False
        self._cancel_notified = False
        # Update session callbacks.
        self._on_submit = on_submit
        self._on_cancel = on_cancel
        # Track whether the head changed so we know if catalog needs refreshing.
        prev_head = getattr(self, '_current_head', None)
        # Update session identity.
        self._current_head = self._normalize_head(selector_head)
        self._current_spindle = self._normalize_spindle(selector_spindle)
        self._print_pots_enabled = bool(initial_print_pots)
        self._assignments_by_target = self._build_initial_buckets(
            initial_assignments,
            initial_assignment_buckets,
        )
        # Reload assignment UI (cheap — no catalog query).
        if hasattr(self, 'print_pots_checkbox'):
            self.print_pots_checkbox.blockSignals(True)
            self.print_pots_checkbox.setChecked(bool(initial_print_pots))
            self.print_pots_checkbox.blockSignals(False)
        self._load_current_bucket()
        # Only re-query the catalog if the head changed — the warm-cached dialog
        # already has a fully loaded catalog from construction.  Skipping the DB
        # query when the head is the same is the single biggest remaining latency
        # saving.
        if self._current_head != prev_head:
            self._refresh_catalog()
        self._rebuild_assignment_list()
        self._update_context_header()
        self._update_assignment_buttons()

    def _build_selector_payload(self) -> dict:
        self._sync_assignment_order()
        selected_items: list[dict] = []
        for spindle in ('main', 'sub'):
            target_key = self._target_key(self._current_head, spindle)
            for item in self._assignments_by_target.get(target_key, []):
                if isinstance(item, dict):
                    selected_items.append(dict(item))
        assignment_buckets = {
            key: [dict(item) for item in value if isinstance(item, dict)]
            for key, value in self._assignments_by_target.items()
            if isinstance(value, list)
        }
        return {
            'kind': 'tools',
            'selected_items': selected_items,
            'selector_head': self._current_head,
            'selector_spindle': self._active_assignment_spindle(),
            'assignment_buckets_by_target': assignment_buckets,
            'print_pots': bool(getattr(self, '_print_pots_enabled', False)),
        }

    def _send_selector_selection(self) -> None:
        payload = self._build_selector_payload()
        self._finish_submit(self._on_submit, payload)
