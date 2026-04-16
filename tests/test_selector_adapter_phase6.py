from __future__ import annotations

import sys
import unittest
from pathlib import Path


_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
_SETUP_ROOT = _WORKSPACE / "Setup Manager"
for _candidate in (_WORKSPACE, _SETUP_ROOT):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from ui.work_editor_support.selector_adapter import (  # noqa: E402
    apply_fixture_selector_result,
    apply_jaw_selector_result,
    apply_tool_selector_result,
)

try:
    sys.path.remove(str(_SETUP_ROOT))
except ValueError:
    pass


class _DummySelector:
    def __init__(self):
        self._value = ""
        self._last_populated = None

    def set_value(self, value: str) -> None:
        self._value = str(value or "")

    def get_value(self) -> str:
        return self._value

    def populate(self, refs):
        self._last_populated = list(refs)


class _DummyOrderedList:
    def __init__(self):
        self._all_tools = []
        self._assignments_by_spindle = {"main": [], "sub": []}

    @staticmethod
    def _assignment_key(assignment: dict) -> str:
        tool_id = str(assignment.get("tool_id") or "").strip()
        tool_uid = assignment.get("tool_uid")
        if tool_uid is not None and str(tool_uid).strip():
            return f"uid:{tool_uid}"
        return f"id:{tool_id}" if tool_id else ""


class _DummyDialog:
    def __init__(self):
        self._tool_cache_by_head = {"HEAD1": [], "HEAD2": []}
        self._tool_cache_all = []
        self._ordered_tool_lists = {"HEAD1": _DummyOrderedList(), "HEAD2": _DummyOrderedList()}
        self._tool_column_lists = {
            "HEAD1": {"main": self._ordered_tool_lists["HEAD1"], "sub": self._ordered_tool_lists["HEAD1"]},
            "HEAD2": {"main": self._ordered_tool_lists["HEAD2"], "sub": self._ordered_tool_lists["HEAD2"]},
        }
        self._jaw_cache = []
        self._jaw_selectors = {"main": _DummySelector(), "sub": _DummySelector()}
        self._set_head_calls = []
        self._refresh_head_calls = []
        self._sync_head_view_calls = 0
        self._fixture_apply_calls = []

    def _selector_target_ordered_list(self, head_key: str):
        return self._ordered_tool_lists[head_key]

    def _set_tools_head_value(self, head_key: str) -> None:
        self._set_head_calls.append(head_key)

    def _sync_tool_head_view(self) -> None:
        self._sync_head_view_calls += 1

    def _refresh_tool_head_widgets(self, head_key: str) -> None:
        self._refresh_head_calls.append(head_key)

    def _apply_fixture_selection_to_operation(self, target_key: str, selected_items: list[dict]) -> bool:
        self._fixture_apply_calls.append((target_key, list(selected_items)))
        return True


class TestSelectorAdapterPhase6(unittest.TestCase):
    def test_apply_tool_selector_result_sets_bucket_and_head(self):
        dialog = _DummyDialog()
        selected = [
            {"tool_id": "T2", "tool_uid": 2, "description": "two", "tool_type": "Drill"},
            {"tool_id": "T1", "tool_uid": 1, "description": "one", "tool_type": "Endmill"},
        ]

        ok = apply_tool_selector_result(dialog, {"head": "head1", "spindle": "main"}, selected)

        self.assertTrue(ok)
        bucket = dialog._ordered_tool_lists["HEAD1"]._assignments_by_spindle["main"]
        self.assertEqual(["T2", "T1"], [item["tool_id"] for item in bucket])
        self.assertEqual(["HEAD1"], dialog._set_head_calls)
        self.assertEqual(["HEAD1"], dialog._refresh_head_calls)
        self.assertEqual(1, dialog._sync_head_view_calls)

    def test_apply_jaw_selector_result_maps_by_spindle(self):
        dialog = _DummyDialog()
        selected = [
            {"jaw_id": "J_MAIN", "spindle": "main"},
            {"jaw_id": "J_SUB", "spindle": "sub"},
        ]

        ok = apply_jaw_selector_result(dialog, {"spindle": "main"}, selected)

        self.assertTrue(ok)
        self.assertEqual("J_MAIN", dialog._jaw_selectors["main"].get_value())
        self.assertEqual("J_SUB", dialog._jaw_selectors["sub"].get_value())

    def test_apply_fixture_selector_result_uses_target_key(self):
        dialog = _DummyDialog()
        selected = [{"fixture_id": "F1"}]

        ok = apply_fixture_selector_result(dialog, {"target_key": "OP20"}, selected)

        self.assertTrue(ok)
        self.assertEqual(1, len(dialog._fixture_apply_calls))
        self.assertEqual("OP20", dialog._fixture_apply_calls[0][0])
        self.assertEqual(selected, dialog._fixture_apply_calls[0][1])


if __name__ == "__main__":
    unittest.main()
