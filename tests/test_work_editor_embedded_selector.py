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

if str(_SETUP_ROOT) in sys.path:
    sys.path.remove(str(_SETUP_ROOT))
sys.path.insert(0, str(_SETUP_ROOT))
for _mod_name in list(sys.modules.keys()):
    if _mod_name == "ui" or _mod_name.startswith("ui."):
        sys.modules.pop(_mod_name, None)

from ui.work_editor_support.selector_provider import (  # noqa: E402
    build_fixture_selector_request,
    build_jaw_selector_request,
    build_tool_selector_request,
)
from ui.work_editor_support.selector_session_controller import WorkEditorSelectorController  # noqa: E402
import ui.work_editor_support.selector_session_controller as ctrl_module  # noqa: E402

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
        self.print_pots_checkbox = SimpleNamespace(isChecked=lambda: True)
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
        self.assertTrue(request["print_pots"])

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
    def test_selector_mode_default_ipc(self):
        mode = WorkEditorSelectorController._resolve_transport_mode()
        self.assertEqual("ipc", mode)

    def test_selector_mode_ipc_ignores_env(self):
        original = os.environ.get("NTX_WORK_EDITOR_SELECTOR_MODE")
        os.environ["NTX_WORK_EDITOR_SELECTOR_MODE"] = "external"
        try:
            mode = WorkEditorSelectorController._resolve_transport_mode()
            self.assertEqual("ipc", mode)
        finally:
            if original is None:
                os.environ.pop("NTX_WORK_EDITOR_SELECTOR_MODE", None)
            else:
                os.environ["NTX_WORK_EDITOR_SELECTOR_MODE"] = original


class _FakeGeometry:
    def __init__(self, x: int, y: int, width: int, height: int):
        self._x = x
        self._y = y
        self._width = width
        self._height = height

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height


class _FakeScreen:
    def __init__(self, available_geometry):
        self._available_geometry = available_geometry

    def availableGeometry(self):
        return self._available_geometry


class TestSelectorTransport(unittest.TestCase):
    def test_open_selector_request_prefers_ipc(self):
        calls = []

        dummy_dialog = SimpleNamespace()
        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dummy_dialog
        ctrl._transport_mode = "ipc"
        ctrl._mode_active = False
        ctrl._open_requested = False
        ctrl._pending_ipc_request_id = None
        ctrl._pending_ipc_kind = None
        ctrl._ipc_saved_geometry = None
        ctrl._active_embedded_widget = None
        ctrl._restore_state = None
        ctrl._hidden_editor_widgets = []
        ctrl._transition_shield_pending_hide = False
        ctrl._trace_widgets = {}
        ctrl._try_open_via_ipc = lambda **kwargs: calls.append(("ipc", kwargs)) or True
        ctrl._try_open_embedded = lambda **kwargs: calls.append(("embedded", kwargs)) or True

        opened = ctrl._open_selector_request(kind="tools", head="HEAD1", spindle="main")

        self.assertTrue(opened)
        self.assertEqual("ipc", calls[0][0])
        self.assertEqual("tools", calls[0][1]["kind"])

    def test_open_selector_request_does_not_fallback_when_ipc_fails(self):
        calls = []

        dummy_dialog = SimpleNamespace()
        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dummy_dialog
        ctrl._transport_mode = "ipc"
        ctrl._mode_active = False
        ctrl._open_requested = False
        ctrl._try_open_via_ipc = lambda **kwargs: calls.append(("ipc", kwargs)) or False
        ctrl._try_open_embedded = lambda **kwargs: calls.append(("embedded", kwargs)) or True

        opened = ctrl._open_selector_request(kind="jaws", spindle="sub")

        self.assertFalse(opened)
        self.assertEqual([("ipc", {"kind": "jaws", "head": "", "spindle": "sub", "target_key": "", "initial_assignments": None, "initial_assignment_buckets": None})], calls)

    def test_open_selector_request_uses_embedded_when_transport_is_embedded(self):
        calls = []

        dummy_dialog = SimpleNamespace()
        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dummy_dialog
        ctrl._transport_mode = "embedded"
        ctrl._mode_active = False
        ctrl._open_requested = False
        ctrl._try_open_via_ipc = lambda **kwargs: calls.append(("ipc", kwargs)) or False
        ctrl._try_open_embedded = lambda **kwargs: calls.append(("embedded", kwargs)) or True

        opened = ctrl._open_selector_request(kind="fixtures", target_key="OP10")

        self.assertTrue(opened)
        self.assertEqual([("embedded", {"kind": "fixtures", "head": "", "spindle": "", "target_key": "OP10", "initial_assignments": None, "initial_assignment_buckets": None})], calls)

    def test_try_open_selector_via_ipc_launches_hidden_library_and_retries(self):
        import importlib.util as _ilu
        import types

        # Load library_ipc from Setup Manager path (avoids 'ui' package conflict)
        _ipc_path = _SETUP_ROOT / "ui" / "main_window_support" / "library_ipc.py"
        setup_root = str(_SETUP_ROOT)
        _added = setup_root not in sys.path
        if _added:
            sys.path.insert(0, setup_root)
        try:
            _spec = _ilu.spec_from_file_location(
                "ui.main_window_support.library_ipc", _ipc_path,
                submodule_search_locations=[])
            library_ipc_module = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(library_ipc_module)
        finally:
            if _added:
                try:
                    sys.path.remove(setup_root)
                except ValueError:
                    pass

        # Also load config from Setup Manager
        _config_path = _SETUP_ROOT / "config.py"
        _cfg_spec = _ilu.spec_from_file_location("config", _config_path)
        config_module = _ilu.module_from_spec(_cfg_spec)
        _cfg_spec.loader.exec_module(config_module)

        # Register both modules so controller's lazy import resolves them
        _keys_to_restore = {}
        for _key, _mod in [
            ("ui.main_window_support.library_ipc", library_ipc_module),
            ("config", config_module),
        ]:
            _keys_to_restore[_key] = sys.modules.get(_key)
            sys.modules[_key] = _mod
        # Also need parent package registered
        _mws_key = "ui.main_window_support"
        _keys_to_restore[_mws_key] = sys.modules.get(_mws_key)
        if _mws_key not in sys.modules:
            mws_pkg = types.ModuleType(_mws_key)
            mws_pkg.__path__ = [str(_SETUP_ROOT / "ui" / "main_window_support")]
            mws_pkg.__package__ = _mws_key
            sys.modules[_mws_key] = mws_pkg
        # Extend ui.__path__ so from-import traversal finds main_window_support
        _ui_mod = sys.modules.get("ui")
        _sm_ui_dir = str(_SETUP_ROOT / "ui")
        _path_added = False
        if _ui_mod is not None and hasattr(_ui_mod, "__path__"):
            if _sm_ui_dir not in _ui_mod.__path__:
                _ui_mod.__path__.insert(0, _sm_ui_dir)
                _path_added = True

        hidden = []
        events = []
        dummy_dialog = SimpleNamespace(
            _machine_profile_key="ntx_2sp_2h",
            geometry=lambda: "original-geometry",
            hide=lambda: hidden.append(True),
            _t=lambda _key, default=None, **_kwargs: default or "",
            print_pots_checkbox=None,
        )

        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dummy_dialog
        ctrl._transport_mode = "ipc"
        ctrl._mode_active = False
        ctrl._open_requested = False
        ctrl._pending_ipc_request_id = None
        ctrl._pending_ipc_kind = None
        ctrl._ipc_saved_geometry = None
        ctrl._active_embedded_widget = None
        ctrl._restore_state = None
        ctrl._hidden_editor_widgets = []
        ctrl._transition_shield_pending_hide = False
        ctrl._trace_widgets = {}
        ctrl._build_session_geometry = lambda: "10,20,1220,780"
        ctrl._log = lambda *args, **kwargs: events.append((args, kwargs))

        with patch.object(library_ipc_module, "allow_set_foreground") as allow_fg, \
             patch.object(library_ipc_module, "send_to_tool_library", return_value=False) as send_ipc, \
             patch.object(library_ipc_module, "launch_tool_library", return_value=True) as launch_library, \
             patch.object(library_ipc_module, "send_request_with_retry") as retry_send:
            opened = ctrl._try_open_via_ipc(
                kind="tools",
                head="HEAD1",
                spindle="main",
                initial_assignments=[{"tool_id": "T001"}],
                initial_assignment_buckets={"HEAD1:main": [{"tool_id": "T001"}]},
            )

        self.assertTrue(opened)
        self.assertTrue(hidden)
        self.assertIsNotNone(ctrl._pending_ipc_request_id)
        self.assertEqual("tools", ctrl._pending_ipc_kind)
        self.assertEqual("original-geometry", ctrl._ipc_saved_geometry)
        allow_fg.assert_called_once()
        send_ipc.assert_called_once()
        launch_library.assert_called_once()
        self.assertEqual(["--hidden"], launch_library.call_args.kwargs["extra_args"])
        retry_send.assert_called_once()
        payload = retry_send.call_args.args[1]
        self.assertEqual("tools", payload["selector_mode"])
        self.assertEqual("10,20,1220,780", payload["geometry"])

        # Restore sys.modules and ui.__path__
        for _k, _v in _keys_to_restore.items():
            if _v is None:
                sys.modules.pop(_k, None)
            else:
                sys.modules[_k] = _v
        if _path_added and _ui_mod is not None:
            try:
                _ui_mod.__path__.remove(_sm_ui_dir)
            except ValueError:
                pass

    def test_build_selector_session_geometry_expands_to_large_default(self):
        available = _FakeGeometry(100, 80, 1600, 1000)
        current = _FakeGeometry(220, 180, 960, 680)
        dummy_dialog = SimpleNamespace(
            _SELECTOR_DIALOG_WIDTH_PAD=260,
            _SELECTOR_DIALOG_HEIGHT_PAD=140,
            _SELECTOR_DIALOG_DEFAULT_WIDTH=1220,
            _SELECTOR_DIALOG_DEFAULT_HEIGHT=780,
            geometry=lambda: current,
            screen=lambda: _FakeScreen(available),
        )

        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dummy_dialog

        geometry_text = ctrl._build_session_geometry()

        self.assertTrue(geometry_text)
        x_text, y_text, width_text, height_text = geometry_text.split(",")
        self.assertGreaterEqual(int(width_text), 1220)
        self.assertGreaterEqual(int(height_text), 780)
        self.assertGreaterEqual(int(x_text), available.x())
        self.assertGreaterEqual(int(y_text), available.y())


class TestEmbeddedSelectorSubmit(unittest.TestCase):
    def test_apply_selector_result_forwards_assignment_buckets(self):
        captured = {}

        class _DummySubmitDialog:
            def _log_selector_event(self, *_args, **_kwargs):
                return

        dummy = _DummySubmitDialog()

        def _capture_apply(_dialog, request, selected_items):
            captured["request"] = dict(request)
            captured["selected_items"] = list(selected_items)
            return True

        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dummy
        ctrl._transport_mode = "ipc"

        with patch.object(ctrl_module, "apply_tool_selector_result", side_effect=_capture_apply):
            ctrl._apply_selector_result(
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
