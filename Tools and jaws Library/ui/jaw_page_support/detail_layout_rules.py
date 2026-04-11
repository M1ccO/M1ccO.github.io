"""Rule helpers for JawPage detail-grid row composition."""

from __future__ import annotations

from typing import Callable


def apply_jaw_detail_grid_rules(
    *,
    jaw: dict,
    translate: Callable[..., str],
    localized_spindle_side: str,
    add_field: Callable[[int, int, int, int, str, str], None],
) -> int:
    """Populate base jaw detail rows and return the next free row index."""
    # Row 0: Jaw ID | Spindle side
    add_field(0, 0, 1, 2, translate('jaw_library.field.jaw_id', 'Jaw ID'), jaw.get('jaw_id', ''))
    add_field(
        0,
        2,
        1,
        2,
        translate('jaw_library.field.spindle_side', 'Spindle side'),
        localized_spindle_side,
    )

    # Row 1: Clamping diameter | Clamping length
    add_field(
        1,
        0,
        1,
        2,
        translate('jaw_library.field.clamping_diameter', 'Clamping diameter'),
        jaw.get('clamping_diameter_text', ''),
    )
    add_field(
        1,
        2,
        1,
        2,
        translate('jaw_library.field.clamping_length', 'Clamping length'),
        jaw.get('clamping_length', ''),
    )

    # Row 2 changes for spiked jaws.
    is_spiked = 'spiked' in (jaw.get('jaw_type') or '').lower()
    if is_spiked:
        add_field(
            2,
            0,
            1,
            4,
            translate('jaw_library.field.turning_ring', 'Turning ring'),
            jaw.get('turning_washer', ''),
        )
    else:
        add_field(
            2,
            0,
            1,
            2,
            translate('jaw_library.field.turning_ring', 'Turning ring'),
            jaw.get('turning_washer', ''),
        )
        add_field(
            2,
            2,
            1,
            2,
            translate('jaw_library.field.last_modified', 'Last modified'),
            jaw.get('last_modified', ''),
        )
    return 3

