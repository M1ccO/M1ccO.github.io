"""Tests for PrintService resolver fallback.

Covers the behavior added per WORK_EDITOR_SELECTOR_ARCHITECTURE_BLUEPRINT.md
(Setup Card migration step): when reference_service is absent or returns
nothing, PrintService falls back to the shared resolver.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_SETUP_MANAGER_DIR = Path(__file__).resolve().parent.parent / "Setup Manager"
# Always push Setup Manager first to win over Library's same-named packages
# (config, services, etc.) when tests are collected together.
_setup_str = str(_SETUP_MANAGER_DIR)
try:
    sys.path.remove(_setup_str)
except ValueError:
    pass
sys.path.insert(0, _setup_str)

# Evict any previously cached ambiguous top-level modules so Setup Manager
# versions are imported fresh.
for _mod in list(sys.modules.keys()):
    if _mod in ("config", "services", "services.print_service") or _mod.startswith("services."):
        sys.modules.pop(_mod, None)

from services.print_service import PrintService  # noqa: E402
from shared.selector.payloads import SpindleKey, ToolBucket  # noqa: E402
from shared.ui.resolvers import (  # noqa: E402
    LibraryBackedJawResolver,
    LibraryBackedToolResolver,
    set_resolver,
)


class _StubToolService:
    def __init__(self, records):
        self._records = records

    def get_tool(self, tool_id):
        return self._records.get(tool_id)


class _StubJawService:
    def __init__(self, records):
        self._records = records

    def get_jaw(self, jaw_id):
        return self._records.get(jaw_id)


class _EmptyReferenceService:
    """Reference service that always returns nothing — forces fallback."""

    def get_full_tool(self, tool_id):
        return None

    def get_full_tool_by_uid(self, uid):
        return None

    def get_tool_ref(self, tool_id):
        return None

    def get_full_jaw(self, jaw_id):
        return None


class PrintServiceResolverFallbackTests(unittest.TestCase):
    def setUp(self):
        self._tool_resolver = LibraryBackedToolResolver(
            _StubToolService(
                {
                    "T42": {
                        "id": "T42",
                        "description": "Resolver-backed tool",
                        "tool_type": "Drilling",
                    },
                }
            )
        )
        self._jaw_resolver = LibraryBackedJawResolver(
            _StubJawService(
                {
                    "J42": {
                        "jaw_id": "J42",
                        "jaw_type": "Hard jaws",
                        "turning_washer": "W01",
                        "last_modified": "2026-04-18",
                    },
                }
            )
        )
        set_resolver("tool", self._tool_resolver)
        set_resolver("jaw", self._jaw_resolver)

    def tearDown(self):
        set_resolver("tool", None)
        set_resolver("jaw", None)

    def test_tool_fallback_used_when_no_reference_service(self):
        svc = PrintService()
        data = svc._tool_data("T42")
        self.assertEqual(data["id"], "T42")
        self.assertEqual(data["description"], "Resolver-backed tool")
        self.assertEqual(data["tool_type"], "Drilling")

    def test_tool_fallback_used_when_reference_service_misses(self):
        svc = PrintService()
        svc.set_reference_service(_EmptyReferenceService())
        data = svc._tool_data("T42")
        self.assertEqual(data["description"], "Resolver-backed tool")

    def test_tool_fallback_returns_placeholder_when_unknown(self):
        svc = PrintService()
        data = svc._tool_data("ghost")
        self.assertEqual(data["id"], "ghost")
        self.assertEqual(data["description"], "")

    def test_jaw_fallback_used_when_reference_service_misses(self):
        svc = PrintService()
        svc.set_reference_service(_EmptyReferenceService())
        details = svc._jaw_details("J42")
        self.assertEqual(details["jaw_type"], "Hard jaws")
        self.assertEqual(details["turning_washer"], "W01")
        self.assertEqual(details["last_modified"], "2026-04-18")

    def test_jaw_fallback_empty_when_resolver_unknown(self):
        svc = PrintService()
        svc.set_reference_service(_EmptyReferenceService())
        self.assertEqual(svc._jaw_details("ghost"), {})

    def test_resolver_is_primary_and_reference_backfills_missing_fields(self):
        class _RealRef:
            def get_full_tool(self, tool_id):
                return {
                    "id": tool_id,
                    "description": "From ref service",
                    "tool_type": "Turning",
                    "radius": "R0.4",
                }

            def get_full_tool_by_uid(self, uid):
                return None

            def get_tool_ref(self, tool_id):
                return None

            def get_full_jaw(self, jaw_id):
                return {"jaw_type": "Soft jaws", "turning_washer": "", "last_modified": ""}

        svc = PrintService()
        svc.set_reference_service(_RealRef())
        data = svc._tool_data("T42")
        self.assertEqual(data["description"], "Resolver-backed tool")
        self.assertEqual(data["tool_type"], "Drilling")
        self.assertEqual(data["radius"], "R0.4")

        jaw = svc._jaw_details("J42")
        self.assertEqual(jaw["jaw_type"], "Hard jaws")

    def test_resolver_not_configured_is_silent(self):
        set_resolver("tool", None)
        set_resolver("jaw", None)
        svc = PrintService()
        data = svc._tool_data("anything")
        self.assertEqual(data["id"], "anything")
        self.assertEqual(svc._jaw_details("anything"), {})

    def test_resolver_bucket_does_not_affect_metadata(self):
        # PrintService uses bucket=MAIN internally; verify resolver still hits.
        resolved = self._tool_resolver.resolve_tool("T42", bucket=ToolBucket.MAIN)
        self.assertIsNotNone(resolved)
        resolved_sub = self._tool_resolver.resolve_tool("T42", bucket=ToolBucket.SUB)
        self.assertIsNotNone(resolved_sub)

    def test_resolver_spindle_does_not_affect_jaw_fallback(self):
        resolved = self._jaw_resolver.resolve_jaw("J42", spindle=SpindleKey.MAIN)
        self.assertIsNotNone(resolved)
        resolved_sub = self._jaw_resolver.resolve_jaw("J42", spindle=SpindleKey.SUB)
        self.assertIsNotNone(resolved_sub)


if __name__ == "__main__":
    unittest.main()
