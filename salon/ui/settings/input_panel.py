# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Input: the remotes, the buttons, and how they feel."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio  # noqa: E402

from salon.ui.settings.advanced_input_panel import advanced_input_panel  # noqa: E402
from salon.ui.settings.bindings_panel import bindings_panel, gamepad_panel  # noqa: E402
from salon.ui.settings.bluetooth_panel import _bluetooth_panel  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    GroupRow,
    InfoRow,
    Keyed,
    SettingsRow,
    ToggleRow,
    opens_panel,
    restore_defaults_row,
)


def input_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    keyed = Keyed(settings)

    def build() -> list[SettingsRow]:
        return [
            GroupRow("Remotes"),
            ToggleRow(
                "Use a phone as the remote",
                context.phone_remote_running,
                lambda value: _set_phone_remote(context, value),
                # The address, once there is one. This used to be the hint
                # string, which said "Off" — under a row whose own value
                # already said Off, in a larger font, half an inch away.
                detail=_phone_detail(context),
            ),
            keyed.toggle(
                "remote-hint",
                "Show the pairing code when nothing is connected",
                detail=(
                    "A small code in the corner of the home screen, gone as soon as "
                    "a controller or a phone turns up"
                ),
            ),
            opens_panel(
                "Pair a remote or controller",
                lambda: context.push(_bluetooth_panel(context)),
                detail="Bluetooth, without needing a mouse to do it",
            ),
            GroupRow("Buttons"),
            opens_panel(
                "Change buttons",
                lambda: context.push(bindings_panel(context)),
                detail="Bind any button on a controller, keyboard or TV remote",
            ),
            opens_panel(
                "Test a controller",
                lambda: context.push(gamepad_panel(context)),
                detail="Shows what Salon receives, live",
            ),
            GroupRow("Feel"),
            keyed.ranged(
                "key-repeat-initial-ms",
                "Repeat delay",
                minimum=150,
                maximum=1000,
                step=50,
                fmt=lambda v: f"{v:.0f} ms",
                detail="How long a direction is held before it starts repeating",
            ),
            keyed.ranged(
                "key-repeat-interval-ms",
                "Repeat interval",
                minimum=40,
                maximum=400,
                step=10,
                fmt=lambda v: f"{v:.0f} ms",
                detail="How fast it repeats once it starts",
            ),
            opens_panel(
                "Try the repeat speed",
                lambda: context.push(_repeat_practice_panel(context)),
                detail="Hold a direction here and feel what these two settings do",
            ),
            keyed.toggle(
                "gamepad-pointer",
                "Gamepad cursor in web tiles",
                detail=(
                    "Right stick moves the pointer over a web tile. "
                    "The desktop asks for permission once."
                ),
            ),
            GroupRow("This section"),
            opens_panel(
                "Advanced input",
                lambda: context.push(advanced_input_panel(context, settings)),
                detail="Injection backend, permissions and HDMI-CEC",
            ),
            restore_defaults_row(keyed, context.toast, context.rebuild),
        ]

    return Panel(
        title="Input",
        build=build,
        subtitle="Remotes, buttons and repeat",
        panel_id="input",
        icon_name="input-gaming-symbolic",
    )


def _repeat_practice_panel(context: SettingsContext) -> Panel:
    """A place to hold a direction down and feel the two timings.

    "Repeat delay 400 ms" and "Repeat interval 120 ms" are numbers you can
    only evaluate against a remembered feeling of a different pair of
    numbers. This is twenty rows to walk through at the current settings,
    which answers the question in about a second.
    """
    def build() -> list[SettingsRow]:
        rows: list[SettingsRow] = [
            InfoRow(
                "Hold UP or DOWN",
                "",
                detail="The cursor moves at exactly the delay and interval you have set",
            )
        ]
        rows.extend(ActionRow(f"Row {number}", lambda: None) for number in range(1, 21))
        return rows

    return Panel(title="Repeat speed", build=build)


def _phone_detail(context: SettingsContext) -> str:
    return context.phone_remote_hint() if context.phone_remote_running() else "Not running"


def _set_phone_remote(context: SettingsContext, enabled: bool) -> None:
    """Turn the phone remote on or off, and say what happened.

    The failure worth naming is the port being taken — by another copy of
    Salon, or by something else on 8437. A toggle that flips back with no
    explanation is indistinguishable from a broken toggle.
    """
    if not context.set_phone_remote(enabled):
        context.toast("Couldn't start the phone remote — port 8437 is already in use.")
    context.rebuild()
