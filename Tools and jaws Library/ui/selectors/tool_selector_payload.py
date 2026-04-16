from __future__ import annotations


class ToolSelectorPayloadMixin:
    def _cancel(self) -> None:
        self._cancel_dialog()

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
            'selector_spindle': 'main',
            'assignment_buckets_by_target': assignment_buckets,
        }

    def _send_selector_selection(self) -> None:
        payload = self._build_selector_payload()
        self._finish_submit(self._on_submit, payload)
