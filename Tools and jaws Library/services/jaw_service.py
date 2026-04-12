import json

from config import JAW_MODELS_ROOT_DEFAULT, SHARED_UI_PREFERENCES_PATH, TOOL_MODELS_ROOT_DEFAULT
from shared.model_paths import JAWS_PREFIX, normalize_model_path_for_storage, read_model_roots


class JawService:
    JAW_TYPES = ['Soft jaws', 'Hard jaws', 'Spiked jaws', 'Special jaws']
    SPINDLE_SIDES = ['Main spindle', 'Sub spindle', 'Both']

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _parse_json_list(raw, default=None):
        fallback = [] if default is None else list(default)
        if isinstance(raw, list):
            return raw
        text = str(raw or '').strip()
        if not text:
            return fallback
        try:
            parsed = json.loads(text)
        except Exception:
            return fallback
        return parsed if isinstance(parsed, list) else fallback

    @staticmethod
    def _normalize_measurement_overlays(raw) -> list[dict]:
        overlays = []
        for item in JawService._parse_json_list(raw):
            if isinstance(item, dict):
                overlays.append(dict(item))
        return overlays

    @staticmethod
    def _normalize_selected_parts(raw) -> list[int]:
        values: list[int] = []
        for item in JawService._parse_json_list(raw):
            try:
                numeric = int(item)
            except Exception:
                continue
            if numeric >= 0:
                values.append(numeric)
        return values

    def _normalize_jaw_3d_payload(self, jaw: dict) -> dict:
        data = dict(jaw or {})
        data['measurement_overlays'] = self._normalize_measurement_overlays(
            data.get('measurement_overlays', [])
        )
        data['preview_selected_parts'] = self._normalize_selected_parts(
            data.get('preview_selected_parts', [])
        )
        try:
            selected_part = int(data.get('preview_selected_part', -1) or -1)
        except Exception:
            selected_part = -1
        data['preview_selected_part'] = selected_part if selected_part >= 0 else -1
        transform_mode = str(data.get('preview_transform_mode', 'translate') or 'translate').strip().lower()
        data['preview_transform_mode'] = transform_mode if transform_mode in {'translate', 'rotate'} else 'translate'
        data['preview_fine_transform'] = bool(data.get('preview_fine_transform', False))
        return data

    @staticmethod
    def _norm(value: str) -> str:
        return str(value or '').strip().lower().replace(' ', '_').replace('/', '_')

    def list_jaws(self, search_text: str = '', view_mode: str = 'all', jaw_type_filter: str = 'All'):
        query = 'SELECT * FROM jaws WHERE 1=1'
        params = []

        mode = (view_mode or 'all').lower()
        if mode == 'main':
            query += (
                " AND ("
                " lower(spindle_side) IN ('main spindle', 'both')"
                " OR lower(spindle_side) LIKE '%main%'"
                " OR lower(spindle_side) LIKE '%paa%'"
                " OR lower(spindle_side) LIKE '%molem%'"
                " OR lower(spindle_side) LIKE '%both%'"
                " )"
            )
        elif mode == 'sub':
            query += (
                " AND ("
                " lower(spindle_side) IN ('sub spindle', 'both')"
                " OR lower(spindle_side) LIKE '%sub%'"
                " OR lower(spindle_side) LIKE '%vasta%'"
                " OR lower(spindle_side) LIKE '%molem%'"
                " OR lower(spindle_side) LIKE '%both%'"
                " )"
            )
        elif mode == 'soft':
            query += (
                " AND ("
                " lower(jaw_type) = 'soft jaws'"
                " OR lower(jaw_type) LIKE '%soft%'"
                " OR lower(jaw_type) LIKE '%pehme%'"
                " )"
            )
        elif mode == 'hard_group':
            query += (
                " AND ("
                " lower(jaw_type) IN ('hard jaws', 'spiked jaws', 'special jaws')"
                " OR lower(jaw_type) LIKE '%hard%'"
                " OR lower(jaw_type) LIKE '%kova%'"
                " OR lower(jaw_type) LIKE '%spiked%'"
                " OR lower(jaw_type) LIKE '%piikki%'"
                " OR lower(jaw_type) LIKE '%special%'"
                " OR lower(jaw_type) LIKE '%eriko%'"
                " )"
            )

        normalized_filter = self._norm(jaw_type_filter)
        if normalized_filter and normalized_filter not in {'all'}:
            if normalized_filter in {'spike_hard_jaws', 'hard_group'}:
                query += (
                    " AND ("
                    " lower(jaw_type) IN ('hard jaws', 'spiked jaws')"
                    " OR lower(jaw_type) LIKE '%hard%'"
                    " OR lower(jaw_type) LIKE '%kova%'"
                    " OR lower(jaw_type) LIKE '%spiked%'"
                    " OR lower(jaw_type) LIKE '%piikki%'"
                    " )"
                )
            elif normalized_filter in {'soft_jaws', 'soft'}:
                query += (
                    " AND ("
                    " lower(jaw_type) = 'soft jaws'"
                    " OR lower(jaw_type) LIKE '%soft%'"
                    " OR lower(jaw_type) LIKE '%pehme%'"
                    " )"
                )
            elif normalized_filter in {'special_jaws', 'special'}:
                query += (
                    " AND ("
                    " lower(jaw_type) = 'special jaws'"
                    " OR lower(jaw_type) LIKE '%special%'"
                    " OR lower(jaw_type) LIKE '%eriko%'"
                    " )"
                )

        if search_text:
            token = f"%{search_text.lower()}%"
            query += (
                ' AND ('
                'lower(jaw_id) LIKE ? OR '
                'lower(jaw_type) LIKE ? OR '
                'lower(spindle_side) LIKE ? OR '
                'lower(clamping_diameter_text) LIKE ? OR '
                'lower(clamping_length) LIKE ? OR '
                'lower(used_in_work) LIKE ? OR '
                'lower(turning_washer) LIKE ? OR '
                'lower(notes) LIKE ?'
                ')'
            )
            params.extend([token] * 8)

        query += ' ORDER BY jaw_id'
        return [dict(row) for row in self.db.conn.execute(query, params).fetchall()]

    def get_jaw(self, jaw_id: str):
        row = self.db.conn.execute('SELECT * FROM jaws WHERE jaw_id = ?', (jaw_id,)).fetchone()
        if not row:
            return None
        return self._normalize_jaw_3d_payload(dict(row))

    def save_jaw(self, jaw: dict):
        jaw_id = (jaw.get('jaw_id', '') or '').strip()
        if not jaw_id:
            raise ValueError('Jaw ID is required.')

        jaw_type = (jaw.get('jaw_type', '') or '').strip()
        if jaw_type not in self.JAW_TYPES:
            raise ValueError('Jaw type is invalid.')

        spindle_side = (jaw.get('spindle_side', '') or '').strip()
        if spindle_side not in self.SPINDLE_SIDES:
            raise ValueError('Spindle side is invalid.')

        _, jaws_models_root = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            JAW_MODELS_ROOT_DEFAULT,
        )
        normalized_stl_path = normalize_model_path_for_storage(
            jaw.get('stl_path', ''),
            jaws_models_root,
            JAWS_PREFIX,
        )

        payload = (
            jaw_id,
            jaw_type,
            spindle_side,
            (jaw.get('clamping_diameter_text', '') or '').strip(),
            (jaw.get('clamping_length', '') or '').strip(),
            (jaw.get('used_in_work', '') or '').strip(),
            (jaw.get('turning_washer', '') or '').strip(),
            (jaw.get('last_modified', '') or '').strip(),
            (jaw.get('notes', '') or '').strip(),
            normalized_stl_path,
            (jaw.get('preview_plane', '') or 'XZ').strip(),
            int(jaw.get('preview_rot_x', 0) or 0) % 360,
            int(jaw.get('preview_rot_y', 0) or 0) % 360,
            int(jaw.get('preview_rot_z', 0) or 0) % 360,
            json.dumps(self._normalize_measurement_overlays(jaw.get('measurement_overlays', []))),
            int(jaw.get('preview_selected_part', -1) or -1),
            json.dumps(self._normalize_selected_parts(jaw.get('preview_selected_parts', []))),
            (
                'rotate'
                if str(jaw.get('preview_transform_mode', 'translate') or 'translate').strip().lower() == 'rotate'
                else 'translate'
            ),
            1 if bool(jaw.get('preview_fine_transform', False)) else 0,
        )

        with self.db.conn:
            self.db.conn.execute(
                """
                INSERT INTO jaws (
                    jaw_id, jaw_type, spindle_side, clamping_diameter_text, clamping_length,
                    used_in_work, turning_washer, last_modified, notes, stl_path,
                    preview_plane, preview_rot_x, preview_rot_y, preview_rot_z,
                    measurement_overlays, preview_selected_part, preview_selected_parts,
                    preview_transform_mode, preview_fine_transform
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(jaw_id) DO UPDATE SET
                    jaw_type=excluded.jaw_type,
                    spindle_side=excluded.spindle_side,
                    clamping_diameter_text=excluded.clamping_diameter_text,
                    clamping_length=excluded.clamping_length,
                    used_in_work=excluded.used_in_work,
                    turning_washer=excluded.turning_washer,
                    last_modified=excluded.last_modified,
                    notes=excluded.notes,
                    stl_path=excluded.stl_path,
                    preview_plane=excluded.preview_plane,
                    preview_rot_x=excluded.preview_rot_x,
                    preview_rot_y=excluded.preview_rot_y,
                    preview_rot_z=excluded.preview_rot_z,
                    measurement_overlays=excluded.measurement_overlays,
                    preview_selected_part=excluded.preview_selected_part,
                    preview_selected_parts=excluded.preview_selected_parts,
                    preview_transform_mode=excluded.preview_transform_mode,
                    preview_fine_transform=excluded.preview_fine_transform
                """,
                payload,
            )

    def delete_jaw(self, jaw_id: str):
        with self.db.conn:
            self.db.conn.execute('DELETE FROM jaws WHERE jaw_id = ?', (jaw_id,))
