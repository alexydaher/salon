# SPDX-License-Identifier: GPL-3.0-or-later
"""What to *call* each button, on the device actually in the user's hands.

Pure — no gi. The on-screen legend needs a name for a button, and there is
no single true answer: `Action.OPTIONS` is the intent, but nobody is
holding an "OPTIONS" button. On a DualSense it is Square, on an Xbox pad it
is X, on a television remote it is whatever the manufacturer printed, and
on a keyboard it is the `o` key.

Naming the *intent* is what the legend used to do, and it is the one answer
that is wrong on every device at once. So this maps (action, source) to the
label that device's owner can find by looking down, and the home screen
tracks which source last delivered a press.

The gamepad families are keyed off the physical position of the face
buttons, not their printed letters, because that is what
`input/gamepad_mapping.py` binds: 0x130 is BTN_SOUTH whatever the vendor
silkscreened on it. A Nintendo pad's south button says B and an Xbox pad's
says A, which is the same disagreement `core/bindings.py` exists to let a
user settle by hand — this only picks a better default caption for it.

Deliberately *not* glyphs. `data/fonts/` is empty and the system UI font is
whatever the distribution ships, so a legend that renders ⓐ or ✕ renders a
tofu box on the machine that does not have them. Words survive.
"""

from __future__ import annotations

from salon.core.actions import Action
from salon.core.bindings import CEC, GAMEPAD, KEYBOARD

# The fourth source. Not in `bindings.SOURCES`, which is the set of things
# that produce rebindable hardware codes — the phone sends action names
# over HTTP and has no buttons to rebind.
PHONE = "phone"

GENERIC = "generic"
PLAYSTATION = "playstation"
NINTENDO = "nintendo"

_KEYBOARD: dict[Action, str] = {
    Action.OK: "Enter",
    Action.BACK: "Backspace",
    Action.MENU: "Menu",
    Action.OPTIONS: "O",
    Action.SEARCH: "/",
    Action.UP: "Up",
    Action.DOWN: "Down",
    Action.LEFT: "Left",
    Action.RIGHT: "Right",
}

# What a remote's keys are called in its own manual, which is as close as
# anyone gets to a standard here. Also the fallback for the phone, whose
# on-screen buttons carry exactly these words.
_REMOTE: dict[Action, str] = {
    Action.OK: "OK",
    Action.BACK: "Back",
    Action.MENU: "Menu",
    Action.OPTIONS: "Options",
    Action.SEARCH: "Search",
    Action.UP: "Up",
    Action.DOWN: "Down",
    Action.LEFT: "Left",
    Action.RIGHT: "Right",
}

_GAMEPAD_DIRECTIONS: dict[Action, str] = {
    Action.UP: "Up",
    Action.DOWN: "Down",
    Action.LEFT: "Left",
    Action.RIGHT: "Right",
}

_GAMEPAD_FAMILIES: dict[str, dict[Action, str]] = {
    GENERIC: {
        Action.OK: "A",
        Action.BACK: "B",
        Action.MENU: "Start",
        Action.OPTIONS: "X",
        Action.SEARCH: "Y",
        **_GAMEPAD_DIRECTIONS,
    },
    PLAYSTATION: {
        Action.OK: "Cross",
        Action.BACK: "Circle",
        Action.MENU: "Options",
        Action.OPTIONS: "Square",
        Action.SEARCH: "Triangle",
        **_GAMEPAD_DIRECTIONS,
    },
    NINTENDO: {
        # South and east are swapped relative to an Xbox pad, so the button
        # Salon binds to OK is the one printed B.
        Action.OK: "B",
        Action.BACK: "A",
        Action.MENU: "Plus",
        Action.OPTIONS: "Y",
        Action.SEARCH: "X",
        **_GAMEPAD_DIRECTIONS,
    },
}

_PLAYSTATION_NAMES = ("dualsense", "dualshock", "playstation", "sony", "ps3", "ps4", "ps5")
_NINTENDO_NAMES = ("nintendo", "switch", "joy-con", "joycon", "pro controller", "wii")


def gamepad_family(device_name: str) -> str:
    """Which face-button vocabulary a controller's own name implies.

    Matched on the name libmanette reports, which is the vendor's USB
    product string — "Sony Interactive Entertainment DualSense Wireless
    Controller" for the one pad this has been tested against. Unrecognised
    names get the Xbox-style letters, because that is what an unlabelled
    generic pad almost always copies.
    """
    lowered = device_name.casefold()
    if any(name in lowered for name in _PLAYSTATION_NAMES):
        return PLAYSTATION
    if any(name in lowered for name in _NINTENDO_NAMES):
        return NINTENDO
    return GENERIC


def label(action: Action, source: str, *, family: str = GENERIC) -> str:
    """The caption for one button on one kind of device.

    Falls back to the remote's vocabulary for anything unknown — an action
    with no button on that device, or a source that has not been named
    here. "OK" on a keyboard is a worse caption than "Enter" and a much
    better one than an empty chip.
    """
    if source == GAMEPAD:
        return _GAMEPAD_FAMILIES.get(family, _GAMEPAD_FAMILIES[GENERIC]).get(
            action, _REMOTE.get(action, "")
        )
    if source == KEYBOARD:
        return _KEYBOARD.get(action, _REMOTE.get(action, ""))
    if source in (CEC, PHONE):
        return _REMOTE.get(action, "")
    return _REMOTE.get(action, "")
