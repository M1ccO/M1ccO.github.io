import json
import sqlite3
from pathlib import Path
cfg = json.loads(Path('.runtime/machine_configurations.json').read_text(encoding='utf-8'))
aid = cfg.get('active_config_id')
active = next((x for x in cfg.get('configurations', []) if x.get('id') == aid), {})
print('active_config:', active.get('name'), active.get('id'))
print('config_profile_key:', active.get('machine_profile_key'))
db = Path(active.get('setup_db_path') or '')
print('setup_db:', db)
conn = sqlite3.connect(str(db))
cur = conn.cursor()
cur.execute("SELECT value FROM app_config WHERE key='machine_profile_key'")
row = cur.fetchone()
print('db_profile_key:', row[0] if row else '<missing>')
conn.close()
