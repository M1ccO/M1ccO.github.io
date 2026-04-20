"""Shared theme contract and stylesheet compiler for both desktop apps.

This module is the canonical source for semantic UI colors and the final
runtime stylesheet that both applications apply. Existing app-local QSS
modules remain in place, but their visible colors are intentionally
normalized by the compiled override block built here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget


APP_THEME_PROPERTY = "_ntx_shared_theme_palette"


def _rgba(color: str, alpha: float) -> str:
    qcolor = QColor(color)
    if not qcolor.isValid():
        return color
    qcolor.setAlphaF(max(0.0, min(1.0, float(alpha))))
    return f"rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, {qcolor.alphaF():.3f})"


def _mix(color: str, other: str, ratio: float) -> str:
    first = QColor(color)
    second = QColor(other)
    if not first.isValid() or not second.isValid():
        return color
    ratio = max(0.0, min(1.0, float(ratio)))
    inv = 1.0 - ratio
    mixed = QColor(
        round(first.red() * inv + second.red() * ratio),
        round(first.green() * inv + second.green() * ratio),
        round(first.blue() * inv + second.blue() * ratio),
        round(first.alpha() * inv + second.alpha() * ratio),
    )
    return mixed.name()


def _shift_lightness(color: str, delta: float) -> str:
    qcolor = QColor(color)
    if not qcolor.isValid():
        return color
    h, s, l, a = qcolor.getHslF()
    l = max(0.0, min(1.0, l + delta))
    shifted = QColor.fromHslF(h, s, l, a)
    return shifted.name()


@dataclass(frozen=True)
class ThemePalette:
    theme_name: str
    font_family: str
    page_bg: str
    row_area_bg: str
    card_bg: str
    editor_bg: str
    section_bg: str
    border: str
    border_strong: str
    border_soft: str
    text_primary: str
    text_secondary: str
    accent_light: str
    accent: str
    accent_hover: str
    accent_pressed: str
    icon_hover_bg: str
    button_neutral_top: str
    button_neutral_bottom: str
    button_neutral_hover_top: str
    button_neutral_hover_bottom: str
    button_neutral_pressed_top: str
    button_neutral_pressed_bottom: str
    tab_active: str
    tab_inactive: str
    tab_hover: str

    def as_dict(self) -> dict[str, str]:
        payload = asdict(self)
        payload.update(
            {
                # Compatibility keys used by the existing codebase.
                "window_bg": self.page_bg,
                "surface_bg": self.row_area_bg,
                "info_box_bg": self.card_bg,
                "button_primary": self.accent,
                "button_neutral": self.button_neutral_bottom,
                "border_focus": self.accent,
            }
        )
        return payload


_BASE_THEMES: dict[str, dict[str, str]] = {
    "classic": {
        "page_bg": "#eceff2",
        "row_area_bg": "rgba(205, 212, 238, 0.97)",
        "card_bg": "#ffffff",
        "editor_bg": "#ffffff",
        "section_bg": "#f0f6fc",
        "border": "#c8d4e0",
        "border_strong": "#637282",
        "text_primary": "#22303c",
        "text_secondary": "#5a6b7c",
        "accent_light": "#54c5ff",
        "accent": "#1e88e5",
        "accent_hover": "#1976d2",
        "accent_pressed": "#1565c0",
        "tab_inactive": "#dfe6ee",
        "tab_active": "#ffffff",
    },
    "graphite": {
        "page_bg": "#d8dce2",
        "row_area_bg": "rgba(168, 179, 198, 0.98)",
        "card_bg": "#ffffff",
        "editor_bg": "#ffffff",
        "section_bg": "#f0f6fc",
        "border": "#c1ccd7",
        "border_strong": "#5e6a76",
        "text_primary": "#22303c",
        "text_secondary": "#586877",
        "accent_light": "#42a5f5",
        "accent": "#1976d2",
        "accent_hover": "#1565c0",
        "accent_pressed": "#0d47a1",
        "tab_inactive": "#d8e0e7",
        "tab_active": "#ffffff",
    },
}


def get_active_theme_palette(preferences: dict[str, Any] | None) -> dict[str, str]:
    """Return the active theme palette dict with semantic and compatibility keys."""
    return get_active_theme_tokens(preferences).as_dict()


def get_active_theme_tokens(preferences: dict[str, Any] | None) -> ThemePalette:
    preferences = preferences or {}
    theme_name = str(preferences.get("color_theme") or "classic").strip().lower()
    font_family = str(preferences.get("font_family") or "Segoe UI").strip() or "Segoe UI"
    base = dict(_BASE_THEMES.get(theme_name, _BASE_THEMES["classic"]))
    border = base["border"]
    accent = base["accent"]
    return ThemePalette(
        theme_name=theme_name,
        font_family=font_family,
        page_bg=base["page_bg"],
        row_area_bg=base["row_area_bg"],
        card_bg=base["card_bg"],
        editor_bg=base["editor_bg"],
        section_bg=base["section_bg"],
        border=border,
        border_strong=base["border_strong"],
        border_soft=_mix(border, base["editor_bg"], 0.35),
        text_primary=base["text_primary"],
        text_secondary=base["text_secondary"],
        accent_light=base["accent_light"],
        accent=accent,
        accent_hover=base["accent_hover"],
        accent_pressed=base["accent_pressed"],
        icon_hover_bg=_rgba(accent, 0.15),
        button_neutral_top="#fafafa",
        button_neutral_bottom="#e2e2e2",
        button_neutral_hover_top="#ffffff",
        button_neutral_hover_bottom="#eaf1f6",
        button_neutral_pressed_top="#f2f5f8",
        button_neutral_pressed_bottom="#d6dee5",
        tab_active=base["tab_active"],
        tab_inactive=base["tab_inactive"],
        tab_hover=_mix(base["tab_inactive"], base["editor_bg"], 0.4),
    )


THEME_PALETTES: dict[str, dict[str, str]] = {
    name: get_active_theme_tokens({"color_theme": name}).as_dict()
    for name in _BASE_THEMES
}


def install_application_theme_state(preferences: dict[str, Any] | None) -> dict[str, str]:
    """Persist the active theme palette on QApplication for shared helpers."""
    palette = get_active_theme_palette(preferences)
    app = QApplication.instance()
    if app is not None:
        app.setProperty(APP_THEME_PROPERTY, dict(palette))
    return palette


def current_theme_palette() -> dict[str, str]:
    """Return the runtime palette stored on QApplication, with classic fallback."""
    app = QApplication.instance()
    if app is not None:
        payload = app.property(APP_THEME_PROPERTY)
        if isinstance(payload, dict) and payload:
            return dict(payload)
    return get_active_theme_palette({"color_theme": "classic"})


def current_theme_color(role: str, fallback: str) -> QColor:
    payload = current_theme_palette()
    color = QColor(str(payload.get(role) or fallback))
    if color.isValid():
        return color
    return QColor(fallback)


def apply_top_level_surface_palette(widget: QWidget, *, role: str) -> None:
    """Apply a stable palette background for glitch-prone top-level surfaces."""
    color = current_theme_color(role, "#eceff2")
    palette = widget.palette()
    palette.setColor(QPalette.Window, color)
    palette.setColor(QPalette.Base, color)
    widget.setPalette(palette)
    widget.setAutoFillBackground(True)


def _resolve_asset_urls(qss: str, assets_dir: Path) -> str:
    assets_posix = assets_dir.resolve().as_posix()
    return qss.replace('url("assets/', f'url("{assets_posix}/').replace("url('assets/", f"url('{assets_posix}/")


def _load_base_stylesheet(style_path: Path) -> str:
    style_dir = style_path.parent
    modules_dir = style_dir / "modules"
    assets_dir = style_dir.parent / "assets"
    merged: list[str] = []
    if modules_dir.is_dir():
        for module_path in sorted(modules_dir.glob("*.qss")):
            try:
                merged.append(_resolve_asset_urls(module_path.read_text(encoding="utf-8"), assets_dir))
            except Exception:
                continue
    if merged:
        return "\n\n".join(merged)
    try:
        return _resolve_asset_urls(style_path.read_text(encoding="utf-8"), assets_dir)
    except Exception:
        return ""


def build_theme_override_stylesheet(preferences: dict[str, Any] | None) -> str:
    """Build the shared final override block appended after app-local QSS."""
    tokens = get_active_theme_tokens(preferences)
    p = tokens.as_dict()
    font_family = tokens.font_family.replace("'", "\\'")
    return f"""
/* Shared semantic theme overrides */
* {{
    font-family: '{font_family}';
}}

QMainWindow,
QWidget#appRoot,
QFrame#navFrame,
QFrame#filterFrame,
QFrame[navRail="true"],
QFrame[topBarContainer="true"],
QFrame[bottomBar="true"],
QDialog[pageFamilyDialog="true"],
QWidget[pageFamilyHost="true"] {{
    background-color: {p['page_bg']};
}}

QSplitter[pageFamilySplitter="true"] {{
    background-color: {p['page_bg']};
}}

QSplitter[pageFamilySplitter="true"]::handle {{
    background: {p['border']};
    margin: 0;
}}

QSplitter[editorFamilySplitter="true"] {{
    background-color: {p['editor_bg']};
}}

QSplitter[editorFamilySplitter="true"]::handle {{
    background: {p['border_soft']};
    margin: 0;
}}

QFrame[catalogShell="true"],
QListView#toolCatalog,
QListView#toolCatalog::viewport,
QListWidget#toolCatalog,
QListWidget#toolCatalog::viewport,
QListView#setupWorkList,
QListView#setupWorkList::viewport,
QListWidget#setupWorkList,
QListWidget#setupWorkList::viewport,
QListWidget#drawingList,
QListWidget#drawingList::viewport,
QWidget[selectorEmbedded="true"],
QWidget[rowAreaSurface="true"],
QFrame[rowAreaSurface="true"] {{
    background-color: {p['row_area_bg']};
}}

QFrame[card="true"],
QFrame[subCard="true"],
QFrame[detailCard="true"],
QFrame[detailHeader="true"],
QFrame[detailField="true"],
QFrame[toolListCard="true"],
QFrame[workCard="true"],
QFrame[miniAssignmentCard="true"],
QFrame[toolPickerPanel="true"],
QFrame[selectorShell="true"],
QFrame[selectorPane="true"],
QFrame[selectorInfoHeader="true"],
QWidget[previewColumn="true"],
QWidget[previewBody="true"],
QFrame[previewBody="true"],
QFrame[pageCard="true"] {{
    background-color: {p['card_bg']};
    border-color: {p['border']};
}}

QScrollArea#detailScrollArea,
QWidget#detailPanel,
QLabel[detailValue="true"],
QLabel[detailReadonlyValue="true"],
QFrame[detailReadonlyBox="true"] {{
    background-color: {p['card_bg']};
}}

QDialog[workEditorDialog="true"],
QDialog[preferencesDialog="true"],
QDialog[machineConfigDialog="true"],
QDialog#measurementEditorDialog,
QFrame#measurementEditorLeftPanel,
QWidget[editorHostSurface="true"],
QFrame[editorHostSurface="true"],
QWidget[editorPageSurface="true"] {{
    background-color: {p['editor_bg']};
}}

QDialog[workEditorDialog="true"] QLineEdit,
QDialog[workEditorDialog="true"] QTextEdit,
QDialog[workEditorDialog="true"] QPlainTextEdit,
QDialog[workEditorDialog="true"] QComboBox,
QDialog[workEditorDialog="true"] QDateEdit,
QDialog[preferencesDialog="true"] QLineEdit,
QDialog[preferencesDialog="true"] QTextEdit,
QDialog[preferencesDialog="true"] QPlainTextEdit,
QDialog[preferencesDialog="true"] QComboBox,
QDialog[preferencesDialog="true"] QDateEdit,
QDialog#measurementEditorDialog QLineEdit,
QDialog#measurementEditorDialog QTextEdit,
QDialog#measurementEditorDialog QPlainTextEdit,
QDialog#measurementEditorDialog QComboBox,
QDialog#measurementEditorDialog QDateEdit {{
    background-color: {p['card_bg']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
}}

QFrame[editorFieldGroup="true"] {{
    background-color: {p['section_bg']};
    border: 1px solid {p['border']};
    border-radius: 6px;
}}

QGroupBox[editorSection="true"] {{
    background-color: {p['section_bg']};
    border: 1px solid #d0d8e0;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
}}

QDialog[workEditorDialog="true"] QGroupBox[editorSection="true"],
QDialog[machineConfigDialog="true"] QGroupBox[editorSection="true"] {{
    background-color: {p['section_bg']};
    border: 1px solid {p['border']};
    border-radius: 6px;
}}

QGroupBox[editorSection="true"]::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    top: -3px;
    padding: 0 6px;
    color: {p['text_primary']};
    font-size: 10.5pt;
    font-weight: 700;
}}

QGroupBox[editorSection="true"][editorSectionCompact="true"]::title {{
    padding: 0 4px;
    color: {p['text_secondary']};
    font-size: 8pt;
    font-weight: 600;
}}

QWidget[selectorContext="true"] QGroupBox[selectorAssignmentsFrame="true"],
QWidget[selectorContext="true"] QGroupBox[toolIdsPanel="true"],
QWidget[selectorContext="true"] QFrame[selectorScrollFrame="true"] {{
    border: 1px solid {p['border']};
}}

QWidget[selectorContext="true"] QFrame[selectorScrollFrame="true"] {{
    background: transparent;
}}

QLabel[editorSectionMeta="true"],
QLabel[editorSectionHint="true"],
QLabel[editorAxisHeader="true"] {{
    color: {p['text_secondary']};
    background: transparent;
}}

QLabel[editorSectionMeta="true"] {{
    font-size: 9pt;
    padding: 0px 0px 1px 0px;
}}

QLabel[editorAxisHeader="true"] {{
    font-size: 10px;
}}

QLabel[detailReadonlyValue="true"] {{
    border: 1px solid {p['border']};
    border-radius: 6px;
    padding: 6px;
    color: {p['text_primary']};
}}

QFrame[editorFieldCard="true"],
QFrame[catalogHeaderRow="true"],
QFrame[selectorHeader="true"],
QFrame[selectorActionBar="true"],
QFrame[bottomBar="true"],
QWidget[selectorActionBar="true"],
QWidget[editorInlineRow="true"],
QWidget[editorTransparentPanel="true"],
QWidget[sectionHeaderRow="true"],
QFrame[hostTransparent="true"],
QWidget[hostTransparent="true"] {{
    background: transparent;
    border: none;
}}

QFrame[selectorDropTarget="true"] {{
    background-color: {p['section_bg']};
    border: 2px dashed {p['border']};
    border-radius: 8px;
}}

QFrame[selectorDropTarget="true"][activeDropTarget="true"] {{
    background-color: {_mix(p['section_bg'], p['editor_bg'], 0.35)};
    border: 2px solid {p['accent']};
}}

QLabel[selectorEmptyHint="true"],
QLabel[miniAssignmentHint="true"],
QLabel[detailHint="true"],
QLabel[sectionSummary="true"] {{
    color: {p['text_secondary']};
}}

QFrame[editorSeparator="true"] {{
    background-color: {p['border']};
    border: none;
    min-height: 1px;
    max-height: 1px;
}}

QPushButton,
QPushButton[secondaryAction="true"] {{
    color: {p['text_primary']};
    border: 1px solid {p['border']};
    background-color: qlineargradient(x1:0, y1:1, x2:0, y2:0,
                                      stop:0 {p['button_neutral_bottom']}, stop:1 {p['button_neutral_top']});
}}

QPushButton:hover,
QPushButton[secondaryAction="true"]:hover,
QPushButton[panelActionButton="true"]:hover {{
    background-color: qlineargradient(x1:0, y1:1, x2:0, y2:0,
                                      stop:0 {p['button_neutral_hover_bottom']}, stop:1 {p['button_neutral_hover_top']});
}}

QPushButton:pressed,
QPushButton[secondaryAction="true"]:pressed,
QPushButton[panelActionButton="true"]:pressed {{
    background-color: qlineargradient(x1:0, y1:1, x2:0, y2:0,
                                      stop:0 {p['button_neutral_pressed_bottom']}, stop:1 {p['button_neutral_pressed_top']});
}}

QPushButton[panelActionButton="true"],
QPushButton[arrowMoveButton="true"] {{
    border: 1px solid {p['border']};
    color: {p['text_primary']};
}}

QPushButton[selectorToggleButton="true"] {{
    min-height: 28px;
    padding: 4px 12px;
    border: 1px solid {p['border']};
    border-radius: 6px;
    color: {p['text_primary']};
    background-color: qlineargradient(x1:0, y1:1, x2:0, y2:0,
                                      stop:0 {p['button_neutral_bottom']}, stop:1 {p['button_neutral_top']});
}}

QPushButton[selectorToggleButton="true"]:hover {{
    background-color: qlineargradient(x1:0, y1:1, x2:0, y2:0,
                                      stop:0 {p['button_neutral_hover_bottom']}, stop:1 {p['button_neutral_hover_top']});
}}

QPushButton[selectorToggleButton="true"]:pressed {{
    background-color: qlineargradient(x1:0, y1:1, x2:0, y2:0,
                                      stop:0 {p['button_neutral_pressed_bottom']}, stop:1 {p['button_neutral_pressed_top']});
}}

QPushButton[selectorToggleButton="true"]:checked {{
    color: {p['text_primary']};
    border: 1px solid {p['accent']};
    background-color: {_mix(p['section_bg'], p['editor_bg'], 0.35)};
}}

QPushButton[primaryAction="true"],
QPushButton[panelActionButton="true"][primaryAction="true"],
QPushButton[selectorPrimaryActionButton="true"],
QPushButton[navButton="true"][active="true"] {{
    color: #ffffff;
    border: 1px solid {p['accent_pressed']};
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 {p['accent_light']}, stop:1 {p['accent']});
}}

QPushButton[primaryAction="true"]:hover,
QPushButton[panelActionButton="true"][primaryAction="true"]:hover,
QPushButton[selectorPrimaryActionButton="true"]:hover,
QPushButton[navButton="true"][active="true"]:hover {{
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 {p['accent']}, stop:1 {p['accent_hover']});
}}

QPushButton[primaryAction="true"]:pressed,
QPushButton[panelActionButton="true"][primaryAction="true"]:pressed,
QPushButton[selectorPrimaryActionButton="true"]:pressed,
QPushButton[navButton="true"][active="true"]:pressed {{
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 {p['accent_hover']}, stop:1 {p['accent_pressed']});
}}

QPushButton[dangerAction="true"],
QPushButton[panelActionButton="true"][dangerAction="true"] {{
    color: #7d1f22;
    border: 1px solid {_mix(p['accent'], '#ffffff', 0.65)};
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 #fff7f7, stop:1 #f3e3e4);
}}

QToolButton[topBarIconButton="true"] {{
    background: transparent;
    border: none;
}}

QToolButton[topBarIconButton="true"]:hover,
QToolButton#sideNavButton:hover {{
    background-color: {p['icon_hover_bg']};
}}

QToolButton[topBarIconButton="true"]:pressed {{
    background-color: {_rgba(p['accent'], 0.22)};
}}

QToolButton#sideNavButton:checked {{
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 {p['accent_light']}, stop:1 {p['accent']});
    border: 1px solid {p['accent_pressed']};
}}

QTabWidget::pane,
QDialog[workEditorDialog="true"] QTabWidget::pane,
QDialog#measurementEditorDialog QTabWidget::pane {{
    border: 1px solid {p['border']};
    background: {p['editor_bg']};
}}

QTabBar::tab,
QDialog[workEditorDialog="true"] QTabBar::tab,
QDialog#measurementEditorDialog QTabBar::tab {{
    background: {p['tab_inactive']};
    border: 1px solid {p['border']};
    color: {p['text_primary']};
}}

QTabBar::tab:hover,
QDialog[workEditorDialog="true"] QTabBar::tab:hover,
QDialog#measurementEditorDialog QTabBar::tab:hover {{
    background: {p['tab_hover']};
}}

QTabBar::tab:selected,
QDialog[workEditorDialog="true"] QTabBar::tab:selected,
QDialog#measurementEditorDialog QTabBar::tab:selected {{
    background: {p['tab_active']};
    border-bottom-color: {p['tab_active']};
    font-weight: 700;
}}

QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus,
QComboBox:focus,
QDateEdit:focus,
QSpinBox:focus,
QComboBox[modernDropdown="true"]:focus,
QComboBox[zeroCoordCombo="true"]:focus,
QDialog[workEditorDialog="true"] QLineEdit:focus,
QDialog[workEditorDialog="true"] QTextEdit:focus,
QDialog[workEditorDialog="true"] QPlainTextEdit:focus,
QDialog[workEditorDialog="true"] QComboBox:focus,
QDialog[workEditorDialog="true"] QDateEdit:focus,
QDialog[workEditorDialog="true"] QSpinBox:focus,
QDialog[workEditorDialog="true"] QTableWidget#editorPartsTable QLineEdit:focus,
QDialog[workEditorDialog="true"] QTableWidget#editorSparePartsTable QLineEdit:focus {{
    border: 1px solid {p['accent']};
}}

QFrame[toolListCard="true"][selected="true"],
QFrame[toolListCard="true"][selected="true"]:hover,
QFrame[workCard="true"][selected="true"],
QFrame[workCard="true"][selected="true"]:hover,
QFrame[miniAssignmentCard="true"][selected="true"],
QFrame[miniAssignmentCard="true"][selected="true"]:hover,
QDialog[workEditorDialog="true"] QFrame[miniAssignmentCard="true"][selected="true"],
QDialog[workEditorDialog="true"] QFrame[miniAssignmentCard="true"][selected="true"]:hover {{
    border-color: {p['accent']};
}}
""".strip()


def compile_app_stylesheet(style_path: Path, preferences: dict[str, Any] | None) -> str:
    base_style = _load_base_stylesheet(Path(style_path))
    override = build_theme_override_stylesheet(preferences)
    if base_style and override:
        return base_style + "\n\n" + override
    return base_style or override
