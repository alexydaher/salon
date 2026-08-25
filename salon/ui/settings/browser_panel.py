# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused settings panel builder."""

from __future__ import annotations

import shlex

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon.services import launcher  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    InfoRow,
    SettingsRow,
    TextRow,
)


def browser_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    resolution = launcher.BrowserResolution(launcher.BrowserAvailability.NOT_INSTALLED)
    preflight_started = False

    def on_preflight(result: launcher.BrowserResolution) -> bool:
        nonlocal resolution
        resolution = result
        context.rebuild()
        return GLib.SOURCE_REMOVE

    def build() -> list[SettingsRow]:
        nonlocal preflight_started
        if not preflight_started:
            preflight_started = True
            launcher.preflight_browser(on_preflight)
        detected = resolution.argv
        failure_detail = {
            launcher.BrowserAvailability.NOT_INSTALLED: "No supported browser is installed.",
            launcher.BrowserAvailability.HOST_EXECUTION_FAILED: "Host browser detection failed.",
        }.get(resolution.availability, "")
        return [
            TextRow(
                "Browser command",
                lambda: settings.get_string("browser-command"),
                lambda: _edit_browser(context, settings),
                placeholder="Autodetect",
                detail=(" ".join(detected) if detected else failure_detail),
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

    return Panel(title="Browser", build=build, panel_id="browser", icon_name="web-browser-symbolic")


def _edit_browser(context: SettingsContext, settings: Gio.Settings) -> None:
    def done(value: str | None) -> None:
        if value is None:
            return
        normalized = value.strip()
        try:
            shlex.split(normalized)
        except ValueError as exc:
            context.toast(f"Browser command wasn't changed: {exc}")
            return
        settings.set_string("browser-command", normalized)
        context.rebuild()

    context.edit_text(
        "Browser command (empty to autodetect)", settings.get_string("browser-command"), done
    )


def _edit_flags(context: SettingsContext, settings: Gio.Settings) -> None:
    def done(value: str | None) -> None:
        if value is None:
            return
        try:
            flags = shlex.split(value)
        except ValueError as exc:
            context.toast(f"Browser flags weren't changed: {exc}")
            return
        settings.set_strv("browser-extra-flags", flags)
        context.rebuild()

    context.edit_text(
        "Extra browser flags, space separated",
        " ".join(settings.get_strv("browser-extra-flags")),
        done,
    )
