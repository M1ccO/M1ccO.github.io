# Machine Profile — Phase 6 Plan: Unify Cross-App Profile View

## Why This Exists

The Tools and Jaws Library cannot import directly from Setup Manager's
`machine_profiles.py` (separate process, different working directory, no shared
package path). So it resolves a profile key into its own ad-hoc plain dict via
`_resolve_machine_profile()` in `ui/main_window.py`:

```python
{
    'key': 'ntx_2sp_2h',
    'machine_type': 'lathe',
    'heads': [
        {'key': 'HEAD1', 'label_key': 'tool_library.head_filter.head1', 'label_default': 'HEAD1'},
        {'key': 'HEAD2', 'label_key': 'tool_library.head_filter.head2', 'label_default': 'HEAD2'},
    ],
    'spindles': [
        {'key': 'main', 'label_key': 'jaw_library.filter.main_spindle', 'label_default': 'Main spindle'},
        {'key': 'sub', 'label_key': 'jaw_library.filter.sub_spindle', 'label_default': 'Sub spindle'},
    ],
}
```

The problem: this dict contract is implicit. The two apps can silently diverge as
Setup Manager adds new profile flags. Consumers inside the Tools Library currently
sprinkle defensive `isinstance(profile, dict)` checks because nothing enforces that
the profile is always a dict. There is also a duplicate `_is_machining_center` /
`_selector_is_machining_center` pattern across two different classes.

**Goal:** replace the implicit dict with an explicit typed view that lives in `shared/`
so both apps share the same definition, without breaking the process-isolation principle.

---

## Audit: What Fields Are Actually Used

A full grep of `machine_profile.get(` and `machine_profile[` across the Tools Library
reveals three distinct access patterns:

| Consumer | File | Fields read |
|---|---|---|
| `_is_machining_center()` | `ui/main_window.py:231` | `machine_type` |
| `_selector_is_machining_center()` | `ui/selectors/tool_selector_layout.py:63` | `machine_type` |
| `_profile_head_keys()` | `ui/main_window.py:234` | `heads[].key` |
| **Head filter combo builder** | `ui/main_window.py:892–898` | `heads[].key` **+ `heads[].label_key` + `heads[].label_default`** |
| `_profile_head_keys()` (topbar) | `ui/home_page_support/topbar_filter_state.py:17–33` | `heads[].key` |
| Pages receive whole profile | `ui/main_window.py:529–568` | stored, then delegated |
| Selectors receive whole profile | `ui/selectors/tool_selector_dialog.py:36` | `machine_type` (via `_selector_is_machining_center`) |
| Jaw selector receives profile | `ui/selectors/jaw_selector_dialog.py:29–40` | stored as `self.machine_profile` |
| Fixture page receives profile | `ui/main_window.py:541` | stored (fixture page reads nothing directly) |

**Correction vs. initial draft:** the head filter combo builder at `main_window.py:892–898`
reads not just `heads[].key` but also `heads[].label_key` and `heads[].label_default`
to build localised combo labels. The initial plan missed this. `spindles` remains
entirely unused.

**Actually needed in the typed view:**
- `machine_type: str`
- `head_keys: tuple[str, ...]` — for filter/bucket keying
- `head_labels: tuple[tuple[str, str], ...]` — `(label_key, label_default)` per head, for the combo builder

---

## Design: `ToolLibProfileView`

A small frozen dataclass in `shared/` that replaces the dict. Both apps import it
— Setup Manager's `machine_profiles.py` to *produce* it (optionally, for tests),
Tools Library to *consume* it. No cross-app registry import needed.

### New file: `shared/services/tool_lib_profile_view.py`

```python
"""Lightweight profile view shared between Setup Manager and Tools Library.

Setup Manager produces a ToolLibProfileView from a full MachineProfile.
Tools Library consumes it in place of the current ad-hoc profile dict.

Only the fields actually consumed by the Tools Library are included here.
Adding a field to this file is the single required change when the library
needs a new piece of profile data.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class HeadView:
    """One head entry as seen by the Tools Library UI."""
    key: str                  # e.g. "HEAD1", "HEAD2"
    label_i18n_key: str       # e.g. "tool_library.head_filter.head1"
    label_default: str        # fallback label if i18n key is missing


@dataclass(frozen=True)
class ToolLibProfileView:
    key: str = "ntx_2sp_2h"
    machine_type: str = "lathe"   # "lathe" or "machining_center"
    heads: tuple[HeadView, ...] = (
        HeadView("HEAD1", "tool_library.head_filter.head1", "HEAD1"),
        HeadView("HEAD2", "tool_library.head_filter.head2", "HEAD2"),
    )

    def is_machining_center(self) -> bool:
        return self.machine_type == "machining_center"

    def head_keys(self) -> list[str]:
        return [h.key for h in self.heads]


# ---------------------------------------------------------------------------
# Factory — Tools Library entry point
# ---------------------------------------------------------------------------

_DEFAULT_HEADS: tuple[HeadView, ...] = (
    HeadView("HEAD1", "tool_library.head_filter.head1", "HEAD1"),
    HeadView("HEAD2", "tool_library.head_filter.head2", "HEAD2"),
)


def profile_view_from_key(raw_key: str | None) -> ToolLibProfileView:
    """Build a ToolLibProfileView from a raw profile key string.

    This is the Tools Library's sole entry point — it never imports
    MachineProfile from Setup Manager.  The only semantic encoded here is
    the stable key-prefix contract: machining-center keys begin with
    'machining_center'.  Head labels are fixed to the two-head default for
    all current profiles; extend _DEFAULT_HEADS when HEAD3 is needed.
    """
    key = str(raw_key or "").strip().lower() or "ntx_2sp_2h"
    is_mc = key.startswith("machining_center")
    return ToolLibProfileView(
        key=key,
        machine_type="machining_center" if is_mc else "lathe",
        heads=_DEFAULT_HEADS,
    )
```

> **Why not vary heads by profile?** All current profiles in the registry use HEAD1
> and HEAD2 in the Tools Library (even single-head lathes — the filter simply shows
> only HEAD1 items). If HEAD3 is ever needed, extend `_DEFAULT_HEADS` and update the
> combo builder together. That controlled coupling is intentional.

---

## Step-by-Step Changes

### Step 1 — Create `shared/services/tool_lib_profile_view.py`

Write the file exactly as shown above. No other changes yet. Both apps can import it
immediately without side effects.

---

### Step 2 — Update `Tools and jaws Library/ui/main_window.py`

**a) Add import** at the top of the file:

```python
from shared.services.tool_lib_profile_view import ToolLibProfileView, profile_view_from_key
```

**b) Replace `_resolve_machine_profile`** (`main_window.py:212–228`):

```python
# Before — returns a plain dict
@staticmethod
def _resolve_machine_profile(profile_key: str | None) -> dict:
    normalized = str(profile_key or '').strip().lower()
    is_mc = normalized.startswith('machining_center')
    return {
        'key': normalized or 'ntx_2sp_2h',
        'machine_type': 'machining_center' if is_mc else 'lathe',
        'heads': [...],
        'spindles': [...],   # never consumed — also disappears
    }

# After — returns a typed view
@staticmethod
def _resolve_machine_profile(profile_key: str | None) -> ToolLibProfileView:
    return profile_view_from_key(profile_key)
```

**c) Replace `_is_machining_center`** (`main_window.py:230–231`):

```python
# Before
def _is_machining_center(self) -> bool:
    return str((self.machine_profile or {}).get('machine_type') or '').strip().lower() == 'machining_center'

# After
def _is_machining_center(self) -> bool:
    return self.machine_profile.is_machining_center()
```

**d) Replace `_profile_head_keys`** (`main_window.py:233–240`):

```python
# Before — dual dict/object path
def _profile_head_keys(self) -> list[str]:
    heads = self.machine_profile.get('heads') if isinstance(self.machine_profile, dict) else []
    keys: list[str] = []
    for head in heads or []:
        key = str((head or {}).get('key') or '').strip().upper()
        if key and key not in keys:
            keys.append(key)
    return keys or ['HEAD1', 'HEAD2']

# After
def _profile_head_keys(self) -> list[str]:
    return self.machine_profile.head_keys()
```

**e) Replace the head filter combo builder** (`main_window.py:892–898`):

```python
# Before — dict-based
for head in (self.machine_profile.get('heads') or []):
    head_key = str((head or {}).get('key') or '').strip().upper()
    if not head_key:
        continue
    label_key = str((head or {}).get('label_key') or '').strip()
    label_default = str((head or {}).get('label_default') or head_key)
    label = self._t(label_key, label_default) if label_key else label_default
    items.append((label, head_key))

# After — typed HeadView
for head in self.machine_profile.heads:
    label = self._t(head.label_i18n_key, head.label_default)
    items.append((label, head.key))
```

**f) Update `self.machine_profile` type annotation** wherever it appears in the
`__init__` signature or inline comments: `dict` → `ToolLibProfileView`.

---

### Step 3 — Update `ui/selectors/tool_selector_layout.py`

Replace `_selector_is_machining_center` (`tool_selector_layout.py:59–66`):

```python
# Before — handles both dict and object with branching isinstance
def _selector_is_machining_center(self) -> bool:
    profile = getattr(self, 'machine_profile', None)
    machine_type = ''
    if isinstance(profile, dict):
        machine_type = str(profile.get('machine_type') or '').strip().lower()
    else:
        machine_type = str(getattr(profile, 'machine_type', '') or '').strip().lower()
    return machine_type in {'machining_center', 'machining center'}

# After — ToolLibProfileView is always an object; no isinstance branch needed
def _selector_is_machining_center(self) -> bool:
    profile: ToolLibProfileView | None = getattr(self, 'machine_profile', None)
    if profile is None:
        return False
    return profile.is_machining_center()
```

Add the import at the top of `tool_selector_layout.py`:
```python
from shared.services.tool_lib_profile_view import ToolLibProfileView
```

---

### Step 4 — Update `ui/home_page_support/topbar_filter_state.py`

Replace `_profile_head_keys` (`topbar_filter_state.py:16–33`):

```python
# Before — dual dict/object path, 17 lines
def _profile_head_keys(page) -> list[str]:
    profile = getattr(page, 'machine_profile', None)
    heads = []
    if isinstance(profile, dict):
        heads = profile.get('heads') or []
    elif profile is not None:
        heads = getattr(profile, 'heads', ()) or ()
    keys: list[str] = []
    for head in heads:
        if isinstance(head, dict):
            key = str(head.get('key') or '').strip().upper()
        else:
            key = str(getattr(head, 'key', '') or '').strip().upper()
        if key and key not in keys:
            keys.append(key)
    return keys or ['HEAD1', 'HEAD2']

# After — 4 lines
def _profile_head_keys(page) -> list[str]:
    from shared.services.tool_lib_profile_view import ToolLibProfileView
    profile = getattr(page, 'machine_profile', None)
    if isinstance(profile, ToolLibProfileView):
        return profile.head_keys()
    return ['HEAD1', 'HEAD2']
```

The `isinstance` guard is kept here (rather than a bare `profile.head_keys()`) because
`topbar_filter_state.py` is a shared helper that could theoretically be called before
`machine_profile` is set. The guard makes the fallback explicit rather than crashing.

---

## What Does NOT Change

- The profile *key* string format — `"ntx_2sp_2h"`, `"machining_center_3ax"`, etc.
- The persisted JSON in `shared_ui_preferences.json` — still `machine_profile_key: str`
- The IPC payload between the two apps — still `{'machine_profile_key': '...', ...}`
- The process-isolation boundary — Tools Library never imports `machine_profiles.py`
- All UI visuals and head filter labels — `HeadView.label_i18n_key` carries the same
  i18n keys the dict used, so localised output is byte-identical
- `spindles` — was defined in the dict but never consumed; it is simply not ported

---

## Verification

Run both apps after **each step**, not just at the end. A `AttributeError` on `.get()`
anywhere means a call site was missed — fix immediately before the next step.

| Check | Lathe config | MC config |
|---|---|---|
| Tool Selector opens | head/spindle toggle visible | head/spindle toggle hidden |
| Head filter combo labels | "HEAD1", "HEAD2" in correct language | same |
| Jaw Selector opens | normal | N/A (jaws are disabled for MC) |
| Head filter on home page | HEAD1/HEAD2 filter buttons present | HEAD1/HEAD2 present |
| Live profile switch (prefs reload) | re-renders correctly | re-renders correctly |
| IPC handoff from Setup Manager | profile key accepted, UI updates | profile key accepted, UI updates |

---

## Risk

**Low.** `ToolLibProfileView` is a frozen dataclass — no mutable state to corrupt.
All field values map 1:1 to what the dict previously provided. The i18n keys and
default labels in `HeadView` are taken verbatim from the old `_resolve_machine_profile`.

The only observable change: `machine_profile` is now a `ToolLibProfileView` object
instead of a `dict`. Any missed call site calling `.get(...)` on it will raise
`AttributeError` immediately and loudly, making the miss obvious — not silently
returning `None` as the dict did.

---

## Suggested Commit Order

1. `shared/services/tool_lib_profile_view.py` — new file, no side effects, both apps can import it
2. `main_window.py` — import + `_resolve_machine_profile` + `_is_machining_center` + `_profile_head_keys` + combo builder *(verify app runs before continuing)*
3. `tool_selector_layout.py` — `_selector_is_machining_center` *(verify Tool Selector opens)*
4. `topbar_filter_state.py` — `_profile_head_keys` *(verify head filter works)*
5. Final verification pass across lathe + MC configs (full Phase 10 matrix from the main plan)
