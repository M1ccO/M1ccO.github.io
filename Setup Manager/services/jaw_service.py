class JawService:
    JAW_TYPES = ['Soft jaws', 'Hard jaws', 'Spiked jaws', 'Special jaws']
    SPINDLE_SIDES = ['SP1', 'SP2', 'Both']

    @staticmethod
    def _normalize_spindle_side(value: str) -> str:
        text = (value or '').strip()
        if text == 'Main spindle':
            return 'SP1'
        if text == 'Sub spindle':
            return 'SP2'
        return text

    def __init__(self, db):
        self.db = db

    def list_jaws(self, search_text: str = '', view_mode: str = 'all', jaw_type_filter: str = 'All'):
        query = 'SELECT * FROM jaws WHERE 1=1'
        params = []

        mode = (view_mode or 'all').lower()
        if mode == 'main':
            query += " AND spindle_side IN ('SP1', 'Main spindle', 'Both')"
        elif mode == 'sub':
            query += " AND spindle_side IN ('SP2', 'Sub spindle', 'Both')"
        elif mode == 'soft':
            query += " AND jaw_type = 'Soft jaws'"
        elif mode == 'hard_group':
            query += " AND jaw_type IN ('Hard jaws', 'Spiked jaws', 'Special jaws')"

        if jaw_type_filter and jaw_type_filter != 'All':
            if jaw_type_filter == 'Spike/Hard Jaws':
                query += " AND jaw_type IN ('Hard jaws', 'Spiked jaws')"
            elif jaw_type_filter == 'Soft Jaws':
                query += " AND jaw_type = 'Soft jaws'"
            elif jaw_type_filter == 'Special Jaws':
                query += " AND jaw_type = 'Special jaws'"

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
        out = [dict(row) for row in self.db.conn.execute(query, params).fetchall()]
        for jaw in out:
            jaw['spindle_side'] = self._normalize_spindle_side(jaw.get('spindle_side', ''))
        return out

    def get_jaw(self, jaw_id: str):
        row = self.db.conn.execute('SELECT * FROM jaws WHERE jaw_id = ?', (jaw_id,)).fetchone()
        if not row:
            return None
        jaw = dict(row)
        jaw['spindle_side'] = self._normalize_spindle_side(jaw.get('spindle_side', ''))
        return jaw

    def save_jaw(self, jaw: dict):
        jaw_id = (jaw.get('jaw_id', '') or '').strip()
        if not jaw_id:
            raise ValueError('Jaw ID is required.')

        jaw_type = (jaw.get('jaw_type', '') or '').strip()
        if jaw_type not in self.JAW_TYPES:
            raise ValueError('Jaw type is invalid.')

        spindle_side = self._normalize_spindle_side((jaw.get('spindle_side', '') or '').strip())
        if spindle_side not in self.SPINDLE_SIDES:
            raise ValueError('Spindle side is invalid.')

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
            (jaw.get('stl_path', '') or '').strip(),
            (jaw.get('preview_plane', '') or 'XZ').strip(),
            int(jaw.get('preview_rot_x', 0) or 0) % 360,
            int(jaw.get('preview_rot_y', 0) or 0) % 360,
            int(jaw.get('preview_rot_z', 0) or 0) % 360,
        )

        with self.db.conn:
            self.db.conn.execute(
                """
                INSERT INTO jaws (
                    jaw_id, jaw_type, spindle_side, clamping_diameter_text, clamping_length,
                    used_in_work, turning_washer, last_modified, notes, stl_path,
                    preview_plane, preview_rot_x, preview_rot_y, preview_rot_z
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    preview_rot_z=excluded.preview_rot_z
                """,
                payload,
            )

    def delete_jaw(self, jaw_id: str):
        with self.db.conn:
            self.db.conn.execute('DELETE FROM jaws WHERE jaw_id = ?', (jaw_id,))
