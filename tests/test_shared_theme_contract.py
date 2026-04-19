from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
_TOOL_ROOT = _WORKSPACE / "Tools and jaws Library"
for _candidate in (_WORKSPACE, _TOOL_ROOT):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from PySide6.QtWidgets import QApplication, QGroupBox  # noqa: E402

from shared.ui.helpers.editor_helpers import create_titled_section  # noqa: E402
from shared.ui.theme import (  # noqa: E402
    compile_app_stylesheet,
    get_active_theme_palette,
    install_application_theme_state,
)
import ui.jaw_catalog_delegate as jaw_catalog_delegate  # noqa: E402
from ui.selectors.common import SelectorDialogBase, SelectorWidgetBase  # noqa: E402
import ui.tool_catalog_delegate as tool_catalog_delegate  # noqa: E402


_APP = QApplication.instance() or QApplication([])


class TestSharedThemeContract(unittest.TestCase):
    def test_theme_palettes_expose_required_semantic_roles(self):
        required = {
            "page_bg",
            "row_area_bg",
            "card_bg",
            "editor_bg",
            "section_bg",
            "border",
            "border_strong",
            "accent",
            "tab_active",
            "tab_inactive",
            "window_bg",
            "surface_bg",
            "info_box_bg",
        }
        for theme_name in ("classic", "graphite"):
            palette = get_active_theme_palette({"color_theme": theme_name})
            self.assertTrue(required.issubset(set(palette.keys())), theme_name)

    def test_compiled_stylesheet_has_no_unresolved_placeholders(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            style_dir = root / "styles"
            modules_dir = style_dir / "modules"
            assets_dir = root / "assets"
            modules_dir.mkdir(parents=True, exist_ok=True)
            assets_dir.mkdir(parents=True, exist_ok=True)
            (modules_dir / "10-base.qss").write_text("QWidget#appRoot { background: #ffffff; }", encoding="utf-8")
            style_path = style_dir / "app_style.qss"
            style_path.write_text("", encoding="utf-8")

            compiled = compile_app_stylesheet(style_path, {"color_theme": "classic", "font_family": "Segoe UI"})

        self.assertIn("Shared semantic theme overrides", compiled)
        self.assertNotIn("{{", compiled)
        self.assertIn("QGroupBox[editorSection=\"true\"]", compiled)
        self.assertIn("QFrame[selectorDropTarget=\"true\"]", compiled)
        self.assertIn("QSplitter[pageFamilySplitter=\"true\"]", compiled)
        self.assertIn("QSplitter[editorFamilySplitter=\"true\"]", compiled)
        self.assertIn("QFrame[editorSeparator=\"true\"]", compiled)
        self.assertIn("QWidget[selectorActionBar=\"true\"]", compiled)
        self.assertIn("QWidget[selectorContext=\"true\"] QGroupBox[selectorAssignmentsFrame=\"true\"]", compiled)
        self.assertIn("QWidget[selectorContext=\"true\"] QFrame[selectorScrollFrame=\"true\"]", compiled)
        self.assertIn("background-color: #f0f6fc;", compiled)
        self.assertIn("border: 1px solid #d0d8e0;", compiled)
        self.assertIn("QGroupBox[editorSection=\"true\"]::title", compiled)
        title_block = compiled.split('QGroupBox[editorSection="true"]::title', 1)[1].split('QGroupBox[editorSection="true"][editorSectionCompact="true"]::title', 1)[0]
        self.assertNotIn("background-color", title_block)
        self.assertIn('QDialog[workEditorDialog="true"] QLineEdit:focus', compiled)

    def test_editor_section_helper_uses_shared_property_path(self):
        install_application_theme_state({"color_theme": "classic"})
        group = create_titled_section("Geometry")
        self.assertIsInstance(group, QGroupBox)
        self.assertTrue(bool(group.property("editorSection")))
        self.assertEqual("", str(group.styleSheet() or ""))

    def test_selector_hosts_use_shared_surface_properties(self):
        class _DummySelectorDialog(SelectorDialogBase):
            pass

        class _DummySelectorWidget(SelectorWidgetBase):
            pass

        install_application_theme_state({"color_theme": "classic"})
        dialog = _DummySelectorDialog(translate=lambda _k, default=None, **_kwargs: default or "", on_cancel=lambda: None)
        widget = _DummySelectorWidget(translate=lambda _k, default=None, **_kwargs: default or "", on_cancel=lambda: None)
        self.assertTrue(bool(dialog.property("pageFamilyDialog")))
        self.assertTrue(bool(widget.property("selectorEmbedded")))
        self.assertTrue(bool(widget.property("rowAreaSurface")))

    def test_delegate_paint_paths_follow_shared_accent(self):
        palette = get_active_theme_palette({"color_theme": "classic"})
        tool_catalog_delegate.apply_delegate_theme(palette)
        jaw_catalog_delegate.apply_delegate_theme(palette)

        self.assertEqual(tool_catalog_delegate.CLR_CARD_SELECTED_BORDER.name().lower(), palette["accent"].lower())
        self.assertEqual(jaw_catalog_delegate.JawCatalogDelegate.CLR_CARD_SELECTED_BORDER.name().lower(), palette["accent"].lower())


if __name__ == "__main__":
    unittest.main()
