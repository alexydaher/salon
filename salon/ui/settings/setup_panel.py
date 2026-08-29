# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Set up this television: the five things anyone changes.

Settings has eight sections and something like sixty rows, and a new
installation needs about five of them: how far in from the edges to draw,
what colour the focus is, how big the tiles are, which output the sound
goes to, and a phone to drive it with. Finding those five means knowing
which section each lives in, which is knowledge you acquire by not needing
it any more.

So they are also here, in the order somebody actually wants them, with the
step they are on named. Nothing is duplicated: every row is built by the
panel that owns it, from the same `Keyed` factory, so a value set here is
the same value that section shows and the live preview still works — safe
area, accent and tile size are all `preview=True`, which means OK on any of
them collapses to the strip over the real home screen.

Deliberately not a modal wizard. It is a panel like every other, BACK
leaves it at any point, and there is no completion state to be stuck in —
a television that will not let you out of its setup screen is the thing
this whole project is a reaction to.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.ui.settings.appearance_panel import ACCENTS  # noqa: E402
from salon.ui.settings.audio_panel import audio_panel  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    GroupRow,
    InfoRow,
    Keyed,
    SettingsRow,
    ToggleRow,
    opens_panel,
)


def setup_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    keyed = Keyed(settings)

    def build() -> list[SettingsRow]:
        return [
            InfoRow(
                "Five things worth setting",
                "",
                detail="Each one shows you the home screen while you choose. BACK leaves.",
            ),
            GroupRow("1 · Fit the picture to the screen"),
            keyed.ranged(
                "safe-area-percent",
                "Safe area",
                minimum=tokens.SAFE_AREA_MIN_PERCENT,
                maximum=tokens.SAFE_AREA_MAX_PERCENT,
                step=0.5,
                fmt=lambda v: f"{v:.1f}%",
                detail="Raise it until nothing is cut off at the edges of your television",
                preview=True,
            ),
            GroupRow("2 · Choose a colour"),
            keyed.choice(
                "accent-color",
                "Accent colour",
                ACCENTS,
                detail="What the focus ring and the glow behind a tile are made of",
                preview=True,
            ),
            GroupRow("3 · Size the tiles"),
            keyed.ranged(
                "tile-scale",
                "Tile size",
                minimum=0.5,
                maximum=1.5,
                step=0.05,
                fmt=lambda v: f"{v * 100:.0f}%",
                detail="Small enough to read from where you sit, large enough to aim at",
                preview=True,
            ),
            GroupRow("4 · Send the sound to the right place"),
            opens_panel(
                "Audio output",
                lambda: context.push(audio_panel(context, settings)),
                detail="Pick an output and play a test sound through it",
            ),
            GroupRow("5 · Pick up your phone"),
            _phone_row(context),
            GroupRow("Then"),
            opens_panel(
                "Everything else",
                lambda: context.push(_more_panel(context)),
                detail="The rest of Settings, whenever you want it",
            ),
        ]

    return Panel(
        title="Set up this television",
        build=build,
        subtitle="What a new installation needs",
        panel_id="setup",
        icon_name="preferences-other-symbolic",
    )


def _phone_row(context: SettingsContext) -> SettingsRow:
    """Turn the remote on from here, rather than sending them to Input.

    The phone is the one step that cannot be done with the thing in your
    hand, because the point of it is that there may not be a thing in your
    hand yet.
    """

    def toggle(enabled: bool) -> None:
        if not context.set_phone_remote(enabled):
            context.toast("Couldn't start the phone remote — port 8437 is already in use.")
        context.rebuild()

    return ToggleRow(
        "Use a phone as the remote",
        context.phone_remote_running,
        toggle,
        detail=(
            context.phone_remote_hint()
            if context.phone_remote_running()
            else "Switch this on, then scan the code that appears on the home screen"
        ),
    )


def _more_panel(context: SettingsContext) -> Panel:
    """A signpost, not a copy: names where each remaining thing lives.

    Listing the sections again would be a second section list that could
    disagree with the real one. This says which section to go to and lets
    the left-hand column do its job.
    """

    def build() -> list[SettingsRow]:
        return [
            InfoRow("Tiles", "", detail="Add, rename and reorder what is on the home screen"),
            InfoRow("Home screen", "", detail="Which rows appear: recents, games, favourites"),
            InfoRow("Appearance", "", detail="Theme, background, motion and density"),
            InfoRow("Input", "", detail="Rebind buttons, pair a controller, repeat speed"),
            InfoRow("Network", "", detail="Wi-Fi, wired and VPN"),
            InfoRow("System", "", detail="The computer's own settings, and power"),
        ]

    return Panel(title="Everything else", build=build)
