# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused settings panel builder."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    InfoRow,
    SettingsRow,
)


def about_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    def build() -> list[SettingsRow]:
        return [
            InfoRow("Version", context.version),
            InfoRow("Tiles", context.config_path, detail="Edit by hand any time; it hot-reloads"),
            InfoRow("Artwork drop folder", _artwork_dir()),
            ActionRow(
                "Open config folder",
                lambda: _open_folder(context),
                detail="Opens in the desktop file manager",
            ),
            InfoRow(
                "Streaming",
                "720p on Linux",
                detail=(
                    "Chrome uses software Widevine here, so Netflix, Prime Video "
                    "and Disney+ cap resolution. No setting changes it."
                ),
            ),
        ]

    return Panel(title="About", build=build, panel_id="about", icon_name="help-about-symbolic")


def _artwork_dir() -> str:
    from salon.services.artwork import artwork_drop_dir

    return str(artwork_drop_dir())


def _open_folder(context: SettingsContext) -> None:
    folder = GLib.path_get_dirname(context.config_path)
    try:
        Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(folder).get_uri(), None)
    except GLib.Error as exc:
        context.toast(f"Couldn't open {folder}: {exc.message}")
