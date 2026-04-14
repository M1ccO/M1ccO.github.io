from __future__ import annotations


class JawSelectorPayloadMixin:
    def _cancel(self) -> None:
        self._cancel_dialog()

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
