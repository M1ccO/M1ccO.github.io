"""
EditorDialogBase — Abstract base class for item editor dialogs (Phase 3 Platform Layer).

Provides schema-driven form rendering, validation, and persistence for TOOLS, JAWS, and future domains.
Subclasses override abstract methods to define domain-specific schema, validation, and field logic.

Usage:
    class AddEditToolDialog(EditorDialogBase):
        def build_schema(self) -> dict:
            return {
                'id': {'type': 'text', 'label': 'Tool ID', 'required': True},
                'tool_type': {'type': 'choice', 'label': 'Type', 'options': ['Turning', 'Drilling']},
                'radius': {'type': 'number', 'label': 'Nose Radius (mm)', 'required': False},
            }
        
        def validate_record(self, record_dict: dict) -> bool:
            return bool(record_dict.get('id')) and record_dict['radius'] >= 0
        
        def on_field_changed(self, field_name: str, value: any) -> None:
            if field_name == 'tool_type':
                self.field_widgets['radius'].setValue(0.0)

Status: Production (April 13, 2026)
"""

from __future__ import annotations

from typing import Any, Callable, Optional
from abc import abstractmethod

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QWidget,
    QLabel,
    QLineEdit,
    QDoubleSpinBox,
    QComboBox,
    QPushButton,
    QMessageBox,
    QScrollArea,
)

__all__ = ['EditorDialogBase']


class EditorDialogBase(QDialog):
    """
    Abstract base class for item editor dialogs.

    Provides schema-driven form rendering, load/save, validation, and batch mode support.
    Subclasses implement domain-specific schema, validation, and field change logic.
    """

    accepted = Signal()
    """Emitted when dialog is accepted and record saved."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        item: Optional[dict] = None,
        item_service: Optional[Any] = None,
        translate: Optional[Callable[[str, Optional[str]], str]] = None,
        batch_label: Optional[str] = None,
        group_edit_mode: bool = False,
        group_count: Optional[int] = None,
    ) -> None:
        """
        Initialize editor dialog.

        Args:
            parent: Parent widget.
            item: Item dict to edit (or None for new).
            item_service: Service for loading/saving items.
            translate: i18n translation function.
            batch_label: Label for batch edit mode (e.g., "Batch Edit").
            group_edit_mode: If True, show batch controls and "Apply to All" mode.
            group_count: Number of items in batch (for display).
        """
        super().__init__(parent)
        self.item = item or {}
        self.item_service = item_service
        self._translate = translate or (lambda key, default=None: default or '')
        self.batch_label = batch_label or ''
        self.group_edit_mode = group_edit_mode
        self.group_count = group_count or 0

        # Field widgets will be populated in _build_ui()
        self.field_widgets: dict[str, QWidget] = {}
        self.schema: dict = {}

        # Setup dialog
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        self._setup_title()

        # Build UI from schema
        self._build_ui()

        # Load initial data if provided
        if self.item:
            self.load_record(self.item)

    # ============================================================================
    # Abstract Methods (Override in Subclass)
    # ============================================================================

    @abstractmethod
    def build_schema(self) -> dict:
        """
        Define form schema.

        Returns:
            Dict mapping field names to field configurations.
            Format: {
                'field_name': {
                    'type': 'text'|'number'|'choice',
                    'label': str,
                    'required': bool,
                    'enabled': bool,
                    'options': list (for 'choice' type),
                    'default': any (optional),
                    'placeholder': str (optional, for text fields),
                    'min': float (optional, for number fields),
                    'max': float (optional, for number fields),
                    'decimals': int (optional, for number fields),
                }
            }
        """
        raise NotImplementedError

    @abstractmethod
    def validate_record(self, record_dict: dict) -> bool:
        """
        Validate record data before save.

        Args:
            record_dict: Form data as dict.

        Returns:
            True if valid; False otherwise. Subclass should show error messages.
        """
        raise NotImplementedError

    def on_field_changed(self, field_name: str, value: Any) -> None:
        """
        Handle field value change (optional hook for cross-field logic).

        Override to implement dependent field updates, auto-population, or validation feedback.

        Args:
            field_name: Name of field that changed.
            value: New value.
        """
        pass  # Optional override

    # ============================================================================
    # Concrete Methods
    # ============================================================================

    def _setup_title(self) -> None:
        """Build dialog title (with batch mode label if applicable)."""
        title_parts = []

        if self.item and self.item.get('id'):
            title_parts.append(f"Edit: {self.item['id']}")
        else:
            title_parts.append("Create New Item")

        if self.batch_label:
            title_parts.append(f"[{self.batch_label}]")

        if self.group_edit_mode and self.group_count:
            title_parts.append(f"({self.group_count} items)")

        self.setWindowTitle(" • ".join(title_parts))

    def _build_ui(self) -> None:
        """Build form UI from schema."""
        # Get schema from subclass
        self.schema = self.build_schema()

        # Create main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # Add batch mode info if applicable
        if self.batch_label and self.group_edit_mode:
            info_label = QLabel(f"Batch Edit Mode: {self.batch_label} ({self.group_count} items)")
            info_label.setStyleSheet("color: #0066cc; font-weight: bold; padding: 8px; background: #e6f2ff;")
            main_layout.addWidget(info_label)

        # Create scrollable form area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setSpacing(10)
        form_layout.setContentsMargins(0, 0, 0, 0)

        # Build form fields from schema
        self.field_widgets = {}
        for field_name, field_config in self.schema.items():
            label = field_config.get('label', field_name)
            required = field_config.get('required', False)
            if required:
                label = f"{label} *"

            field_type = field_config.get('type', 'text')
            widget = self._create_field_widget(field_name, field_config)

            if widget:
                # Apply enabled state
                enabled = field_config.get('enabled', True)
                widget.setEnabled(enabled)

                # Add to form
                form_layout.addRow(label, widget)
                self.field_widgets[field_name] = widget

        scroll.setWidget(form_widget)
        main_layout.addWidget(scroll, 1)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.addStretch()

        apply_button = QPushButton("OK")
        apply_button.setMinimumWidth(100)
        apply_button.clicked.connect(self.accept)

        cancel_button = QPushButton("Cancel")
        cancel_button.setMinimumWidth(100)
        cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(apply_button)
        button_layout.addWidget(cancel_button)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

    def _create_field_widget(self, field_name: str, field_config: dict) -> Optional[QWidget]:
        """
        Create QWidget for field based on type.

        Args:
            field_name: Field name (used for signal callbacks).
            field_config: Field configuration dict.

        Returns:
            QWidget (QLineEdit, QDoubleSpinBox, QComboBox, etc.) or None if type unsupported.
        """
        field_type = field_config.get('type', 'text')

        if field_type == 'text':
            return self._create_text_field(field_name, field_config)
        elif field_type == 'number':
            return self._create_number_field(field_name, field_config)
        elif field_type == 'choice':
            return self._create_choice_field(field_name, field_config)
        else:
            # Unsupported type; skip
            return None

    def _create_text_field(self, field_name: str, field_config: dict) -> QLineEdit:
        """Create text input field."""
        widget = QLineEdit()

        if placeholder := field_config.get('placeholder'):
            widget.setPlaceholderText(placeholder)

        # Connect change signal
        def on_text_changed(text: str) -> None:
            self.on_field_changed(field_name, text)

        widget.textChanged.connect(on_text_changed)
        return widget

    def _create_number_field(self, field_name: str, field_config: dict) -> QDoubleSpinBox:
        """Create numeric spin box field."""
        widget = QDoubleSpinBox()

        # Configure min/max
        widget.setMinimum(field_config.get('min', -999999.0))
        widget.setMaximum(field_config.get('max', 999999.0))
        widget.setDecimals(field_config.get('decimals', 2))

        # Connect change signal
        def on_value_changed(value: float) -> None:
            self.on_field_changed(field_name, value)

        widget.valueChanged.connect(on_value_changed)
        return widget

    def _create_choice_field(self, field_name: str, field_config: dict) -> QComboBox:
        """Create dropdown choice field."""
        widget = QComboBox()

        # Add options
        options = field_config.get('options', [])
        if isinstance(options, list):
            widget.addItems([str(opt) for opt in options])

        # Connect change signal
        def on_current_text_changed(text: str) -> None:
            self.on_field_changed(field_name, text)

        widget.currentTextChanged.connect(on_current_text_changed)
        return widget

    def load_record(self, record_dict: dict) -> None:
        """
        Populate form fields from record data.

        Args:
            record_dict: Item data dict.
        """
        for field_name, widget in self.field_widgets.items():
            value = record_dict.get(field_name)

            if isinstance(widget, QLineEdit):
                widget.setText(str(value or ''))
            elif isinstance(widget, QDoubleSpinBox):
                try:
                    widget.setValue(float(value or 0.0))
                except (ValueError, TypeError):
                    widget.setValue(0.0)
            elif isinstance(widget, QComboBox):
                text = str(value or '')
                index = widget.findText(text)
                if index >= 0:
                    widget.setCurrentIndex(index)
                else:
                    widget.setCurrentIndex(0)

    def get_record_data(self) -> dict:
        """
        Extract form data as dict.

        Returns:
            Dict with field values.
        """
        record: dict = {}
        for field_name, widget in self.field_widgets.items():
            if isinstance(widget, QLineEdit):
                record[field_name] = widget.text()
            elif isinstance(widget, QDoubleSpinBox):
                record[field_name] = widget.value()
            elif isinstance(widget, QComboBox):
                record[field_name] = widget.currentText()
        return record

    def accept(self) -> None:
        """
        Validate, save, and close dialog.

        Calls validate_record(); if valid, merges form data with original item,
        saves via item_service, and emits accepted signal.
        """
        # Extract form data
        record = self.get_record_data()

        # Validate record
        if not self.validate_record(record):
            # Subclass validate_record() should show error message
            return

        # Merge with original (preserve unedited fields)
        self.item.update(record)

        # Save via service if available
        if self.item_service:
            try:
                uid = self.item_service.save_item(self.item)
                self.item['uid'] = uid
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Save Error",
                    f"Failed to save item:\n{str(e)}"
                )
                return

        # Emit accepted signal
        self.accepted.emit()

        # Close dialog (calls QDialog.accept())
        super().accept()
