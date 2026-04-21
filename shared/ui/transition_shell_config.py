from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class TransitionShellMode(str, Enum):
    SENDER_FADE = "sender_fade"
    DISABLED = "disabled"


@dataclass(slots=True)
class TransitionShellConfig:
    mode: TransitionShellMode
    capture_timeout_ms: int = 100
    fade_duration_ms: int = 250
    reveal_delay_ms: int = 0
    shell_min_show_ms: int = 50
    preload_gate_enabled: bool = True

    @property
    def enabled(self) -> bool:
        return self.mode != TransitionShellMode.DISABLED


_DEFAULT_MODE = TransitionShellMode.SENDER_FADE
_GLOBAL_CONFIG: TransitionShellConfig | None = None


def _normalize_mode(mode: str | None) -> TransitionShellMode:
    value = str(mode or os.getenv("NTX_TRANSITION_SHELL_MODE", "")).strip().lower()
    for candidate in TransitionShellMode:
        if candidate.value == value:
            return candidate
    return _DEFAULT_MODE


def init_transition_shell_config(mode: str | None = None) -> TransitionShellConfig:
    global _GLOBAL_CONFIG
    _GLOBAL_CONFIG = TransitionShellConfig(mode=_normalize_mode(mode))
    return _GLOBAL_CONFIG


def get_transition_shell_config() -> TransitionShellConfig:
    global _GLOBAL_CONFIG
    if _GLOBAL_CONFIG is None:
        _GLOBAL_CONFIG = init_transition_shell_config()
    return _GLOBAL_CONFIG