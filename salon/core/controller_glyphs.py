# SPDX-License-Identifier: GPL-3.0-or-later
"""Semantic names for controller marks drawn by the button legend."""

from __future__ import annotations

from salon.core.actions import Action
from salon.core.bindings import GAMEPAD

_GAMEPAD_GLYPHS: dict[str, dict[Action, str]] = {
    "playstation": {
        Action.OK: "playstation-cross",
        Action.BACK: "playstation-circle",
        Action.MENU: "playstation-options",
        Action.OPTIONS: "playstation-square",
        Action.SEARCH: "playstation-triangle",
        Action.PLAY_PAUSE: "playstation-create",
    },
    "xbox": {
        Action.OK: "xbox-a",
        Action.BACK: "xbox-b",
        Action.MENU: "xbox-menu",
        Action.OPTIONS: "xbox-x",
        Action.SEARCH: "xbox-y",
        Action.PLAY_PAUSE: "xbox-view",
    },
}


def glyph(action: Action, source: str, *, family: str = "generic") -> str:
    """Return a UI-drawable controller mark, or ``""`` for text fallback.

    Semantic names keep the core independent of GTK and avoid controller
    symbols that may be missing from the host's fonts.
    """
    if source != GAMEPAD:
        return ""
    return _GAMEPAD_GLYPHS.get(family, {}).get(action, "")
