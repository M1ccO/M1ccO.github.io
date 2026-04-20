from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QFont, QFontMetrics


@dataclass(frozen=True)
class ContainerLayoutContract:
    """Shared container-level geometry contract for Setup and Library pages.

    This contract intentionally excludes row-card delegate sizing/painting.
    It only governs page container anchors, toolbar offsets, and rail geometry.
    """

    rail_width: int = 210
    rail_margins: tuple[int, int, int, int] = (8, 14, 8, 14)
    rail_section_spacing: int = 8
    rail_header_inner_margins: tuple[int, int, int, int] = (18, 0, 2, 0)
    rail_header_font_pt: int = 21
    rail_header_height: int = 52
    # Reserved horizontal clearance for rail title rendering. Keep independent
    # from rail_header_inner_margins so header positioning does not alter rail width.
    rail_header_text_clearance: int = 22
    rail_nav_section_top_inset: int = 32
    rail_nav_button_min_width: int = 154
    rail_footer_card_width: int = 186
    rail_footer_card_min_height: int = 186

    # Vertical inset applied to the left content column (toolbar + frame host)
    # so the overall frame area gets shorter and header area gets bigger.
    content_top_inset: int = 58
    content_section_spacing: int = 2

    # Overall catalog frame host position inside the left content column.
    frame_host_margins: tuple[int, int, int, int] = (24, 6, 0, 0)

    # Top toolbar follows the frame host via a fixed left-edge delta.
    toolbar_to_frame_left_delta: int = 2
    toolbar_vertical_inset: int = 6
    toolbar_right_inset: int = 8

    bottom_bar_margins: tuple[int, int, int, int] = (10, 10, 10, 6)


def get_container_layout_contract() -> ContainerLayoutContract:
    """Return the shared container layout contract."""
    return ContainerLayoutContract()


def get_toolbar_margins(contract: ContainerLayoutContract | None = None) -> tuple[int, int, int, int]:
    """Toolbar margins derived from frame-host inset to keep both coupled."""
    c = contract or get_container_layout_contract()
    frame_left = c.frame_host_margins[0]
    toolbar_left = max(0, frame_left - c.toolbar_to_frame_left_delta)
    return (toolbar_left, c.toolbar_vertical_inset, c.toolbar_right_inset, c.toolbar_vertical_inset)


def get_required_rail_width(
    header_text: str,
    contract: ContainerLayoutContract | None = None,
    *,
    extra_header_padding: int = 8,
) -> int:
    """Return a rail width that can contain header/footer/nav requirements.

    The returned width is the maximum of:
    - baseline contract rail width,
    - footer card width + rail side margins,
    - nav button min width + rail side margins,
        - header text width (at configured header font size) + rail side margins +
            reserved clearance.
    """
    c = contract or get_container_layout_contract()
    side_margins = c.rail_margins[0] + c.rail_margins[2]
    required = max(
        c.rail_width,
        c.rail_footer_card_width + side_margins,
        c.rail_nav_button_min_width + side_margins,
    )

    text = str(header_text or "").strip()
    if not text:
        return required

    try:
        font = QFont()
        font.setBold(True)
        font.setPointSize(c.rail_header_font_pt)
        text_width = QFontMetrics(font).horizontalAdvance(text)
        header_clearance = max(c.rail_header_text_clearance, extra_header_padding)
        required = max(required, text_width + side_margins + header_clearance)
    except Exception:
        # Fall back to structural minimums if font metrics are unavailable.
        pass

    return required
