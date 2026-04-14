from __future__ import annotations


class ToolSelectorPayloadMixin:
    def _cancel(self) -> None:
        self._cancel_dialog()

    def _build_selector_payload(self) -> dict:
        self._sync_assignment_order()
        selected_items = [dict(item) for item in self._assigned_tools]
        assignment_buckets = {
            key: [dict(item) for item in value if isinstance(item, dict)]
            for key, value in self._assignments_by_target.items()
            if isinstance(value, list)
        }
        return {
            'kind': 'tools',
            'selected_items': selected_items,
            'selector_head': self._current_head,
            'selector_spindle': self._current_spindle,
            'assignment_buckets_by_target': assignment_buckets,
        }

    def _send_selector_selection(self) -> None:
        payload = self._build_selector_payload()
        self._finish_submit(self._on_submit, payload)
