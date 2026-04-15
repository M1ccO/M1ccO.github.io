import json
import sqlite3
from pathlib import Path
cfg = json.loads(Path('.runtime/machine_configurations.json').read_text(encoding='utf-8'))
aid = cfg.get('active_config_id')
active = next((x for x in cfg.get('configurations', []) if x.get('id') == aid), None)
if not active:
    raise SystemExit('No active config found')
profile_key = str(active.get('machine_profile_key') or '').strip().lower()
setup_db = Path(active.get('setup_db_path') or '')
if not profile_key:
    raise SystemExit('Active config has empty machine_profile_key')
conn = sqlite3.connect(str(setup_db))
cur = conn.cursor()
cur.execute("INSERT INTO app_config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ('machine_profile_key', profile_key))
conn.commit()
cur.execute("SELECT value FROM app_config WHERE key='machine_profile_key'")
print('synced_db_profile_key:', cur.fetchone()[0])
conn.close()
print('setup_db:', setup_db)
