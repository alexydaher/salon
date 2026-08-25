# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F401
"""Focused settings panel builder."""
from __future__ import annotations

import shutil
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon import config as app_config  # noqa: E402
from salon.core import sandbox, tokens  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.services import artwork, audio, bluetooth, launcher, netinfo, wifi  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext, confirm_panel  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    ChoiceRow,
    InfoRow,
    RangeRow,
    SettingsRow,
    TextRow,
    ToggleRow,
)

_BINDABLE: tuple[tuple[Action, str], ...] = (
    (Action.OK, "Choose the highlighted thing"),
    (Action.BACK, "Go back one step"),
    (Action.MENU, "System menu, and the way out of an app"),
    (Action.OPTIONS, "The menu for the thing under the cursor"),
    (Action.SEARCH, "Open search"),
    (Action.PLAY_PAUSE, "Pause or resume whatever is playing"),
    (Action.PREV_GROUP, "Jump back a letter or a group"),
    (Action.NEXT_GROUP, "Jump on a letter or a group"),
    (Action.VOLUME_UP, "Louder"),
    (Action.VOLUME_DOWN, "Quieter"),
    (Action.MUTE, "Silence"),
)
_SOURCE_NAMES = {"pad": "Controller", "key": "Keyboard", "cec": "TV remote"}


def _bindings_panel(context: SettingsContext) -> Panel:
    """One row per action, showing what the user has bound to it.

    Shows overrides only, and says so: listing the defaults as well would
    mean printing "Cross / A / the bottom face button" for OK and inviting
    the reader to work out which of those their controller has. What this
    screen answers is "what have I changed", and the row for an action
    nobody has rebound says "Default".
    """

    def described(action: Action) -> str:
        bindings = context.bindings()
        keys = bindings.keys_for(action.value)  # type: ignore[attr-defined]
        if not keys:
            return "Default"
        labels = []
        for key in keys:
            source, _, code = key.partition(":")
            labels.append(f"{_SOURCE_NAMES.get(source, source)} 0x{int(code):X}")
        return ", ".join(labels)

    def build() -> list[SettingsRow]:
        rows: list[SettingsRow] = [
            InfoRow(
                "Press the button you want",
                "",
                detail="Choose an action, then press any button on any remote or controller",
            )
        ]
        rows.extend(
            ActionRow(
                action.value.replace("_", " ").upper(),
                lambda a=action: context.push(_capture_panel(context, a)),
                detail=f"{note} · {described(action)}",
                value="›",
            )
            for action, note in _BINDABLE
        )
        rows.append(
            ActionRow(
                "Use Salon's defaults again",
                lambda: _reset_bindings(context),
                detail="Forgets every button you have changed",
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
    captured: list[str] = []

    def on_captured(source: str, code: int) -> None:
        context.rebind(source, code, action.value)
        captured.append(f"{_SOURCE_NAMES.get(source, source)} 0x{code:X}")
        context.toast(f"{action.value.replace('_', ' ').upper()} is now {captured[-1]}.")
        context.pop()

    def build() -> list[SettingsRow]:
        context.capture_binding(on_captured)
        return [
            InfoRow(
                f"Press the button for {action.value.replace('_', ' ').upper()}",
                "Waiting…",
                detail="Any controller, keyboard or TV remote. LEFT cancels.",
            )
        ]

    return Panel(title="Waiting for a button", build=build)


def _reset_bindings(context: SettingsContext) -> None:
    context.reset_bindings()
    context.toast("Every button is back to Salon's default.")
    context.rebuild()


def _gamepad_panel(context: SettingsContext) -> Panel:
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
                detail="Recent actions appear below, newest first",
            ),
            *(
                InfoRow(entry, "")
                for entry in (context.notes[:8] or ["Nothing received yet"])
            ),
        ]

    return Panel(title="Controller test", build=build)
