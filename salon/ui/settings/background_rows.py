# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Appearance → Background: what is behind everything else.

Split out of `appearance_panel.py`, which had grown past the source line
cap. This is the natural seam: six rows and a sub-panel that between them
answer one question and touch three keys nothing else in the panel reads.
`wallpaper.py` next door already owns the choosing and the validating; this
is only how it is laid out as rows.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio  # noqa: E402

from salon.ui import backdrop_wallpaper  # noqa: E402
from salon.ui.settings import wallpaper  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    GroupRow,
    Keyed,
    SettingsRow,
    opens_panel,
    opens_picker,
)


def background_rows(
    context: SettingsContext, settings: Gio.Settings, keyed: Keyed
) -> list[SettingsRow]:
    """The Background group, heading included.

    Takes the caller's `Keyed` rather than making one: `restore_defaults_row`
    resets whatever that instance has handed out, so a second instance here
    would quietly put these three keys beyond the reach of the panel's own
    "Restore defaults".
    """
    has_image = backdrop_wallpaper.has_image(settings.get_string("wallpaper-path").strip())
    colour_treatment = keyed.choice(
        "wallpaper-color-treatment",
        "Background colours",
        wallpaper.COLOR_TREATMENTS,
        preview=True,
    )
    dimming = keyed.ranged(
        "wallpaper-dim",
        "Background dimming",
        minimum=0.0,
        maximum=1.0,
        step=0.04,
        fmt=lambda v: "Hidden" if v >= 0.999 else f"{v * 100:.0f}%",
        preview=True,
    )
    if not has_image:
        reason = "Only applies when a background image is selected"
        colour_treatment.make_unavailable(reason)
        dimming.make_unavailable(reason)

    return [
        GroupRow("Background"),
        keyed.choice(
            "wallpaper-path",
            "Background",
            wallpaper.choices(settings),
            detail=wallpaper.detail(settings),
            preview=True,
        ),
        opens_picker(
            "Choose a picture…",
            lambda: wallpaper.choose(context, settings, folder=False),
        ),
        opens_picker(
            "Choose a folder…",
            lambda: wallpaper.choose(context, settings, folder=True),
        ),
        colour_treatment,
        dimming,
        opens_panel(
            "Type a path…",
            lambda: context.push(_background_path_panel(context, settings)),
            detail="For paths the picker cannot reach",
        ),
    ]


def _background_path_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    """The typed path, and a way to find out whether it exists.

    A sub-panel rather than two more rows in Appearance: between them they
    serve the one person on the machine who keeps their pictures somewhere
    a file picker will not go, and they were costing everyone else two rows
    in the longest list in Settings.
    """

    def build() -> list[SettingsRow]:
        return [
            Keyed(settings).text(
                "wallpaper-path",
                "Path",
                lambda: wallpaper.edit_path(context, settings),
                placeholder="Salon ambient",
                detail="Image, folder, or - for none",
            ),
            ActionRow(
                "Check this path",
                lambda: context.toast(wallpaper.detail(settings)),
            ),
        ]

    return Panel(title="Background path", build=build)
