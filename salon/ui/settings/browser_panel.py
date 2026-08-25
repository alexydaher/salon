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


def browser_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    def build() -> list[SettingsRow]:
        detected = launcher.detect_browser()
        configured = settings.get_string("browser-command")
        return [
            TextRow(
                "Browser command",
                lambda: configured,
                lambda: _edit_browser(context, settings),
                placeholder="Autodetect",
                detail=(
                    " ".join(detected)
                    if detected
                    else "No browser found. Install Google Chrome to open web services."
                ),
            ),
            InfoRow(
                "Detected",
                " ".join(detected) if detected else "None",
                detail="Chrome, then Chromium, then the Flatpak, in that order",
            ),
            TextRow(
                "Extra flags",
                lambda: " ".join(settings.get_strv("browser-extra-flags")),
                lambda: _edit_flags(context, settings),
                placeholder="None",
                detail="Appended after the flags Salon computes for each tile",
            ),
            InfoRow(
                "Streaming quality",
                "720p maximum",
                detail=(
                    "Chrome on Linux uses software Widevine, so Netflix and "
                    "others cap resolution. This is a licensing limit, not a setting."
                ),
            ),
        ]

    return Panel(
        title="Browser", build=build, panel_id="browser", icon_name="web-browser-symbolic"
    )


def _edit_browser(context: SettingsContext, settings: Gio.Settings) -> None:
    def done(value: str | None) -> None:
        if value is None:
            return
        settings.set_string("browser-command", value.strip())
        context.rebuild()

    context.edit_text(
        "Browser command (empty to autodetect)", settings.get_string("browser-command"), done
    )


def _edit_flags(context: SettingsContext, settings: Gio.Settings) -> None:
    def done(value: str | None) -> None:
        if value is None:
            return
        settings.set_strv("browser-extra-flags", value.split())
        context.rebuild()

    context.edit_text(
        "Extra browser flags, space separated",
        " ".join(settings.get_strv("browser-extra-flags")),
        done,
    )
