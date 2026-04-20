from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch
import importlib.util
import importlib
from pathlib import Path
from types import SimpleNamespace


_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
_SETUP_ROOT = _WORKSPACE / "Setup Manager"
_TOOLS_ROOT = _WORKSPACE / "Tools and jaws Library"
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
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module.WorkEditorDialog
    finally:
        try:
            sys.path.remove(setup_root)
        except ValueError:
            pass


def _import_tools_selector_class(module_name: str, class_name: str):
    tools_root = str(_TOOLS_ROOT)
    previous_config = sys.modules.pop("config", None)
    if tools_root in sys.path:
        sys.path.remove(tools_root)
    sys.path.insert(0, tools_root)
    sys.modules.pop(module_name, None)

    try:
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
    finally:
        try:
            sys.path.remove(tools_root)
        except ValueError:
            pass
        if previous_config is None:
            sys.modules.pop("config", None)
        else:
            sys.modules["config"] = previous_config


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
        self._tool_column_lists = {
            "HEAD1": {"main": self._ordered_tool_lists["HEAD1"], "sub": self._ordered_tool_lists["HEAD1"]},
            "HEAD2": {"main": self._ordered_tool_lists["HEAD2"], "sub": self._ordered_tool_lists["HEAD2"]},
        }
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

    def _normalize_selector_head(self, head: str | None) -> str:
        value = str(head or "").strip().upper()
        if value in {"HEAD2", "LOWER", "L"}:
            return "HEAD2"
        return "HEAD1"


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

    def test_tool_selector_request_uses_actual_sub_column_bucket_when_available(self):
        dialog = _DummyDialog()
        head1_main = _DummyOrderedList()
        head1_sub = _DummyOrderedList()
        head1_main._assignments_by_spindle["main"] = [{"tool_id": "T101", "spindle": "main"}]
        head1_sub._assignments_by_spindle["sub"] = [{"tool_id": "T102", "spindle": "sub"}]
        dialog._tool_column_lists["HEAD1"] = {"main": head1_main, "sub": head1_sub}

        request = build_tool_selector_request(dialog)

        self.assertEqual(
            [{"tool_id": "T102"}],
            request["initial_assignment_buckets"]["HEAD1:sub"],
        )

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


class TestEmbeddedSelectorSubmit(unittest.TestCase):
    def test_handle_embedded_selector_submit_forwards_assignment_buckets(self):
        WorkEditorDialog = _load_work_editor_dialog_class()
        captured = {}

        class _DummySubmitDialog:
            def _log_selector_event(self, *_args, **_kwargs):
                return

        dummy = _DummySubmitDialog()

        def _capture_apply(_dialog, request, selected_items):
            captured["request"] = dict(request)
            captured["selected_items"] = list(selected_items)
            return True

        module = sys.modules[WorkEditorDialog.__module__]
        with patch.object(module, "apply_tool_selector_result", side_effect=_capture_apply):
            WorkEditorDialog._handle_embedded_selector_submit(
                dummy,
                {"kind": "tools", "head": "HEAD1", "spindle": "main"},
                {
                    "kind": "tools",
                    "selected_items": [{"tool_id": "T001"}],
                    "assignment_buckets_by_target": {
                        "HEAD1:main": [{"tool_id": "T001"}],
                        "HEAD2:sub": [{"tool_id": "T201"}],
                    },
                },
            )

        self.assertEqual([{"tool_id": "T001"}], captured["selected_items"])
        self.assertIn("assignment_buckets_by_target", captured["request"])
        self.assertIn("HEAD2:sub", captured["request"]["assignment_buckets_by_target"])


class _DummyToggleButton:
    def __init__(self, checked: bool = True):
        self._checked = bool(checked)

    def setChecked(self, checked: bool) -> None:
        self._checked = bool(checked)

    def isChecked(self) -> bool:
        return self._checked


class TestEmbeddedSelectorPreviewGuards(unittest.TestCase):
    def test_tool_embedded_toggle_preview_is_blocked(self):
        EmbeddedToolSelectorWidget = _import_tools_selector_class(
            "tools_and_jaws_library.ui.selectors.tool_selector_dialog",
            "EmbeddedToolSelectorWidget",
        )

        button = _DummyToggleButton(checked=True)
        dummy = SimpleNamespace(_embedded_mode=True, preview_window_btn=button)
        EmbeddedToolSelectorWidget.toggle_preview_window(dummy)
        self.assertFalse(button.isChecked())

    def test_jaw_embedded_toggle_preview_is_blocked(self):
        EmbeddedJawSelectorWidget = _import_tools_selector_class(
            "tools_and_jaws_library.ui.selectors.jaw_selector_dialog",
            "EmbeddedJawSelectorWidget",
        )

        button = _DummyToggleButton(checked=True)
        dummy = SimpleNamespace(_embedded_mode=True, preview_window_btn=button)
        EmbeddedJawSelectorWidget.toggle_preview_window(dummy)
        self.assertFalse(button.isChecked())


if __name__ == "__main__":
    unittest.main()
