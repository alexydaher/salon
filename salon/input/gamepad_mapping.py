# SPDX-License-Identifier: GPL-3.0-or-later
"""Linux evdev codes and Salon's default controller mapping."""

from salon.core.actions import Action

ABS_X = 0
ABS_Y = 1
ABS_RX = 3
ABS_RY = 4
ABS_HAT_X = 16
ABS_HAT_Y = 17
RIGHT_STICK_AXES = (ABS_RX, ABS_RY)

BUTTON_ACTIONS: dict[int, Action] = {
    0x130: Action.OK,
    0x131: Action.BACK,
    0x133: Action.SEARCH,
    0x134: Action.OPTIONS,
    0x136: Action.PREV_GROUP,
    0x137: Action.NEXT_GROUP,
    0x13B: Action.MENU,
    0x220: Action.UP,
    0x221: Action.DOWN,
    0x222: Action.LEFT,
    0x223: Action.RIGHT,
}
