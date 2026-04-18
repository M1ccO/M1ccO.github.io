"""Sanity tests for shared selector payloads and resolver contracts.

Covers the additive foundation introduced per
WORK_EDITOR_SELECTOR_ARCHITECTURE_BLUEPRINT.md workstreams 2 and 3
(resolver contract + payload schema). These tests must pass before any
consumer migrates onto the new contracts.
"""

from __future__ import annotations

import pickle
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from shared.selector.payloads import (
    JawSelectionPayload,
    SelectionBatch,
    SpindleKey,
    ToolBucket,
    ToolSelectionPayload,
)
from shared.ui.resolvers import (
    JawResolver,
    LibraryBackedJawResolver,
    LibraryBackedToolResolver,
    ResolvedJaw,
    ResolvedTool,
    ResolverNotConfiguredError,
    ToolResolver,
    get_resolver,
    set_resolver,
)


class PayloadSchemaTests(unittest.TestCase):
    def test_tool_payload_rejects_bad_bucket(self):
        with self.assertRaises(TypeError):
            ToolSelectionPayload(
                bucket="main",  # type: ignore[arg-type]
                head_key="HEAD1",
                tool_id="T01",
                source_library_rev=1,
            )

    def test_tool_payload_rejects_empty_id(self):
        with self.assertRaises(ValueError):
            ToolSelectionPayload(
                bucket=ToolBucket.MAIN,
                head_key="HEAD1",
                tool_id="",
                source_library_rev=0,
            )

    def test_jaw_payload_rejects_negative_rev(self):
        with self.assertRaises(ValueError):
            JawSelectionPayload(
                spindle=SpindleKey.MAIN,
                jaw_id="J1",
                source_library_rev=-1,
            )

    def test_batch_enforces_tuple(self):
        with self.assertRaises(TypeError):
            SelectionBatch(tools=[], jaws=())  # type: ignore[arg-type]

    def test_batch_default_empty(self):
        batch = SelectionBatch()
        self.assertTrue(batch.is_empty)
        self.assertEqual(batch.tools, ())
        self.assertEqual(batch.jaws, ())

    def test_batch_is_picklable(self):
        batch = SelectionBatch(
            session_id=uuid4(),
            tools=(
                ToolSelectionPayload(
                    bucket=ToolBucket.SUB,
                    head_key="HEAD2",
                    tool_id="T09",
                    source_library_rev=3,
                    selected_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
                ),
            ),
            jaws=(
                JawSelectionPayload(
                    spindle=SpindleKey.MAIN,
                    jaw_id="JSOFT-01",
                    source_library_rev=3,
                    selected_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
                ),
            ),
        )
        restored = pickle.loads(pickle.dumps(batch))
        self.assertEqual(restored, batch)

    def test_payload_is_frozen(self):
        payload = ToolSelectionPayload(
            bucket=ToolBucket.MAIN,
            head_key="HEAD1",
            tool_id="T01",
            source_library_rev=0,
        )
        with self.assertRaises(Exception):
            payload.tool_id = "T99"  # type: ignore[misc]


class ResolvedTypesTests(unittest.TestCase):
    def test_resolved_tool_metadata_is_read_only(self):
        mutable = {"desc": "hi"}
        resolved = ResolvedTool(
            tool_id="T01",
            display_name="T01",
            icon_key="tool/turning",
            pot_number=5,
            metadata=mutable,
            library_rev=1,
        )
        mutable["desc"] = "changed"
        self.assertEqual(resolved.metadata["desc"], "hi")
        with self.assertRaises(TypeError):
            resolved.metadata["desc"] = "nope"  # type: ignore[index]

    def test_resolved_jaw_defaults(self):
        resolved = ResolvedJaw(
            jaw_id="J1",
            display_name="J1",
            icon_key="jaw/soft_jaws",
            spindle=SpindleKey.SUB,
        )
        self.assertEqual(dict(resolved.metadata), {})
        self.assertEqual(resolved.library_rev, 0)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        set_resolver("tool", None)
        set_resolver("jaw", None)

    def tearDown(self):
        set_resolver("tool", None)
        set_resolver("jaw", None)

    def test_get_before_set_raises(self):
        with self.assertRaises(ResolverNotConfiguredError):
            get_resolver("tool")
        with self.assertRaises(ResolverNotConfiguredError):
            get_resolver("jaw")

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            get_resolver("fixture")  # type: ignore[arg-type]

    def test_set_and_get_roundtrip(self):
        tool_res = LibraryBackedToolResolver(_FakeToolService())
        jaw_res = LibraryBackedJawResolver(_FakeJawService())
        set_resolver("tool", tool_res)
        set_resolver("jaw", jaw_res)
        self.assertIs(get_resolver("tool"), tool_res)
        self.assertIs(get_resolver("jaw"), jaw_res)

    def test_protocol_check_rejects_non_resolver(self):
        with self.assertRaises(TypeError):
            set_resolver("tool", object())  # type: ignore[arg-type]


class _FakeToolService:
    def __init__(self, records=None):
        self._records = records or {
            "T01": {"id": "T01", "description": "Turn OD", "tool_type": "Turning", "pot_number": "7"},
            "T02": {"id": "T02", "description": "Drill", "tool_type": "Drilling", "pot_number": None},
        }
        self.calls: list[str] = []

    def get_tool(self, tool_id: str):
        self.calls.append(tool_id)
        return self._records.get(tool_id)


class _FakeJawService:
    def __init__(self, records=None):
        self._records = records or {
            "J1": {"jaw_id": "J1", "jaw_type": "Soft jaws", "spindle_side": "Main spindle"},
        }
        self.calls: list[str] = []

    def get_jaw(self, jaw_id: str):
        self.calls.append(jaw_id)
        return self._records.get(jaw_id)


class LibraryBackedResolverTests(unittest.TestCase):
    def test_tool_resolver_satisfies_protocol(self):
        resolver = LibraryBackedToolResolver(_FakeToolService())
        self.assertIsInstance(resolver, ToolResolver)

    def test_jaw_resolver_satisfies_protocol(self):
        resolver = LibraryBackedJawResolver(_FakeJawService())
        self.assertIsInstance(resolver, JawResolver)

    def test_resolve_tool_returns_none_for_unknown(self):
        resolver = LibraryBackedToolResolver(_FakeToolService())
        self.assertIsNone(resolver.resolve_tool("missing", bucket=ToolBucket.MAIN))

    def test_resolve_tool_populates_fields(self):
        resolver = LibraryBackedToolResolver(_FakeToolService())
        got = resolver.resolve_tool("T01", bucket=ToolBucket.MAIN)
        assert got is not None
        self.assertEqual(got.tool_id, "T01")
        self.assertEqual(got.icon_key, "tool/turning")
        self.assertEqual(got.pot_number, 7)
        self.assertIn("Turn OD", got.display_name)

    def test_cache_hits_avoid_service_calls(self):
        svc = _FakeToolService()
        resolver = LibraryBackedToolResolver(svc)
        resolver.resolve_tool("T01", bucket=ToolBucket.MAIN)
        resolver.resolve_tool("T01", bucket=ToolBucket.MAIN)
        self.assertEqual(svc.calls, ["T01"])

    def test_bump_revision_invalidates_cache(self):
        svc = _FakeToolService()
        resolver = LibraryBackedToolResolver(svc)
        resolver.resolve_tool("T01", bucket=ToolBucket.MAIN)
        resolver.bump_revision()
        resolver.resolve_tool("T01", bucket=ToolBucket.MAIN)
        self.assertEqual(svc.calls, ["T01", "T01"])

    def test_unknown_results_are_not_re_fetched_until_bump(self):
        svc = _FakeToolService()
        resolver = LibraryBackedToolResolver(svc)
        self.assertIsNone(resolver.resolve_tool("ghost", bucket=ToolBucket.MAIN))
        self.assertIsNone(resolver.resolve_tool("ghost", bucket=ToolBucket.MAIN))
        self.assertEqual(svc.calls, ["ghost"])
        resolver.bump_revision()
        resolver.resolve_tool("ghost", bucket=ToolBucket.MAIN)
        self.assertEqual(svc.calls, ["ghost", "ghost"])

    def test_resolve_many_filters_missing(self):
        resolver = LibraryBackedToolResolver(_FakeToolService())
        got = resolver.resolve_many(["T01", "missing", "T02"], bucket=ToolBucket.MAIN)
        self.assertEqual(set(got.keys()), {"T01", "T02"})

    def test_jaw_resolve_populates_spindle(self):
        resolver = LibraryBackedJawResolver(_FakeJawService())
        got = resolver.resolve_jaw("J1", spindle=SpindleKey.MAIN)
        assert got is not None
        self.assertEqual(got.spindle, SpindleKey.MAIN)
        self.assertEqual(got.icon_key, "jaw/soft_jaws")


class TargetedInvalidationTests(unittest.TestCase):
    def test_invalidate_tool_drops_entry_but_keeps_rev(self):
        svc = _FakeToolService()
        resolver = LibraryBackedToolResolver(svc)
        resolver.resolve_tool("T01", bucket=ToolBucket.MAIN)
        rev_before = resolver.library_rev
        dropped = resolver.invalidate_tool("T01")
        self.assertEqual(dropped, 1)
        self.assertEqual(resolver.library_rev, rev_before)
        resolver.resolve_tool("T01", bucket=ToolBucket.MAIN)
        self.assertEqual(svc.calls, ["T01", "T01"])

    def test_invalidate_tool_all_buckets_cleared(self):
        svc = _FakeToolService()
        resolver = LibraryBackedToolResolver(svc)
        resolver.resolve_tool("T01", bucket=ToolBucket.MAIN)
        resolver.resolve_tool("T01", bucket=ToolBucket.SUB)
        dropped = resolver.invalidate_tool("T01")
        self.assertEqual(dropped, 2)

    def test_invalidate_tool_ignores_unknown(self):
        resolver = LibraryBackedToolResolver(_FakeToolService())
        self.assertEqual(resolver.invalidate_tool("nope"), 0)
        self.assertEqual(resolver.invalidate_tool(""), 0)

    def test_invalidate_jaw_drops_entry_but_keeps_rev(self):
        svc = _FakeJawService()
        resolver = LibraryBackedJawResolver(svc)
        resolver.resolve_jaw("J1", spindle=SpindleKey.MAIN)
        rev_before = resolver.library_rev
        dropped = resolver.invalidate_jaw("J1")
        self.assertEqual(dropped, 1)
        self.assertEqual(resolver.library_rev, rev_before)
        resolver.resolve_jaw("J1", spindle=SpindleKey.MAIN)
        self.assertEqual(svc.calls, ["J1", "J1"])

    def test_invalidate_jaw_both_spindles(self):
        svc = _FakeJawService()
        resolver = LibraryBackedJawResolver(svc)
        resolver.resolve_jaw("J1", spindle=SpindleKey.MAIN)
        resolver.resolve_jaw("J1", spindle=SpindleKey.SUB)
        dropped = resolver.invalidate_jaw("J1")
        self.assertEqual(dropped, 2)


if __name__ == "__main__":
    unittest.main()
