# New Domain Onboarding Template (Phase 9)

This template defines the repeatable process for adding a new domain (for example: Fixtures) into Tools and jaws Library using platform abstractions from `shared.ui.platforms`.

## Scope and Guarantees

- Backward compatibility first: no destructive schema changes.
- No cross-app imports.
- New domain must compile, pass smoke tests, and not break existing tools/jaws flows.
- Platform extension classes must be registered in `docs/module-extension-points.json`.

## Required Contracts

Each new domain must define these contracts before implementation is called complete.

1. Service contract
- Required methods:
  - `list_<domain>(search_text: str = '', **filters) -> list[dict]`
  - `list_items(search_text: str = '', **filters) -> list[dict]` (platform alias)
  - `save_<domain>(payload: dict) -> dict`
  - `delete_item(item_id: str) -> None`

2. UI contract
- A page class inheriting `CatalogPageBase` with required overrides:
  - `create_delegate`
  - `get_item_service`
  - `build_filter_pane`
  - `apply_filters`

3. Export contract
- Domain export mapping function returning `ExportSpecification`.
- Must define field list, defaults, and coercers.

4. Migration contract
- If persistence is DB-backed, add additive migration only.
- If persistence is in-memory/example mode, document migration as N/A.

5. Test contract
- Compile checks for service/page/export modules.
- Import smoke includes all new modules.
- Quality gate must stay green.

## Step-by-Step Implementation

1. Create service module
- File: `services/<domain>_service.py`
- Keep this thin and deterministic.

2. Create page module
- File: `ui/<domain>_page.py`
- Subclass `CatalogPageBase`.
- Create a delegate by subclassing `CatalogDelegate` if custom rendering is needed.

3. Create export specification module
- File: `services/<domain>_export_spec.py`
- Return `ExportSpecification` from a factory function.

4. Register extension points
- Add page/delegate classes to `docs/module-extension-points.json`.

5. Integrate with main window
- Add page import and page construction.
- Add stack widget entry.
- Add navigation entry and route in `_open_tool_page` or domain-specific route.

6. Update smoke tests
- Add compile targets and import smoke for new modules.

7. Verify
- Run:
  - `python scripts/import_path_checker.py`
  - `python scripts/module_boundary_checker.py`
  - `python scripts/module_extension_checker.py`
  - `python scripts/smoke_test.py`
  - `python scripts/run_quality_gate.py`

## Copy-Paste Stubs

### Service Stub

```python
class DomainService:
    def list_domain(self, search_text: str = '', **filters) -> list[dict]:
        ...

    def list_items(self, search_text: str = '', **filters) -> list[dict]:
        return self.list_domain(search_text=search_text, **filters)

    def save_domain(self, payload: dict) -> dict:
        ...

    def delete_item(self, item_id: str) -> None:
        ...
```

### Page Stub

```python
class DomainPage(CatalogPageBase):
    def create_delegate(self) -> QAbstractItemDelegate:
        ...

    def get_item_service(self):
        return self.domain_service

    def build_filter_pane(self) -> QWidget:
        ...

    def apply_filters(self, filters: dict) -> list[dict]:
        return self.domain_service.list_domain(
            search_text=str(filters.get('search', '')),
            **filters,
        )
```

### Export Spec Stub

```python
def create_domain_export_spec(domain_service, translator=None) -> ExportSpecification:
    return ExportSpecification(
        domain_name='domain',
        item_service=domain_service,
        fields=[('id', 'ID'), ('name', 'Name')],
        defaults={'name': ''},
        coercers={},
        translator=translator,
    )
```

## Working Examples

- Tools page pattern: `ui/home_page.py`
- Jaws page pattern: `ui/jaw_page.py`
- Phase 9 fixtures example service: `services/fixture_service.py`
- Phase 9 fixtures example page: `ui/fixtures_page.py`
- Phase 9 fixtures export spec: `services/fixtures_export_spec.py`

## Phase 9 Definition of Done

- `docs/new-domain-template.md` exists and is actionable.
- One example domain compiles and is reachable from UI navigation.
- Quality gate passes with no new boundary/import violations.
- Status tracker is updated with completion proof.