from __future__ import annotations

from typing import Callable

from .base_selector_widget import BaseSelectorWidget


class JawSelectorWidget(BaseSelectorWidget):
    """Initial embedded Jaw selector widget shell."""

    def __init__(
        self,
        *,
        translate: Callable[[str, str | None], str],
        selector_spindle: str,
        initial_assignments: list[dict] | None = None,
        parent=None,
    ):
        self._selected_items = [dict(item) for item in (initial_assignments or []) if isinstance(item, dict)]
        details = "\n".join(
            [
                translate("work_editor.selector.embedded_placeholder.kind", "Kind: jaws"),
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
            "kind": "jaws",
            "selected_items": [dict(item) for item in self._selected_items],
        }
