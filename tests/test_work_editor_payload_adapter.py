from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
_SETUP_ROOT = _WORKSPACE / "Setup Manager"

for _candidate in (_WORKSPACE, _SETUP_ROOT):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

if str(_SETUP_ROOT) in sys.path:
    sys.path.remove(str(_SETUP_ROOT))
sys.path.insert(0, str(_SETUP_ROOT))
for _mod_name in list(sys.modules.keys()):
    if _mod_name == "ui" or _mod_name.startswith("ui."):
        sys.modules.pop(_mod_name, None)

from ui.work_editor_support.model import _collect_head_tool_assignments  # noqa: E402


class _StubOrderedList:
    def __init__(self, assignments_by_spindle: dict[str, list[dict]] | None = None):
        self._assignments_by_spindle = assignments_by_spindle or {"main": [], "sub": []}

    def get_tool_assignments(self) -> list[dict]:
        return [
            *[dict(item) for item in self._assignments_by_spindle.get("main", [])],
            *[dict(item) for item in self._assignments_by_spindle.get("sub", [])],
        ]


class TestWorkEditorPayloadAdapterHelpers(unittest.TestCase):
    def test_collect_head_tool_assignments_merges_split_spindle_widgets(self):
        main_widget = _StubOrderedList(
            {
                "main": [
                    {
                        "tool_id": "T1001",
                        "spindle": "main",
                        "override_id": "T9001",
                        "override_description": "OD rough edit",
                        "comment": "critical",
                        "pot": "P21",
                    }
                ],
                "sub": [],
            }
        )
        sub_widget = _StubOrderedList(
            {
                "main": [],
                "sub": [
                    {
                        "tool_id": "T2002",
                        "spindle": "sub",
                        "override_description": "ID finish edit",
                        "comment": "op20",
                        "pot": "P22",
                    }
                ],
            }
        )

        dialog = SimpleNamespace(
            _tool_column_lists={"HEAD1": {"main": main_widget, "sub": sub_widget}},
            _ordered_tool_lists={"HEAD1": main_widget},
        )

        assignments = _collect_head_tool_assignments(dialog, "HEAD1")

        self.assertEqual(2, len(assignments))
        self.assertEqual("T1001", assignments[0]["tool_id"])
        self.assertEqual("T9001", assignments[0]["override_id"])
        self.assertEqual("OD rough edit", assignments[0]["override_description"])
        self.assertEqual("T2002", assignments[1]["tool_id"])
        self.assertEqual("sub", assignments[1]["spindle"])
        self.assertEqual("ID finish edit", assignments[1]["override_description"])


if __name__ == "__main__":
    unittest.main()
