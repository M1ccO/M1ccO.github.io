import json
from typing import Any

_EVENT_PREFIXES = {
    'TRANSFORM': 'TRANSFORM:',
    'TRANSFORM_BATCH': 'TRANSFORM_BATCH:',
    'PART_SELECTED': 'PART_SELECTED:',
    'PART_SELECTIONS': 'PART_SELECTIONS:',
    'POINT_PICKED': 'POINT_PICKED:',
    'MEASUREMENT_UPDATED': 'MEASUREMENT_UPDATED:',
}


def build_js_call(function_name: str, *args: Any) -> str:
    args_json = ', '.join(json.dumps(arg) for arg in args)
    return f"window.{function_name} && window.{function_name}({args_json});"


def parse_title_event(title: str) -> tuple[str, Any] | None:
    text = str(title or '')
    for event_name, prefix in _EVENT_PREFIXES.items():
        if not text.startswith(prefix):
            continue
        raw = text[len(prefix):]
        if event_name == 'PART_SELECTED':
            try:
                return event_name, int(raw)
            except ValueError:
                return None
        try:
            return event_name, json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def normalize_index_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, int):
            result.append(item)
            continue
        text = str(item).strip()
        if text and text.lstrip('-').isdigit():
            result.append(int(text))
    return result
