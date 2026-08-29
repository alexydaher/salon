# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → About: what this is, and where to take a problem with it.

It used to be four absolute filesystem paths and a copy of a row in the
browser panel. A path is unreadable at three metres and unactionable with a
D-pad, and About is the one screen on a television that somebody reaches
while holding a phone — so the project's address is offered as a QR code,
which is the only form of URL this device can hand over.

Paths have not been removed, only demoted: they are detail lines under rows
that say what the thing *is*, and "Open config folder" is the row that
actually does something with them.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.qr_panel import qr_panel  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    GroupRow,
    InfoRow,
    SettingsRow,
    opens_panel,
)

PROJECT_URL = "https://github.com/alexydaher/salon"
_ISSUES_URL = f"{PROJECT_URL}/issues"


def about_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    def build() -> list[SettingsRow]:
        return [
            GroupRow("Salon"),
            InfoRow(
                "Version",
                context.version,
                detail="A fullscreen launcher for a television, driven by a remote",
            ),
            InfoRow("Licence", "GPL-3.0-or-later", detail="Free software; the source is public"),
            GroupRow("The project"),
            opens_panel(
                "Project page",
                lambda: context.push(
                    qr_panel(
                        "Project page",
                        PROJECT_URL,
                        "Point a phone camera at this to open the repository.",
                    )
                ),
                detail=PROJECT_URL,
            ),
            opens_panel(
                "Report a problem",
                lambda: context.push(
                    qr_panel(
                        "Report a problem",
                        _ISSUES_URL,
                        "Please say what you pressed and what happened instead.",
                    )
                ),
                detail=_ISSUES_URL,
            ),
            GroupRow("Files on this computer"),
            ActionRow(
                "Open config folder",
                lambda: _open_folder(context),
                detail=GLib.path_get_dirname(context.config_path),
            ),
            InfoRow(
                "Your tiles",
                "tiles.json",
                detail=f"{context.config_path} — edited by hand, it hot-reloads",
            ),
            InfoRow(
                "Artwork drop folder",
                "artwork",
                detail=f"{_artwork_dir()} — drop <tile id>.png here",
            ),
        ]

    return Panel(
        title="About",
        build=build,
        subtitle="Version, licence and files",
        panel_id="about",
        icon_name="help-about-symbolic",
    )


def _artwork_dir() -> str:
    from salon.services.artwork import artwork_drop_dir

    return str(artwork_drop_dir())


def _open_folder(context: SettingsContext) -> None:
    folder = GLib.path_get_dirname(context.config_path)
    try:
        Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(folder).get_uri(), None)
    except GLib.Error as exc:
        context.toast(f"Couldn't open {folder}: {exc.message}")
