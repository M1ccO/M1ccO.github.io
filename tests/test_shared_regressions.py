from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from shared.services.localization_service import LocalizationService
from shared.services.ui_preferences_service import UiPreferencesService
from shared.ui.helpers.common_widgets import AutoShrinkLabel, CollapsibleGroup, add_shadow
from shared.ui.helpers.editor_helpers import apply_shared_checkbox_style, create_titled_section
from shared.ui.helpers.editor_table import EditorTable
from PySide6.QtWidgets import QCheckBox, QWidget


class SharedServicesRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_localization_merges_shared_and_app_catalog(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            app_i18n = workspace / "Setup Manager" / "i18n"
            shared_i18n = workspace / "shared" / "i18n"
            app_i18n.mkdir(parents=True, exist_ok=True)
            shared_i18n.mkdir(parents=True, exist_ok=True)

            (shared_i18n / "en.json").write_text(
                json.dumps({"greeting": "Hello {name}", "only_shared": "S"}),
                encoding="utf-8",
            )
            (app_i18n / "en.json").write_text(
                json.dumps({"only_app": "A", "greeting": "Hi {name}"}),
                encoding="utf-8",
            )

            service = LocalizationService(app_i18n)
            service.set_language("en")

            self.assertEqual(service.t("only_shared"), "S")
            self.assertEqual(service.t("only_app"), "A")
            self.assertEqual(service.t("greeting", name="Mika"), "Hi Mika")

    def test_localization_falls_back_to_default_language(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            i18n_dir = Path(temp_dir) / "App" / "i18n"
            i18n_dir.mkdir(parents=True, exist_ok=True)
            (i18n_dir / "en.json").write_text(json.dumps({"k": "v"}), encoding="utf-8")

            service = LocalizationService(i18n_dir, fallback_language="en")
            service.set_language("zz")

            self.assertEqual(service.language, "en")
            self.assertEqual(service.t("k"), "v")
            self.assertEqual(service.t("missing", default="d"), "d")

    def test_ui_preferences_normalizes_and_creates_model_dirs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            prefs_path = Path(temp_dir) / "prefs" / "ui.json"
            tools_root = Path(temp_dir) / "models" / "tools"
            jaws_root = Path(temp_dir) / "models" / "jaws"
            setup_db_path = Path(temp_dir) / "db" / "setup.sqlite"

            service = UiPreferencesService(prefs_path, include_setup_db_path=True)
            normalized = service.save(
                {
                    "language": "FI",
                    "font_family": "Unknown",
                    "color_theme": "GRAPHITE",
                    "tools_models_root": str(tools_root),
                    "jaws_models_root": str(jaws_root),
                    "setup_db_path": str(setup_db_path),
                    "enable_assembly_transform": 1,
                    "enable_drawings_tab": 0,
                }
            )

            self.assertEqual(normalized["language"], "fi")
            self.assertEqual(normalized["font_family"], "Segoe UI")
            self.assertEqual(normalized["color_theme"], "graphite")
            self.assertTrue(Path(normalized["tools_models_root"]).exists())
            self.assertTrue(Path(normalized["jaws_models_root"]).exists())
            self.assertTrue(normalized["setup_db_path"].endswith("setup.sqlite"))
            self.assertTrue(normalized["enable_assembly_transform"])
            self.assertFalse(normalized["enable_drawings_tab"])

            loaded = service.load()
            self.assertEqual(loaded["language"], "fi")


class SharedUiHelpersRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_editor_table_row_helpers_and_reorder(self):
        table = EditorTable(headers=["Code", "Description"], min_rows=0)
        table.add_row_dict({"Code": "A", "Description": "First"})
        table.add_row_dict({"Code": "B", "Description": "Second"})

        self.assertEqual(table.rowCount(), 2)
        self.assertEqual(table.row_dict(0)["Code"], "A")
        self.assertEqual(table.row_dict(1)["Code"], "B")

        table.setCurrentCell(1, 0)
        table.move_selected_row(-1)

        self.assertEqual(table.row_dict(0)["Code"], "B")
        self.assertEqual(table.row_dict(1)["Code"], "A")

    def test_editor_table_respects_read_only_columns(self):
        table = EditorTable(headers=["Code", "Description"], min_rows=0)
        table.add_empty_row(["A", "Desc"])
        table.set_read_only_columns(["Code"])

        read_only_item = table.item(0, 0)
        editable_item = table.item(0, 1)

        self.assertIsNotNone(read_only_item)
        self.assertIsNotNone(editable_item)
        self.assertFalse(bool(read_only_item.flags() & Qt.ItemIsEditable))
        self.assertTrue(bool(editable_item.flags() & Qt.ItemIsEditable))

    def test_checkbox_and_titled_section_helpers_apply_styles(self):
        checkbox = QCheckBox("x")
        apply_shared_checkbox_style(checkbox, indicator_size=14, min_height=20)
        self.assertIn("QCheckBox::indicator:checked", checkbox.styleSheet())

        section = create_titled_section("Group")
        self.assertEqual(section.title(), "Group")
        self.assertIn("QGroupBox::title", section.styleSheet())

    def test_common_widgets_autoshrink_and_collapsible_group(self):
        label = AutoShrinkLabel("Very long sample text for shrink checks", min_point_size=7)
        label.resize(80, 24)
        label.refresh_fit()
        self.assertGreaterEqual(label.font().pointSizeF(), 7.0)

        group = CollapsibleGroup("Section")
        self.assertFalse(group.body.isVisible())
        group.toggle.setChecked(True)
        self.assertFalse(group.body.isHidden())

        panel = QWidget()
        add_shadow(panel)
        self.assertIsNotNone(panel.graphicsEffect())


if __name__ == "__main__":
    unittest.main()
