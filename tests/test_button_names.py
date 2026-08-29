# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Change buttons names a button, rather than printing its code.

`Controller 0x130` identifies a button nobody can find by looking down at
the pad in their hands, which is the one thing that screen exists to help
with.
"""

from __future__ import annotations

from salon.core import buttons
from salon.core.actions import Action
from salon.core.bindings import CEC, GAMEPAD, KEYBOARD
from salon.input.gamepad_mapping import BUTTON_ACTIONS


def test_the_face_buttons_are_named_per_family() -> None:
    assert buttons.code_label(GAMEPAD, 0x130, family=buttons.PLAYSTATION) == "Cross"
    assert buttons.code_label(GAMEPAD, 0x134, family=buttons.PLAYSTATION) == "Square"
    assert buttons.code_label(GAMEPAD, 0x130, family=buttons.GENERIC) == "A"
    # South and east are swapped on a Nintendo pad, so the button Salon
    # binds to OK is the one printed B.
    assert buttons.code_label(GAMEPAD, 0x130, family=buttons.NINTENDO) == "B"


def test_the_two_tables_agree_about_every_action_they_share() -> None:
    """`_GAMEPAD_FAMILIES` maps action → caption and `code_label` maps code
    → caption. They are derived from the same physical facts, and if they
    ever disagree the legend and the rebinding screen would be calling one
    button two things.

    The directions are excluded deliberately, and it is the one place the
    two answers *should* differ: the legend says "Left" because that is the
    intent, while the rebinding screen says "D-pad left" because a stick
    reaches the same action and the row is naming one physical control.
    """
    directions = (Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT)
    for family in (buttons.GENERIC, buttons.PLAYSTATION, buttons.NINTENDO):
        for code, action in BUTTON_ACTIONS.items():
            if action in directions:
                continue
            by_code = buttons.code_label(GAMEPAD, code, family=family)
            by_action = buttons.label(action, GAMEPAD, family=family)
            if by_code and by_action:
                assert by_code == by_action, (family, hex(code), action)


def test_every_bound_gamepad_code_has_a_name() -> None:
    """Anything Salon reacts to is a button somebody may want to rebind, so
    there is no code in the default map this cannot describe."""
    for code in BUTTON_ACTIONS:
        assert buttons.code_label(GAMEPAD, code, family=buttons.GENERIC), hex(code)


def test_cec_codes_use_the_words_a_television_manual_uses() -> None:
    assert buttons.code_label(CEC, 0x00) == "Select"
    assert buttons.code_label(CEC, 0x44) == "Play"
    assert buttons.code_label(CEC, 0x71) == "Blue"


def test_unknown_codes_and_keyboards_answer_empty() -> None:
    """Empty is the contract: the caller falls back to `Gdk.keyval_name`
    for a keyboard and to the number for anything genuinely unknown, and
    duplicating GDK's keyval table here would be a second thing to keep
    current."""
    assert buttons.code_label(KEYBOARD, 0xFF0D) == ""
    assert buttons.code_label(GAMEPAD, 0x999) == ""
    assert buttons.code_label(CEC, 0xFE) == ""
