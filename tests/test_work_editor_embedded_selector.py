from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch
import importlib.util
import importlib
from pathlib import Path
from types import ModuleType, SimpleNamespace

from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QWidget


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
import ui.work_editor_support.selector_parity_factory as parity_module  # noqa: E402
from ui.work_editor_support.selector_session_controller import WorkEditorSelectorController  # noqa: E402
import ui.work_editor_support.selector_session_controller as ctrl_module  # noqa: E402


_APP = QApplication.instance() or QApplication([])

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
    def test_selector_mode_default_embedded(self):
        mode = WorkEditorSelectorController._resolve_transport_mode()
        self.assertEqual("embedded", mode)

    def test_selector_mode_ipc_aliases_are_supported(self):
        original = os.environ.get("NTX_WORK_EDITOR_SELECTOR_MODE")
        os.environ["NTX_WORK_EDITOR_SELECTOR_MODE"] = "external"
        try:
            ctrl_module.WORK_EDITOR_SELECTOR_MODE = "external"
            mode = WorkEditorSelectorController._resolve_transport_mode()
            self.assertEqual("ipc", mode)
        finally:
            restored = (original or "embedded").strip().lower() if original is not None else "embedded"
            ctrl_module.WORK_EDITOR_SELECTOR_MODE = restored
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
    def test_open_selector_request_prefers_embedded(self):
        calls = []

        dummy_dialog = SimpleNamespace()
        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dummy_dialog
        ctrl._transport_mode = "embedded"
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
        ctrl._coordinator = SimpleNamespace(is_busy=False)
        ctrl._log = lambda *args, **kwargs: None
        ctrl._try_open_via_ipc = lambda **kwargs: calls.append(("ipc", kwargs)) or True
        ctrl._try_open_embedded = lambda **kwargs: calls.append(("embedded", kwargs)) or True

        opened = ctrl._open_selector_request(kind="tools", head="HEAD1", spindle="main")

        self.assertTrue(opened)
        self.assertEqual("embedded", calls[0][0])
        self.assertEqual("tools", calls[0][1]["kind"])

    def test_try_open_embedded_settles_widget_before_enter_mode(self):
        events = []

        class _DummyCoordinator:
            session_id = "session-1"
            is_busy = False

            @staticmethod
            def request_open(*, caller):
                events.append(("request_open", caller))
                return "session-1"

            @staticmethod
            def mark_mount_complete(*, caller):
                events.append(("mark_mount_complete", caller))

        class _DummyLayout:
            def setContentsMargins(self, *_args):
                return None

            def setSpacing(self, *_args):
                return None

            def addWidget(self, _widget):
                events.append("layout.addWidget")

            def activate(self):
                events.append("layout.activate")

        class _DummyMount:
            def __init__(self):
                self._layout = _DummyLayout()

            def layout(self):
                return self._layout

            def updateGeometry(self):
                events.append("mount.updateGeometry")

        class _DummyRootStack:
            def layout(self):
                return _DummyLayout()

            def updateGeometry(self):
                events.append("stack.updateGeometry")

        class _DummyWidget:
            def __init__(self):
                self._layout = _DummyLayout()

            def ensurePolished(self):
                events.append("widget.ensurePolished")

            def show(self):
                events.append("widget.show")

            def updateGeometry(self):
                events.append("widget.updateGeometry")

            def layout(self):
                return self._layout

            def raise_(self):
                events.append("widget.raise")

            def activateWindow(self):
                events.append("widget.activate")

        dummy_dialog = SimpleNamespace(
            _root_stack=_DummyRootStack(),
            _SELECTOR_LOCAL_FADE_MS=0,
            setUpdatesEnabled=lambda _v: None,
            hide=lambda: None,
            show=lambda: None,
        )

        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dummy_dialog
        ctrl._coordinator = _DummyCoordinator()
        ctrl._active_embedded_widget = None
        ctrl._transport_mode = "embedded"
        ctrl._schedule_preview_host_preload = lambda: events.append("preload.schedule")
        ctrl._log = lambda *_args, **_kwargs: None
        ctrl._enter_mode = lambda: events.append("enter_mode")
        ctrl._exit_mode = lambda: events.append("exit_mode")
        ctrl._detach_active_embedded_widget = lambda: events.append("detach_active")
        ctrl._current_mount_container = lambda: _DummyMount()
        ctrl._apply_selector_result = lambda *_args, **_kwargs: None
        ctrl._settle_embedded_selector_surface = ctrl_module.WorkEditorSelectorController._settle_embedded_selector_surface.__get__(ctrl, WorkEditorSelectorController)

        dummy_widget = _DummyWidget()

        with patch.object(ctrl_module, "build_embedded_selector_parity_widget", return_value=dummy_widget):
            opened = ctrl._try_open_embedded(kind="tools", head="HEAD1", spindle="main")

        self.assertTrue(opened)
        self.assertLess(events.index("widget.show"), events.index("enter_mode"))

    def test_try_open_embedded_settles_then_enters_mode(self):
        events = []

        class _DummyCoordinator:
            session_id = "session-1"
            is_busy = False

            @staticmethod
            def request_open(*, caller):
                events.append(("request_open", caller))
                return "session-1"

            @staticmethod
            def mark_mount_complete(*, caller):
                events.append(("mark_mount_complete", caller))

        class _DummyLayout:
            def setContentsMargins(self, *_args):
                return None

            def setSpacing(self, *_args):
                return None

            def addWidget(self, _widget):
                events.append("layout.addWidget")

            def activate(self):
                events.append("layout.activate")

        class _DummyMount:
            def __init__(self):
                self._layout = _DummyLayout()

            def layout(self):
                return self._layout

            def updateGeometry(self):
                events.append("mount.updateGeometry")

        class _DummyRootStack:
            def layout(self):
                return _DummyLayout()

            def updateGeometry(self):
                events.append("stack.updateGeometry")

        class _DummyWidget:
            def __init__(self):
                self._layout = _DummyLayout()

            def ensurePolished(self):
                events.append("widget.ensurePolished")

            def show(self):
                events.append("widget.show")

            def updateGeometry(self):
                events.append("widget.updateGeometry")

            def layout(self):
                return self._layout

            def raise_(self):
                events.append("widget.raise")

            def activateWindow(self):
                events.append("widget.activate")

        dummy_dialog = SimpleNamespace(
            _root_stack=_DummyRootStack(),
            _SELECTOR_LOCAL_FADE_MS=0,
            setUpdatesEnabled=lambda _v: None,
            hide=lambda: None,
            show=lambda: None,
        )

        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dummy_dialog
        ctrl._coordinator = _DummyCoordinator()
        ctrl._active_embedded_widget = None
        ctrl._transport_mode = "embedded"
        ctrl._pending_enter_fade_surface = None
        ctrl._schedule_preview_host_preload = lambda: events.append("preload.schedule")
        ctrl._log = lambda *_args, **_kwargs: None
        ctrl._enter_mode = lambda: events.append("enter_mode")
        ctrl._exit_mode = lambda: events.append("exit_mode")
        ctrl._detach_active_embedded_widget = lambda: events.append("detach_active")
        ctrl._current_mount_container = lambda: _DummyMount()
        ctrl._apply_selector_result = lambda *_args, **_kwargs: None

        dummy_widget = _DummyWidget()

        with patch.object(ctrl_module, "build_embedded_selector_parity_widget", return_value=dummy_widget):
            opened = ctrl._try_open_embedded(kind="tools", head="HEAD1", spindle="main")

        self.assertTrue(opened)
        # Widget must be shown (inside the suppressed block) before enter_mode
        # switches the stack, so the first paint sees a fully populated page.
        self.assertLess(events.index("widget.show"), events.index("enter_mode"))

    def test_try_open_embedded_preexpands_dialog_before_building_widget(self):
        events = []

        class _DummyCoordinator:
            session_id = "session-1"
            is_busy = False

            @staticmethod
            def request_open(*, caller):
                return "session-1"

            @staticmethod
            def mark_mount_complete(*, caller):
                events.append(("mark_mount_complete", caller))

        class _DummyLayout:
            def setContentsMargins(self, *_args):
                return None

            def setSpacing(self, *_args):
                return None

            def addWidget(self, _widget):
                events.append("layout.addWidget")

            def activate(self):
                return None

        class _DummyMount:
            def __init__(self):
                self._layout = _DummyLayout()

            def layout(self):
                return self._layout

            def updateGeometry(self):
                return None

        class _DummyRootStack:
            def layout(self):
                return _DummyLayout()

            def updateGeometry(self):
                return None

        class _DummyWidget:
            def __init__(self):
                self._layout = _DummyLayout()

            def ensurePolished(self):
                return None

            def show(self):
                return None

            def updateGeometry(self):
                return None

            def layout(self):
                return self._layout

            def raise_(self):
                return None

            def activateWindow(self):
                return None

        dummy_dialog = SimpleNamespace(
            _root_stack=_DummyRootStack(),
            _SELECTOR_LOCAL_FADE_MS=0,
            _RESIZE_FOR_SELECTOR_MODE=True,
            setUpdatesEnabled=lambda _v: None,
            hide=lambda: None,
            show=lambda: None,
        )

        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dummy_dialog
        ctrl._coordinator = _DummyCoordinator()
        ctrl._active_embedded_widget = None
        ctrl._transport_mode = "embedded"
        ctrl._pending_enter_fade_surface = None
        ctrl._preexpanded_for_selector_open = False
        ctrl._restore_state = None
        ctrl._mode_active = False
        ctrl._schedule_preview_host_preload = lambda: None
        ctrl._log = lambda *_args, **_kwargs: None
        ctrl._enter_mode = lambda: events.append("enter_mode")
        ctrl._exit_mode = lambda: events.append("exit_mode")
        ctrl._detach_active_embedded_widget = lambda: events.append("detach_active")
        ctrl._current_mount_container = lambda: _DummyMount()
        ctrl._apply_selector_result = lambda *_args, **_kwargs: None
        ctrl._expand_for_mode = lambda: events.append("dialog.preexpand")
        ctrl._capture_restore_state = lambda: {"geometry": "original"}

        dummy_widget = _DummyWidget()

        with patch.object(ctrl_module, "build_embedded_selector_parity_widget", side_effect=lambda *args, **kwargs: events.append("widget.build") or dummy_widget):
            opened = ctrl._try_open_embedded(kind="tools", head="HEAD1", spindle="main")

        self.assertTrue(opened)
        # widget build happens before enter_mode (stack switch).
        self.assertLess(events.index("widget.build"), events.index("enter_mode"))

    def test_preexpand_dialog_for_selector_open_disables_updates_during_resize(self):
        events = []

        class _DummyLayout:
            def activate(self):
                events.append("layout.activate")

        class _DummyRootStack:
            def layout(self):
                return _DummyLayout()

            def updateGeometry(self):
                events.append("stack.updateGeometry")

        class _DummyDialog:
            _RESIZE_FOR_SELECTOR_MODE = True

            def __init__(self):
                self._updates_enabled = True
                self._root_stack = _DummyRootStack()

            def updatesEnabled(self):
                return self._updates_enabled

            def setUpdatesEnabled(self, enabled):
                self._updates_enabled = bool(enabled)
                events.append(f"updates:{enabled}")

            def layout(self):
                return _DummyLayout()

            def updateGeometry(self):
                events.append("dialog.updateGeometry")

        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = _DummyDialog()
        ctrl._preexpanded_for_selector_open = False
        ctrl._restore_state = None
        ctrl._capture_restore_state = lambda: {"geometry": "original"}
        ctrl._expand_for_mode = lambda: events.append("dialog.preexpand")

        ctrl_module.WorkEditorSelectorController._preexpand_dialog_for_selector_open(ctrl)

        # updates guard removed — outer _try_open_embedded owns it now
        self.assertEqual(["dialog.preexpand", "layout.activate", "dialog.updateGeometry"], events)

    def test_reveal_mode_transition_does_not_surface_fade_on_open(self):
        events = []

        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._pending_enter_fade_surface = "selector-surface"
        ctrl._animate_transition_shield_out = lambda: events.append("shield") or False
        ctrl._animate_surface_fade = lambda surface: events.append(("surface", surface))

        ctrl_module.WorkEditorSelectorController._reveal_mode_transition(ctrl, "selector-surface")

        self.assertEqual(["shield"], events)
        self.assertIsNone(ctrl._pending_enter_fade_surface)

    def test_animate_transition_shield_out_hides_immediately_when_open_reveal_disabled(self):
        events = []

        class _VisibleShield(QWidget):
            def isVisible(self):
                return True

        shield = _VisibleShield()
        effect = QGraphicsOpacityEffect(shield)
        shield.setGraphicsEffect(effect)
        shield._selector_shield_effect = effect

        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = SimpleNamespace(
            _selector_transition_shield=shield,
            _SELECTOR_OPEN_REVEAL_MS=0,
            _SELECTOR_LOCAL_FADE_MS=360,
        )
        ctrl._hide_shield = lambda: events.append("hide")

        handled = ctrl_module.WorkEditorSelectorController._animate_transition_shield_out(ctrl)

        self.assertTrue(handled)
        self.assertEqual(["hide"], events)

    def test_open_selector_request_falls_back_to_ipc_when_embedded_fails(self):
        calls = []

        dummy_dialog = SimpleNamespace()
        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dummy_dialog
        ctrl._transport_mode = "embedded"
        ctrl._mode_active = False
        ctrl._open_requested = False
        ctrl._coordinator = SimpleNamespace(is_busy=False)
        ctrl._log = lambda *args, **kwargs: None
        ctrl._try_open_via_ipc = lambda **kwargs: calls.append(("ipc", kwargs)) or True
        ctrl._try_open_embedded = lambda **kwargs: calls.append(("embedded", kwargs)) or False

        opened = ctrl._open_selector_request(kind="jaws", spindle="sub")

        self.assertTrue(opened)
        self.assertEqual(
            [
                ("embedded", {"kind": "jaws", "head": "", "spindle": "sub", "target_key": "", "initial_assignments": None, "initial_assignment_buckets": None}),
                ("ipc", {"kind": "jaws", "head": "", "spindle": "sub", "target_key": "", "initial_assignments": None, "initial_assignment_buckets": None}),
            ],
            calls,
        )

    def test_open_selector_request_uses_embedded_when_transport_is_embedded(self):
        calls = []

        dummy_dialog = SimpleNamespace()
        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dummy_dialog
        ctrl._transport_mode = "embedded"
        ctrl._mode_active = False
        ctrl._open_requested = False
        ctrl._coordinator = SimpleNamespace(is_busy=False)
        ctrl._log = lambda *args, **kwargs: None
        ctrl._try_open_via_ipc = lambda **kwargs: calls.append(("ipc", kwargs)) or False
        ctrl._try_open_embedded = lambda **kwargs: calls.append(("embedded", kwargs)) or True

        opened = ctrl._open_selector_request(kind="fixtures", target_key="OP10")

        self.assertTrue(opened)
        self.assertEqual([("embedded", {"kind": "fixtures", "head": "", "spindle": "", "target_key": "OP10", "initial_assignments": None, "initial_assignment_buckets": None})], calls)

    def test_open_selector_request_does_not_fallback_when_embedded_refuses_busy_session(self):
        calls = []

        dummy_dialog = SimpleNamespace()
        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dummy_dialog
        ctrl._transport_mode = "embedded"
        ctrl._mode_active = False
        ctrl._open_requested = False
        ctrl._coordinator = SimpleNamespace(is_busy=True)
        ctrl._log = lambda *args, **kwargs: None
        ctrl._try_open_via_ipc = lambda **kwargs: calls.append(("ipc", kwargs)) or True
        ctrl._try_open_embedded = lambda **kwargs: calls.append(("embedded", kwargs)) or False

        opened = ctrl._open_selector_request(kind="tools", head="HEAD1")

        self.assertFalse(opened)
        self.assertEqual(
            [("embedded", {"kind": "tools", "head": "HEAD1", "spindle": "", "target_key": "", "initial_assignments": None, "initial_assignment_buckets": None})],
            calls,
        )

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


class TestSelectorControllerReuse(unittest.TestCase):
    def test_reset_for_reuse_disposes_cached_embedded_runtime(self):
        dialog = SimpleNamespace()
        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._dialog = dialog
        ctrl._coordinator = SimpleNamespace(is_busy=False)
        ctrl._mode_active = False
        ctrl._open_requested = True
        ctrl._pending_ipc_request_id = "pending"
        ctrl._pending_ipc_kind = "tools"
        ctrl._ipc_saved_geometry = object()
        ctrl._restore_state = {"geometry": "old"}
        ctrl._hidden_editor_widgets = [object()]
        ctrl._transition_shield_pending_hide = True

        detached = []
        ctrl._detach_active_embedded_widget = lambda: detached.append(True)

        with patch.object(ctrl_module, "dispose_embedded_selector_runtime") as dispose_runtime:
            ctrl.reset_for_reuse()

        self.assertEqual([True], detached)
        dispose_runtime.assert_called_once_with(dialog)
        self.assertFalse(ctrl._mode_active)
        self.assertFalse(ctrl._open_requested)
        self.assertEqual([], ctrl._hidden_editor_widgets)
        self.assertFalse(ctrl._transition_shield_pending_hide)
        self.assertIsNone(ctrl._pending_ipc_request_id)
        self.assertIsNone(ctrl._pending_ipc_kind)
        self.assertIsNone(ctrl._ipc_saved_geometry)
        self.assertIsNone(ctrl._restore_state)


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


class TestEmbeddedSelectorPreviewPreload(unittest.TestCase):
    def test_preload_preview_host_launches_hidden_library_and_warms_preview_runtime(self):
        ctrl = WorkEditorSelectorController.__new__(WorkEditorSelectorController)
        ctrl._transport_mode = "embedded"
        ctrl._preview_host_preload_scheduled = False
        ctrl._preview_host_launch_started = False

        with patch.object(ctrl_module, "is_tool_library_ready", return_value=False) as ready_check, \
             patch.object(ctrl_module, "launch_tool_library", return_value=True) as launch_tool_library, \
             patch.object(ctrl_module, "send_to_tool_library", return_value=False), \
             patch.object(ctrl_module, "send_request_with_retry") as send_with_retry:
            WorkEditorSelectorController._preload_preview_host(ctrl)

        ready_check.assert_called()
        launch_tool_library.assert_called_once()
        send_with_retry.assert_called_once()
        payload = send_with_retry.call_args.args[1]
        self.assertEqual("warm_preview_runtime", payload["command"])
        self.assertFalse(payload["show"])


class TestEmbeddedSelectorParityFactory(unittest.TestCase):
    def test_fixture_selector_reuses_cached_widget_and_resets_session(self):
        construct_calls = []
        reset_calls = []

        class _FakeFixtureSelectorDialog(QWidget):
            def __init__(
                self,
                *,
                fixture_service,
                translate,
                initial_assignments,
                initial_assignment_buckets,
                initial_target_key,
                on_submit,
                on_cancel,
                parent,
                embedded_mode,
            ):
                super().__init__(parent)
                construct_calls.append(
                    {
                        "fixture_service": fixture_service,
                        "initial_assignments": initial_assignments,
                        "initial_assignment_buckets": initial_assignment_buckets,
                        "initial_target_key": initial_target_key,
                        "embedded_mode": embedded_mode,
                    }
                )
                self._on_submit = on_submit
                self._on_cancel = on_cancel

            def reset_for_session(
                self,
                *,
                initial_assignments,
                initial_assignment_buckets,
                initial_target_key,
                on_submit,
                on_cancel,
            ):
                reset_calls.append(
                    {
                        "initial_assignments": initial_assignments,
                        "initial_assignment_buckets": initial_assignment_buckets,
                        "initial_target_key": initial_target_key,
                    }
                )
                self._on_submit = on_submit
                self._on_cancel = on_cancel

        fake_module = ModuleType("tools_and_jaws_library.ui.selectors.fixture_selector_dialog")
        fake_module.FixtureSelectorDialog = _FakeFixtureSelectorDialog

        dialog = SimpleNamespace(_t=lambda _key, default=None, **_kwargs: default or "")
        mount_container = QWidget()
        self.addCleanup(mount_container.deleteLater)

        with patch.dict(sys.modules, {"tools_and_jaws_library.ui.selectors.fixture_selector_dialog": fake_module}), \
             patch.object(parity_module, "_activate_tool_library_namespace_aliases", lambda _dialog: None), \
             patch.object(parity_module, "_ensure_service_bundle", return_value={"fixture_service": object()}), \
             patch.object(parity_module, "_prime_embedded_selector_widget", lambda _widget: None), \
             patch.object(parity_module, "_apply_embedded_selector_style", lambda _widget: None):
            first = parity_module.build_embedded_selector_parity_widget(
                dialog,
                mount_container=mount_container,
                kind="fixtures",
                follow_up={"target_key": "OP10"},
                initial_assignments=[{"fixture_id": "F1"}],
                initial_assignment_buckets={"OP10": [{"fixture_id": "F1"}]},
                on_submit=lambda _payload: None,
                on_cancel=lambda: None,
            )
            second = parity_module.build_embedded_selector_parity_widget(
                dialog,
                mount_container=mount_container,
                kind="fixtures",
                follow_up={"target_key": "OP20"},
                initial_assignments=[{"fixture_id": "F2"}],
                initial_assignment_buckets={"OP20": [{"fixture_id": "F2"}]},
                on_submit=lambda _payload: None,
                on_cancel=lambda: None,
            )

        self.addCleanup(first.deleteLater)
        self.assertIs(first, second)
        self.assertEqual(1, len(construct_calls))
        self.assertEqual(2, len(reset_calls))
        self.assertEqual("OP20", reset_calls[-1]["initial_target_key"])
        self.assertEqual([{"fixture_id": "F2"}], reset_calls[-1]["initial_assignments"])
        self.assertEqual({"OP20": [{"fixture_id": "F2"}]}, reset_calls[-1]["initial_assignment_buckets"])
        self.assertTrue(getattr(first, "_reuse_cached_selector_widget"))


class TestFixtureSelectorReset(unittest.TestCase):
    def test_fixture_reset_for_session_clears_cached_ui_state(self):
        FixtureSelectorDialog = _import_tools_selector_class(
            "tools_and_jaws_library.ui.selectors.fixture_selector_dialog",
            "FixtureSelectorDialog",
        )

        class _DummyToggle:
            def __init__(self, checked: bool = True):
                self.checked = checked

            def setChecked(self, checked: bool) -> None:
                self.checked = bool(checked)

        class _DummySearchInput:
            def __init__(self):
                self.visible = True
                self.block_calls = []
                self.cleared = False

            def setVisible(self, visible: bool) -> None:
                self.visible = bool(visible)

            def blockSignals(self, blocked: bool) -> None:
                self.block_calls.append(bool(blocked))

            def clear(self) -> None:
                self.cleared = True

        class _DummyCombo:
            def __init__(self):
                self.items = [("OLD", "OLD")]
                self.current_index = 0
                self.block_calls = []

            def count(self) -> int:
                return len(self.items)

            def setCurrentIndex(self, index: int) -> None:
                self.current_index = int(index)

            def blockSignals(self, blocked: bool) -> None:
                self.block_calls.append(bool(blocked))

            def clear(self) -> None:
                self.items = []

            def addItem(self, label: str, data: str) -> None:
                self.items.append((label, data))

            def findData(self, value: str) -> int:
                for index, (_label, data) in enumerate(self.items):
                    if data == value:
                        return index
                return -1

        class _DummyDetailCard:
            def __init__(self):
                self.visible = True

            def isVisible(self) -> bool:
                return self.visible

        class _DummyListView:
            def __init__(self):
                self.cleared = False
                self.current_index = None

            def clearSelection(self) -> None:
                self.cleared = True

            def setCurrentIndex(self, index) -> None:
                self.current_index = index

        class _DummyFixtureSelector:
            reset_for_session = FixtureSelectorDialog.reset_for_session

            def __init__(self):
                self._submitted = True
                self._cancel_notified = True
                self._on_submit = None
                self._on_cancel = None
                self._assignment_buckets_by_target = {"OLD": [{"fixture_id": "OLD"}]}
                self._target_keys = ["OLD"]
                self._active_target_key = "OLD"
                self._selected_items = [{"fixture_id": "OLD"}]
                self._selected_ids = {"OLD"}
                self.search_toggle = _DummyToggle(True)
                self.search_input = _DummySearchInput()
                self.view_filter = _DummyCombo()
                self.preview_window_btn = _DummyToggle(True)
                self.detail_card = _DummyDetailCard()
                self.list_view = _DummyListView()
                self.target_filter = _DummyCombo()
                self.switch_calls = 0
                self.refresh_calls = 0
                self.rebuild_calls = 0
                self.update_calls = 0

            @staticmethod
            def _fixture_key(item: dict | None) -> str:
                if not isinstance(item, dict):
                    return ""
                return str(item.get("fixture_id") or "").strip()

            @staticmethod
            def _normalize_fixture(item: dict | None) -> dict | None:
                if not isinstance(item, dict):
                    return None
                fixture_id = str(item.get("fixture_id") or "").strip()
                if not fixture_id:
                    return None
                return {"fixture_id": fixture_id}

            def _switch_to_selector_panel(self) -> None:
                self.switch_calls += 1
                self.detail_card.visible = False

            def _refresh_catalog(self) -> None:
                self.refresh_calls += 1

            def _rebuild_assignment_list(self) -> None:
                self.rebuild_calls += 1

            def _update_assignment_buttons(self) -> None:
                self.update_calls += 1

        dummy = _DummyFixtureSelector()

        dummy.reset_for_session(
            initial_assignments=[{"fixture_id": "F2"}],
            initial_assignment_buckets={"OP20": [{"fixture_id": "F2"}]},
            initial_target_key="OP20",
            on_submit=lambda _payload: None,
            on_cancel=lambda: None,
        )

        self.assertFalse(dummy.search_toggle.checked)
        self.assertFalse(dummy.search_input.visible)
        self.assertEqual([True, False], dummy.search_input.block_calls)
        self.assertTrue(dummy.search_input.cleared)
        self.assertEqual(0, dummy.view_filter.current_index)
        self.assertFalse(dummy.preview_window_btn.checked)
        self.assertEqual(1, dummy.switch_calls)
        self.assertTrue(dummy.list_view.cleared)
        self.assertIsInstance(dummy.list_view.current_index, QModelIndex)
        self.assertFalse(dummy.list_view.current_index.isValid())
        self.assertEqual(1, dummy.refresh_calls)
        self.assertEqual(1, dummy.rebuild_calls)
        self.assertEqual(1, dummy.update_calls)
        self.assertEqual("OP20", dummy._active_target_key)
        self.assertEqual([{"fixture_id": "F2"}], dummy._selected_items)
        self.assertEqual({"F2"}, dummy._selected_ids)
        self.assertEqual([("OP20", "OP20")], dummy.target_filter.items)


class _DummyToggleButton:
    def __init__(self, checked: bool = True):
        self._checked = bool(checked)

    def setChecked(self, checked: bool) -> None:
        self._checked = bool(checked)

    def isChecked(self) -> bool:
        return self._checked


class TestEmbeddedSelectorPreviewGuards(unittest.TestCase):
    def test_fixture_selector_preview_methods_use_selector_preview_host(self):
        FixtureSelectorDialog = _import_tools_selector_class(
            "tools_and_jaws_library.ui.selectors.fixture_selector_dialog",
            "FixtureSelectorDialog",
        )

        module = sys.modules[FixtureSelectorDialog.__module__]
        dummy = SimpleNamespace(_embedded_mode=False, preview_window_btn=_DummyToggleButton(False))
        viewer = object()
        fixture = {"fixture_id": "F1"}

        with patch.object(module, "load_fixture_selector_preview_content", return_value=True) as load_preview, \
             patch.object(module, "on_fixture_selector_detached_measurements_toggled") as toggle_measurements, \
             patch.object(module, "on_fixture_selector_detached_preview_closed") as close_preview, \
             patch.object(module, "sync_fixture_selector_detached_preview", return_value=True) as sync_preview, \
             patch.object(module, "toggle_fixture_selector_preview_window") as toggle_preview, \
             patch.object(module, "fixture_preview_transform_signature", return_value=("sig",)):
            self.assertTrue(FixtureSelectorDialog._load_preview_content(dummy, viewer, fixture, label="Fixture"))
            self.assertEqual(("F1", "null", "[]", ("sig",)), FixtureSelectorDialog._preview_model_key(dummy, fixture))
            FixtureSelectorDialog._on_detached_measurements_toggled(dummy, True)
            FixtureSelectorDialog._on_detached_preview_closed(dummy, 0)
            self.assertTrue(FixtureSelectorDialog._sync_detached_preview(dummy, show_errors=True))
            FixtureSelectorDialog.toggle_preview_window(dummy)

        load_preview.assert_called_once_with(dummy, viewer, fixture, label="Fixture")
        toggle_measurements.assert_called_once_with(dummy, True)
        close_preview.assert_called_once_with(dummy, 0)
        sync_preview.assert_called_once_with(dummy, show_errors=True)
        toggle_preview.assert_called_once_with(dummy)

    def test_tool_selector_preview_methods_use_selector_preview_host(self):
        ToolSelectorDialog = _import_tools_selector_class(
            "tools_and_jaws_library.ui.selectors.tool_selector_dialog",
            "ToolSelectorDialog",
        )

        module = sys.modules[ToolSelectorDialog.__module__]
        dummy = SimpleNamespace(_embedded_mode=False)
        viewer = object()

        with patch.object(module, "load_tool_selector_preview_content", return_value=True) as load_preview, \
             patch.object(module, "sync_tool_selector_detached_preview", return_value=True) as sync_preview, \
             patch.object(module, "toggle_tool_selector_preview_window") as toggle_preview:
            self.assertTrue(ToolSelectorDialog._load_preview_content(dummy, viewer, "tool.stl", label="Tool"))
            self.assertTrue(ToolSelectorDialog._sync_detached_preview(dummy, show_errors=True))
            ToolSelectorDialog.toggle_preview_window(dummy)

        load_preview.assert_called_once_with(viewer, "tool.stl", label="Tool")
        sync_preview.assert_called_once_with(dummy, show_errors=True)
        toggle_preview.assert_called_once_with(dummy)

    def test_jaw_selector_preview_methods_use_selector_preview_host(self):
        JawSelectorDialog = _import_tools_selector_class(
            "tools_and_jaws_library.ui.selectors.jaw_selector_dialog",
            "JawSelectorDialog",
        )

        module = sys.modules[JawSelectorDialog.__module__]
        dummy = SimpleNamespace(_embedded_mode=False)
        viewer = object()
        jaw = {"jaw_id": "J1"}

        with patch.object(module, "load_jaw_selector_preview_content", return_value=True) as load_preview, \
             patch.object(module, "on_jaw_selector_detached_measurements_toggled") as toggle_measurements, \
             patch.object(module, "on_jaw_selector_detached_preview_closed") as close_preview, \
             patch.object(module, "sync_jaw_selector_detached_preview", return_value=True) as sync_preview, \
             patch.object(module, "toggle_jaw_selector_preview_window") as toggle_preview:
            self.assertTrue(JawSelectorDialog._load_preview_content(dummy, viewer, jaw, label="Jaw"))
            JawSelectorDialog._on_detached_measurements_toggled(dummy, True)
            JawSelectorDialog._on_detached_preview_closed(dummy, 0)
            self.assertTrue(JawSelectorDialog._sync_detached_preview(dummy, show_errors=True))
            JawSelectorDialog.toggle_preview_window(dummy)

        load_preview.assert_called_once_with(dummy, viewer, jaw, label="Jaw")
        toggle_measurements.assert_called_once_with(dummy, True)
        close_preview.assert_called_once_with(dummy, 0)
        sync_preview.assert_called_once_with(dummy, True)
        toggle_preview.assert_called_once_with(dummy)

    def test_fixture_embedded_preview_toggle_is_visible_and_enabled(self):
        FixtureSelectorDialog = _import_tools_selector_class(
            "tools_and_jaws_library.ui.selectors.fixture_selector_dialog",
            "FixtureSelectorDialog",
        )

        fixture_service = SimpleNamespace(list_fixtures=lambda **_kwargs: [])
        dialog = FixtureSelectorDialog(
            fixture_service=fixture_service,
            translate=lambda _key, default=None, **_kwargs: default or "",
            initial_assignments=[],
            initial_assignment_buckets={"OP10": []},
            initial_target_key="OP10",
            on_submit=lambda _payload: None,
            on_cancel=lambda: None,
            embedded_mode=True,
        )
        self.addCleanup(dialog.deleteLater)

        self.assertFalse(dialog.preview_window_btn.isHidden())
        self.assertTrue(dialog.preview_window_btn.isEnabled())

    def test_tool_embedded_toggle_preview_uses_external_preview_host(self):
        EmbeddedToolSelectorWidget = _import_tools_selector_class(
            "tools_and_jaws_library.ui.selectors.tool_selector_dialog",
            "EmbeddedToolSelectorWidget",
        )

        module = sys.modules[EmbeddedToolSelectorWidget.__module__]
        button = _DummyToggleButton(checked=True)
        dummy = SimpleNamespace(_embedded_mode=True, preview_window_btn=button)
        with patch.object(module, "toggle_embedded_tool_selector_preview_window") as toggle_preview, \
             patch.object(module, "sync_embedded_tool_selector_preview", return_value=True) as sync_preview:
            EmbeddedToolSelectorWidget.toggle_preview_window(dummy)
            self.assertTrue(EmbeddedToolSelectorWidget._sync_detached_preview(dummy, show_errors=True))

        toggle_preview.assert_called_once_with(dummy)
        sync_preview.assert_called_once_with(dummy, show_errors=True)

    def test_jaw_embedded_toggle_preview_uses_external_preview_host(self):
        EmbeddedJawSelectorWidget = _import_tools_selector_class(
            "tools_and_jaws_library.ui.selectors.jaw_selector_dialog",
            "EmbeddedJawSelectorWidget",
        )

        module = sys.modules[EmbeddedJawSelectorWidget.__module__]
        button = _DummyToggleButton(checked=True)
        dummy = SimpleNamespace(_embedded_mode=True, preview_window_btn=button)
        with patch.object(module, "toggle_embedded_jaw_selector_preview_window") as toggle_preview, \
             patch.object(module, "sync_embedded_jaw_selector_preview", return_value=True) as sync_preview:
            EmbeddedJawSelectorWidget.toggle_preview_window(dummy)
            self.assertTrue(EmbeddedJawSelectorWidget._sync_detached_preview(dummy, show_errors=True))

        toggle_preview.assert_called_once_with(dummy)
        sync_preview.assert_called_once_with(dummy, show_errors=True)

    def test_fixture_embedded_toggle_preview_uses_external_preview_host(self):
        FixtureSelectorDialog = _import_tools_selector_class(
            "tools_and_jaws_library.ui.selectors.fixture_selector_dialog",
            "FixtureSelectorDialog",
        )

        module = sys.modules[FixtureSelectorDialog.__module__]
        button = _DummyToggleButton(checked=True)
        dummy = SimpleNamespace(_embedded_mode=True, preview_window_btn=button)
        with patch.object(module, "toggle_embedded_fixture_selector_preview_window") as toggle_preview, \
             patch.object(module, "sync_embedded_fixture_selector_preview", return_value=True) as sync_preview:
            FixtureSelectorDialog.toggle_preview_window(dummy)
            self.assertTrue(FixtureSelectorDialog._sync_detached_preview(dummy, show_errors=True))

        toggle_preview.assert_called_once_with(dummy)
        sync_preview.assert_called_once_with(dummy, show_errors=True)


class TestEmbeddedSelectorPreviewPayload(unittest.TestCase):
    def test_tool_embedded_preview_payload_includes_host_geometry(self):
        module = importlib.import_module("tools_and_jaws_library.ui.selectors.external_preview_ipc")

        class _Rect:
            def __init__(self, x, y, w, h):
                self._x = x
                self._y = y
                self._w = w
                self._h = h

            def x(self):
                return self._x

            def y(self):
                return self._y

            def width(self):
                return self._w

            def height(self):
                return self._h

        class _Host:
            @staticmethod
            def frameGeometry():
                return _Rect(100, 120, 1400, 900)

            @staticmethod
            def geometry():
                return _Rect(112, 152, 1376, 836)

        page = SimpleNamespace(
            _get_selected_tool=lambda: {"id": "T001", "description": "Tool", "stl_path": "tool.stl", "measurement_overlays": []},
            _t=lambda _k, default=None, **_kwargs: default or "",
            _detached_measurements_enabled=True,
            window=lambda: _Host(),
        )

        payload = module._tool_preview_payload(page)

        self.assertEqual([100, 120, 1400, 900], payload["host_frame_geometry"])
        self.assertEqual([112, 152, 1376, 836], payload["host_content_geometry"])


if __name__ == "__main__":
    unittest.main()
