"""Selector session coordinator.

Implements the LIFECYCLE STATE MACHINE defined in
WORK_EDITOR_SELECTOR_ARCHITECTURE_BLUEPRINT.md.

Single class `SelectorSessionCoordinator` owns the one and only selector
session per Work Editor. Callers drive state transitions via the public
API; the coordinator enforces legality and emits payloads on confirm.

This module is pure logic: no Qt widgets, no library imports. Widget
hosting stays in WorkEditorSelectorHost; this coordinator is the brain
wired behind it. Integration happens in a later workstream.

States
------
IDLE, OPENING, ACTIVE, CLOSING, CANCELLED

Transitions (only these are legal)
----------------------------------
IDLE      -> OPENING     request_open()
OPENING   -> ACTIVE      mark_mount_complete()
OPENING   -> CANCELLED   cancel()         (dismissed before mount done)
ACTIVE    -> CLOSING     confirm()/cancel()
CLOSING   -> IDLE        mark_teardown_complete()
CANCELLED -> IDLE        mark_teardown_complete()

Invariants
----------
* One session at a time. Second request_open while state != IDLE raises
  SelectorSessionBusyError.
* Confirm while state != ACTIVE raises InvalidSelectorTransitionError.
* Cancel from IDLE raises InvalidSelectorTransitionError.
* Shutdown forces any non-IDLE state through CLOSING -> IDLE with no
  payload emission.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
from uuid import UUID, uuid4

from shared.selector.payloads import SelectionBatch


_log = logging.getLogger(__name__)


class SessionState(str, Enum):
    IDLE = "idle"
    OPENING = "opening"
    ACTIVE = "active"
    CLOSING = "closing"
    CANCELLED = "cancelled"


class SelectorSessionError(RuntimeError):
    """Base class for selector-session errors."""


class SelectorSessionBusyError(SelectorSessionError):
    """Raised when a second open is requested while a session is live."""


class InvalidSelectorTransitionError(SelectorSessionError):
    """Raised when a caller attempts a forbidden state transition."""


# Legal transitions, exhaustive. Any pair not in this set is rejected.
_ALLOWED: frozenset[tuple[SessionState, SessionState]] = frozenset(
    {
        (SessionState.IDLE, SessionState.OPENING),
        (SessionState.OPENING, SessionState.ACTIVE),
        (SessionState.OPENING, SessionState.CANCELLED),
        (SessionState.ACTIVE, SessionState.CLOSING),
        (SessionState.CLOSING, SessionState.IDLE),
        (SessionState.CANCELLED, SessionState.IDLE),
    }
)


@dataclass(frozen=True)
class SessionTransition:
    session_id: UUID
    from_state: SessionState
    to_state: SessionState
    caller: str
    timestamp: datetime


_TransitionListener = Callable[[SessionTransition], None]
_BatchListener = Callable[[SelectionBatch], None]


class SelectorSessionCoordinator:
    def __init__(
        self,
        *,
        name: str = "default",
        trace_listener: _TransitionListener | None = None,
    ) -> None:
        self._name = str(name)
        self._state: SessionState = SessionState.IDLE
        self._session_id: UUID | None = None
        self._pending_batch: SelectionBatch | None = None
        self._lock = threading.RLock()
        self._transition_listeners: list[_TransitionListener] = []
        self._batch_listeners: list[_BatchListener] = []
        if trace_listener is not None:
            self.add_transition_listener(trace_listener)

    # -- Public state ---------------------------------------------------

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def session_id(self) -> UUID | None:
        return self._session_id

    @property
    def is_idle(self) -> bool:
        return self._state is SessionState.IDLE

    @property
    def is_busy(self) -> bool:
        return self._state is not SessionState.IDLE

    @property
    def name(self) -> str:
        return self._name

    # -- Listeners ------------------------------------------------------

    def add_transition_listener(self, listener: _TransitionListener) -> None:
        if not callable(listener):
            raise TypeError("transition listener must be callable")
        if listener not in self._transition_listeners:
            self._transition_listeners.append(listener)

    def remove_transition_listener(self, listener: _TransitionListener) -> None:
        try:
            self._transition_listeners.remove(listener)
        except ValueError:
            pass

    def add_batch_listener(self, listener: _BatchListener) -> None:
        if not callable(listener):
            raise TypeError("batch listener must be callable")
        if listener not in self._batch_listeners:
            self._batch_listeners.append(listener)

    def remove_batch_listener(self, listener: _BatchListener) -> None:
        try:
            self._batch_listeners.remove(listener)
        except ValueError:
            pass

    # -- Transitions ----------------------------------------------------

    def request_open(self, *, caller: str = "unknown") -> UUID:
        with self._lock:
            if self._state is not SessionState.IDLE:
                raise SelectorSessionBusyError(
                    f"cannot open: coordinator busy in state {self._state.value}"
                )
            self._session_id = uuid4()
            self._pending_batch = None
            self._transition_to(SessionState.OPENING, caller=caller)
            return self._session_id

    def mark_mount_complete(self, *, caller: str = "mount") -> None:
        with self._lock:
            if self._state is not SessionState.OPENING:
                raise InvalidSelectorTransitionError(
                    f"mark_mount_complete requires OPENING, got {self._state.value}"
                )
            self._transition_to(SessionState.ACTIVE, caller=caller)

    def confirm(self, batch: SelectionBatch, *, caller: str = "ok") -> None:
        if not isinstance(batch, SelectionBatch):
            raise TypeError("confirm requires SelectionBatch")
        with self._lock:
            if self._state is not SessionState.ACTIVE:
                raise InvalidSelectorTransitionError(
                    f"confirm requires ACTIVE, got {self._state.value}"
                )
            if self._session_id is None:
                raise SelectorSessionError("confirm without live session_id (internal)")
            if batch.session_id != self._session_id:
                raise SelectorSessionError(
                    f"batch session_id mismatch: expected {self._session_id}, got {batch.session_id}"
                )
            self._pending_batch = batch
            self._transition_to(SessionState.CLOSING, caller=caller)

    def cancel(self, *, caller: str = "cancel") -> None:
        with self._lock:
            if self._state is SessionState.OPENING:
                self._pending_batch = None
                self._transition_to(SessionState.CANCELLED, caller=caller)
                return
            if self._state is SessionState.ACTIVE:
                self._pending_batch = None
                self._transition_to(SessionState.CLOSING, caller=caller)
                return
            raise InvalidSelectorTransitionError(
                f"cancel requires OPENING or ACTIVE, got {self._state.value}"
            )

    def mark_teardown_complete(self, *, caller: str = "teardown") -> SelectionBatch | None:
        """Finalize CLOSING or CANCELLED back to IDLE.

        Returns the pending batch (and emits it to batch listeners) only
        when transitioning from CLOSING *and* a confirm placed a batch.
        CANCELLED and cancel-from-ACTIVE paths return None.
        """
        with self._lock:
            if self._state not in (SessionState.CLOSING, SessionState.CANCELLED):
                raise InvalidSelectorTransitionError(
                    f"mark_teardown_complete requires CLOSING or CANCELLED, got {self._state.value}"
                )
            emitted = self._pending_batch if self._state is SessionState.CLOSING else None
            self._pending_batch = None
            self._transition_to(SessionState.IDLE, caller=caller)
            self._session_id = None
        if emitted is not None:
            self._emit_batch(emitted)
        return emitted

    def force_shutdown(self, *, caller: str = "shutdown") -> None:
        """Forced IDLE from any state. No payload emission, no raise.

        Intended for Work Editor dispose paths that must guarantee the
        coordinator is IDLE before destruction regardless of user state.
        """
        with self._lock:
            if self._state is SessionState.IDLE:
                return
            self._pending_batch = None
            # Shortcut through a synthetic CLOSING when currently ACTIVE so
            # listeners see a consistent transition log even on forced exit.
            if self._state is SessionState.ACTIVE:
                self._transition_to(SessionState.CLOSING, caller=f"{caller}:forced-closing")
            if self._state is SessionState.OPENING:
                self._transition_to(SessionState.CANCELLED, caller=f"{caller}:forced-cancel")
            # Both CLOSING and CANCELLED have IDLE as their next legal move.
            self._transition_to(SessionState.IDLE, caller=caller)
            self._session_id = None

    # -- Internal -------------------------------------------------------

    def _transition_to(self, target: SessionState, *, caller: str) -> None:
        source = self._state
        if (source, target) not in _ALLOWED:
            raise InvalidSelectorTransitionError(
                f"illegal transition {source.value} -> {target.value}"
            )
        self._state = target
        transition = SessionTransition(
            session_id=self._session_id or uuid4(),
            from_state=source,
            to_state=target,
            caller=str(caller or "unknown"),
            timestamp=datetime.now(timezone.utc),
        )
        for listener in list(self._transition_listeners):
            try:
                listener(transition)
            except Exception:
                _log.debug("transition listener raised", exc_info=True)

    def _emit_batch(self, batch: SelectionBatch) -> None:
        for listener in list(self._batch_listeners):
            try:
                listener(batch)
            except Exception:
                _log.debug("batch listener raised", exc_info=True)


# -- File-based trace listener ----------------------------------------------


def make_file_trace_listener(path: Any) -> _TransitionListener:
    """Returns a transition listener that appends one JSON line per event.

    Used to wire the coordinator to
    `Setup Manager/temp/selector_session_trace.log` per blueprint §
    LIFECYCLE STATE MACHINE > Observability.

    The listener is best-effort: IO failures are swallowed so selector
    behavior is never blocked on disk state.
    """
    import json
    from pathlib import Path

    target = Path(path)

    def _listener(transition: SessionTransition) -> None:
        record = {
            "ts": transition.timestamp.isoformat(),
            "session": str(transition.session_id),
            "from": transition.from_state.value,
            "to": transition.to_state.value,
            "caller": transition.caller,
        }
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            _log.debug("failed to write selector trace", exc_info=True)

    return _listener
