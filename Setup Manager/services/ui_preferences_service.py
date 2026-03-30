from __future__ import annotations

import json
from pathlib import Path


def _default_model_roots() -> tuple[Path, Path]:
    workspace_root = Path(__file__).resolve().parents[2]
    base_dir = workspace_root / "Tools and jaws Library" / "assets" / "3d"
    return base_dir / "tools", base_dir / "jaws"


_DEFAULT_TOOLS_ROOT, _DEFAULT_JAWS_ROOT = _default_model_roots()


DEFAULT_UI_PREFERENCES = {
    "language": "en",
    "font_family": "Segoe UI",
    "color_theme": "classic",
    "tools_models_root": str(_DEFAULT_TOOLS_ROOT),
    "jaws_models_root": str(_DEFAULT_JAWS_ROOT),
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

    tools_root = str(data.get("tools_models_root") or DEFAULT_UI_PREFERENCES["tools_models_root"]).strip()
    jaws_root = str(data.get("jaws_models_root") or DEFAULT_UI_PREFERENCES["jaws_models_root"]).strip()
    data["tools_models_root"] = str(Path(tools_root).expanduser().resolve())
    data["jaws_models_root"] = str(Path(jaws_root).expanduser().resolve())

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
            normalized = _normalize_preferences(payload)
        else:
            normalized = _normalize_preferences({})

        Path(normalized["tools_models_root"]).mkdir(parents=True, exist_ok=True)
        Path(normalized["jaws_models_root"]).mkdir(parents=True, exist_ok=True)
        return normalized

    def save(self, payload: dict) -> dict:
        normalized = _normalize_preferences(payload)
        Path(normalized["tools_models_root"]).mkdir(parents=True, exist_ok=True)
        Path(normalized["jaws_models_root"]).mkdir(parents=True, exist_ok=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
        return normalized

