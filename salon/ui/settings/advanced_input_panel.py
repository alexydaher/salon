# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Input → Advanced: injection backend, permission, HDMI-CEC.

Three settings that matter enormously when they are wrong and never
otherwise. Split out of `input_panel.py` both because that file had grown
past what one screen of code should be and because these belong behind one
press: nobody arrives at Settings meaning to change which D-Bus interface
Salon injects pointer events through.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio  # noqa: E402

from salon.core import sandbox  # noqa: E402
from salon.input import cec_in  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    GroupRow,
    Keyed,
    SettingsRow,
)

_TOKEN_KEY = "remote-desktop-restore-token"


def advanced_input_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    caps = sandbox.capabilities()
    keyed = Keyed(settings)

    def build() -> list[SettingsRow]:
        return [
            GroupRow("Pointer and typing"),
            keyed.choice(
                "input-injection",
                "Input injection",
                (
                    [
                        ("auto", "Automatic"),
                        ("mutter", "Compositor only"),
                        ("portal", "Ask the desktop"),
                    ]
                    if caps.mutter_injection
                    else [("portal", "Ask the desktop")]
                ),
                detail=_injection_detail(context, settings),
            ),
            ActionRow(
                "Check which route is live",
                lambda: context.toast(
                    f"Pointer backend: {context.pointer_backend() or 'not active yet'}"
                ),
                detail="Reports the backend currently controlling browser tiles",
            ),
            ActionRow(
                "Forget remote-control permission",
                lambda: _forget_remote_desktop(context, settings),
                detail=(
                    "Granted — Salon reopens its session silently"
                    if settings.get_string(_TOKEN_KEY)
                    else "Not granted yet; you'll be asked the next time it's needed"
                ),
            ),
            GroupRow("Television remote"),
            keyed.toggle(
                "cec-enabled",
                "HDMI-CEC input",
                # host_which, not shutil.which: in the Flatpak cec-client is
                # spawned on the host, so the sandbox's PATH is the wrong
                # place to look and always answered "not installed".
                detail=(
                    "Use the TV remote over HDMI. Needs cec-client installed."
                    if cec_in.available()
                    else "Needs cec-client, which isn't installed."
                ),
            ),
        ]

    return Panel(title="Advanced input", build=build)


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
    if settings.get_string("input-injection") == "portal":
        return "Not started yet; the desktop will ask permission when it is"
    return "Not started yet"


def _forget_remote_desktop(context: SettingsContext, settings: Gio.Settings) -> None:
    """Hand the remote-control grant back.

    Salon keeps the portal's restore token so the consent dialog only ever
    appears once; dropping it is how that grant is withdrawn from this side.
    The desktop's own privacy settings can revoke it independently, which is
    why a token that stops working is discarded rather than retried.
    """
    if not settings.get_string(_TOKEN_KEY):
        context.toast("There's no remote-control permission to forget.")
        return
    settings.set_string(_TOKEN_KEY, "")
    context.toast("Forgotten. You'll be asked again the next time it's needed.")
    context.rebuild()
