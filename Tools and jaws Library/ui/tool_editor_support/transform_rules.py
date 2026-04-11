"""Transform normalization helpers for Tool Editor preview integration."""

from __future__ import annotations


TRANSFORM_KEYS = ("x", "y", "z", "rx", "ry", "rz")


def normalize_transform_dict(transform: dict | None) -> dict:
    src = transform if isinstance(transform, dict) else {}
    return {key: float(src.get(key, 0) or 0) for key in TRANSFORM_KEYS}


def compact_transform_dict(transform: dict) -> dict:
    compact = {}
    for key in TRANSFORM_KEYS:
        value = float(transform.get(key, 0) or 0)
        if abs(value) > 1e-9:
            compact[key] = value
    return compact


def all_part_transforms_payload(part_transforms: dict[int, dict], row_count: int) -> list[dict]:
    payload = []
    for index in range(max(0, int(row_count))):
        payload.append(normalize_transform_dict(part_transforms.get(index, {})))
    return payload
