# SPDX-License-Identifier: GPL-3.0-or-later
"""The legend names the button the user is looking at, not the intent."""

from __future__ import annotations

from salon.core import buttons
from salon.core.actions import Action
from salon.core.bindings import CEC, GAMEPAD, KEYBOARD
from salon.input.gamepad_mapping import BUTTON_ACTIONS

# evdev's four face buttons, in the order this module reasons about them.
BTN_SOUTH = 0x130
BTN_EAST = 0x131
BTN_NORTH = 0x133
BTN_WEST = 0x134


def test_the_dualsense_this_was_tested_against_is_recognised() -> None:
    """The exact string libmanette reports for the one controller that has
    ever been attached to this project."""
    name = "Sony Interactive Entertainment DualSense Wireless Controller"
    assert buttons.gamepad_family(name) == buttons.PLAYSTATION


def test_unknown_controllers_get_the_generic_letters() -> None:
    assert buttons.gamepad_family("Some Vendor Arcade Stick") == buttons.GENERIC
    assert buttons.gamepad_family("") == buttons.GENERIC


def test_nintendo_pads_are_named_by_their_own_printing() -> None:
    """The south button is the one bound to OK, and Nintendo prints B on it."""
    assert buttons.gamepad_family("Nintendo Switch Pro Controller") == buttons.NINTENDO
    assert (
        buttons.label(Action.OK, GAMEPAD, family=buttons.NINTENDO)
        != buttons.label(Action.OK, GAMEPAD, family=buttons.GENERIC)
    )


def test_every_face_button_salon_binds_has_a_name_in_every_family() -> None:
    """Guards the mapping against drifting apart from the binding table:
    a bound button with no caption is a blank chip in the legend."""
    for code in (BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST):
        action = BUTTON_ACTIONS[code]
        for family in (buttons.GENERIC, buttons.PLAYSTATION, buttons.NINTENDO):
            assert buttons.label(action, GAMEPAD, family=family), (action, family)


def test_menu_is_named_on_every_source() -> None:
    """MENU is the one button that always means the same thing, so it is
    the one the legend can least afford to leave unnamed."""
    for source in (GAMEPAD, KEYBOARD, CEC, buttons.PHONE):
        assert buttons.label(Action.MENU, source)


def test_keyboard_names_keys_rather_than_intents() -> None:
    assert buttons.label(Action.OK, KEYBOARD) == "Enter"
    assert buttons.label(Action.OPTIONS, KEYBOARD) == "O"


def test_an_unknown_source_still_produces_a_caption() -> None:
    assert buttons.label(Action.OK, "smoke-signal") == "OK"


def test_an_action_with_no_button_is_empty_rather_than_wrong() -> None:
    assert buttons.label(Action.VOLUME_UP, GAMEPAD) == ""
