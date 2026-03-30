import json
from pathlib import Path


class SettingsService:
    def __init__(self, path: Path):
        self.path = path

    def load(self):
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding='utf-8'))
            except Exception:
                return {}
        return {}

    def save(self, payload: dict):
        self.path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
