"""Shared selection plumbing helpers for catalog pages."""

from __future__ import annotations


def connect_selection_model_once(
    page,
    *,
    current_changed_handler,
    selection_changed_handler,
    list_view_attr: str = 'list_view',
    cache_attr: str = '_selection_model_connected',
) -> None:
    """Connect current/selection change signals once per selection model instance."""
    list_view = getattr(page, list_view_attr, None)
    if list_view is None:
        return
    selection_model = list_view.selectionModel()
    if selection_model is None or getattr(page, cache_attr, None) is selection_model:
        return

    selection_model.currentChanged.connect(current_changed_handler)
    selection_model.selectionChanged.connect(selection_changed_handler)
    setattr(page, cache_attr, selection_model)


def on_multi_selection_changed_refresh_label(page, _selected, _deselected) -> None:
    """Default multi-selection handler: refresh selected-count label."""
    page._update_selection_count_label()


def update_selection_count_label(page, *, count: int, translation_key: str, default_text: str = '{count} selected') -> None:
    """Render selected-count label for multi-selection state."""
    label = getattr(page, 'selection_count_label', None)
    if label is None:
        return

    if count > 1:
        label.setText(page._t(translation_key, default_text, count=count))
        label.show()
        return

    label.hide()
