import re
from datetime import date

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


SERIAL_PATTERN = re.compile(r"^([A-Z]+)(\d{2})(?:/(\d+))?$")


def index_to_letters(index):
    if index < 0:
        raise ValueError("index must be >= 0")
    value = index
    letters = []
    while True:
        value, rem = divmod(value, 26)
        letters.append(chr(ord("A") + rem))
        if value == 0:
            break
        value -= 1
    return "".join(reversed(letters))


class LogbookService:
    _ROW_COLORS = [
        'EAF4FF',
        'EDF8EA',
        'FFF4E8',
        'F5ECFF',
        'EAF8F8',
        'FFF9E3',
        'FDEEEF',
        'ECEFF3',
    ]

    def __init__(self, database):
        self.db = database

    @staticmethod
    def _normalize_like(value):
        return f"%{(value or '').strip()}%"

    def list_entries(self, search="", filters=None, limit=0):
        filters = filters or {}
        like = self._normalize_like(search)
        clauses = [
            "(work_id LIKE ? OR order_number LIKE ? OR batch_serial LIKE ? OR notes LIKE ?)",
        ]
        params = [like, like, like, like]

        work_filter = (filters.get("work_id") or "").strip()
        if work_filter:
            clauses.append("work_id LIKE ?")
            params.append(self._normalize_like(work_filter))

        order_filter = (filters.get("order_number") or "").strip()
        if order_filter:
            clauses.append("order_number LIKE ?")
            params.append(self._normalize_like(order_filter))

        year_filter = (filters.get("year") or "").strip()
        if year_filter:
            clauses.append("substr(date, 1, 4) = ?")
            params.append(year_filter)

        date_from = (filters.get("date_from") or "").strip()
        if date_from:
            clauses.append("date >= ?")
            params.append(date_from)

        date_to = (filters.get("date_to") or "").strip()
        if date_to:
            clauses.append("date <= ?")
            params.append(date_to)

        limit_clause = f" LIMIT {int(limit)}" if int(limit) > 0 else ""
        rows = self.db.conn.execute(
            f"""
            SELECT id, work_id, order_number, quantity, batch_serial, date, notes
            FROM logbook
            WHERE {' AND '.join(clauses)}
            ORDER BY date DESC, id DESC{limit_clause}
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def latest_entries_by_work_ids(self, work_ids):
        clean_ids = [str(work_id).strip() for work_id in (work_ids or []) if str(work_id).strip()]
        if not clean_ids:
            return {}

        placeholders = ", ".join("?" for _ in clean_ids)
        rows = self.db.conn.execute(
            f"""
            SELECT l1.id, l1.work_id, l1.order_number, l1.quantity, l1.batch_serial, l1.date, l1.notes
            FROM logbook l1
            JOIN (
                SELECT work_id, MAX(date || '|' || printf('%010d', id)) AS max_key
                FROM logbook
                WHERE work_id IN ({placeholders})
                GROUP BY work_id
            ) latest
              ON latest.work_id = l1.work_id
             AND latest.max_key = l1.date || '|' || printf('%010d', l1.id)
            ORDER BY l1.work_id COLLATE NOCASE ASC
            """,
            clean_ids,
        ).fetchall()
        return {row["work_id"]: dict(row) for row in rows}

    def generate_next_serial(self, work_id, year, quantity=None):
        yy = str(int(year))[-2:]
        rows = self.db.conn.execute(
            "SELECT batch_serial FROM logbook WHERE work_id = ? AND substr(date, 1, 4) = ?",
            (work_id, str(int(year))),
        ).fetchall()
        used_indices = []
        for row in rows:
            serial = (row["batch_serial"] or "").strip().upper()
            match = SERIAL_PATTERN.match(serial)
            if not match:
                continue
            letters, serial_yy, _qty = match.groups()
            if serial_yy != yy:
                continue
            index = 0
            for ch in letters:
                index = index * 26 + (ord(ch) - ord("A") + 1)
            used_indices.append(index - 1)

        next_index = (max(used_indices) + 1) if used_indices else 0
        prefix = index_to_letters(next_index)
        return f"{prefix}{yy}"

    def add_entry(self, work_id, order_number, quantity, notes="", custom_serial="", entry_date=None):
        work_id = (work_id or "").strip()
        if not work_id:
            raise ValueError("work_id is required")
        order_number = (order_number or "").strip()
        qty = int(quantity)
        if qty <= 0:
            raise ValueError("quantity must be > 0")

        use_date = entry_date or date.today().isoformat()
        year = int(use_date[:4])
        serial = (custom_serial or "").strip().upper() or self.generate_next_serial(work_id, year, qty)

        with self.db.conn:
            cur = self.db.conn.execute(
                """
                INSERT INTO logbook (work_id, order_number, quantity, batch_serial, date, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (work_id, order_number, qty, serial, use_date, (notes or "").strip()),
            )
            entry_id = cur.lastrowid
        return self.get_entry(entry_id)

    def get_entry(self, entry_id):
        row = self.db.conn.execute("SELECT * FROM logbook WHERE id = ?", (int(entry_id),)).fetchone()
        return dict(row) if row else None

    def delete_entry(self, entry_id):
        with self.db.conn:
            self.db.conn.execute("DELETE FROM logbook WHERE id = ?", (int(entry_id),))

    def export_entries_to_excel(self, entries, output_path):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Logbook"

        headers = ["Date", "Serial", "Work ID", "Order", "Quantity", "Notes"]
        ws.append(headers)
        header_fill = PatternFill(fill_type='solid', fgColor='1F4E78')
        header_font = Font(color='FFFFFF', bold=True)
        thin = Side(style='thin', color='D0D7DE')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border

        unique_work_ids = []
        for entry in entries or []:
            work_id = str(entry.get('work_id', '') or '').strip()
            if work_id and work_id not in unique_work_ids:
                unique_work_ids.append(work_id)
        work_fill = {
            work_id: PatternFill(fill_type='solid', fgColor=self._ROW_COLORS[idx % len(self._ROW_COLORS)])
            for idx, work_id in enumerate(sorted(unique_work_ids))
        }

        for item in entries:
            ws.append(
                [
                    item.get("date", ""),
                    item.get("batch_serial", ""),
                    item.get("work_id", ""),
                    item.get("order_number", ""),
                    item.get("quantity", 0),
                    item.get("notes", ""),
                ]
            )
            row_idx = ws.max_row
            fill = work_fill.get(str(item.get('work_id', '') or '').strip())
            for col in range(1, len(headers) + 1):
                cell = ws.cell(row=row_idx, column=col)
                cell.border = border
                if fill is not None:
                    cell.fill = fill
                if col == 5 and isinstance(cell.value, int):
                    cell.number_format = '0'
                    cell.alignment = Alignment(horizontal='right', vertical='center')
                else:
                    cell.alignment = Alignment(horizontal='left', vertical='center')

        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions

        for idx in range(1, len(headers) + 1):
            letter = get_column_letter(idx)
            max_len = len(headers[idx - 1])
            for row_idx in range(2, ws.max_row + 1):
                value = ws.cell(row=row_idx, column=idx).value
                if value is None:
                    continue
                max_len = max(max_len, len(str(value)))
            ws.column_dimensions[letter].width = min(max(max_len + 2, 12), 48)

        ws.row_dimensions[1].height = 24
        for row_idx in range(2, ws.max_row + 1):
            ws.row_dimensions[row_idx].height = 21

        wb.save(output_path)
