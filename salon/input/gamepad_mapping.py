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
    # BTN_SELECT — Create on a DualSense, View on an Xbox pad, Minus on a
    # Switch Pro. A controller had no play/pause at all: CEC's play keys
    # and the keyboard's media keys both reach `Action.PLAY_PAUSE` and the
    # pad reached nothing, so pausing a film meant picking up the phone.
    # Deliberately not L3/R3 (0x13D/0x13E), which are clicked by accident
    # while the stick that drives navigation is being pushed.
    0x13A: Action.PLAY_PAUSE,
    0x13B: Action.MENU,
    0x220: Action.UP,
    0x221: Action.DOWN,
    0x222: Action.LEFT,
    0x223: Action.RIGHT,
}
