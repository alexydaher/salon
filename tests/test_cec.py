# SPDX-License-Identifier: GPL-3.0-or-later
"""The CEC keycode mapping (§6.11).

There is no CEC adapter on the development machine and `cec-client` isn't
installed, so the subprocess wiring is untested. What *is* testable is the
part that would be wrong silently: parsing cec-client's output and mapping
CEC user control codes to Actions.
"""

from __future__ import annotations

import pytest

from salon.input.actions import Action
from salon.input.cec_in import action_for_code, parse_line


@pytest.mark.parametrize(
    ("code", "action"),
    [
        (0x01, Action.UP),
        (0x02, Action.DOWN),
        (0x03, Action.LEFT),
        (0x04, Action.RIGHT),
        (0x00, Action.OK),
        (0x0D, Action.BACK),
        (0x41, Action.VOLUME_UP),
        (0x42, Action.VOLUME_DOWN),
        (0x43, Action.MUTE),
    ],
)
def test_cec_user_control_codes(code: int, action: Action) -> None:
    assert action_for_code(code) == action


def test_unknown_codes_are_ignored_not_guessed() -> None:
    assert action_for_code(0x7F) is None


def test_parses_a_real_cec_client_line() -> None:
    assert parse_line("TRAFFIC: [123] key pressed: up (1)") is Action.UP


def test_parses_a_hex_code() -> None:
    assert parse_line("key pressed: exit (D)") is Action.BACK


def test_ignores_lines_that_are_not_key_presses() -> None:
    assert parse_line("DEBUG: [1] << requesting vendor ID") is None
    assert parse_line("") is None


def test_the_code_is_read_not_the_label() -> None:
    """cec-client localises the label; the numeric code is what's stable."""
    assert parse_line("key pressed: haut (1)") is Action.UP
