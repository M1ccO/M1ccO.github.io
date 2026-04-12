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
    if Path(arrow_icon_path).exists():
        combo.setStyleSheet(
            "QComboBox::drop-down { width: 28px; border: none; background: transparent; }"
            f"QComboBox::down-arrow {{ image: url('{arrow_icon_path}'); width: 20px; height: 20px; }}"
        )
    apply_shared_dropdown_style(combo)
