"""Minimal Fixtures domain service used as a Phase 9 onboarding example.

This service is intentionally in-memory to prove domain wiring without adding
new database schema in the same phase.
"""

from __future__ import annotations

from copy import deepcopy

__all__ = ['FixtureService']


class FixtureService:
    """CRUD-like service contract for the Fixtures example domain."""

    def __init__(self, seed_items: list[dict] | None = None) -> None:
        base = seed_items if seed_items is not None else _default_seed_items()
        self._items: list[dict] = []
        self._next_uid = 1
        for item in base:
            self.save_fixture(item)

    def list_fixtures(
        self,
        search_text: str = '',
        category: str = 'All',
        include_archived: bool = False,
    ) -> list[dict]:
        token = str(search_text or '').strip().lower()
        selected_category = str(category or 'All').strip().lower()

        filtered: list[dict] = []
        for item in self._items:
            if not include_archived and not bool(item.get('is_active', True)):
                continue
            if selected_category not in {'', 'all'}:
                if str(item.get('category', '')).strip().lower() != selected_category:
                    continue
            if token:
                haystack = ' '.join(
                    [
                        str(item.get('id', '')),
                        str(item.get('name', '')),
                        str(item.get('category', '')),
                        str(item.get('mount_type', '')),
                        str(item.get('notes', '')),
                    ]
                ).lower()
                if token not in haystack:
                    continue
            filtered.append(deepcopy(item))

        filtered.sort(key=lambda row: str(row.get('id', '')))
        return filtered

    def list_items(self, search_text: str = '', **filters) -> list[dict]:
        """Alias used by shared platform APIs and generic callers."""
        return self.list_fixtures(
            search_text=search_text,
            category=str(filters.get('category', 'All')),
            include_archived=bool(filters.get('include_archived', False)),
        )

    def get_fixture(self, fixture_id: str) -> dict | None:
        target = str(fixture_id or '').strip()
        for item in self._items:
            if str(item.get('id', '')) == target:
                return deepcopy(item)
        return None

    def save_fixture(self, fixture: dict) -> dict:
        normalized = _normalize_fixture_payload(fixture, fallback_uid=self._next_uid)
        existing_index = self._index_by_id(normalized['id'])
        if existing_index >= 0:
            self._items[existing_index] = normalized
            return deepcopy(normalized)

        self._items.append(normalized)
        self._next_uid = max(self._next_uid, int(normalized['uid']) + 1)
        return deepcopy(normalized)

    def delete_item(self, fixture_id: str) -> None:
        """Delete method name aligned with CatalogPageBase batch delete path."""
        idx = self._index_by_id(fixture_id)
        if idx >= 0:
            self._items.pop(idx)

    def _index_by_id(self, fixture_id: str) -> int:
        target = str(fixture_id or '').strip()
        for idx, row in enumerate(self._items):
            if str(row.get('id', '')) == target:
                return idx
        return -1


def _normalize_fixture_payload(payload: dict, fallback_uid: int) -> dict:
    fixture_id = str(payload.get('id', '')).strip()
    if not fixture_id:
        raise ValueError('Fixture id is required.')

    try:
        uid = int(payload.get('uid', fallback_uid) or fallback_uid)
    except Exception:
        uid = int(fallback_uid)

    category = str(payload.get('category', 'General') or 'General').strip() or 'General'
    mount_type = str(payload.get('mount_type', 'Bolt-on') or 'Bolt-on').strip() or 'Bolt-on'
    is_active = bool(payload.get('is_active', True))

    return {
        'id': fixture_id,
        'uid': uid,
        'name': str(payload.get('name', fixture_id) or fixture_id).strip() or fixture_id,
        'category': category,
        'mount_type': mount_type,
        'notes': str(payload.get('notes', '') or '').strip(),
        'is_active': is_active,
    }


def _default_seed_items() -> list[dict]:
    return [
        {
            'id': 'FIX-1001',
            'uid': 1,
            'name': 'Hydraulic Chuck Plate',
            'category': 'Chuck',
            'mount_type': 'Bolt-on',
            'notes': 'Baseline fixture for chuck setup validation.',
            'is_active': True,
        },
        {
            'id': 'FIX-1002',
            'uid': 2,
            'name': 'Robot Pallet Locator',
            'category': 'Robot',
            'mount_type': 'Quick-lock',
            'notes': 'Used for palletized robot loading cells.',
            'is_active': True,
        },
        {
            'id': 'FIX-1999',
            'uid': 3,
            'name': 'Legacy Turning Clamp',
            'category': 'Legacy',
            'mount_type': 'Bolt-on',
            'notes': 'Archived sample to test include_archived filtering.',
            'is_active': False,
        },
    ]