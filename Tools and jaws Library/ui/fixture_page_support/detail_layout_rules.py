"""Rule helpers for FixturePage detail-grid row composition."""

from __future__ import annotations

from typing import Callable


def apply_jaw_detail_grid_rules(
    *,
    fixture: dict,
    translate: Callable[..., str],
    localized_spindle_side: str,
    add_field: Callable[[int, int, int, int, str, str], None],
) -> int:
    """Populate base fixture detail rows and return the next free row index."""
    # Row 0: Fixture ID | Spindle side
    add_field(0, 0, 1, 2, translate('jaw_library.field.fixture_id', 'Fixture ID'), fixture.get('fixture_id', ''))
    add_field(
        0,
        2,
        1,
        2,
        translate('fixture_library.field.fixture_kind', 'Fixture kind'),
        localized_spindle_side,
    )

    # Row 1: Clamping diameter | Clamping length
    add_field(
        1,
        0,
        1,
        2,
        translate('jaw_library.field.clamping_diameter', 'Clamping diameter'),
        fixture.get('clamping_diameter_text', ''),
    )
    add_field(
        1,
        2,
        1,
        2,
        translate('jaw_library.field.clamping_length', 'Clamping length'),
        fixture.get('clamping_length', ''),
    )

    # Row 2 changes for spiked fixtures.
    is_spiked = 'spiked' in (fixture.get('fixture_type') or '').lower()
    if is_spiked:
        add_field(
            2,
            0,
            1,
            4,
            translate('jaw_library.field.turning_ring', 'Turning ring'),
            fixture.get('turning_washer', ''),
        )
    else:
        add_field(
            2,
            0,
            1,
            2,
            translate('jaw_library.field.turning_ring', 'Turning ring'),
            fixture.get('turning_washer', ''),
        )
        add_field(
            2,
            2,
            1,
            2,
            translate('jaw_library.field.last_modified', 'Last modified'),
            fixture.get('last_modified', ''),
        )
    return 3

