"""Cards page — setup card and dispatch card workflow controls."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


class CardsPage(QWidget):
    """Provides quick access to setup card and dispatch card printing.

    Shows a list of recent logbook entries across all works. The user
    selects a run entry, then prints either a full setup card or a compact
    dispatch card (suitable for order-floor use).
    """

    def __init__(self, work_service, logbook_service, print_service, parent=None):
        super().__init__(parent)
        self.work_service = work_service
        self.logbook_service = logbook_service
        self.print_service = print_service

        self._entries: list = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        title = QLabel("Cards")
        title.setProperty("pageTitle", True)
        root.addWidget(title)

        subtitle = QLabel(
            "Select a recent run below, then print a setup card (full detail) or a dispatch card (compact summary)."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("sectionSummary", True)
        root.addWidget(subtitle)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: recent run list ─────────────────────────────────────
        left_host = QWidget()
        left_layout = QVBoxLayout(left_host)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        list_title = QLabel("Recent Runs")
        list_title.setProperty("sectionTitle", True)
        left_layout.addWidget(list_title)

        self.run_list = QListWidget()
        self.run_list.currentItemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.run_list, 1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setProperty("panelActionButton", True)
        refresh_btn.clicked.connect(self.refresh_runs)
        left_layout.addWidget(refresh_btn)

        splitter.addWidget(left_host)

        # ── Right: detail + actions ───────────────────────────────────
        right_host = QWidget()
        right_layout = QVBoxLayout(right_host)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        detail_title = QLabel("Run Details")
        detail_title.setProperty("sectionTitle", True)
        right_layout.addWidget(detail_title)

        self.detail_card = QFrame()
        self.detail_card.setProperty("detailCard", True)
        detail_card_layout = QVBoxLayout(self.detail_card)
        detail_card_layout.setContentsMargins(16, 14, 16, 14)
        detail_card_layout.setSpacing(6)
        self.detail_label = QLabel("Select a run to see details.")
        self.detail_label.setWordWrap(True)
        self.detail_label.setProperty("detailValue", True)
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_card_layout.addWidget(self.detail_label)
        right_layout.addWidget(self.detail_card)

        action_label = QLabel("Print")
        action_label.setProperty("sectionTitle", True)
        right_layout.addWidget(action_label)

        btn_row = QHBoxLayout()
        self.print_setup_btn = QPushButton("View Setup Card")
        self.print_setup_btn.setProperty("panelActionButton", True)
        self.print_setup_btn.clicked.connect(self._print_setup_card)
        self.print_setup_btn.setEnabled(False)

        self.print_dispatch_btn = QPushButton("Print Dispatch Card")
        self.print_dispatch_btn.setProperty("panelActionButton", True)
        self.print_dispatch_btn.clicked.connect(self._print_dispatch_card)
        self.print_dispatch_btn.setEnabled(False)

        btn_row.addWidget(self.print_setup_btn)
        btn_row.addWidget(self.print_dispatch_btn)
        btn_row.addStretch(1)
        right_layout.addLayout(btn_row)

        right_layout.addStretch(1)
        splitter.addWidget(right_host)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, 1)

        self.refresh_runs()

    # ------------------------------------------------------------------

    def refresh_runs(self):
        """Reload the 40 most recent logbook entries across all works."""
        self.run_list.clear()
        self._entries = []
        try:
            entries = self.logbook_service.list_entries(filters={}, limit=40)
        except Exception:
            entries = []

        for entry in entries:
            work_id = entry.get("work_id", "")
            serial = entry.get("batch_serial", "")
            order = entry.get("order_number", "")
            date = entry.get("date", "")
            qty = entry.get("quantity", "")
            label = f"{date}  |  {work_id}  |  {serial}"
            if order:
                label += f"  |  Order: {order}"
            if qty:
                label += f"  |  Qty: {qty}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, len(self._entries))
            self._entries.append(entry)
            self.run_list.addItem(item)

    def _current_entry(self):
        item = self.run_list.currentItem()
        if item is None:
            return None, None
        idx = item.data(Qt.UserRole)
        entry = self._entries[idx] if 0 <= idx < len(self._entries) else None
        if entry is None:
            return None, None
        work = self.work_service.get_work(entry.get("work_id", ""))
        return entry, work

    def _on_selection_changed(self, current, _previous):
        if current is None:
            self.detail_label.setText("Select a run to see details.")
            self.print_setup_btn.setEnabled(False)
            self.print_dispatch_btn.setEnabled(False)
            return

        entry, work = self._current_entry()
        if entry is None or work is None:
            self.detail_label.setText("Work data not found.")
            self.print_setup_btn.setEnabled(False)
            self.print_dispatch_btn.setEnabled(False)
            return

        lines = [
            f"Work ID:      {work.get('work_id', '-')}",
            f"Drawing ID:   {work.get('drawing_id', '-') or '-'}",
            f"Description:  {work.get('description', '-') or '-'}",
            "",
            f"Batch serial: {entry.get('batch_serial', '-')}",
            f"Order: {entry.get('order_number', '-') or '-'}",
            f"Quantity:     {entry.get('quantity', '-')}",
            f"Date:         {entry.get('date', '-')}",
            "",
            f"Main jaw:     {work.get('main_jaw_id', '-') or '-'}",
            f"Sub jaw:      {work.get('sub_jaw_id', '-') or '-'}",
        ]
        self.detail_label.setText("\n".join(lines))
        self.print_setup_btn.setEnabled(True)
        self.print_dispatch_btn.setEnabled(True)

    # ------------------------------------------------------------------

    def _print_setup_card(self):
        entry, work = self._current_entry()
        if not entry or not work:
            QMessageBox.information(self, "No selection", "Select a run entry first.")
            return
        work_id = work.get("work_id", "entry")
        default_name = f"setup_card_{work_id}.pdf"
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Save setup card", str(Path.home() / default_name), "PDF Files (*.pdf)"
        )
        if not output_path:
            return
        try:
            self.print_service.generate_setup_card(work, entry, output_path)
            QMessageBox.information(self, "Done", f"Setup card saved:\n{output_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Print failed", str(exc))

    def _print_dispatch_card(self):
        entry, work = self._current_entry()
        if not entry or not work:
            QMessageBox.information(self, "No selection", "Select a run entry first.")
            return
        work_id = work.get("work_id", "entry")
        default_name = f"dispatch_{work_id}.pdf"
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Save dispatch card", str(Path.home() / default_name), "PDF Files (*.pdf)"
        )
        if not output_path:
            return
        try:
            self.print_service.generate_dispatch_card(work, entry, output_path)
            QMessageBox.information(self, "Done", f"Dispatch card saved:\n{output_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Print failed", str(exc))
