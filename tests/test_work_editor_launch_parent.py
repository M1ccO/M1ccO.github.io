from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
_SETUP_ROOT = _WORKSPACE / "Setup Manager"
for _candidate in (_WORKSPACE, _SETUP_ROOT):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from PySide6.QtGui import QShowEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QBoxLayout, QDialog, QWidget  # noqa: E402
import ui.main_window as main_window_module  # noqa: E402
from ui.setup_page_support import batch_actions, crud_actions  # noqa: E402
from ui.setup_page_support.work_editor_launch import (  # noqa: E402
    exec_work_editor_dialog,
    prime_work_editor_dialog,
    resolve_work_editor_parent,
)
from ui.work_editor_factory import (  # noqa: E402
    LatheWorkEditorDialog,
    MachiningCenterWorkEditorDialog,
    create_work_editor_dialog,
    resolve_work_editor_dialog_class,
)
import ui.work_editor_dialog as work_editor_dialog_module  # noqa: E402
from ui.work_editor_dialog import WorkEditorDialog  # noqa: E402
from ui.work_editor_support.dialog_lifecycle import setup_tabs  # noqa: E402
from ui.work_editor_support.zero_points import set_zero_xy_visibility  # noqa: E402

try:
    sys.path.remove(str(_SETUP_ROOT))
except ValueError:
    pass

_APP = QApplication.instance() or QApplication([])


class _HostWindow(QWidget):
    pass


class _PageStub(QWidget):
    def __init__(self, host: QWidget):
        super().__init__(host)
        self.draw_service = object()
        self.drawings_enabled = True
        self.work_service = SimpleNamespace(
            get_machine_profile_key=lambda: "lathe_1sp_1h",
            get_work=lambda _work_id: {"work_id": _work_id},
            save_work=lambda _payload: None,
        )
        self.refresh_works = lambda: None
        self._selected_work_ids = lambda: ["W001"]
        self._t = lambda _key, default=None, **_kwargs: default or ""


class TestWorkEditorLaunchParent(unittest.TestCase):
    def test_zero_points_layout_uses_dialog_width_when_host_is_not_ready(self):
        class _Host:
            def __init__(self):
                self._switch_width = 820
                self._direction = QBoxLayout.TopToBottom
                self._layout = SimpleNamespace(
                    direction=lambda: self._direction,
                    setDirection=lambda new_direction: setattr(self, "_direction", new_direction),
                )
                self.updated = False

            def width(self):
                return 0

            def _update_separator_shapes(self):
                self.updated = True

        class _Dialog:
            def __init__(self):
                self.zero_points_host = _Host()
                self._zero_axis_widgets = {"z": [], "x": [], "y": [], "c": []}
                self._zero_row_spacers = []
                self._zero_coord_combos = []
                self._zero_grids_with_groups = []

            def width(self):
                return 960

        dialog = _Dialog()
        set_zero_xy_visibility(dialog, False)

        self.assertEqual(820, dialog.zero_points_host._switch_width)
        self.assertEqual(QBoxLayout.LeftToRight, dialog.zero_points_host._direction)
        self.assertTrue(dialog.zero_points_host.updated)

    def test_machining_center_work_editor_primes_zero_points_during_construction(self):
        class _DummyHead:
            def __init__(self, key: str):
                self.key = key

        class _DummySpindle:
            def __init__(self, key: str, title: str, filter_text: str):
                self.key = key
                self.jaw_title_key = f"work_editor.jaw.{key}"
                self.jaw_title_default = title
                self.jaw_filter = filter_text
                self.jaw_filter_placeholder_key = f"work_editor.jaw.filter_{key}_placeholder"
                self.jaw_filter_placeholder_default = f"Filter {title}"

        class _DummyProfile:
            zero_axes = ("z",)
            heads = [_DummyHead("HEAD1")]
            spindles = [_DummySpindle("main", "Pääkaran leuat", "Main spindle")]
            spindle_count = 1
            supports_zero_xy_toggle = False
            default_zero_xy_visible = False
            supports_sub_pickup = False

            def spindle(self, key: str):
                return next((spindle for spindle in self.spindles if spindle.key == key), None)

        class _DialogStub(WorkEditorDialog):
            def _build_general_tab(self):
                pass

            def _build_notes_tab(self):
                pass

            def _load_external_refs(self):
                pass

            def _load_work(self):
                pass

            def _set_secondary_button_theme(self):
                pass

            def _apply_host_visual_style(self):
                pass

            def _install_local_event_filters(self):
                pass

            def _setup_raw_part_combo_popup_guard(self):
                pass

            def _close_transient_combo_popups(self):
                pass

        module = work_editor_dialog_module
        with mock.patch.object(module, "UiPreferencesService") as prefs_mock, mock.patch.object(
            module, "load_profile", return_value=_DummyProfile()
        ), mock.patch.object(module, "resolve_profile_key", side_effect=lambda value: value), mock.patch(
            "machine_profiles.apply_machining_center_overrides",
            side_effect=lambda base_profile, **_kwargs: base_profile,
        ), mock.patch.object(WorkEditorDialog, "_build_zeros_tab") as build_zeros_mock, mock.patch.object(
            WorkEditorDialog, "_apply_work_payload_to_zeros_tab"
        ), mock.patch.object(WorkEditorDialog, "_build_tools_tab") as build_tools_mock, mock.patch.object(
            WorkEditorDialog, "_apply_work_payload_to_tools_tab"
        ), mock.patch.object(WorkEditorDialog, "_refresh_tool_head_widgets"
        ), mock.patch.object(WorkEditorDialog, "_sync_tool_head_view"
        ):
            prefs_mock.return_value.load.return_value = {}
            dialog = _DialogStub(
                draw_service=SimpleNamespace(),
                work=None,
                parent=None,
                style_host=None,
                translate=lambda _k, default=None, **_kwargs: default or "",
                batch_label="",
                group_edit_mode=False,
                group_count=None,
                drawings_enabled=True,
                machine_profile_key=None,
            )

        build_zeros_mock.assert_called_once()
        build_tools_mock.assert_called_once()

    def test_lathe_work_editor_shell_primes_zero_points_and_tools_during_construction(self):
        class _DialogStub(LatheWorkEditorDialog):
            def _build_general_tab(self):
                pass

            def _build_notes_tab(self):
                pass

            def _load_external_refs(self):
                pass

            def _load_work(self):
                pass

            def _set_secondary_button_theme(self):
                pass

            def _apply_host_visual_style(self):
                pass

            def _install_local_event_filters(self):
                pass

            def _setup_raw_part_combo_popup_guard(self):
                pass

            def _close_transient_combo_popups(self):
                pass

        module = work_editor_dialog_module
        with mock.patch.object(module, "UiPreferencesService") as prefs_mock, mock.patch.object(
            module, "load_profile"
        ), mock.patch.object(module, "resolve_profile_key", side_effect=lambda value: value), mock.patch.object(
            LatheWorkEditorDialog, "_build_zeros_tab"
        ) as build_zeros_mock, mock.patch.object(
            LatheWorkEditorDialog, "_apply_work_payload_to_zeros_tab"
        ), mock.patch.object(
            LatheWorkEditorDialog, "_build_tools_tab"
        ) as build_tools_mock, mock.patch.object(
            LatheWorkEditorDialog, "_apply_work_payload_to_tools_tab"
        ), mock.patch.object(
            LatheWorkEditorDialog, "_refresh_tool_head_widgets"
        ), mock.patch.object(
            LatheWorkEditorDialog, "_sync_tool_head_view"
        ):
            prefs_mock.return_value.load.return_value = {}
            _DialogStub(
                draw_service=SimpleNamespace(),
                work=None,
                parent=None,
                style_host=None,
                translate=lambda _k, default=None, **_kwargs: default or "",
                batch_label="",
                group_edit_mode=False,
                group_count=None,
                drawings_enabled=True,
                machine_profile_key="lathe_1sp_1h",
            )

        build_zeros_mock.assert_called_once()
        build_tools_mock.assert_called_once()

    def test_machining_center_work_editor_shell_primes_zero_points_and_tools_during_construction(self):
        class _DummyProfile:
            zero_axes = ("x", "y", "z")
            heads = ()
            spindles = ()
            spindle_count = 0
            supports_zero_xy_toggle = False
            default_zero_xy_visible = True
            supports_sub_pickup = False

        class _DialogStub(MachiningCenterWorkEditorDialog):
            def _build_general_tab(self):
                pass

            def _build_notes_tab(self):
                pass

            def _load_external_refs(self):
                pass

            def _load_work(self):
                pass

            def _set_secondary_button_theme(self):
                pass

            def _apply_host_visual_style(self):
                pass

            def _install_local_event_filters(self):
                pass

            def _setup_raw_part_combo_popup_guard(self):
                pass

            def _close_transient_combo_popups(self):
                pass

        module = work_editor_dialog_module
        with mock.patch.object(module, "UiPreferencesService") as prefs_mock, mock.patch.object(
            module, "load_profile", return_value=_DummyProfile()
        ), mock.patch.object(module, "resolve_profile_key", side_effect=lambda value: value), mock.patch(
            "machine_profiles.apply_machining_center_overrides",
            side_effect=lambda base_profile, **_kwargs: base_profile,
        ), mock.patch.object(
            MachiningCenterWorkEditorDialog, "_build_zeros_tab"
        ) as build_zeros_mock, mock.patch.object(
            MachiningCenterWorkEditorDialog, "_apply_work_payload_to_zeros_tab"
        ), mock.patch.object(
            MachiningCenterWorkEditorDialog, "_build_tools_tab"
        ) as build_tools_mock, mock.patch.object(
            MachiningCenterWorkEditorDialog, "_apply_work_payload_to_tools_tab"
        ), mock.patch.object(
            MachiningCenterWorkEditorDialog, "_refresh_tool_head_widgets"
        ), mock.patch.object(
            MachiningCenterWorkEditorDialog, "_sync_tool_head_view"
        ):
            prefs_mock.return_value.load.return_value = {}
            _DialogStub(
                draw_service=SimpleNamespace(),
                work=None,
                parent=None,
                style_host=None,
                translate=lambda _k, default=None, **_kwargs: default or "",
                batch_label="",
                group_edit_mode=False,
                group_count=None,
                drawings_enabled=True,
                machine_profile_key="machining_center_3ax",
            )

        build_zeros_mock.assert_called_once()
        build_tools_mock.assert_called_once()

    def test_setup_tabs_parents_pages_to_tab_widget(self):
        class _DialogStub(QWidget):
            def __init__(self):
                super().__init__()
                self._t = lambda _key, default=None, **_kwargs: default or ""

        dialog = _DialogStub()
        setup_tabs(dialog)

        self.assertIs(dialog.tabs.parent(), dialog)
        self.assertGreaterEqual(dialog.tabs.indexOf(dialog.general_tab), 0)
        self.assertGreaterEqual(dialog.tabs.indexOf(dialog.zeros_tab), 0)
        self.assertGreaterEqual(dialog.tabs.indexOf(dialog.tools_tab), 0)
        self.assertGreaterEqual(dialog.tabs.indexOf(dialog.notes_tab), 0)

    def test_resolve_work_editor_parent_returns_top_level_window(self):
        host = _HostWindow()
        page = _PageStub(host)

        self.assertIs(host, resolve_work_editor_parent(page))

    def test_work_editor_factory_returns_lathe_shell_for_lathe_profile(self):
        dialog_cls = resolve_work_editor_dialog_class("lathe_1sp_1h")

        self.assertIs(dialog_cls, LatheWorkEditorDialog)

    def test_work_editor_factory_returns_machining_center_shell_for_mc_profile(self):
        dialog_cls = resolve_work_editor_dialog_class("machining_center_5ax")

        self.assertIs(dialog_cls, MachiningCenterWorkEditorDialog)

    def test_create_work_editor_dialog_uses_family_shell(self):
        dialog = create_work_editor_dialog(
            draw_service=SimpleNamespace(),
            machine_profile_key="machining_center_3ax",
            translate=lambda _k, default=None, **_kwargs: default or "",
        )
        try:
            self.assertIsInstance(dialog, MachiningCenterWorkEditorDialog)
        finally:
            dialog.close()

    def test_create_work_uses_top_level_parent(self):
        host = _HostWindow()
        page = _PageStub(host)
        captured = {}

        class _DialogStub:
            def __init__(self, *_args, **kwargs):
                captured.update(kwargs)

            def exec(self):
                return 0

        with mock.patch.object(crud_actions, "create_work_editor_dialog", _DialogStub), mock.patch.object(
            crud_actions, "prime_work_editor_dialog"
        ), mock.patch.object(crud_actions, "exec_work_editor_dialog", return_value=0):
            crud_actions.create_work(page)

        self.assertIs(host, captured["parent"])
        self.assertIs(host, captured["style_host"])

    def test_edit_work_uses_top_level_parent(self):
        host = _HostWindow()
        page = _PageStub(host)
        captured = {}

        class _DialogStub:
            def __init__(self, *_args, **kwargs):
                captured.update(kwargs)

            def exec(self):
                return 0

        with mock.patch.object(crud_actions, "create_work_editor_dialog", _DialogStub), mock.patch.object(
            crud_actions, "prime_work_editor_dialog"
        ), mock.patch.object(crud_actions, "exec_work_editor_dialog", return_value=0):
            crud_actions.edit_work(page)

        self.assertIs(host, captured["parent"])
        self.assertIs(host, captured["style_host"])

    def test_create_work_reuses_cached_dialog_on_cancel(self):
        host = _HostWindow()
        page = _PageStub(host)
        created = {"count": 0}

        class _DialogStub:
            def __init__(self, *_args, **kwargs):
                created["count"] += 1
                self.work = dict(kwargs.get("work") or {})

            def exec(self):
                return 0

        with mock.patch.object(crud_actions, "create_work_editor_dialog", _DialogStub), mock.patch.object(
            crud_actions, "prime_work_editor_dialog"
        ), mock.patch.object(crud_actions, "exec_work_editor_dialog", return_value=0):
            crud_actions.create_work(page)
            crud_actions.create_work(page)

        self.assertEqual(1, created["count"])

    def test_edit_work_reuses_cached_dialog_for_same_work(self):
        host = _HostWindow()
        page = _PageStub(host)
        created = {"count": 0}

        class _DialogStub:
            def __init__(self, *_args, **kwargs):
                created["count"] += 1
                self.work = dict(kwargs.get("work") or {})

            def exec(self):
                return 0

        with mock.patch.object(crud_actions, "create_work_editor_dialog", _DialogStub), mock.patch.object(
            crud_actions, "prime_work_editor_dialog"
        ), mock.patch.object(crud_actions, "exec_work_editor_dialog", return_value=0):
            crud_actions.edit_work(page)
            crud_actions.edit_work(page)

        self.assertEqual(1, created["count"])

    def test_group_edit_uses_top_level_parent(self):
        host = _HostWindow()
        page = _PageStub(host)
        captured = {}

        class _DialogStub:
            def __init__(self, *_args, **kwargs):
                captured.update(kwargs)

            def get_work_data(self):
                return {}

            def exec(self):
                return 0

        with mock.patch.object(batch_actions, "create_work_editor_dialog", _DialogStub):
            batch_actions.group_edit_works(page, ["W001", "W002"])

        self.assertIs(host, captured["parent"])
        self.assertIs(host, captured["style_host"])

    def test_create_work_prepares_shared_dialog_before_exec(self):
        host = _HostWindow()
        page = _PageStub(host)

        class _DialogStub:
            def __init__(self, *_args, **_kwargs):
                pass

            def exec(self):
                return 0

        with mock.patch.object(crud_actions, "create_work_editor_dialog", _DialogStub), mock.patch.object(
            crud_actions, "prime_work_editor_dialog"
        ) as prime_mock, mock.patch.object(crud_actions, "exec_work_editor_dialog", return_value=0):
            crud_actions.create_work(page)

        prime_mock.assert_called()

    def test_prime_work_editor_dialog_runs_once(self):
        events = []

        class _DialogStub(QDialog):
            def __init__(self):
                super().__init__()
                self._startup_open_primed = False
                self._layout = SimpleNamespace(activate=lambda: events.append("layout.activate"))

            def ensurePolished(self):
                events.append("ensurePolished")

            def layout(self):
                return self._layout

            def _ensure_normal_editor_surface_visible(self):
                events.append("surface")

            def _ensure_normal_editor_content_visible(self):
                events.append("content")

            def _warmup_initial_interaction_surfaces(self):
                events.append("warmup")

            def _close_transient_combo_popups(self):
                events.append("close_popups")

            def updateGeometry(self):
                events.append("updateGeometry")

        dialog = _DialogStub()

        prime_work_editor_dialog(dialog)
        prime_work_editor_dialog(dialog)

        self.assertEqual(1, events.count("ensurePolished"))
        self.assertEqual(1, events.count("layout.activate"))
        self.assertEqual(1, events.count("surface"))
        self.assertEqual(1, events.count("content"))
        self.assertEqual(1, events.count("warmup"))
        self.assertEqual(1, events.count("close_popups"))
        self.assertEqual(1, events.count("updateGeometry"))

    def test_prime_work_editor_dialog_warmup_surfaces_runs_once(self):
        class _DialogStub(QDialog):
            def __init__(self):
                super().__init__()
                self._startup_open_primed = False
                self.warmup_called = 0

            def layout(self):
                return SimpleNamespace(activate=lambda: None)

            def _warmup_initial_interaction_surfaces(self):
                self.warmup_called += 1

            def updateGeometry(self):
                pass

        dialog = _DialogStub()

        prime_work_editor_dialog(dialog)
        prime_work_editor_dialog(dialog)

        self.assertEqual(1, dialog.warmup_called)

    def test_exec_work_editor_dialog_primes_before_exec(self):
        events = []

        class _DialogStub(QDialog):
            def __init__(self):
                super().__init__()
                self._startup_open_primed = False

            def exec(self):
                events.append("exec")
                return 1

        dialog = _DialogStub()

        result = exec_work_editor_dialog(dialog)

        self.assertEqual(1, result)
        self.assertIn("exec", events)

    def test_exec_work_editor_dialog_pauses_and_resumes_preload(self):
        events = []

        class _Host(QWidget):
            def isVisible(self):
                return True

            def isMinimized(self):
                return False

            def hide(self):
                events.append("host.hide")

            def show(self):
                events.append("host.show")

            def raise_(self):
                events.append("host.raise")

            def activateWindow(self):
                events.append("host.activate")

        class _DialogStub(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self._startup_open_primed = False
                self._layout = SimpleNamespace(activate=lambda: events.append("layout.activate"))

            def ensurePolished(self):
                events.append("ensurePolished")

            def layout(self):
                return self._layout

            def _ensure_normal_editor_surface_visible(self):
                events.append("surface")

            def _ensure_normal_editor_content_visible(self):
                events.append("content")

            def _close_transient_combo_popups(self):
                events.append("close_popups")

            def updateGeometry(self):
                events.append("updateGeometry")

            def exec(self):
                events.append("exec")
                return 1

        host = _Host()
        host._tool_library_preload_pause_count = 0
        host._tool_library_preload_completed = False
        host._tool_library_preload_scheduled = False
        dialog = _DialogStub(parent=host)

        result = exec_work_editor_dialog(dialog)

        self.assertEqual(1, result)
        self.assertEqual(0, host._tool_library_preload_pause_count)
        self.assertTrue(host._tool_library_preload_scheduled)
        self.assertNotIn("host.hide", events)
        self.assertNotIn("host.show", events)

    def test_work_editor_show_event_applies_style_without_hidden_reveal(self):
        class _DialogStub(WorkEditorDialog):
            def __init__(self):
                QDialog.__init__(self)
                self._host_visual_style_applied = False
                self.calls = []

            def _apply_host_visual_style(self):
                self.calls.append("style")

        dialog = _DialogStub()

        WorkEditorDialog.showEvent(dialog, QShowEvent())

        self.assertEqual(["style"], dialog.calls)


if __name__ == "__main__":
    unittest.main()
