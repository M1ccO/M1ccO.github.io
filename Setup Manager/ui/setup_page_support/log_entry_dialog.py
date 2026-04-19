"""Log entry dialog for adding logbook entries to a setup work."""

from __future__ import annotations

from datetime import date
from typing import Callable

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
)

try:
    from shared.ui.helpers.editor_helpers import (
        apply_shared_checkbox_style,
        create_titled_section,
        setup_editor_dialog,
    )
except ModuleNotFoundError:
    from editor_helpers import (  # type: ignore[no-redef]
        apply_shared_checkbox_style,
        create_titled_section,
        setup_editor_dialog,
    )


class LogEntryDialog(QDialog):
    def __init__(
        self,
        work_id,
        next_serial="",
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or "")
        self._save_and_print = False
        self._next_serial_value = (next_serial or "").strip().upper()
        self._default_export_date = date.today().isoformat()
        self._default_export_date_display = date.today().strftime("%d/%m/%Y")
        self.setWindowTitle(
            self._t("setup_page.log_entry.title_with_work", "Add Logbook Entry - {work_id}", work_id=work_id)
        )
        self.setObjectName("logEntryDialog")
        self.setAttribute(Qt.WA_StyledBackground, True)
        setup_editor_dialog(self)
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignTop)

        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.setSpacing(12)
        toggle_row.addStretch(1)

        self.custom_serial_toggle = QCheckBox(
            self._t("setup_page.log_entry.use_custom_serial", "Use custom batch")
        )
        apply_shared_checkbox_style(self.custom_serial_toggle, indicator_size=16)
        self.custom_date_toggle = QCheckBox(
            self._t("setup_page.log_entry.use_custom_date", "Use custom date")
        )
        apply_shared_checkbox_style(self.custom_date_toggle, indicator_size=16)
        toggle_row.addWidget(self.custom_serial_toggle)
        toggle_row.addWidget(self.custom_date_toggle)
        layout.addLayout(toggle_row)

        group = create_titled_section(self._t("setup_page.log_entry.section", "Logbook entry details"))
        form_host = QVBoxLayout(group)
        form_host.setContentsMargins(12, 12, 12, 12)
        form_host.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.order_input = QLineEdit()
        self.order_input.setPlaceholderText(
            self._t("setup_page.log_entry.order_hint", "Write order number")
        )
        self.quantity_input = QLineEdit()
        self.quantity_input.setPlaceholderText(
            self._t("setup_page.log_entry.quantity_hint", "Write quantity (e.g. 25)")
        )
        self.notes_input = QTextEdit()
        self.notes_input.setFixedHeight(80)
        self.work_id_display = QLineEdit(work_id)
        self.work_id_display.setReadOnly(True)
        self.next_serial_display = QLineEdit(self._next_serial_value or "-")
        self.next_serial_display.setReadOnly(True)
        self.export_date_display = QLineEdit(self._default_export_date_display)
        self.export_date_display.setReadOnly(True)
        self.custom_serial_input = QLineEdit()
        self.custom_serial_input.setPlaceholderText(
            self._t("setup_page.log_entry.custom_serial_hint", "Optional override, e.g. Z26")
        )
        self.custom_date_input = QDateEdit()
        self.custom_date_input.setCalendarPopup(True)
        self.custom_date_input.setDisplayFormat("dd/MM/yyyy")
        self.custom_date_input.setDate(QDate.currentDate())
        self.custom_date_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.custom_date_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.custom_date_input.setMinimumHeight(self.order_input.sizeHint().height())
        self.custom_date_input.setFont(self.order_input.font())

        custom_date_label = QLabel(self._t("setup_page.log_entry.custom_date", "Custom date"))
        custom_date_label.setWordWrap(True)
        custom_date_label.setProperty("detailFieldKey", True)
        custom_date_label.setText(custom_date_label.text().replace(" ", "\n", 1))

        custom_serial_label = QLabel(self._t("setup_page.log_entry.custom_serial", "Custom serial"))
        custom_serial_label.setWordWrap(True)
        custom_serial_label.setProperty("detailFieldKey", True)
        custom_serial_label.setText(custom_serial_label.text().replace(" ", "\n", 1))

        label_col_width = 118

        def _form_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setProperty("detailFieldKey", True)
            lbl.setMinimumWidth(label_col_width)
            lbl.setMaximumWidth(label_col_width)
            lbl.setWordWrap(True)
            return lbl

        work_label = _form_label(self._t("setup_page.log_entry.work", "Work"))
        serial_label = _form_label(self._t("setup_page.log_entry.next_serial", "Next serial"))
        date_label = _form_label(self._t("setup_page.log_entry.export_date", "Date"))
        order_label = _form_label(self._t("setup_page.log_entry.order", "Order"))
        qty_label = _form_label(self._t("setup_page.log_entry.quantity", "Quantity"))
        notes_label = _form_label(self._t("setup_page.log_entry.notes", "Notes"))
        custom_serial_label.setMinimumWidth(label_col_width)
        custom_serial_label.setMaximumWidth(label_col_width)
        custom_date_label.setMinimumWidth(label_col_width)
        custom_date_label.setMaximumWidth(label_col_width)

        form.addRow(work_label, self.work_id_display)
        form.addRow(serial_label, self.next_serial_display)
        form.addRow(custom_serial_label, self.custom_serial_input)
        form.addRow(date_label, self.export_date_display)
        form.addRow(custom_date_label, self.custom_date_input)
        form.addRow(order_label, self.order_input)
        form.addRow(qty_label, self.quantity_input)
        form.addRow(notes_label, self.notes_input)
        form_host.addLayout(form)
        layout.addWidget(group)

        # Keep custom rows hidden unless explicitly enabled.
        form.setRowVisible(2, False)  # custom serial
        form.setRowVisible(4, False)  # custom date

        self.custom_serial_toggle.toggled.connect(
            lambda checked: self._toggle_custom_serial_row(form, checked)
        )
        self.custom_date_toggle.toggled.connect(
            lambda checked: self._toggle_custom_date_row(form, checked)
        )
        self.custom_date_input.dateChanged.connect(self._sync_export_date_display)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        save_print_btn = QPushButton(self._t("setup_page.log_entry.save_and_print", "SAVE && PRINT LAVA CARD"))
        save_print_btn.setProperty("panelActionButton", True)
        save_print_btn.setProperty("primaryAction", True)
        save_btn = QPushButton(self._t("common.save", "Save"))
        save_btn.setProperty("panelActionButton", True)
        save_btn.setProperty("secondaryAction", True)
        cancel_btn = QPushButton(self._t("common.cancel", "Cancel"))
        cancel_btn.setProperty("panelActionButton", True)
        cancel_btn.setProperty("secondaryAction", True)
        save_print_btn.clicked.connect(self._on_save_and_print)
        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self.reject)
        for button in (save_print_btn, save_btn, cancel_btn):
            button.style().unpolish(button)
            button.style().polish(button)
        buttons.addWidget(save_print_btn)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def _toggle_custom_serial_row(self, form: QFormLayout, checked: bool):
        form.setRowVisible(1, not checked)  # base serial row
        form.setRowVisible(2, checked)
        self.next_serial_display.setEnabled(not checked)
        if checked:
            self.custom_serial_input.setFocus()
            self.custom_serial_input.selectAll()

    def _toggle_custom_date_row(self, form: QFormLayout, checked: bool):
        form.setRowVisible(3, not checked)  # original date row
        form.setRowVisible(4, checked)
        self.export_date_display.setEnabled(not checked)
        self._sync_export_date_display()

    def _sync_export_date_display(self):
        if self.custom_date_toggle.isChecked():
            self.export_date_display.setText(self.custom_date_input.date().toString("dd/MM/yyyy"))
            return
        self.export_date_display.setText(self._default_export_date_display)

    def _validate_before_accept(self) -> bool:
        try:
            self.get_data()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                self._t("tool_library.error.invalid_data", "Invalid data"),
                str(exc),
            )
            return False
        return True

    def _on_save(self):
        if not self._validate_before_accept():
            return
        self._save_and_print = False
        self.accept()

    def _on_save_and_print(self):
        if not self._validate_before_accept():
            return
        self._save_and_print = True
        self.accept()

    def should_print_card(self) -> bool:
        return bool(self._save_and_print)

    def get_data(self):
        qty_raw = self.quantity_input.text().strip()
        if not qty_raw:
            raise ValueError(self._t("setup_page.log_entry.quantity_required", "Quantity is required."))
        try:
            qty = int(qty_raw)
        except Exception as exc:
            raise ValueError(
                self._t("setup_page.log_entry.quantity_invalid", "Quantity must be a positive whole number.")
            ) from exc
        if qty <= 0:
            raise ValueError(self._t("setup_page.log_entry.quantity_invalid", "Quantity must be a positive whole number."))

        custom_serial = ""
        if self.custom_serial_toggle.isChecked():
            custom_serial = self.custom_serial_input.text().strip().upper()

        entry_date = self._default_export_date
        if self.custom_date_toggle.isChecked():
            entry_date = self.custom_date_input.date().toString("yyyy-MM-dd")

        return {
            "order_number": self.order_input.text().strip(),
            "quantity": qty,
            "notes": self.notes_input.toPlainText().strip(),
            "custom_serial": custom_serial,
            "entry_date": entry_date,
        }

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)


__all__ = ["LogEntryDialog"]
