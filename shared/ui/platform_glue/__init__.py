"""
Platform Glue Layer — Adapter bridges for Phase 3-4 parallel development.

Strategy:
  - Old code (HomePage, ToolService, ExportService) runs unchanged
  - Bridge adapters present new platform interfaces without modifying old code
  - Phase 4: old code migrated to inherit from platform directly
  - Phase 8: adapters deleted once parity tests confirm no behavior regression

Deprecation path:
  All adapters marked with Phase 8 removal target.
  
  DEP-ADAPTER-001: LegacyHomePageBridge (Phase 8 removal)
  DEP-ADAPTER-002: CatalogServiceAdapter (Phase 8 removal)
  DEP-ADAPTER-003: ExportSpecificationAdapter (Phase 8 removal)

Design principle:
  Adapters are TEMPORARY BRIDGES enabling parallel platform hardening + old code preservation.
  They are NOT permanent APIs and must not be extended or relied upon beyond Phase 7.
"""

__all__ = []
