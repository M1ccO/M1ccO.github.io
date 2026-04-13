"""
State machine for managing dynamic selector/filter UI state (Phase 3 Platform Layer).

This module provides SelectorState, a pure-Python (non-Qt-specific) state container
that manages selection state for dynamic filter/selector UIs (tool head selector,
spindle selector, jaw type selector, etc.). Emits change signals for UI binding.

Design Principles:
  - No domain-specific Qt machinery; pure state machine
  - Signal/Slot for change notification (Qt 6 via PySide6)
  - Validation on set operations
  - State persistence (save/load dict)
  - Observable pattern with immutable options list
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal

__all__ = [
    "SelectorState",
]


class SelectorState(QObject):
    """
    Stateful model for dynamic selector UI state.

    Manages a single selection from a set of options. Validates transitions,
    emits signals on change, and provides state persistence hooks.

    Attributes:
        changed (Signal[str]): Emitted when current selection changes.
                              Passes new value as str argument.
    """

    # ── Signals ──────────────────────────────────────────────────────────
    changed = Signal(str)
    """Emitted when the current selection changes; passes new value as str."""

    def __init__(self, options: list[str] | None = None, default: str | None = None):
        """
        Initialize selector state.

        Args:
            options: List of valid options. Must not be empty.
                     Raises ValueError if empty or None.
            default: Initial selection. If None, uses first option in list.
                     Must be in options list; raises ValueError otherwise.

        Raises:
            ValueError: If options is empty/None or default not in options.

        Example:
            selector = SelectorState(['Main', 'Sub'], default='Main')
            # Default is 'Main'

            selector2 = SelectorState(['HEAD1', 'HEAD2'])
            # Default is 'HEAD1' (first option)
        """
        super().__init__()

        if not options or len(options) == 0:
            raise ValueError("options list cannot be empty")

        self._options = list(options)  # Defensive copy

        # Determine initial value
        if default is None:
            self._current = self._options[0]
        else:
            if default not in self._options:
                raise ValueError(
                    f"default '{default}' not in options {self._options}"
                )
            self._current = default

    def get_current(self) -> str:
        """
        Return the currently selected value.

        Returns:
            str: Current selection.

        Example:
            selector = SelectorState(['A', 'B', 'C'], default='B')
            assert selector.get_current() == 'B'
        """
        return self._current

    def set_current(self, value: str) -> None:
        """
        Update the current selection.

        Only emits changed signal if value differs from current selection.

        Args:
            value: New selection value.

        Raises:
            ValueError: If value not in options.

        Example:
            selector = SelectorState(['A', 'B'])
            selector.set_current('B')  # Emits changed('B')
            selector.set_current('B')  # No signal (no change)
            selector.set_current('X')  # Raises ValueError
        """
        if value not in self._options:
            raise ValueError(
                f"invalid selection '{value}'; not in options {self._options}"
            )

        if value != self._current:
            self._current = value
            self.changed.emit(value)

    def get_options(self) -> list[str]:
        """
        Return the list of available options.

        Returns a defensive copy to prevent external mutation.

        Returns:
            list[str]: Available options (immutable snapshot).

        Example:
            selector = SelectorState(['A', 'B', 'C'])
            options = selector.get_options()
            # options = ['A', 'B', 'C']
        """
        return list(self._options)

    def save(self) -> dict[str, Any]:
        """
        Serialize state to dict for persistence.

        Returns:
            dict: State dict with keys:
                - 'current': Current selection value (str)
                - 'options': List of available options (list[str])

        Example:
            selector = SelectorState(['Main', 'Sub'], default='Sub')
            state = selector.save()
            # state = {'current': 'Sub', 'options': ['Main', 'Sub']}
        """
        return {
            "current": self._current,
            "options": list(self._options),
        }

    def load(self, state_dict: dict[str, Any]) -> None:
        """
        Restore state from dict.

        Updates both options and current selection. Emits changed signal
        if current value differs from previous state.

        Args:
            state_dict: State dict with keys:
                - 'current': Selection value (str)
                - 'options': Available options (list[str])

        Raises:
            ValueError: If state_dict keys missing or current not in options.

        Example:
            state = {'current': 'Sub', 'options': ['Main', 'Sub']}
            selector = SelectorState(['Other'])
            selector.load(state)
            # selector.get_current() == 'Sub'
            # selector.get_options() == ['Main', 'Sub']
        """
        if "current" not in state_dict or "options" not in state_dict:
            raise ValueError(
                "state_dict must contain 'current' and 'options' keys"
            )

        options = state_dict["options"]
        current = state_dict["current"]

        if not options or len(options) == 0:
            raise ValueError("options in state_dict cannot be empty")

        if current not in options:
            raise ValueError(
                f"current '{current}' in state_dict not in options {options}"
            )

        self._options = list(options)

        old_current = self._current
        self._current = current

        if self._current != old_current:
            self.changed.emit(self._current)

    def __repr__(self) -> str:
        """
        Return string representation for debugging.

        Returns:
            str: Representation in form: SelectorState(current='X', options=['X', 'Y', 'Z'])

        Example:
            selector = SelectorState(['A', 'B'], default='A')
            print(repr(selector))
            # SelectorState(current='A', options=['A', 'B'])
        """
        return (
            f"SelectorState(current={self._current!r}, "
            f"options={self._options!r})"
        )

    def __bool__(self) -> bool:
        """
        Return True if selector has valid state.

        Always True for well-formed instances (constructor ensures non-empty options).

        Returns:
            bool: True
        """
        return bool(self._options and self._current in self._options)
