from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class MachineHeadProfile:
    key: str
    label_key: str
    label_default: str
    default_coord: str


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


# These legacy keys remain the storage contract even after the UI becomes
# profile-driven. Future machine variants can hide unsupported capabilities
# while still mapping back into the current additive schema.
KNOWN_HEAD_KEYS = ("HEAD1", "HEAD2")
KNOWN_SPINDLE_KEYS = ("main", "sub")


NTX_MACHINE_PROFILE = MachineProfile(
    key="ntx_dual_spindle_dual_head",
    name="NTX Dual-Spindle Dual-Head",
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
        ),
        MachineHeadProfile(
            key="HEAD2",
            label_key="work_editor.tools.head2",
            label_default="Head 2",
            default_coord="G55",
        ),
    ),
    zero_axes=("z", "x", "y", "c"),
    supports_sub_pickup=True,
    supports_print_pots=True,
    supports_zero_xy_toggle=True,
    default_zero_xy_visible=False,
    default_tools_spindle="main",
)
