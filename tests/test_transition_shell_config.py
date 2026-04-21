from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
for _candidate in (_WORKSPACE,):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from shared.ui.transition_shell_config import (  # noqa: E402
    TransitionShellMode,
    get_transition_shell_config,
    init_transition_shell_config,
)


class TestTransitionShellConfig(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("NTX_TRANSITION_SHELL_MODE", None)
        init_transition_shell_config(TransitionShellMode.SENDER_FADE.value)

    def test_default_mode_is_sender_fade(self) -> None:
        os.environ.pop("NTX_TRANSITION_SHELL_MODE", None)

        config = init_transition_shell_config()

        self.assertEqual(TransitionShellMode.SENDER_FADE, config.mode)
        self.assertTrue(config.enabled)
        self.assertIs(config, get_transition_shell_config())

    def test_disabled_mode_is_supported(self) -> None:
        config = init_transition_shell_config(TransitionShellMode.DISABLED.value)

        self.assertEqual(TransitionShellMode.DISABLED, config.mode)
        self.assertFalse(config.enabled)

    def test_invalid_mode_falls_back_to_sender_fade(self) -> None:
        os.environ["NTX_TRANSITION_SHELL_MODE"] = "not-a-real-mode"

        config = init_transition_shell_config()

        self.assertEqual(TransitionShellMode.SENDER_FADE, config.mode)


if __name__ == "__main__":
    unittest.main()