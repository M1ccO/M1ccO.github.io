from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
_SETUP_ROOT = _WORKSPACE / "Setup Manager"
for _candidate in (_WORKSPACE, _SETUP_ROOT):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from PySide6.QtCore import Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
from ui.work_editor_support.embedded_selector_host import WorkEditorSelectorHost  # noqa: E402

try:
    sys.path.remove(str(_SETUP_ROOT))
except ValueError:
    pass

_APP = QApplication.instance() or QApplication([])


class _DialogStub:
    def __init__(self):
        self.events = []

    def _log_selector_event(self, event: str, **_fields):
        self.events.append(event)


class _WidgetWithSignals(QWidget):
    submitted = Signal(dict)
    canceled = Signal()

    def __init__(self):
        super().__init__()
        self.show_events = 0
        self.hide_events = 0

    def showEvent(self, event):
        self.show_events += 1
        super().showEvent(event)

    def hideEvent(self, event):
        self.hide_events += 1
        super().hideEvent(event)


class TestSelectorHostPhase6(unittest.TestCase):
    def test_open_and_close_mounts_and_detaches_widget(self):
        dialog = _DialogStub()
        mount = QWidget()

        host = WorkEditorSelectorHost(
            dialog=dialog,
            mount_container=mount,
        )

        widget = _WidgetWithSignals()
        host.open_widget(widget)

        self.assertIs(host.active_widget, widget)
        self.assertIs(widget.parent(), mount)

        host.close_active_widget()
        self.assertIsNone(host.active_widget)
        self.assertIsNone(widget.parent())
        self.assertGreaterEqual(widget.hide_events, 1)

    def test_submit_signal_ignored_by_default(self):
        dialog = _DialogStub()
        mount = QWidget()

        host = WorkEditorSelectorHost(
            dialog=dialog,
            mount_container=mount,
        )

        widget = _WidgetWithSignals()
        host.open_widget(widget)
        widget.submitted.emit({"kind": "tools"})

        self.assertIs(host.active_widget, widget)
        self.assertNotIn("submit.embedded", dialog.events)

    def test_open_widget_can_mount_into_override_container(self):
        dialog = _DialogStub()
        default_mount = QWidget()
        override_mount = QWidget()

        host = WorkEditorSelectorHost(
            dialog=dialog,
            mount_container=default_mount,
        )

        widget = _WidgetWithSignals()
        host.open_widget(widget, mount_container=override_mount)

        self.assertIs(host.active_widget, widget)
        self.assertIs(widget.parent(), override_mount)

    def test_submit_signal_closes_and_logs_when_opted_in(self):
        dialog = _DialogStub()
        mount = QWidget()

        host = WorkEditorSelectorHost(
            dialog=dialog,
            mount_container=mount,
            auto_close_on_widget_signals=True,
        )

        widget = _WidgetWithSignals()
        host.open_widget(widget)
        widget.submitted.emit({"kind": "tools"})

        self.assertIsNone(host.active_widget)
        self.assertIn("submit.embedded", dialog.events)

    def test_cancel_signal_closes_and_logs_when_opted_in(self):
        dialog = _DialogStub()
        mount = QWidget()

        host = WorkEditorSelectorHost(
            dialog=dialog,
            mount_container=mount,
            auto_close_on_widget_signals=True,
        )

        widget = _WidgetWithSignals()
        host.open_widget(widget)
        widget.canceled.emit()

        self.assertIsNone(host.active_widget)
        self.assertIn("cancel.embedded", dialog.events)


if __name__ == "__main__":
    unittest.main()
