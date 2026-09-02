# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Input → Change buttons, and the controller test beside it."""

from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")

from gi.repository import Gdk  # noqa: E402

from salon.core import buttons  # noqa: E402
from salon.core.bindings import CEC, GAMEPAD, KEYBOARD, split_key  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    GroupRow,
    InfoRow,
    SettingsRow,
    opens_panel,
)

# Sentence case, because these are read as prose in a row label. They used
# to be `action.value.replace("_", " ").upper()`, which put PREV GROUP and
# PLAY PAUSE on the screen — enum names, shouted.
_ACTION_NAMES: dict[Action, str] = {
    Action.OK: "Select",
    Action.BACK: "Go back",
    Action.MENU: "Menu",
    Action.OPTIONS: "Options",
    Action.SEARCH: "Search",
    Action.PLAY_PAUSE: "Play / Pause",
    Action.PREV_GROUP: "Previous group",
    Action.NEXT_GROUP: "Next group",
    Action.VOLUME_UP: "Volume up",
    Action.VOLUME_DOWN: "Volume down",
    Action.MUTE: "Mute",
}

_GROUPS: tuple[tuple[str, tuple[Action, ...]], ...] = (
    ("Getting around", (Action.OK, Action.BACK, Action.MENU, Action.OPTIONS, Action.SEARCH)),
    ("Jumping", (Action.PREV_GROUP, Action.NEXT_GROUP)),
    ("Sound and playback", (Action.PLAY_PAUSE, Action.VOLUME_UP, Action.VOLUME_DOWN, Action.MUTE)),
)

_SOURCE_NAMES = {GAMEPAD: "Controller", KEYBOARD: "Keyboard", CEC: "TV remote"}


def button_name(source: str, code: int) -> str:
    """What to call one physical button.

    `Controller 0x130` names a button nobody can find by looking down at
    the pad in their hands. `core/buttons.py` knows the face-button
    vocabulary and GDK already names every keyval, so between them almost
    every code has a word; the number survives only as the last resort,
    where it is still the most useful thing that can be said.
    """
    if source == KEYBOARD:
        named = Gdk.keyval_name(code)
        return str(named) if named else f"Key {code}"
    # No pad is connected to Settings — this is describing a *stored*
    # binding, so the generic vocabulary is the only honest one to use.
    named = buttons.code_label(source, code)
    return named or f"{_SOURCE_NAMES.get(source, source)} {code:#x}"


def _described(context: SettingsContext, action: Action) -> str:
    bindings = context.bindings()
    keys = bindings.keys_for(action.value)  # type: ignore[attr-defined]
    named: list[str] = []
    for key in keys:
        parsed = split_key(key)
        if parsed is None:
            continue
        source, code = parsed
        named.append(f"{_SOURCE_NAMES.get(source, source)}: {button_name(source, code)}")
    return " · ".join(named) if named else "Default"


def bindings_panel(context: SettingsContext) -> Panel:
    """One row per action, showing what the user has bound to it.

    Shows overrides only, and says so: listing the defaults as well would
    mean printing "Cross / A / the bottom face button" for OK and inviting
    the reader to work out which of those their controller has. What this
    screen answers is "what have I changed", and the row for an action
    nobody has rebound says "Default".
    """

    def build() -> list[SettingsRow]:
        rows: list[SettingsRow] = []
        for heading, actions in _GROUPS:
            rows.append(GroupRow(heading))
            rows.extend(
                opens_panel(
                    _ACTION_NAMES[action],
                    lambda a=action: context.push(_capture_panel(context, a)),
                    detail=_described(context, action),
                )
                for action in actions
            )
        rows.append(GroupRow("This section"))
        rows.append(
            ActionRow(
                "Use Salon's defaults again",
                lambda: _reset_bindings(context),
            )
        )
        return rows

    return Panel(title="Change buttons", build=build)


def _capture_panel(context: SettingsContext, action: Action) -> Panel:
    """Waits for one press, binds it, and pops itself.

    A panel rather than a dialog because BACK has to be able to get out of
    it — and BACK is itself a bindable button, so the capture is armed only
    while this panel is on screen and is cancelled on the way out.
    """

    def on_captured(source: str, code: int) -> None:
        context.rebind(source, code, action.value)
        context.toast(f"{_ACTION_NAMES[action]} is now {button_name(source, code)}.")
        context.pop()

    def build() -> list[SettingsRow]:
        context.capture_binding(on_captured)
        return [
            InfoRow(
                "Press a button",
                "",
                detail="Back cancels",
            )
        ]

    return Panel(title=f"Change {_ACTION_NAMES[action]}", build=build)


def _reset_bindings(context: SettingsContext) -> None:
    context.reset_bindings()
    context.toast("Every button is back to Salon's default.")
    context.rebuild()


def gamepad_panel(context: SettingsContext) -> Panel:
    """§6.8's gamepad visualiser: show the `Action` stream as it arrives.

    The value of this is diagnostic — when a controller "doesn't work", this
    is what distinguishes "the pad sends nothing" from "the pad sends
    something Salon doesn't map".
    """

    def build() -> list[SettingsRow]:
        return [
            InfoRow(
                "Press anything on the controller",
                "",
            ),
            *(
                InfoRow(_ACTION_NAMES.get(_action_of(entry), entry), "")
                for entry in (context.notes[:8] or ["Nothing received yet"])
            ),
        ]

    return Panel(title="Controller test", build=build)


def _action_of(name: str) -> Action | None:
    try:
        return Action(name)
    except ValueError:
        return None
