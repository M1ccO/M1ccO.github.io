"""Tests for SelectorSessionCoordinator state machine.

Mirrors the legal/forbidden transitions specified in
WORK_EDITOR_SELECTOR_ARCHITECTURE_BLUEPRINT.md (LIFECYCLE STATE MACHINE).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_SETUP_MANAGER_DIR = Path(__file__).resolve().parent.parent / "Setup Manager"
if str(_SETUP_MANAGER_DIR) not in sys.path:
    sys.path.insert(0, str(_SETUP_MANAGER_DIR))

from services.selector_session import (  # noqa: E402
    InvalidSelectorTransitionError,
    SelectorSessionBusyError,
    SelectorSessionCoordinator,
    SessionState,
    make_file_trace_listener,
)
from shared.selector.payloads import (  # noqa: E402
    JawSelectionPayload,
    SelectionBatch,
    SpindleKey,
    ToolBucket,
    ToolSelectionPayload,
)


def _make_batch(session_id, *, with_tool=True):
    tools = ()
    if with_tool:
        tools = (
            ToolSelectionPayload(
                bucket=ToolBucket.MAIN,
                head_key="HEAD1",
                tool_id="T01",
                source_library_rev=0,
            ),
        )
    return SelectionBatch(session_id=session_id, tools=tools)


class StateMachineHappyPathTests(unittest.TestCase):
    def test_starts_idle(self):
        c = SelectorSessionCoordinator()
        self.assertEqual(c.state, SessionState.IDLE)
        self.assertIsNone(c.session_id)

    def test_open_mount_confirm_teardown(self):
        c = SelectorSessionCoordinator()
        sid = c.request_open(caller="test")
        self.assertEqual(c.state, SessionState.OPENING)
        self.assertEqual(c.session_id, sid)

        c.mark_mount_complete()
        self.assertEqual(c.state, SessionState.ACTIVE)

        batch = _make_batch(sid)
        c.confirm(batch)
        self.assertEqual(c.state, SessionState.CLOSING)

        emitted = c.mark_teardown_complete()
        self.assertEqual(c.state, SessionState.IDLE)
        self.assertIs(emitted, batch)
        self.assertIsNone(c.session_id)

    def test_cancel_from_opening_goes_cancelled(self):
        c = SelectorSessionCoordinator()
        c.request_open()
        c.cancel()
        self.assertEqual(c.state, SessionState.CANCELLED)
        emitted = c.mark_teardown_complete()
        self.assertIsNone(emitted)
        self.assertEqual(c.state, SessionState.IDLE)

    def test_cancel_from_active_goes_closing_no_batch(self):
        c = SelectorSessionCoordinator()
        c.request_open()
        c.mark_mount_complete()
        c.cancel()
        self.assertEqual(c.state, SessionState.CLOSING)
        emitted = c.mark_teardown_complete()
        self.assertIsNone(emitted)


class IllegalTransitionTests(unittest.TestCase):
    def test_second_open_raises_busy(self):
        c = SelectorSessionCoordinator()
        c.request_open()
        with self.assertRaises(SelectorSessionBusyError):
            c.request_open()

    def test_mark_mount_from_idle_illegal(self):
        c = SelectorSessionCoordinator()
        with self.assertRaises(InvalidSelectorTransitionError):
            c.mark_mount_complete()

    def test_mark_mount_from_active_illegal(self):
        c = SelectorSessionCoordinator()
        c.request_open()
        c.mark_mount_complete()
        with self.assertRaises(InvalidSelectorTransitionError):
            c.mark_mount_complete()

    def test_confirm_requires_active(self):
        c = SelectorSessionCoordinator()
        with self.assertRaises(InvalidSelectorTransitionError):
            c.confirm(SelectionBatch())

        c.request_open()
        with self.assertRaises(InvalidSelectorTransitionError):
            c.confirm(_make_batch(c.session_id))  # in OPENING

    def test_cancel_from_idle_illegal(self):
        c = SelectorSessionCoordinator()
        with self.assertRaises(InvalidSelectorTransitionError):
            c.cancel()

    def test_cancel_from_closing_illegal(self):
        c = SelectorSessionCoordinator()
        c.request_open()
        c.mark_mount_complete()
        c.confirm(_make_batch(c.session_id))
        with self.assertRaises(InvalidSelectorTransitionError):
            c.cancel()

    def test_teardown_from_idle_illegal(self):
        c = SelectorSessionCoordinator()
        with self.assertRaises(InvalidSelectorTransitionError):
            c.mark_teardown_complete()

    def test_teardown_from_active_illegal(self):
        c = SelectorSessionCoordinator()
        c.request_open()
        c.mark_mount_complete()
        with self.assertRaises(InvalidSelectorTransitionError):
            c.mark_teardown_complete()

    def test_confirm_type_check(self):
        c = SelectorSessionCoordinator()
        c.request_open()
        c.mark_mount_complete()
        with self.assertRaises(TypeError):
            c.confirm({"tools": []})  # type: ignore[arg-type]

    def test_confirm_with_wrong_session_id_raises(self):
        c = SelectorSessionCoordinator()
        c.request_open()
        c.mark_mount_complete()
        from uuid import uuid4
        foreign = SelectionBatch(session_id=uuid4())
        with self.assertRaises(Exception):
            c.confirm(foreign)


class ForceShutdownTests(unittest.TestCase):
    def test_force_shutdown_from_idle_is_noop(self):
        c = SelectorSessionCoordinator()
        c.force_shutdown()
        self.assertEqual(c.state, SessionState.IDLE)

    def test_force_shutdown_from_opening(self):
        c = SelectorSessionCoordinator()
        c.request_open()
        c.force_shutdown()
        self.assertEqual(c.state, SessionState.IDLE)
        self.assertIsNone(c.session_id)

    def test_force_shutdown_from_active_does_not_emit_batch(self):
        c = SelectorSessionCoordinator()
        received: list[SelectionBatch] = []
        c.add_batch_listener(received.append)
        c.request_open()
        c.mark_mount_complete()
        c.force_shutdown()
        self.assertEqual(c.state, SessionState.IDLE)
        self.assertEqual(received, [])

    def test_force_shutdown_from_closing(self):
        c = SelectorSessionCoordinator()
        c.request_open()
        c.mark_mount_complete()
        c.confirm(_make_batch(c.session_id))
        received: list[SelectionBatch] = []
        c.add_batch_listener(received.append)
        c.force_shutdown()
        self.assertEqual(c.state, SessionState.IDLE)
        self.assertEqual(received, [])  # batch dropped

    def test_can_open_again_after_force_shutdown(self):
        c = SelectorSessionCoordinator()
        c.request_open()
        c.force_shutdown()
        sid2 = c.request_open()
        self.assertEqual(c.state, SessionState.OPENING)
        self.assertIsNotNone(sid2)


class ListenerTests(unittest.TestCase):
    def test_transition_listener_sees_every_step(self):
        c = SelectorSessionCoordinator()
        seen: list[tuple[str, str, str]] = []
        c.add_transition_listener(
            lambda t: seen.append((t.from_state.value, t.to_state.value, t.caller))
        )
        c.request_open(caller="ui")
        c.mark_mount_complete(caller="mount")
        c.confirm(_make_batch(c.session_id), caller="ok")
        c.mark_teardown_complete(caller="cleanup")
        self.assertEqual(
            seen,
            [
                ("idle", "opening", "ui"),
                ("opening", "active", "mount"),
                ("active", "closing", "ok"),
                ("closing", "idle", "cleanup"),
            ],
        )

    def test_batch_listener_receives_confirmed_batch(self):
        c = SelectorSessionCoordinator()
        received: list[SelectionBatch] = []
        c.add_batch_listener(received.append)
        c.request_open()
        c.mark_mount_complete()
        batch = _make_batch(c.session_id)
        c.confirm(batch)
        c.mark_teardown_complete()
        self.assertEqual(received, [batch])

    def test_batch_listener_not_called_on_cancel(self):
        c = SelectorSessionCoordinator()
        received: list[SelectionBatch] = []
        c.add_batch_listener(received.append)
        c.request_open()
        c.mark_mount_complete()
        c.cancel()
        c.mark_teardown_complete()
        self.assertEqual(received, [])

    def test_remove_listener(self):
        c = SelectorSessionCoordinator()
        seen = []
        listener = lambda t: seen.append(t.to_state)
        c.add_transition_listener(listener)
        c.remove_transition_listener(listener)
        c.request_open()
        self.assertEqual(seen, [])

    def test_listener_exception_isolated(self):
        def boom(_t): raise RuntimeError("fail")
        c = SelectorSessionCoordinator()
        c.add_transition_listener(boom)
        c.request_open()  # must not raise

    def test_listener_non_callable_rejected(self):
        c = SelectorSessionCoordinator()
        with self.assertRaises(TypeError):
            c.add_transition_listener("nope")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            c.add_batch_listener("nope")  # type: ignore[arg-type]


class FileTraceListenerTests(unittest.TestCase):
    def test_trace_listener_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "trace.log"
            c = SelectorSessionCoordinator(trace_listener=make_file_trace_listener(log_path))
            c.request_open(caller="ui")
            c.mark_mount_complete(caller="mount")
            c.cancel(caller="esc")
            c.mark_teardown_complete(caller="cleanup")

            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 4)
            events = [json.loads(line) for line in lines]
            self.assertEqual(
                [(e["from"], e["to"]) for e in events],
                [
                    ("idle", "opening"),
                    ("opening", "active"),
                    ("active", "closing"),
                    ("closing", "idle"),
                ],
            )
            self.assertEqual(events[2]["caller"], "esc")

    def test_trace_listener_survives_unwritable_path(self):
        listener = make_file_trace_listener("/definitely/does/not/exist/nope/trace.log")
        c = SelectorSessionCoordinator(trace_listener=listener)
        c.request_open()  # must not raise even though file path invalid


class PayloadIntegrationTests(unittest.TestCase):
    def test_batch_carrying_both_tools_and_jaws_roundtrips(self):
        c = SelectorSessionCoordinator()
        c.request_open()
        c.mark_mount_complete()
        batch = SelectionBatch(
            session_id=c.session_id,
            tools=(
                ToolSelectionPayload(
                    bucket=ToolBucket.SUB, head_key="HEAD2", tool_id="T09", source_library_rev=2
                ),
            ),
            jaws=(
                JawSelectionPayload(spindle=SpindleKey.MAIN, jaw_id="J1", source_library_rev=2),
            ),
        )
        got: list[SelectionBatch] = []
        c.add_batch_listener(got.append)
        c.confirm(batch)
        emitted = c.mark_teardown_complete()
        self.assertIs(emitted, batch)
        self.assertEqual(got, [batch])


if __name__ == "__main__":
    unittest.main()
