from __future__ import annotations

from machine_profiles import MachineProfile, is_machining_center, load_profile


LATHE_FAMILY = "lathe"
MACHINING_CENTER_FAMILY = "machining_center"


def resolve_machine_profile(profile_key: str | None) -> MachineProfile:
    """Return the normalized machine profile for a profile key."""
    return load_profile(profile_key)


def resolve_machine_family(*, profile: MachineProfile | None = None, profile_key: str | None = None) -> str:
    """Resolve a machine family identifier from a profile or profile key."""
    current_profile = profile if profile is not None else resolve_machine_profile(profile_key)
    return MACHINING_CENTER_FAMILY if is_machining_center(current_profile) else LATHE_FAMILY


def is_machining_center_family(*, profile: MachineProfile | None = None, profile_key: str | None = None) -> bool:
    return resolve_machine_family(profile=profile, profile_key=profile_key) == MACHINING_CENTER_FAMILY


def secondary_library_module(*, profile: MachineProfile | None = None, profile_key: str | None = None) -> str:
    """Return the secondary master-data module for the current machine family."""
    return "fixtures" if is_machining_center_family(profile=profile, profile_key=profile_key) else "jaws"


def secondary_library_label(*, profile: MachineProfile | None = None, profile_key: str | None = None) -> str:
    """Return the translated-independent secondary library label."""
    return "Fixtures" if is_machining_center_family(profile=profile, profile_key=profile_key) else "Jaws"
