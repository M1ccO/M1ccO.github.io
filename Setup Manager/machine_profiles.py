from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Head profile — describes a single cutting head on the machine
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MachineHeadProfile:
    key: str
    label_key: str
    label_default: str
    default_coord: str

    # Head capability flags
    # head_type: "turret" = traditional turret/VDI carrier
    #            "milling" = powered milling head (e.g. HMC-style)
    head_type: str = "turret"

    # Whether drill / endmill / rotating-tool types are permitted on this head.
    # Turret heads may or may not allow powered tooling; milling heads always
    # do (field is ignored for milling — rotating tools are always allowed).
    allows_rotating_tools: bool = False

    # Whether the b_axis_angle field is meaningful for tools on this head.
    # When False, the Tool Editor and detail panel must hide b_axis input/display.
    allows_b_axis: bool = False

    # Whether a tool on this head can target both spindles (orientation-aware).
    # Relevant for turret heads on dual-spindle machines.  Single-spindle
    # profiles should set this to False because orientation is meaningless.
    allows_dual_spindle_orientation: bool = True

    # Machining center flag — true when this head represents the single
    # milling spindle of a machining center rather than a lathe head.
    is_machining_center_head: bool = False


# ---------------------------------------------------------------------------
# Spindle profile — describes one spindle / operation context
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MachineSpindleProfile:
    key: str
    label_key: str
    label_default: str
    short_label: str
    jaw_title_key: str
    jaw_title_default: str
    jaw_filter_placeholder_key: str
    jaw_filter_placeholder_default: str
    jaw_filter: str | None = None


# ---------------------------------------------------------------------------
# Machine profile — top-level descriptor for one machine variant
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MachineProfile:
    key: str
    name: str
    spindles: tuple[MachineSpindleProfile, ...]
    heads: tuple[MachineHeadProfile, ...]
    zero_axes: tuple[str, ...]
    supports_sub_pickup: bool = False
    supports_print_pots: bool = False
    supports_zero_xy_toggle: bool = False
    default_zero_xy_visible: bool = False
    default_tools_spindle: str = "main"

    # Machine family — "lathe" is fully implemented.
    # "machining_center" is reserved for future work (Fixtures library, etc.).
    machine_type: str = "lathe"

    # Single-spindle profiles set this to True.  Drives OP10/OP20 terminology
    # wherever Main spindle / Sub spindle labels would otherwise appear.
    use_op_terminology: bool = False

    # ---------------------------------------------------------------------------
    # Machining Center fields
    # These are only meaningful when machine_type == "machining_center".
    # For lathe profiles they remain at default and are ignored.
    # ---------------------------------------------------------------------------
    axis_count: int = 3                  # 3, 4, or 5
    fourth_axis_letter: str = "C"        # used when axis_count >= 4
    fifth_axis_letter: str = "B"         # used when axis_count == 5
    has_turning_option: bool = False     # enables lathe tool types in Tool Library

    # ---------------------------------------------------------------------------
    # Lookup helpers
    # ---------------------------------------------------------------------------

    def spindle(self, spindle_key: str) -> MachineSpindleProfile | None:
        target = str(spindle_key or "").strip().lower()
        for spindle in self.spindles:
            if spindle.key == target:
                return spindle
        return None

    def head(self, head_key: str) -> MachineHeadProfile | None:
        target = str(head_key or "").strip().upper()
        for head in self.heads:
            if head.key == target:
                return head
        return None

    def head_allows_rotating_tools(self, head_key: str) -> bool:
        """Return True when the head allows powered/rotating tooling."""
        h = self.head(head_key)
        if h is None:
            return False
        if h.head_type == "milling":
            return True  # milling heads always allow rotating tools
        return h.allows_rotating_tools

    def head_allows_b_axis(self, head_key: str) -> bool:
        h = self.head(head_key)
        return h.allows_b_axis if h is not None else False

    @property
    def spindle_count(self) -> int:
        return len(self.spindles)

    @property
    def head_count(self) -> int:
        return len(self.heads)


# ---------------------------------------------------------------------------
# These legacy keys remain the STORAGE CONTRACT even after the UI becomes
# profile-driven.  Future machine variants can hide unsupported capabilities
# while still mapping back into the current additive schema.
# ---------------------------------------------------------------------------
KNOWN_HEAD_KEYS = ("HEAD1", "HEAD2", "HEAD3")
KNOWN_SPINDLE_KEYS = ("main", "sub")


# ---------------------------------------------------------------------------
# Profile 1 — NTX dual-spindle dual-head (default / legacy NTX)
# Behaviour is 100 % identical to the previous NTX_MACHINE_PROFILE object.
# ---------------------------------------------------------------------------
NTX_MACHINE_PROFILE = MachineProfile(
    key="ntx_2sp_2h",
    name="NTX 2 Spindles / 2 Turret Heads",
    spindles=(
        MachineSpindleProfile(
            key="main",
            label_key="work_editor.spindles.sp1_jaw",
            label_default="Main spindle",
            short_label="SP1",
            jaw_title_key="work_editor.spindles.sp1_jaw",
            jaw_title_default="Pääkara",
            jaw_filter_placeholder_key="work_editor.jaw.filter_sp1_placeholder",
            jaw_filter_placeholder_default="Suodata Pääkara-leukoja...",
            jaw_filter="Main spindle",
        ),
        MachineSpindleProfile(
            key="sub",
            label_key="work_editor.spindles.sp2_jaw",
            label_default="Sub spindle",
            short_label="SP2",
            jaw_title_key="work_editor.spindles.sp2_jaw",
            jaw_title_default="Vastakara",
            jaw_filter_placeholder_key="work_editor.jaw.filter_sp2_placeholder",
            jaw_filter_placeholder_default="Suodata Vastakara-leukoja...",
            jaw_filter="Sub spindle",
        ),
    ),
    heads=(
        MachineHeadProfile(
            key="HEAD1",
            label_key="work_editor.tools.head1",
            label_default="Head 1",
            default_coord="G54",
            head_type="turret",
            allows_rotating_tools=False,
            allows_b_axis=False,
            allows_dual_spindle_orientation=True,
        ),
        MachineHeadProfile(
            key="HEAD2",
            label_key="work_editor.tools.head2",
            label_default="Head 2",
            default_coord="G55",
            head_type="turret",
            allows_rotating_tools=False,
            allows_b_axis=False,
            allows_dual_spindle_orientation=True,
        ),
    ),
    zero_axes=("z", "x", "y", "c"),
    supports_sub_pickup=True,
    supports_print_pots=True,
    supports_zero_xy_toggle=True,
    default_zero_xy_visible=False,
    default_tools_spindle="main",
    machine_type="lathe",
    use_op_terminology=False,
)


# ---------------------------------------------------------------------------
# Profile 2 — 2 spindles / 1 milling head (e.g. Nakamura NTX/NZX with B-axis)
# ---------------------------------------------------------------------------
LATHE_2SP_1MILL = MachineProfile(
    key="lathe_2sp_1mill",
    name="Lathe 2 Spindles / 1 Milling Head",
    spindles=(
        MachineSpindleProfile(
            key="main",
            label_key="work_editor.spindles.sp1_jaw",
            label_default="Main spindle",
            short_label="SP1",
            jaw_title_key="work_editor.spindles.sp1_jaw",
            jaw_title_default="Pääkara",
            jaw_filter_placeholder_key="work_editor.jaw.filter_sp1_placeholder",
            jaw_filter_placeholder_default="Suodata Pääkara-leukoja...",
            jaw_filter="Main spindle",
        ),
        MachineSpindleProfile(
            key="sub",
            label_key="work_editor.spindles.sp2_jaw",
            label_default="Sub spindle",
            short_label="SP2",
            jaw_title_key="work_editor.spindles.sp2_jaw",
            jaw_title_default="Vastakara",
            jaw_filter_placeholder_key="work_editor.jaw.filter_sp2_placeholder",
            jaw_filter_placeholder_default="Suodata Vastakara-leukoja...",
            jaw_filter="Sub spindle",
        ),
    ),
    heads=(
        MachineHeadProfile(
            key="HEAD1",
            label_key="work_editor.tools.head1",
            label_default="Milling Head",
            default_coord="G54",
            head_type="milling",
            allows_rotating_tools=True,
            allows_b_axis=True,
            allows_dual_spindle_orientation=True,
        ),
    ),
    zero_axes=("z", "x", "y", "c"),
    supports_sub_pickup=True,
    supports_print_pots=True,
    supports_zero_xy_toggle=True,
    default_zero_xy_visible=False,
    default_tools_spindle="main",
    machine_type="lathe",
    use_op_terminology=False,
)


# ---------------------------------------------------------------------------
# Profile 3 — 2 spindles / 3 turret heads
# ---------------------------------------------------------------------------
LATHE_2SP_3H = MachineProfile(
    key="lathe_2sp_3h",
    name="Lathe 2 Spindles / 3 Turret Heads",
    spindles=(
        MachineSpindleProfile(
            key="main",
            label_key="work_editor.spindles.sp1_jaw",
            label_default="Main spindle",
            short_label="SP1",
            jaw_title_key="work_editor.spindles.sp1_jaw",
            jaw_title_default="Pääkara",
            jaw_filter_placeholder_key="work_editor.jaw.filter_sp1_placeholder",
            jaw_filter_placeholder_default="Suodata Pääkara-leukoja...",
            jaw_filter="Main spindle",
        ),
        MachineSpindleProfile(
            key="sub",
            label_key="work_editor.spindles.sp2_jaw",
            label_default="Sub spindle",
            short_label="SP2",
            jaw_title_key="work_editor.spindles.sp2_jaw",
            jaw_title_default="Vastakara",
            jaw_filter_placeholder_key="work_editor.jaw.filter_sp2_placeholder",
            jaw_filter_placeholder_default="Suodata Vastakara-leukoja...",
            jaw_filter="Sub spindle",
        ),
    ),
    heads=(
        MachineHeadProfile(
            key="HEAD1",
            label_key="work_editor.tools.head1",
            label_default="Head 1",
            default_coord="G54",
            head_type="turret",
            allows_rotating_tools=False,
            allows_b_axis=False,
            allows_dual_spindle_orientation=True,
        ),
        MachineHeadProfile(
            key="HEAD2",
            label_key="work_editor.tools.head2",
            label_default="Head 2",
            default_coord="G55",
            head_type="turret",
            allows_rotating_tools=False,
            allows_b_axis=False,
            allows_dual_spindle_orientation=True,
        ),
        MachineHeadProfile(
            key="HEAD3",
            label_key="work_editor.tools.head3",
            label_default="Head 3",
            default_coord="G56",
            head_type="turret",
            allows_rotating_tools=False,
            allows_b_axis=False,
            allows_dual_spindle_orientation=True,
        ),
    ),
    zero_axes=("z", "x", "y", "c"),
    supports_sub_pickup=True,
    supports_print_pots=True,
    supports_zero_xy_toggle=True,
    default_zero_xy_visible=False,
    default_tools_spindle="main",
    machine_type="lathe",
    use_op_terminology=False,
)


# ---------------------------------------------------------------------------
# Profile 4 — 1 spindle / 1 turret head  (OP10 / OP20 semantics)
# Sub-spindle is absent; orientation is single-spindle only.
# OP20 (second operation in this context) uses the same spindle.
# ---------------------------------------------------------------------------
LATHE_1SP_1H = MachineProfile(
    key="lathe_1sp_1h",
    name="Lathe 1 Spindle / 1 Turret Head",
    spindles=(
        MachineSpindleProfile(
            key="main",
            label_key="work_editor.spindles.op10",
            label_default="OP10",
            short_label="OP10",
            jaw_title_key="work_editor.spindles.op10_jaws",
            jaw_title_default="OP10 Jaws",
            jaw_filter_placeholder_key="work_editor.jaw.filter_op10_placeholder",
            jaw_filter_placeholder_default="Filter OP10 jaws...",
            jaw_filter="Main spindle",
        ),
    ),
    heads=(
        MachineHeadProfile(
            key="HEAD1",
            label_key="work_editor.tools.head1",
            label_default="Head 1",
            default_coord="G54",
            head_type="turret",
            allows_rotating_tools=False,
            allows_b_axis=False,
            allows_dual_spindle_orientation=False,  # single spindle: no dual orientation
        ),
    ),
    zero_axes=("z", "x", "y", "c"),
    supports_sub_pickup=False,
    supports_print_pots=True,
    supports_zero_xy_toggle=True,
    default_zero_xy_visible=False,
    default_tools_spindle="main",
    machine_type="lathe",
    use_op_terminology=True,
)


# ---------------------------------------------------------------------------
# Profile 5 — 1 spindle / 1 milling head  (OP10 / OP20 semantics)
# ---------------------------------------------------------------------------
LATHE_1SP_1MILL = MachineProfile(
    key="lathe_1sp_1mill",
    name="Lathe 1 Spindle / 1 Milling Head",
    spindles=(
        MachineSpindleProfile(
            key="main",
            label_key="work_editor.spindles.op10",
            label_default="OP10",
            short_label="OP10",
            jaw_title_key="work_editor.spindles.op10_jaws",
            jaw_title_default="OP10 Jaws",
            jaw_filter_placeholder_key="work_editor.jaw.filter_op10_placeholder",
            jaw_filter_placeholder_default="Filter OP10 jaws...",
            jaw_filter="Main spindle",
        ),
    ),
    heads=(
        MachineHeadProfile(
            key="HEAD1",
            label_key="work_editor.tools.head1",
            label_default="Milling Head",
            default_coord="G54",
            head_type="milling",
            allows_rotating_tools=True,
            allows_b_axis=True,
            allows_dual_spindle_orientation=False,
        ),
    ),
    zero_axes=("z", "x", "y", "c"),
    supports_sub_pickup=False,
    supports_print_pots=True,
    supports_zero_xy_toggle=True,
    default_zero_xy_visible=False,
    default_tools_spindle="main",
    machine_type="lathe",
    use_op_terminology=True,
)


# ---------------------------------------------------------------------------
# Profile 6 — Machining Center 3-Axis
# Machining centers have no lathe-style spindles, no jaws.
# The single milling head uses operations keyed by OP10/OP20/OP30/...
# Fixtures (not jaws) are used to hold the workpiece.
# ---------------------------------------------------------------------------
MACHINING_CENTER_3AX = MachineProfile(
    key="machining_center_3ax",
    name="Machining Center — 3 Axis",
    spindles=(),                        # no spindle concept
    heads=(
        MachineHeadProfile(
            key="HEAD1",
            label_key="work_editor.tools.head1",
            label_default="Milling Spindle",
            default_coord="G54",
            head_type="milling",
            allows_rotating_tools=True,
            allows_b_axis=False,
            allows_dual_spindle_orientation=False,
            is_machining_center_head=True,
        ),
    ),
    zero_axes=("x", "y", "z"),
    supports_sub_pickup=False,
    supports_print_pots=False,
    supports_zero_xy_toggle=False,
    default_zero_xy_visible=True,
    default_tools_spindle="main",
    machine_type="machining_center",
    use_op_terminology=True,
    axis_count=3,
    fourth_axis_letter="C",
    fifth_axis_letter="B",
    has_turning_option=False,
)


# ---------------------------------------------------------------------------
# Profile 7 — Machining Center 4-Axis (adds a rotary axis, default letter C)
# ---------------------------------------------------------------------------
MACHINING_CENTER_4AX = MachineProfile(
    key="machining_center_4ax",
    name="Machining Center — 4 Axis",
    spindles=(),
    heads=(
        MachineHeadProfile(
            key="HEAD1",
            label_key="work_editor.tools.head1",
            label_default="Milling Spindle",
            default_coord="G54",
            head_type="milling",
            allows_rotating_tools=True,
            allows_b_axis=False,
            allows_dual_spindle_orientation=False,
            is_machining_center_head=True,
        ),
    ),
    zero_axes=("x", "y", "z", "c"),
    supports_sub_pickup=False,
    supports_print_pots=False,
    supports_zero_xy_toggle=False,
    default_zero_xy_visible=True,
    default_tools_spindle="main",
    machine_type="machining_center",
    use_op_terminology=True,
    axis_count=4,
    fourth_axis_letter="C",
    fifth_axis_letter="B",
    has_turning_option=False,
)


# ---------------------------------------------------------------------------
# Profile 8 — Machining Center 5-Axis (two rotary axes, defaults B + C)
# Enables B-axis tool orientation on the milling head.
# ---------------------------------------------------------------------------
MACHINING_CENTER_5AX = MachineProfile(
    key="machining_center_5ax",
    name="Machining Center — 5 Axis",
    spindles=(),
    heads=(
        MachineHeadProfile(
            key="HEAD1",
            label_key="work_editor.tools.head1",
            label_default="Milling Spindle",
            default_coord="G54",
            head_type="milling",
            allows_rotating_tools=True,
            allows_b_axis=True,
            allows_dual_spindle_orientation=False,
            is_machining_center_head=True,
        ),
    ),
    zero_axes=("x", "y", "z", "b", "c"),
    supports_sub_pickup=False,
    supports_print_pots=False,
    supports_zero_xy_toggle=False,
    default_zero_xy_visible=True,
    default_tools_spindle="main",
    machine_type="machining_center",
    use_op_terminology=True,
    axis_count=5,
    fourth_axis_letter="C",
    fifth_axis_letter="B",
    has_turning_option=False,
)


# ---------------------------------------------------------------------------
# Registry — all keys are lowercased for case-insensitive lookup
# ---------------------------------------------------------------------------
DEFAULT_PROFILE_KEY = "ntx_2sp_2h"

PROFILE_REGISTRY: dict[str, MachineProfile] = {
    # canonical keys
    "ntx_2sp_2h":           NTX_MACHINE_PROFILE,
    "lathe_2sp_1mill":      LATHE_2SP_1MILL,
    "lathe_2sp_3h":         LATHE_2SP_3H,
    "lathe_1sp_1h":         LATHE_1SP_1H,
    "lathe_1sp_1mill":      LATHE_1SP_1MILL,
    "machining_center_3ax": MACHINING_CENTER_3AX,
    "machining_center_4ax": MACHINING_CENTER_4AX,
    "machining_center_5ax": MACHINING_CENTER_5AX,
    # legacy alias kept for any stored preference values that used the old key
    "ntx_dual_spindle_dual_head": NTX_MACHINE_PROFILE,
}

# Ordered list for display in wizard / UI (excludes legacy aliases)
PROFILE_DISPLAY_ORDER: list[str] = [
    "ntx_2sp_2h",
    "lathe_2sp_1mill",
    "lathe_2sp_3h",
    "lathe_1sp_1h",
    "lathe_1sp_1mill",
    "machining_center_3ax",
    "machining_center_4ax",
    "machining_center_5ax",
]


def is_machining_center(profile: MachineProfile | None) -> bool:
    """Return True when the profile describes a machining center."""
    if profile is None:
        return False
    return str(profile.machine_type).strip().lower() == "machining_center"


def load_profile(profile_key: str | None) -> MachineProfile:
    """Return a MachineProfile by key, falling back to the default for unknown keys."""
    normalized = str(profile_key or "").strip().lower()
    if normalized and normalized in PROFILE_REGISTRY:
        return PROFILE_REGISTRY[normalized]
    return PROFILE_REGISTRY[DEFAULT_PROFILE_KEY]


def apply_machining_center_overrides(
    profile: MachineProfile,
    *,
    fourth_axis_letter: str | None = None,
    fifth_axis_letter: str | None = None,
    has_turning_option: bool | None = None,
) -> MachineProfile:
    """Return a new MachineProfile with user-configurable MC overrides applied.

    Non-MC profiles are returned unchanged.  Axis-letter overrides are ignored
    unless the profile's ``axis_count`` supports them.
    """
    from dataclasses import replace

    if not is_machining_center(profile):
        return profile

    kwargs: dict = {}
    if fourth_axis_letter is not None and profile.axis_count >= 4:
        letter = str(fourth_axis_letter).strip().upper()
        if letter:
            kwargs["fourth_axis_letter"] = letter
    if fifth_axis_letter is not None and profile.axis_count == 5:
        letter = str(fifth_axis_letter).strip().upper()
        if letter:
            kwargs["fifth_axis_letter"] = letter
    if has_turning_option is not None:
        kwargs["has_turning_option"] = bool(has_turning_option)

    if not kwargs:
        return profile
    return replace(profile, **kwargs)
