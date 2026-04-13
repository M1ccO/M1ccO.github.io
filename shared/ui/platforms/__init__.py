"""
Shared UI Platform Layer — Phase 3 platform abstractions for catalog pages, editors, and export.

This is the shared foundation for all catalog-based UI modules (TOOLS, JAWS, future domains).
Instead of duplicating 72-85% of UI code across domains, inherit from these abstract base classes.

Phase 3 Abstractions (April 2026):
  - CatalogPageBase: Common search/filter/list/batch operations page
  - EditorDialogBase: Schema-driven form dialog with validation
  - CatalogDelegate: Domain-neutral item painting via QPainter
  - SelectorState: Stateful filter selector UI state machine
  - ExportSpecification: Domain-neutral Excel I/O schema mapper

Import Pattern (Production):
    from shared.ui.platforms import CatalogPageBase, EditorDialogBase, CatalogDelegate, SelectorState
    
    class HomePage(CatalogPageBase):
        def create_delegate(self):
            return ToolCatalogDelegate()
        
        def get_item_service(self):
            return self.tool_service
        
        ... (see docstrings in each class)

Architecture Note:
  - Phase 3 (Current): Platform hardens behind adapters; old code unchanged
  - Phase 4: HomePage/JawPage migrated to inherit from platform
  - Phase 5+: New domains (Fixtures, etc.) inherit with <300L per domain (86% reduction)
  - Phase 8: Adapter layer deleted; platform becomes canonical UI base

Backward Compatibility:
  - All classes maintain Qt.UserRole conventions for model item storage
  - Signal names follow domain ecosystem (item_selected, item_deleted, accepted)
  - Schema format extensible without breaking existing field definitions
  - Reverse-compatible: old domains can migrate incrementally
"""

from .catalog_page_base import (
    CatalogPageBase,
    CATALOG_ROLE_ID,
    CATALOG_ROLE_UID,
    CATALOG_ROLE_DATA,
    CATALOG_ROLE_ICON,
)
from .editor_dialog_base import EditorDialogBase
from .catalog_delegate import CatalogDelegate
from .selector_state import SelectorState
from .export_specification import (
    ExportSpecification,
    ColumnDefinition,
    ColumnGrouping,
)

__all__ = [
    "CatalogPageBase",
    "CATALOG_ROLE_ID",
    "CATALOG_ROLE_UID",
    "CATALOG_ROLE_DATA",
    "CATALOG_ROLE_ICON",
    "EditorDialogBase",
    "CatalogDelegate",
    "SelectorState",
    "ExportSpecification",
    "ColumnDefinition",
    "ColumnGrouping",
]
