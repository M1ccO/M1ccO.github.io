from __future__ import annotations

from typing import Callable

from .base_selector_widget import BaseSelectorWidget


class FixtureSelectorWidget(BaseSelectorWidget):
    """Initial embedded Fixture selector widget shell."""

    def __init__(
        self,
        *,
        translate: Callable[[str, str | None], str],
        target_key: str,
        initial_assignments: list[dict] | None = None,
        assignment_buckets_by_target: dict[str, list[dict]] | None = None,
        parent=None,
    ):
        self._target_key = str(target_key or "").strip()
        self._selected_items = [dict(item) for item in (initial_assignments or []) if isinstance(item, dict)]
        self._assignment_buckets_by_target = {
            str(key): [dict(item) for item in value if isinstance(item, dict)]
            for key, value in (assignment_buckets_by_target or {}).items()
            if isinstance(value, list)
        }
        lines = [translate("work_editor.selector.embedded_placeholder.kind", "Kind: fixtures")]
        target_text = str(target_key or "").strip()
        if target_text:
            lines.append(
                translate(
                    "work_editor.selector.embedded_placeholder.target",
                    "Target: {target_key}",
                    target_key=target_text,
                )
            )
        details = "\n".join(lines)
        super().__init__(
            title=translate("work_editor.selector.embedded_placeholder.title", "Embedded selector mode"),
            details_text=details,
            translate=translate,
            parent=parent,
        )

    def _build_submit_payload(self) -> dict:
        return {
            "kind": "fixtures",
            "selected_items": [dict(item) for item in self._selected_items],
            "target_key": self._target_key,
            "assignment_buckets_by_target": {
                key: [dict(item) for item in value]
                for key, value in self._assignment_buckets_by_target.items()
            },
        }
