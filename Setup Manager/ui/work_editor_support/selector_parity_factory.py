from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt


def _activate_tool_library_namespace_aliases(dialog: Any) -> None:
    existing = getattr(dialog, "_embedded_selector_namespace_aliases", None)
    if isinstance(existing, dict):
        return

    aliases = {
        "config": "tools_and_jaws_library.config",
        "ui": "tools_and_jaws_library.ui",
        "data": "tools_and_jaws_library.data",
        "services": "tools_and_jaws_library.services",
        "models": "tools_and_jaws_library.models",
    }
    snapshot: dict[str, Any] = {}
    for alias, target in aliases.items():
        snapshot[alias] = sys.modules.get(alias)
        try:
            sys.modules[alias] = importlib.import_module(target)
        except Exception:
            # Keep best-effort behavior; unresolved aliases will surface via normal import errors.
            pass
    setattr(dialog, "_embedded_selector_namespace_aliases", snapshot)


def release_tool_library_namespace_aliases(dialog: Any) -> None:
    snapshot = getattr(dialog, "_embedded_selector_namespace_aliases", None)
    if not isinstance(snapshot, dict):
        return
    for alias, original in snapshot.items():
        if original is None:
            sys.modules.pop(alias, None)
        else:
            sys.modules[alias] = original
    setattr(dialog, "_embedded_selector_namespace_aliases", None)


def _ensure_service_bundle(dialog: Any) -> dict[str, Any]:
    bundle = getattr(dialog, "_embedded_selector_service_bundle", None)
    if isinstance(bundle, dict):
        return bundle

    from tools_and_jaws_library.data.database import Database
    from tools_and_jaws_library.data.fixture_database import FixtureDatabase
    from tools_and_jaws_library.data.jaw_database import JawDatabase
    from tools_and_jaws_library.services.fixture_service import FixtureService
    from tools_and_jaws_library.services.jaw_service import JawService
    from tools_and_jaws_library.services.tool_service import ToolService

    draw_service = dialog.draw_service
    tool_db = Database(Path(draw_service.tool_db_path))
    jaw_db = JawDatabase(Path(draw_service.jaw_db_path))
    fixture_db = FixtureDatabase(Path(getattr(draw_service, "fixture_db_path", draw_service.jaw_db_path)))

    bundle = {
        "tool_service": ToolService(tool_db),
        "jaw_service": JawService(jaw_db),
        "fixture_service": FixtureService(fixture_db),
        "tool_db": tool_db,
        "jaw_db": jaw_db,
        "fixture_db": fixture_db,
    }
    setattr(dialog, "_embedded_selector_service_bundle", bundle)
    return bundle


def _apply_embedded_selector_style(widget: Any) -> None:
    """Apply selector-local style overrides for embedded hosting in Work Editor.

    Setup Manager and Tool Library use different global stylesheets. These
    targeted rules restore selector visual parity without touching app-wide QSS.
    """
    if widget is None:
        return

    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.setProperty("selectorContext", True)
    widget.setStyleSheet(
        """
QWidget[selectorContext="true"] QFrame[bottomBar="true"] {
    background: transparent;
    border: none;
}
QWidget[selectorContext="true"] QWidget[selectorPanel="true"],
QWidget[selectorContext="true"] QFrame[selectorContext="true"],
QWidget[selectorContext="true"] QFrame[selectorScrollFrame="true"],
QWidget[selectorContext="true"] QFrame[subCard="true"],
QWidget[selectorContext="true"] QFrame[card="true"],
QWidget[selectorContext="true"] QScrollArea,
QWidget[selectorContext="true"] QScrollArea QWidget {
    background-color: #ffffff;
}
QWidget[selectorContext="true"] QFrame[subCard="true"],
QWidget[selectorContext="true"] QFrame[card="true"] {
    border: 1px solid #b8c5d1;
    border-radius: 2px;
}
QWidget[selectorContext="true"] QFrame[detailHeader="true"],
QWidget[selectorContext="true"] QFrame[selectorInfoHeader="true"] {
    background-color: transparent;
    border: 1px solid #c8d4e0;
    border-radius: 6px;
}
QWidget[selectorContext="true"] QLabel[selectorInlineHint="true"] {
    font-size: 8pt;
    font-style: italic;
    font-weight: 400;
    color: #5f6f7d;
}
QWidget[selectorContext="true"] QLabel[toolBadge="true"] {
    background-color: #eaf1f8;
    color: #233344;
    border: 1px solid #b9c9d8;
    border-radius: 12px;
    padding: 3px 10px;
    font-size: 9pt;
    font-weight: 700;
}
QWidget[selectorContext="true"] QComboBox#topTypeFilter {
    background-color: qlineargradient(x1:0, y1:1, x2:0, y2:0,
                                      stop:0 #E2E2E2, stop:1 #FAFAFA);
    border: 1px solid #c0c4c8;
    border-radius: 6px;
    min-height: 30px;
    font-size: 9.5pt;
    font-weight: 600;
    color: #111111;
    padding: 3px 8px;
    min-width: 68px;
}
QWidget[selectorContext="true"] QComboBox#topTypeFilter::drop-down {
    width: 24px;
    border: none;
    background: transparent;
}
QWidget[selectorContext="true"] QComboBox#topTypeFilter QAbstractItemView {
    background-color: #FCFCFC;
    border: 1px solid #c8d0d8;
    border-radius: 6px;
    color: #111111;
    font-size: 10pt;
    font-weight: 600;
    selection-background-color: #F0F0F0;
    selection-color: #000000;
}
QWidget[selectorContext="true"] QLabel[detailHeroTitle="true"] {
    color: #13202b;
    font-size: 16px;
    font-weight: 700;
}
QWidget[selectorContext="true"] QLabel[detailHint="true"] {
    color: #5f6f7d;
}
"""
    )
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)


def build_embedded_selector_parity_widget(
    dialog: Any,
    *,
    mount_container: QWidget | None = None,
    kind: str,
    head: str | None = None,
    spindle: str | None = None,
    follow_up: dict | None = None,
    initial_assignments: list[dict] | None = None,
    initial_assignment_buckets: dict[str, list[dict]] | None = None,
    on_submit: Callable[[dict], None],
    on_cancel: Callable[[], None],
):
    kind_key = str(kind or "").strip().lower()
    _activate_tool_library_namespace_aliases(dialog)
    services = _ensure_service_bundle(dialog)

    if kind_key == "tools":
        from tools_and_jaws_library.ui.selectors.tool_selector_dialog import ToolSelectorDialog

        widget = ToolSelectorDialog(
            tool_service=services["tool_service"],
            machine_profile=dialog.machine_profile,
            translate=dialog._t,
            selector_head=str(head or ""),
            selector_spindle=str(spindle or ""),
            initial_assignments=initial_assignments,
            initial_assignment_buckets=initial_assignment_buckets,
            on_submit=on_submit,
            on_cancel=on_cancel,
            parent=mount_container or dialog,
        )
    elif kind_key == "jaws":
        from tools_and_jaws_library.ui.selectors.jaw_selector_dialog import JawSelectorDialog

        widget = JawSelectorDialog(
            jaw_service=services["jaw_service"],
            machine_profile=dialog.machine_profile,
            translate=dialog._t,
            selector_spindle=str(spindle or ""),
            initial_assignments=initial_assignments,
            on_submit=on_submit,
            on_cancel=on_cancel,
            parent=mount_container or dialog,
        )
    else:
        from tools_and_jaws_library.ui.selectors.fixture_selector_dialog import FixtureSelectorDialog

        widget = FixtureSelectorDialog(
            fixture_service=services["fixture_service"],
            translate=dialog._t,
            initial_assignments=initial_assignments,
            initial_assignment_buckets=initial_assignment_buckets,
            initial_target_key=str((follow_up or {}).get("target_key") or ""),
            on_submit=on_submit,
            on_cancel=on_cancel,
            parent=mount_container or dialog,
        )

    # Force child-widget hosting to avoid transient top-level QDialog flashes.
    widget.setParent(mount_container or dialog, Qt.Widget)
    widget.setWindowFlag(Qt.Dialog, False)
    widget.setWindowFlag(Qt.Window, False)
    widget.setWindowFlag(Qt.Popup, False)
    widget.setWindowFlag(Qt.SubWindow, False)
    widget.setWindowFlags(Qt.Widget)
    widget.setWindowModality(Qt.NonModal)
    widget.setVisible(False)
    _apply_embedded_selector_style(widget)
    return widget
