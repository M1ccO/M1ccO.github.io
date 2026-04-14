from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class LocalizationService:
    def __init__(self, i18n_dir: Path, fallback_language: str = "en"):
        self.i18n_dir = Path(i18n_dir)
        self.shared_i18n_dir = self._resolve_shared_i18n_dir(self.i18n_dir)
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
                logger.debug("localization: format failed for key=%r kwargs=%r", key, kwargs)
        return text

    def _load_catalog(self, language: str) -> dict:
        merged = {}
        if self.shared_i18n_dir is not None:
            merged.update(self._read_catalog_file(self.shared_i18n_dir / f"{language}.json"))
        merged.update(self._read_catalog_file(self.i18n_dir / f"{language}.json"))
        return merged

    @staticmethod
    def _read_catalog_file(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("localization: failed to load catalog %s", path, exc_info=True)
            return {}
        if not isinstance(payload, dict):
            logger.warning("localization: catalog %s is not a JSON object", path)
            return {}
        return {str(k): str(v) for k, v in payload.items()}

    @staticmethod
    def _resolve_shared_i18n_dir(i18n_dir: Path) -> Path | None:
        # App i18n lives at <workspace>/<App Name>/i18n; shared catalog is <workspace>/shared/i18n.
        workspace_root = i18n_dir.resolve().parents[1]
        candidate = workspace_root / "shared" / "i18n"
        return candidate if candidate.exists() else None
