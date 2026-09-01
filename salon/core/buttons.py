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

The words remain the portable fallback, but recognised PlayStation and Xbox
controllers also expose a small semantic glyph name.  The UI draws those marks
itself instead of relying on controller-symbol Unicode characters that may be
missing from the system font.
"""

from __future__ import annotations

from salon.core.actions import Action
from salon.core.bindings import CEC, GAMEPAD, KEYBOARD
from salon.core.controller_glyphs import glyph as glyph

# The fourth source. Not in `bindings.SOURCES`, which is the set of things
# that produce rebindable hardware codes — the phone sends action names
# over HTTP and has no buttons to rebind.
PHONE = "phone"

GENERIC = "generic"
PLAYSTATION = "playstation"
XBOX = "xbox"
NINTENDO = "nintendo"

_KEYBOARD: dict[Action, str] = {
    Action.OK: "Enter",
    Action.BACK: "Backspace",
    Action.MENU: "Menu",
    Action.OPTIONS: "O",
    Action.SEARCH: "/",
    Action.PLAY_PAUSE: "Play",
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
    Action.PLAY_PAUSE: "Play",
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
        Action.PLAY_PAUSE: "View",
        **_GAMEPAD_DIRECTIONS,
    },
    PLAYSTATION: {
        Action.OK: "Cross",
        Action.BACK: "Circle",
        Action.MENU: "Options",
        Action.OPTIONS: "Square",
        Action.SEARCH: "Triangle",
        Action.PLAY_PAUSE: "Create",
        **_GAMEPAD_DIRECTIONS,
    },
    XBOX: {
        Action.OK: "A",
        Action.BACK: "B",
        Action.MENU: "Menu",
        Action.OPTIONS: "X",
        Action.SEARCH: "Y",
        Action.PLAY_PAUSE: "View",
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
        Action.PLAY_PAUSE: "Minus",
        **_GAMEPAD_DIRECTIONS,
    },
}

_PLAYSTATION_NAMES = ("dualsense", "dualshock", "playstation", "sony", "ps3", "ps4", "ps5")
_XBOX_NAMES = ("xbox", "x-box", "xinput", "microsoft")
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
    if any(name in lowered for name in _XBOX_NAMES):
        return XBOX
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


# --- naming a button by its hardware code --------------------------------

# The physical position of each face and shoulder button, in evdev's
# vocabulary. `_GAMEPAD_FAMILIES` above already says what each *action* is
# called on a given pad; this is the other direction, for Settings → Change
# buttons, which has a code in hand and no action to look it up by.
_PAD_POSITIONS: dict[int, str] = {
    0x130: "south",
    0x131: "east",
    0x133: "north",
    0x134: "west",
    0x136: "left shoulder",
    0x137: "right shoulder",
    0x13A: "select",
    0x13B: "start",
    0x13D: "left stick",
    0x13E: "right stick",
    0x220: "up",
    0x221: "down",
    0x222: "left",
    0x223: "right",
}

# What each position is *printed* as, per family. Derived from the same
# physical facts as `_GAMEPAD_FAMILIES` and kept beside it so the two can
# never drift: OK is bound to south, and south is Cross on a PlayStation
# pad in both tables.
_PAD_NAMES: dict[str, dict[str, str]] = {
    GENERIC: {"south": "A", "east": "B", "north": "Y", "west": "X",
              "select": "View", "start": "Start"},
    PLAYSTATION: {"south": "Cross", "east": "Circle", "north": "Triangle", "west": "Square",
                  "select": "Create", "start": "Options"},
    XBOX: {"south": "A", "east": "B", "north": "Y", "west": "X",
           "select": "View", "start": "Menu"},
    NINTENDO: {"south": "B", "east": "A", "north": "X", "west": "Y",
               "select": "Minus", "start": "Plus"},
}
_PAD_SHARED: dict[str, str] = {
    "left shoulder": "L1",
    "right shoulder": "R1",
    "left stick": "L3",
    "right stick": "R3",
    "up": "D-pad up",
    "down": "D-pad down",
    "left": "D-pad left",
    "right": "D-pad right",
}

# CEC 1.4 user-control codes, in the words a television manual uses. Only
# the ones Salon reacts to plus the handful a remote sends by accident —
# a code nobody has named is shown as its number, which is still the most
# useful thing that can be said about it.
_CEC_NAMES: dict[int, str] = {
    0x00: "Select", 0x01: "Up", 0x02: "Down", 0x03: "Left", 0x04: "Right",
    0x09: "Root menu", 0x0B: "Contents menu", 0x0D: "Exit",
    0x30: "Channel up", 0x31: "Channel down",
    0x40: "Power", 0x41: "Volume up", 0x42: "Volume down", 0x43: "Mute",
    0x44: "Play", 0x45: "Stop", 0x46: "Pause", 0x48: "Rewind",
    0x49: "Fast forward", 0x6B: "Power on", 0x71: "Blue", 0x72: "Red",
    0x73: "Green", 0x74: "Yellow",
}


def code_label(source: str, code: int, *, family: str = GENERIC) -> str:
    """What the button with this hardware code is called, or "".

    Settings → Change buttons used to print `Controller 0x130`, which names
    a button nobody can find by looking down at the pad in their hands.
    Empty for a code this doesn't know and for `KEYBOARD`, whose codes are
    GDK keyvals — the toolkit already names those and duplicating its table
    here would be a second thing to keep current.
    """
    if source == GAMEPAD:
        position = _PAD_POSITIONS.get(code)
        if position is None:
            return ""
        names = _PAD_NAMES.get(family, _PAD_NAMES[GENERIC])
        return names.get(position) or _PAD_SHARED.get(position, "")
    if source == CEC:
        return _CEC_NAMES.get(code, "")
    return ""
