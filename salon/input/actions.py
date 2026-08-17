"""The shared input action vocabulary. Pure — no gi.

All input sources (keyboard, gamepad, CEC) normalize to this enum before
anything else sees them; adding a new input source is one new file that
emits Action values, and nothing downstream has to change.
"""

from __future__ import annotations

from enum import StrEnum


class Action(StrEnum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    OK = "ok"
    BACK = "back"
    MENU = "menu"
    SEARCH = "search"
    PLAY_PAUSE = "play_pause"
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    MUTE = "mute"
    POWER = "power"
