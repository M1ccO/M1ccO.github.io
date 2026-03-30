from __future__ import annotations

import json
from pathlib import Path


class LocalizationService:
    def __init__(self, i18n_dir: Path, fallback_language: str = "en"):
        self.i18n_dir = Path(i18n_dir)
        self.fallback_language = fallback_language
        self.language = fallback_language
        self._fallback_catalog = self._load_catalog(fallback_language)
        self._catalog = dict(self._fallback_catalog)

    def set_language(self, language: str):
        requested = str(language or "").strip().lower() or self.fallback_language
        loaded = self._load_catalog(requested)
        if not loaded and requested != self.fallback_language:
            requested = self.fallback_language
            loaded = dict(self._fallback_catalog)
        self.language = requested
        self._catalog = loaded or dict(self._fallback_catalog)

    def t(self, key: str, default: str | None = None, **kwargs) -> str:
        text = self._catalog.get(key)
        if text is None:
            text = self._fallback_catalog.get(key)
        if text is None:
            text = default if default is not None else key
        if kwargs:
            try:
                text = text.format(**kwargs)
            except Exception:
                pass
        return text

    def _load_catalog(self, language: str) -> dict:
        path = self.i18n_dir / f"{language}.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(k): str(v) for k, v in payload.items()}

