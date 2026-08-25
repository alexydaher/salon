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
from salon.ui.settings.bindings_panel import (  # noqa: E402
    _bindings_panel,
    _gamepad_panel,
)
from salon.ui.settings.bluetooth_panel import _bluetooth_panel  # noqa: E402
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


def input_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    def build() -> list[SettingsRow]:
        return [
            ToggleRow(
                "Use a phone as the remote",
                context.phone_remote_running,
                lambda value: _set_phone_remote(context, value),
                detail=context.phone_remote_hint(),
            ),
            ToggleRow(
                "Show the pairing code when nothing is connected",
                lambda: settings.get_boolean("remote-hint"),
                lambda value: settings.set_boolean("remote-hint", value),
                detail=(
                    "A small code in the corner of the home screen, gone as soon as "
                    "a controller or a phone turns up"
                ),
            ),
            ActionRow(
                "Pair a remote or controller",
                lambda: context.push(_bluetooth_panel(context)),
                detail="Bluetooth, without needing a mouse to do it",
                value="›",
            ),
            ActionRow(
                "Bluetooth, in detail",
                lambda: context.open_control_center("bluetooth"),
                detail="Devices needing a typed PIN, and everything else",
            ),
            ActionRow(
                "Change buttons",
                lambda: context.push(_bindings_panel(context)),
                detail="Bind any button on a controller, keyboard or TV remote",
                value="›",
            ),
            ActionRow(
                "Test a controller",
                lambda: context.push(_gamepad_panel(context)),
                detail="Shows what Salon receives, live",
                value="›",
            ),
            RangeRow(
                "Repeat delay",
                lambda: float(settings.get_int("key-repeat-initial-ms")),
                lambda value: settings.set_int("key-repeat-initial-ms", int(value)),
                minimum=150,
                maximum=1000,
                step=50,
                fmt=lambda v: f"{v:.0f} ms",
                detail="How long a direction is held before it repeats",
            ),
            RangeRow(
                "Repeat interval",
                lambda: float(settings.get_int("key-repeat-interval-ms")),
                lambda value: settings.set_int("key-repeat-interval-ms", int(value)),
                minimum=40,
                maximum=400,
                step=10,
                fmt=lambda v: f"{v:.0f} ms",
            ),
            ToggleRow(
                "Gamepad cursor in web tiles",
                lambda: settings.get_boolean("gamepad-pointer"),
                lambda value: settings.set_boolean("gamepad-pointer", value),
                detail=(
                    "Right stick moves the pointer over a web tile. "
                    "The desktop asks for permission once."
                ),
            ),
            ChoiceRow(
                "Input injection",
                [
                    ("auto", "Automatic"),
                    ("mutter", "Compositor only"),
                    ("portal", "Ask the desktop"),
                ],
                lambda: settings.get_string("input-injection"),
                lambda value: settings.set_string("input-injection", value),
                detail=_injection_detail(context, settings),
            ),
            ActionRow(
                "Forget remote-control permission",
                lambda: _forget_remote_desktop(context, settings),
                detail=(
                    "Granted — Salon reopens its session silently"
                    if settings.get_string("remote-desktop-restore-token")
                    else "Not granted yet; you'll be asked the next time it's needed"
                ),
            ),
            ToggleRow(
                "HDMI-CEC input",
                lambda: settings.get_boolean("cec-enabled"),
                lambda value: settings.set_boolean("cec-enabled", value),
                detail=(
                    "Use the TV remote over HDMI. Needs cec-client installed."
                    if shutil.which("cec-client")
                    else "Needs cec-client, which isn't installed."
                ),
            ),
        ]

    return Panel(title="Input", build=build, panel_id="input", icon_name="input-gaming-symbolic")


def _set_phone_remote(context: SettingsContext, enabled: bool) -> None:
    """Turn the phone remote on or off, and say what happened.

    The failure worth naming is the port being taken — by another copy of
    Salon, or by something else on 8437. A toggle that flips back with no
    explanation is indistinguishable from a broken toggle.
    """
    if not context.set_phone_remote(enabled):
        context.toast("Couldn't start the phone remote — port 8437 is already in use.")
    context.rebuild()


def _injection_detail(context: SettingsContext, settings: Gio.Settings) -> str:
    """What the row is actually doing, not what it was asked to do.

    The two are different often enough to matter: "Automatic" prefers the
    compositor and silently falls back to the portal, so the setting alone
    never tells you whether a consent dialog is still in your future. The
    live backend does.
    """
    live = context.pointer_backend()
    if live == "mutter":
        return "Asking the compositor directly — no permission dialog"
    if live == "portal":
        return "Going through the desktop portal, which asks permission once"
    choice = settings.get_string("input-injection")
    if choice == "portal":
        return "Not started yet; the desktop will ask permission when it is"
    return "Not started yet"


def _forget_remote_desktop(context: SettingsContext, settings: Gio.Settings) -> None:
    """Hand the remote-control grant back.

    Salon keeps the portal's restore token so the consent dialog only ever
    appears once; dropping it is how that grant is withdrawn from this side.
    The desktop's own privacy settings can revoke it independently, which is
    why a token that stops working is discarded rather than retried.
    """
    if not settings.get_string("remote-desktop-restore-token"):
        context.toast("There's no remote-control permission to forget.")
        return
    settings.set_string("remote-desktop-restore-token", "")
    context.toast("Forgotten. You'll be asked again the next time it's needed.")
    context.rebuild()
