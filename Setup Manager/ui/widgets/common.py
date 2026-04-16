from pathlib import Path

from PySide6.QtWidgets import QComboBox

from config import ICONS_DIR
from shared.ui.helpers.common_widgets import (  # noqa: F401 — re-exported for app callers
    AutoShrinkLabel,
    CollapsibleGroup,
    add_shadow,
    apply_shared_dropdown_style,
    clear_focused_dropdown_on_outside_click,
    repolish_widget,
    styled_list_item_height,
)


def apply_tool_library_combo_style(combo: QComboBox) -> None:
    """Apply the unified tool-library dropdown look (white shell, menu_open chevron arrow)."""
    combo.setProperty("modernDropdown", False)
    combo.setProperty("toolLibraryCombo", True)
    arrow_icon_path = (Path(ICONS_DIR) / "tools" / "menu_open.svg").as_posix()
    style_parts = [
        "QComboBox {"
        " background-color: #ffffff;"
        " border: 1px solid #a0b4c8;"
        " border-radius: 6px;"
        " min-height: 0px;"
        " font-size: 10.5pt;"
        " font-weight: 400;"
        " padding: 6px 10px;"
        "}",
        "QComboBox[hovered='true'] {"
        " background-color: #edf5fc;"
        " border: 1px solid #c0c4c8;"
        "}",
        "QComboBox::drop-down { width: 28px; border: none; background: transparent; }",
    ]
    if Path(arrow_icon_path).exists():
        style_parts.append(
            f"QComboBox::down-arrow {{ image: url('{arrow_icon_path}'); width: 20px; height: 20px; }}"
        )
    combo.setStyleSheet("".join(style_parts))
    apply_shared_dropdown_style(combo)
