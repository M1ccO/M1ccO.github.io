from __future__ import annotations

from typing import Callable

from .base_selector_widget import BaseSelectorWidget


class ToolSelectorWidget(BaseSelectorWidget):
    """Initial embedded Tool selector widget shell.

    Phase-3 step: provides shared signal contract and selector context rendering.
    """

    def __init__(
        self,
        *,
        translate: Callable[[str, str | None], str],
        selector_head: str,
        selector_spindle: str,
        initial_assignments: list[dict] | None = None,
        assignment_buckets_by_target: dict[str, list[dict]] | None = None,
        parent=None,
    ):
        self._selector_head = str(selector_head or "")
        self._selector_spindle = str(selector_spindle or "")
        self._selected_items = [dict(item) for item in (initial_assignments or []) if isinstance(item, dict)]
        self._assignment_buckets_by_target = {
            str(key): [dict(item) for item in value if isinstance(item, dict)]
            for key, value in (assignment_buckets_by_target or {}).items()
            if isinstance(value, list)
        }
        details = "\n".join(
            [
                translate("work_editor.selector.embedded_placeholder.kind", "Kind: tools"),
                translate(
                    "work_editor.selector.embedded_placeholder.head",
                    "Head: {head}",
                    head=str(selector_head or ""),
                ),
                translate(
                    "work_editor.selector.embedded_placeholder.spindle",
                    "Spindle: {spindle}",
                    spindle=str(selector_spindle or ""),
                ),
            ]
        )
        super().__init__(
            title=translate("work_editor.selector.embedded_placeholder.title", "Embedded selector mode"),
            details_text=details,
            translate=translate,
            parent=parent,
        )

    def _build_submit_payload(self) -> dict:
        return {
            "kind": "tools",
            "selected_items": [dict(item) for item in self._selected_items],
            "selector_head": self._selector_head,
            "selector_spindle": self._selector_spindle,
            "assignment_buckets_by_target": {
                key: [dict(item) for item in value]
                for key, value in self._assignment_buckets_by_target.items()
            },
        }
