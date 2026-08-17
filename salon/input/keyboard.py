"""Keyboard input source: normalizes GDK keyvals to Action.

An IR remote behind a Flirc-style receiver presents as a keyboard, so it's
served entirely by this mapping with no extra code.
"""

from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")

from gi.repository import Gdk  # noqa: E402

from salon.input.actions import Action  # noqa: E402

_KEYVAL_ACTIONS: dict[int, Action] = {
    Gdk.KEY_Up: Action.UP,
    Gdk.KEY_Down: Action.DOWN,
    Gdk.KEY_Left: Action.LEFT,
    Gdk.KEY_Right: Action.RIGHT,
    Gdk.KEY_Return: Action.OK,
    Gdk.KEY_KP_Enter: Action.OK,
    Gdk.KEY_Escape: Action.BACK,
    Gdk.KEY_BackSpace: Action.BACK,
    Gdk.KEY_Menu: Action.MENU,
    Gdk.KEY_slash: Action.SEARCH,
    Gdk.KEY_AudioPlay: Action.PLAY_PAUSE,
    Gdk.KEY_AudioRaiseVolume: Action.VOLUME_UP,
    Gdk.KEY_AudioLowerVolume: Action.VOLUME_DOWN,
    Gdk.KEY_AudioMute: Action.MUTE,
}


def action_for_keyval(keyval: int) -> Action | None:
    return _KEYVAL_ACTIONS.get(keyval)
