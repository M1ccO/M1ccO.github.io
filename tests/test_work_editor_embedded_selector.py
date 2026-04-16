from __future__ import annotations

import os
import sys
import unittest
import importlib.util
from pathlib import Path


_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
_SETUP_ROOT = _WORKSPACE / "Setup Manager"
for _candidate in (_WORKSPACE, _SETUP_ROOT):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from ui.work_editor_support.selector_provider import (  # noqa: E402
    build_fixture_selector_request,
    build_jaw_selector_request,
    build_tool_selector_request,
)

try:
    sys.path.remove(str(_SETUP_ROOT))
except ValueError:
    pass


def _load_work_editor_dialog_class():
    module_path = _SETUP_ROOT / "ui" / "work_editor_dialog.py"
    setup_root = str(_SETUP_ROOT)

    # Switch ambiguous top-level packages (ui/data/services/config) to Setup Manager
    # just for this import, then restore the previous path ordering.
    if setup_root in sys.path:
        sys.path.remove(setup_root)
    sys.path.insert(0, setup_root)
    for mod_name in list(sys.modules.keys()):
        if mod_name == "config" or mod_name == "ui" or mod_name.startswith("ui."):
            sys.modules.pop(mod_name, None)

    try:
        spec = importlib.util.spec_from_file_location("setup_work_editor_dialog_for_tests", str(module_path))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load WorkEditorDialog module from {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.WorkEditorDialog
    finally:
        try:
            sys.path.remove(setup_root)
        except ValueError:
            pass


class _Profile:
    def __init__(self, key: str):
        self.key = key


class _DummyOrderedList:
    def __init__(self):
        self._all_tools = []
        self._assignments_by_spindle = {"main": [], "sub": []}

    @staticmethod
    def _assignment_key(assignment: dict) -> str:
        tool_id = str(assignment.get("tool_id") or "").strip()
        return f"id:{tool_id}" if tool_id else ""


class _DummyDialog:
    def __init__(self):
        self._head_profiles = {"HEAD1": _Profile("HEAD1"), "HEAD2": _Profile("HEAD2")}
        self._spindle_profiles = {"main": _Profile("main"), "sub": _Profile("sub")}
        self._ordered_tool_lists = {"HEAD1": _DummyOrderedList(), "HEAD2": _DummyOrderedList()}
        self._jaw_cache = []
        self._jaw_selectors = {}
        self._mc_operations = [
            {"op_key": "OP10", "fixture_items": [{"fixture_id": "F1"}]},
            {"op_key": "OP20", "fixture_items": [{"fixture_id": "F2"}]},
        ]

    def _default_selector_head(self):
        return "HEAD1"

    def _default_selector_spindle(self):
        return "main"

    def _default_jaw_selector_spindle(self):
        return "main"

    def _selector_target_ordered_list(self, _head_key: str):
        return _DummyOrderedList()


class TestSelectorProvider(unittest.TestCase):
    def test_tool_selector_request_normalizes_head_and_spindle(self):
        dialog = _DummyDialog()

        request = build_tool_selector_request(
            dialog,
            initial_head="head2",
            initial_spindle="sp2",
            initial_assignments=[{"tool_id": "T10"}],
        )

        self.assertEqual("tools", request["kind"])
        self.assertEqual("HEAD2", request["head"])
        self.assertEqual("sub", request["spindle"])
        self.assertEqual([{"tool_id": "T10"}], request["initial_assignments"])
        self.assertIn("HEAD1:main", request["initial_assignment_buckets"])

    def test_jaw_selector_request_defaults(self):
        dialog = _DummyDialog()
        request = build_jaw_selector_request(dialog)

        self.assertEqual("jaws", request["kind"])
        self.assertEqual("main", request["spindle"])
        self.assertIsInstance(request["initial_assignments"], list)

    def test_fixture_selector_request_target_and_buckets(self):
        dialog = _DummyDialog()
        request = build_fixture_selector_request(dialog, operation_key="OP20")

        self.assertEqual("fixtures", request["kind"])
        self.assertEqual("OP20", request["follow_up"]["target_key"])
        self.assertEqual([{"fixture_id": "F2"}], request["initial_assignments"])
        self.assertIn("OP10", request["initial_assignment_buckets"])


class TestSelectorModeEnv(unittest.TestCase):
    def test_selector_mode_default_embedded(self):
        WorkEditorDialog = _load_work_editor_dialog_class()

        mode = WorkEditorDialog._resolve_selector_transport_mode(object())
        self.assertEqual("embedded", mode)

    def test_selector_mode_embedded_ignores_env(self):
        WorkEditorDialog = _load_work_editor_dialog_class()

        original = os.environ.get("NTX_WORK_EDITOR_SELECTOR_MODE")
        os.environ["NTX_WORK_EDITOR_SELECTOR_MODE"] = "external"
        try:
            mode = WorkEditorDialog._resolve_selector_transport_mode(object())
            self.assertEqual("embedded", mode)
        finally:
            if original is None:
                os.environ.pop("NTX_WORK_EDITOR_SELECTOR_MODE", None)
            else:
                os.environ["NTX_WORK_EDITOR_SELECTOR_MODE"] = original


if __name__ == "__main__":
    unittest.main()
