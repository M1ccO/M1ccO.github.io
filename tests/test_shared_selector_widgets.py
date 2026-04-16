from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
for _candidate in (_WORKSPACE,):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtWidgets import QPushButton
from shared.ui.selectors import FixtureSelectorWidget, JawSelectorWidget, ToolSelectorWidget  # noqa: E402

_APP = QApplication.instance() or QApplication([])


def _t(_key: str, default: str | None = None, **kwargs) -> str:
    text = default or ""
    for key, value in kwargs.items():
        text = text.replace("{" + key + "}", str(value))
    return text


class TestSharedSelectorWidgetPayloads(unittest.TestCase):
    def test_tool_widget_payload_contract(self):
        widget = ToolSelectorWidget(
            translate=_t,
            selector_head="HEAD1",
            selector_spindle="main",
            initial_assignments=[{"tool_id": "T1"}],
            assignment_buckets_by_target={"HEAD1:main": [{"tool_id": "T1"}]},
        )
        payload = widget._build_submit_payload()
        self.assertEqual(
            {
                "kind",
                "selected_items",
                "selector_head",
                "selector_spindle",
                "assignment_buckets_by_target",
            },
            set(payload.keys()),
        )
        self.assertEqual("tools", payload["kind"])
        self.assertEqual("HEAD1", payload["selector_head"])
        self.assertEqual("main", payload["selector_spindle"])
        self.assertEqual([{"tool_id": "T1"}], payload["selected_items"])
        self.assertIn("HEAD1:main", payload["assignment_buckets_by_target"])

    def test_jaw_widget_payload_contract(self):
        widget = JawSelectorWidget(
            translate=_t,
            selector_spindle="sub",
            initial_assignments=[{"jaw_id": "J1", "spindle": "sub"}],
        )
        payload = widget._build_submit_payload()
        self.assertEqual({"kind", "selected_items"}, set(payload.keys()))
        self.assertEqual("jaws", payload["kind"])
        self.assertEqual([{"jaw_id": "J1", "spindle": "sub"}], payload["selected_items"])

    def test_fixture_widget_payload_contract(self):
        widget = FixtureSelectorWidget(
            translate=_t,
            target_key="OP20",
            initial_assignments=[{"fixture_id": "F2"}],
            assignment_buckets_by_target={"OP20": [{"fixture_id": "F2"}]},
        )
        payload = widget._build_submit_payload()
        self.assertEqual(
            {"kind", "selected_items", "target_key", "assignment_buckets_by_target"},
            set(payload.keys()),
        )
        self.assertEqual("fixtures", payload["kind"])
        self.assertEqual("OP20", payload["target_key"])
        self.assertEqual([{"fixture_id": "F2"}], payload["selected_items"])
        self.assertIn("OP20", payload["assignment_buckets_by_target"])

    def test_action_buttons_keep_style_hooks(self):
        widget = ToolSelectorWidget(
            translate=_t,
            selector_head="HEAD1",
            selector_spindle="main",
            initial_assignments=[{"tool_id": "T1"}],
            assignment_buckets_by_target={"HEAD1:main": [{"tool_id": "T1"}]},
        )
        buttons = widget.findChildren(QPushButton)
        done_btn = next((btn for btn in buttons if btn.text().lower() == "done"), None)
        cancel_btn = next((btn for btn in buttons if btn.text().lower() == "cancel"), None)

        self.assertIsNotNone(done_btn)
        self.assertIsNotNone(cancel_btn)
        self.assertTrue(bool(done_btn.property("panelActionButton")))
        self.assertTrue(bool(done_btn.property("primaryAction")))
        self.assertTrue(bool(cancel_btn.property("panelActionButton")))
        self.assertTrue(bool(cancel_btn.property("secondaryAction")))


if __name__ == "__main__":
    unittest.main()
