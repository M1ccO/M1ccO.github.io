"""Fixtures export contract example for Phase 9 onboarding template."""

from __future__ import annotations

from typing import Any, Callable

from shared.ui.platforms.export_specification import ExportSpecification

__all__ = ['create_fixtures_export_spec']


def create_fixtures_export_spec(
    fixture_service: Any,
    translator: Callable[[str, str], str] | None = None,
) -> ExportSpecification:
    """Build an ExportSpecification for the Fixtures domain."""

    def _coerce_bool(value: Any) -> bool:
        text = str(value or '').strip().lower()
        if text in {'0', 'false', 'no', 'off', ''}:
            return False
        return True

    return ExportSpecification(
        domain_name='fixtures',
        item_service=fixture_service,
        fields=[
            ('id', 'Fixture ID'),
            ('name', 'Name'),
            ('category', 'Category'),
            ('mount_type', 'Mount Type'),
            ('is_active', 'Active'),
            ('notes', 'Notes'),
        ],
        grouping_strategy='none',
        defaults={
            'category': 'General',
            'mount_type': 'Bolt-on',
            'is_active': True,
            'notes': '',
        },
        coercers={
            'is_active': _coerce_bool,
        },
        translator=translator,
    )