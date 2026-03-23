from __future__ import annotations

import json
from pathlib import Path


DEFAULT_UI_PREFERENCES = {
    "language": "en",
    "font_family": "Segoe UI",
    "color_theme": "classic",
}

SUPPORTED_LANGUAGES = {"en", "fi"}
SUPPORTED_FONTS = {"Segoe UI", "Tahoma", "Verdana"}
SUPPORTED_THEMES = {"classic", "graphite"}


def _normalize_preferences(payload: dict | None) -> dict:
    data = dict(DEFAULT_UI_PREFERENCES)
    if isinstance(payload, dict):
        data.update(payload)

    language = str(data.get("language") or DEFAULT_UI_PREFERENCES["language"]).strip().lower()
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_UI_PREFERENCES["language"]
    data["language"] = language

    font_family = str(data.get("font_family") or DEFAULT_UI_PREFERENCES["font_family"]).strip()
    if font_family not in SUPPORTED_FONTS:
        font_family = DEFAULT_UI_PREFERENCES["font_family"]
    data["font_family"] = font_family

    theme = str(data.get("color_theme") or DEFAULT_UI_PREFERENCES["color_theme"]).strip().lower()
    if theme not in SUPPORTED_THEMES:
        theme = DEFAULT_UI_PREFERENCES["color_theme"]
    data["color_theme"] = theme

    return data


class UiPreferencesService:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict:
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            return _normalize_preferences(payload)
        return dict(DEFAULT_UI_PREFERENCES)

    def save(self, payload: dict) -> dict:
        normalized = _normalize_preferences(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
        return normalized

