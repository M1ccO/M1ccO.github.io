from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
_SETUP_ROOT = _WORKSPACE / "Setup Manager"
_TOOLS_LIBRARY_ROOT = _WORKSPACE / "Tools and jaws Library"
for _candidate in (_SETUP_ROOT, _WORKSPACE, _TOOLS_LIBRARY_ROOT):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from PySide6.QtCore import QEvent, QPoint, Qt, QStringListModel  # noqa: E402
from PySide6.QtGui import QCloseEvent, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QListView, QWidget  # noqa: E402
from tools_and_jaws_library.ui.selectors import fixture_selector_dialog, jaw_selector_dialog, tool_selector_dialog  # noqa: E402
from shared.ui.helpers.dragdrop_helpers import clear_selection_on_blank_click  # noqa: E402


def _load_selector_parity_factory():
    module_path = _SETUP_ROOT / "ui" / "work_editor_support" / "selector_parity_factory.py"
    spec = importlib.util.spec_from_file_location("selector_parity_factory_for_tests", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load selector_parity_factory from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


selector_parity_factory = _load_selector_parity_factory()

_APP = QApplication.instance() or QApplication([])


class _DummyService:
    pass


class _DummyToolProfile:
    zero_axes = ("z",)
    spindles = ()


class _DummyJawProfile:
    pass


class _DummyFixtureService:
    pass


class _ToolDialogUnderTest(tool_selector_dialog.ToolSelectorDialog):
    def _build_filter_row(self, *args, **kwargs):
        pass

    def _build_content(self, *args, **kwargs):
        pass

    def _build_bottom_bar(self, *args, **kwargs):
        pass

    def _load_current_bucket(self):
        pass

    def _refresh_catalog(self):
        pass

    def _rebuild_assignment_list(self):
        pass

    def _update_context_header(self):
        pass

    def _update_assignment_buttons(self):
        pass

    def _prime_detail_panel_cache(self):
        pass


class _JawDialogUnderTest(jaw_selector_dialog.JawSelectorDialog):
    def _load_initial_assignments(self, *_args, **_kwargs):
        pass

    def _build_filter_row(self, *args, **kwargs):
        pass

    def _build_content(self, *args, **kwargs):
        pass

    def _build_bottom_bar(self, *args, **kwargs):
        pass

    def _refresh_catalog(self):
        pass

    def _refresh_slot_ui(self):
        pass

    def _update_context_header(self):
        pass

    def _update_remove_button(self):
        pass

    def _prime_detail_panel_cache(self):
        pass


class _ToolEmbeddedUnderTest(tool_selector_dialog.EmbeddedToolSelectorWidget):
    def _build_filter_row(self, *args, **kwargs):
        pass

    def _build_content(self, *args, **kwargs):
        pass

    def _build_bottom_bar(self, *args, **kwargs):
        pass

    def _load_current_bucket(self):
        pass

    def _refresh_catalog(self):
        pass

    def _rebuild_assignment_list(self):
        pass

    def _update_context_header(self):
        pass

    def _update_assignment_buttons(self):
        pass


class _JawEmbeddedUnderTest(jaw_selector_dialog.EmbeddedJawSelectorWidget):
    def _load_initial_assignments(self, *_args, **_kwargs):
        pass

    def _build_filter_row(self, *args, **kwargs):
        pass

    def _build_content(self, *args, **kwargs):
        pass

    def _build_bottom_bar(self, *args, **kwargs):
        pass

    def _refresh_catalog(self):
        pass

    def _refresh_slot_ui(self):
        pass

    def _update_context_header(self):
        pass

    def _update_remove_button(self):
        pass


class _FixtureDialogUnderTest(fixture_selector_dialog.FixtureSelectorDialog):
    def _build_toolbar(self, *args, **kwargs):
        pass

    def _build_content(self, *args, **kwargs):
        pass

    def _build_bottom_bar(self, *args, **kwargs):
        pass

    def _switch_to_selector_panel(self):
        pass

    def _refresh_catalog(self):
        pass

    def _rebuild_assignment_list(self):
        pass

    def _update_assignment_buttons(self):
        pass


class _SpySelectorWidget(QWidget):
    def __init__(self, **kwargs):
        super().__init__()
        self.kwargs = dict(kwargs)


class _FactoryDialog(QWidget):
    def __init__(self):
        super().__init__()
        self.machine_profile = object()
        self.draw_service = object()
        self._t = lambda _k, default=None, **_kwargs: default or ""


class TestEmbeddedSelectorFactory(unittest.TestCase):
    def test_factory_uses_native_embedded_widgets_for_tool_and_jaw(self):
        dialog = _FactoryDialog()
        with mock.patch.object(selector_parity_factory, "_activate_tool_library_namespace_aliases"), mock.patch.object(
            selector_parity_factory, "_ensure_service_bundle",
            return_value={"tool_service": object(), "jaw_service": object(), "fixture_service": object()},
        ), mock.patch.object(tool_selector_dialog, "EmbeddedToolSelectorWidget", _SpySelectorWidget), mock.patch.object(
            jaw_selector_dialog, "EmbeddedJawSelectorWidget", _SpySelectorWidget
        ), mock.patch.object(fixture_selector_dialog, "FixtureSelectorDialog", _SpySelectorWidget):
            tool_widget = selector_parity_factory.build_embedded_selector_parity_widget(
                dialog,
                kind="tools",
                head="HEAD1",
                spindle="main",
                initial_assignments=[],
                initial_assignment_buckets={},
                on_submit=lambda _payload: None,
                on_cancel=lambda: None,
            )
            jaw_widget = selector_parity_factory.build_embedded_selector_parity_widget(
                dialog,
                kind="jaws",
                spindle="main",
                initial_assignments=[],
                on_submit=lambda _payload: None,
                on_cancel=lambda: None,
            )
            fixture_widget = selector_parity_factory.build_embedded_selector_parity_widget(
                dialog,
                kind="fixtures",
                follow_up={"target_key": "OP10"},
                initial_assignments=[],
                initial_assignment_buckets={},
                on_submit=lambda _payload: None,
                on_cancel=lambda: None,
            )

        self.assertNotIn("embedded_mode", tool_widget.kwargs)
        self.assertNotIn("embedded_mode", jaw_widget.kwargs)
        self.assertEqual(True, fixture_widget.kwargs["embedded_mode"])
        self.assertIs(dialog, tool_widget.kwargs["parent"])
        self.assertIs(dialog, jaw_widget.kwargs["parent"])
        self.assertIs(dialog, fixture_widget.kwargs["parent"])

    def test_factory_can_swap_to_trivial_diagnostic_widget(self):
        dialog = _FactoryDialog()
        with mock.patch.dict(os.environ, {"NTX_WORK_EDITOR_SELECTOR_DIAGNOSTIC_KIND": "trivial"}), mock.patch.object(
            selector_parity_factory, "_activate_tool_library_namespace_aliases"
        ) as alias_mock, mock.patch.object(
            selector_parity_factory, "_ensure_service_bundle"
        ) as bundle_mock:
            widget = selector_parity_factory.build_embedded_selector_parity_widget(
                dialog,
                kind="tools",
                head="HEAD1",
                spindle="main",
                initial_assignments=[],
                initial_assignment_buckets={},
                on_submit=lambda _payload: None,
                on_cancel=lambda: None,
            )

        alias_mock.assert_not_called()
        bundle_mock.assert_not_called()
        self.assertEqual("workEditorDiagnosticSelector", widget.objectName())
        self.assertIs(dialog, widget.parentWidget())
        self.assertFalse(widget.isWindow())

    def test_factory_embedded_selector_is_forced_to_child_widget_flags(self):
        parent = QWidget()
        dialog = _FactoryDialog()
        with mock.patch.object(selector_parity_factory, "_activate_tool_library_namespace_aliases"), mock.patch.object(
            selector_parity_factory, "_ensure_service_bundle",
            return_value={"tool_service": object(), "jaw_service": object(), "fixture_service": object()},
        ), mock.patch.object(
            tool_selector_dialog, "EmbeddedToolSelectorWidget", _ToolEmbeddedUnderTest
        ):
            widget = selector_parity_factory.build_embedded_selector_parity_widget(
                dialog,
                mount_container=parent,
                kind="tools",
                head="HEAD1",
                spindle="main",
                initial_assignments=[],
                initial_assignment_buckets={},
                on_submit=lambda _payload: None,
                on_cancel=lambda: None,
            )

        self.assertIs(widget.parentWidget(), parent)
        self.assertFalse(widget.isWindow())
        self.assertEqual(Qt.Widget, widget.windowType())


class TestEmbeddedSelectorMode(unittest.TestCase):
    def test_tool_selector_embedded_mode_skips_window_geometry(self):
        with mock.patch.object(tool_selector_dialog, "restore_window_geometry") as restore_mock, mock.patch.object(
            tool_selector_dialog, "save_window_geometry"
        ) as save_mock:
            dialog = _ToolDialogUnderTest(
                tool_service=_DummyService(),
                machine_profile=_DummyToolProfile(),
                translate=lambda _k, default=None, **_kwargs: default or "",
                selector_head="HEAD1",
                selector_spindle="main",
                initial_assignments=[],
                initial_assignment_buckets={},
                on_submit=lambda _payload: None,
                on_cancel=lambda: None,
                embedded_mode=True,
            )
            self.assertFalse(dialog.testAttribute(Qt.WA_DeleteOnClose))
            dialog.closeEvent(QCloseEvent())

        restore_mock.assert_not_called()
        save_mock.assert_not_called()


class TestDragDropHelpers(unittest.TestCase):
    def test_clear_selection_on_blank_click_supports_qlistview(self):
        view = QListView()
        model = QStringListModel(["A", "B"])
        view.setModel(model)
        view.resize(240, 240)
        view.show()
        _APP.processEvents()

        first_index = model.index(0, 0)
        view.setCurrentIndex(first_index)
        view.selectionModel().select(first_index, view.selectionModel().SelectionFlag.Select)
        self.assertTrue(view.currentIndex().isValid())

        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPoint(200, 200),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        clear_selection_on_blank_click(view, event)

        self.assertFalse(view.currentIndex().isValid())
        self.assertEqual([], view.selectionModel().selectedIndexes())

    def test_jaw_selector_embedded_mode_skips_window_geometry(self):
        with mock.patch.object(jaw_selector_dialog, "restore_window_geometry") as restore_mock, mock.patch.object(
            jaw_selector_dialog, "save_window_geometry"
        ) as save_mock:
            dialog = _JawDialogUnderTest(
                jaw_service=_DummyService(),
                machine_profile=_DummyJawProfile(),
                translate=lambda _k, default=None, **_kwargs: default or "",
                selector_spindle="main",
                initial_assignments=[],
                on_submit=lambda _payload: None,
                on_cancel=lambda: None,
                embedded_mode=True,
            )
            self.assertFalse(dialog.testAttribute(Qt.WA_DeleteOnClose))
            dialog.closeEvent(QCloseEvent())

        restore_mock.assert_not_called()
        save_mock.assert_not_called()

    def test_fixture_selector_embedded_mode_skips_window_geometry(self):
        with mock.patch.object(fixture_selector_dialog, "restore_window_geometry") as restore_mock, mock.patch.object(
            fixture_selector_dialog, "save_window_geometry"
        ) as save_mock:
            dialog = _FixtureDialogUnderTest(
                fixture_service=_DummyFixtureService(),
                translate=lambda _k, default=None, **_kwargs: default or "",
                initial_assignments=[],
                initial_assignment_buckets={},
                initial_target_key="",
                on_submit=lambda _payload: None,
                on_cancel=lambda: None,
                embedded_mode=True,
            )
            self.assertFalse(dialog.testAttribute(Qt.WA_DeleteOnClose))
            dialog.closeEvent(QCloseEvent())

        restore_mock.assert_not_called()
        save_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
