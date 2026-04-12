from __future__ import annotations

import json
from pathlib import Path


TOOLS_PREFIX = 'tools://'
JAWS_PREFIX = 'jaws://'


def read_model_roots(
    preferences_path: Path,
    default_tools_root: Path,
    default_jaws_root: Path,
) -> tuple[Path, Path]:
    defaults = (Path(default_tools_root), Path(default_jaws_root))
    try:
        payload = json.loads(Path(preferences_path).read_text(encoding='utf-8'))
    except Exception:
        return defaults

    if not isinstance(payload, dict):
        return defaults

    tools_value = str(payload.get('tools_models_root') or '').strip()
    jaws_value = str(payload.get('jaws_models_root') or '').strip()

    tools_root = Path(tools_value) if tools_value else defaults[0]
    jaws_root = Path(jaws_value) if jaws_value else defaults[1]
    return tools_root, jaws_root


def normalize_model_path_for_storage(raw_path: str, root: Path, prefix: str) -> str:
    text = str(raw_path or '').strip()
    if not text:
        return ''

    normalized = text.replace('\\', '/')
    if normalized.startswith(TOOLS_PREFIX) or normalized.startswith(JAWS_PREFIX):
        return normalized

    path = Path(text).expanduser()
    if not path.is_absolute():
        return text

    absolute = path.resolve()
    root_path = Path(root).expanduser().resolve()
    try:
        relative = absolute.relative_to(root_path)
    except Exception:
        return str(absolute)

    return f'{prefix}{relative.as_posix()}'


def resolve_model_path(raw_path: str, tools_root: Path, jaws_root: Path) -> Path:
    text = str(raw_path or '').strip()
    if not text:
        return Path('')

    normalized = text.replace('\\', '/')
    if normalized.startswith(TOOLS_PREFIX):
        rel = normalized[len(TOOLS_PREFIX):].strip('/')
        return (Path(tools_root) / Path(rel)).resolve()
    if normalized.startswith(JAWS_PREFIX):
        rel = normalized[len(JAWS_PREFIX):].strip('/')
        return (Path(jaws_root) / Path(rel)).resolve()

    path = Path(text).expanduser()
    if path.is_absolute():
        return path.resolve()

    tools_candidate = (Path(tools_root) / path).resolve()
    if tools_candidate.exists():
        return tools_candidate

    jaws_candidate = (Path(jaws_root) / path).resolve()
    if jaws_candidate.exists():
        return jaws_candidate

    return path.resolve()


def format_model_path_for_display(raw_path: str, tools_root: Path, jaws_root: Path) -> str:
    text = str(raw_path or '').strip()
    if not text:
        return ''

    normalized = text.replace('\\', '/')
    if normalized.startswith(TOOLS_PREFIX):
        return normalized[len(TOOLS_PREFIX):].strip('/')
    if normalized.startswith(JAWS_PREFIX):
        return normalized[len(JAWS_PREFIX):].strip('/')

    path = Path(text).expanduser()
    if path.is_absolute():
        resolved = path.resolve()
        for root in (Path(tools_root).expanduser().resolve(), Path(jaws_root).expanduser().resolve()):
            try:
                return resolved.relative_to(root).as_posix()
            except Exception:
                continue
        return str(resolved)

    return normalized
