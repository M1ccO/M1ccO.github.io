"""Tests for _resolve_tool_ref_via_resolver fallback in WorkEditorDialog.

Exercises the resolver-backed fallback path that fires when draw_service
cannot supply a tool reference (e.g. service unavailable, tool not in DB).
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_SETUP_MANAGER_DIR = Path(__file__).resolve().parent.parent / "Setup Manager"
if str(_SETUP_MANAGER_DIR) not in sys.path:
    sys.path.insert(0, str(_SETUP_MANAGER_DIR))

# We test the helper method in isolation; no Qt dialog instantiation needed.
# Import the module and extract the logic via a lightweight stub object.
from shared.ui.resolvers import (  # noqa: E402
    LibraryBackedToolResolver,
    ResolverNotConfiguredError,
    set_resolver,
)
from shared.selector.payloads import ToolBucket  # noqa: E402


class _FakeToolService:
    def __init__(self, records=None):
        self._records = records or {
            "T01": {"id": "T01", "description": "Turn OD", "tool_type": "Turning", "pot_number": 7},
        }

    def get_tool(self, tool_id: str):
        return self._records.get(tool_id)


def _make_dialog_stub():
    """Return a minimal object that hosts _resolve_tool_ref_via_resolver."""
    import importlib.util, types as _types
    # Ensure Setup Manager is first in sys.path and ambiguous top-level
    # packages are evicted so the right modules are imported.
    _sm_dir = str(_SETUP_MANAGER_DIR)
    try:
        sys.path.remove(_sm_dir)
    except ValueError:
        pass
    sys.path.insert(0, _sm_dir)
    # Evict cached conflicting modules so Setup Manager versions are picked.
    _AMBIGUOUS = ("ui", "config", "services", "data", "models")
    for _mod in list(sys.modules.keys()):
        if _mod in _AMBIGUOUS or any(_mod.startswith(f"{p}.") for p in _AMBIGUOUS):
            sys.modules.pop(_mod, None)
    import ui.work_editor_dialog as _mod  # noqa: E402  (after path fix)
    stub = _types.SimpleNamespace()
    stub.draw_service = _types.SimpleNamespace(
        get_tool_ref_by_uid=lambda _uid: None,
        get_tool_ref=lambda _tool_id: None,
    )
    stub._resolve_tool_ref_via_resolver = lambda tool_id: (
        _mod.WorkEditorDialog._resolve_tool_ref_via_resolver(stub, tool_id)  # type: ignore[attr-defined]
    )
    stub._resolve_tool_reference_for_assignment = lambda assignment: (
        _mod.WorkEditorDialog._resolve_tool_reference_for_assignment(stub, assignment)  # type: ignore[attr-defined]
    )
    return stub


class ResolverFallbackTests(unittest.TestCase):
    def setUp(self):
        set_resolver("tool", None)
        set_resolver("jaw", None)

    def tearDown(self):
        set_resolver("tool", None)
        set_resolver("jaw", None)

    def _stub(self):
        return _make_dialog_stub()

    def test_returns_none_when_resolver_not_configured(self):
        stub = self._stub()
        result = stub._resolve_tool_ref_via_resolver("T01")
        self.assertIsNone(result)

    def test_returns_none_for_unknown_tool(self):
        resolver = LibraryBackedToolResolver(_FakeToolService({}))
        set_resolver("tool", resolver)
        stub = self._stub()
        result = stub._resolve_tool_ref_via_resolver("ghost")
        self.assertIsNone(result)

    def test_returns_dict_with_id_and_description(self):
        resolver = LibraryBackedToolResolver(_FakeToolService())
        set_resolver("tool", resolver)
        stub = self._stub()
        result = stub._resolve_tool_ref_via_resolver("T01")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "T01")
        self.assertIn("Turn OD", result["description"])

    def test_result_has_pot_number(self):
        resolver = LibraryBackedToolResolver(_FakeToolService())
        set_resolver("tool", resolver)
        stub = self._stub()
        result = stub._resolve_tool_ref_via_resolver("T01")
        self.assertIsNotNone(result)
        self.assertEqual(result["pot_number"], 7)

    def test_returns_none_for_empty_tool_id(self):
        resolver = LibraryBackedToolResolver(_FakeToolService())
        set_resolver("tool", resolver)
        stub = self._stub()
        result = stub._resolve_tool_ref_via_resolver("")
        self.assertIsNone(result)

    def test_exception_in_resolver_returns_none(self):
        broken_resolver = LibraryBackedToolResolver(_FakeToolService())
        broken_resolver.resolve_tool = MagicMock(side_effect=RuntimeError("boom"))
        set_resolver("tool", broken_resolver)
        stub = self._stub()
        result = stub._resolve_tool_ref_via_resolver("T01")
        self.assertIsNone(result)

    def test_assignment_resolution_prefers_resolver_over_draw_service(self):
        resolver = LibraryBackedToolResolver(_FakeToolService())
        set_resolver("tool", resolver)
        stub = self._stub()
        stub.draw_service = types.SimpleNamespace(
            get_tool_ref_by_uid=lambda _uid: {"id": "T01", "description": "Legacy Draw Service", "tool_type": "Turning"},
            get_tool_ref=lambda _tool_id: {"id": "T01", "description": "Legacy Draw Service", "tool_type": "Turning"},
        )
        result = stub._resolve_tool_reference_for_assignment({"tool_id": "T01", "tool_uid": 42})
        self.assertIsNotNone(result)
        self.assertIn("Turn OD", result["description"])


if __name__ == "__main__":
    unittest.main()
