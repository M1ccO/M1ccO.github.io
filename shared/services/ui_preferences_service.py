from __future__ import annotations

import json
from pathlib import Path


SUPPORTED_LANGUAGES = {"en", "fi"}
SUPPORTED_FONTS = {"Segoe UI", "Tahoma", "Verdana"}
SUPPORTED_THEMES = {"classic", "graphite"}
SUPPORTED_DETACHED_PREVIEW_MODES = {"follow_last", "left", "right", "current"}


def _default_model_roots() -> tuple[Path, Path]:
    workspace_root = Path(__file__).resolve().parents[2]
    base_dir = workspace_root / "Tools and jaws Library" / "assets" / "3d"
    return base_dir / "tools", base_dir / "jaws"


_DEFAULT_TOOLS_ROOT, _DEFAULT_JAWS_ROOT = _default_model_roots()


def _base_defaults() -> dict:
    return {
        "language": "en",
        "font_family": "Segoe UI",
        "color_theme": "classic",
        "machine_profile_key": "ntx_2sp_2h",
        "tools_models_root": str(_DEFAULT_TOOLS_ROOT),
        "jaws_models_root": str(_DEFAULT_JAWS_ROOT),
        "enable_assembly_transform": False,
        "enable_drawings_tab": True,
        "detached_preview_policy": {"mode": "follow_last"},
    }


class UiPreferencesService:
    def __init__(self, path: Path, include_setup_db_path: bool = False):
        self.path = Path(path)
        self.include_setup_db_path = bool(include_setup_db_path)
        self.default_preferences = _base_defaults()
        if self.include_setup_db_path:
            self.default_preferences["setup_db_path"] = ""

    def _normalize_preferences(self, payload: dict | None) -> dict:
        data = dict(self.default_preferences)
        if isinstance(payload, dict):
            data.update(payload)

        language = str(data.get("language") or self.default_preferences["language"]).strip().lower()
        if language not in SUPPORTED_LANGUAGES:
            language = self.default_preferences["language"]
        data["language"] = language

        font_family = str(data.get("font_family") or self.default_preferences["font_family"]).strip()
        if font_family not in SUPPORTED_FONTS:
            font_family = self.default_preferences["font_family"]
        data["font_family"] = font_family

        theme = str(data.get("color_theme") or self.default_preferences["color_theme"]).strip().lower()
        if theme not in SUPPORTED_THEMES:
            theme = self.default_preferences["color_theme"]
        data["color_theme"] = theme

        machine_profile_key = str(
            data.get("machine_profile_key") or self.default_preferences["machine_profile_key"]
        ).strip().lower()
        if not machine_profile_key:
            machine_profile_key = self.default_preferences["machine_profile_key"]
        data["machine_profile_key"] = machine_profile_key

        tools_root = str(data.get("tools_models_root") or self.default_preferences["tools_models_root"]).strip()
        jaws_root = str(data.get("jaws_models_root") or self.default_preferences["jaws_models_root"]).strip()
        data["tools_models_root"] = str(Path(tools_root).expanduser().resolve())
        data["jaws_models_root"] = str(Path(jaws_root).expanduser().resolve())

        if self.include_setup_db_path:
            setup_db_path = str(data.get("setup_db_path") or "").strip()
            if setup_db_path:
                data["setup_db_path"] = str(Path(setup_db_path).expanduser().resolve())
            else:
                data["setup_db_path"] = ""
        else:
            data.pop("setup_db_path", None)

        data["enable_assembly_transform"] = bool(data.get("enable_assembly_transform", False))
        data["enable_drawings_tab"] = bool(data.get("enable_drawings_tab", True))

        policy = data.get("detached_preview_policy")
        if not isinstance(policy, dict):
            policy = {}
        mode = str(policy.get("mode") or "follow_last").strip().lower()
        if mode not in SUPPORTED_DETACHED_PREVIEW_MODES:
            mode = "follow_last"
        data["detached_preview_policy"] = {"mode": mode}

        return data

    def load(self) -> dict:
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            normalized = self._normalize_preferences(payload)
        else:
            normalized = self._normalize_preferences({})

        Path(normalized["tools_models_root"]).mkdir(parents=True, exist_ok=True)
        Path(normalized["jaws_models_root"]).mkdir(parents=True, exist_ok=True)
        return normalized

    def save(self, payload: dict) -> dict:
        normalized = self._normalize_preferences(payload)
        Path(normalized["tools_models_root"]).mkdir(parents=True, exist_ok=True)
        Path(normalized["jaws_models_root"]).mkdir(parents=True, exist_ok=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
        return normalized

    def get_machine_profile_key(self) -> str:
        """Return persisted machine profile key with default fallback."""
        prefs = self.load()
        return str(prefs.get("machine_profile_key") or self.default_preferences["machine_profile_key"]).strip().lower()

    def set_machine_profile_key(self, key: str) -> dict:
        """Persist machine profile key while keeping other preferences unchanged."""
        prefs = self.load()
        prefs["machine_profile_key"] = str(key or self.default_preferences["machine_profile_key"]).strip().lower()
        return self.save(prefs)
