# SPDX-License-Identifier: GPL-3.0-or-later
"""Web tiles: which browser opens them, and what it can be told to do.

No longer a top-level section. It was four rows — two of them read-only,
and one of those a verbatim copy of a row in About — sitting beside Audio
and Network in a list of nine that had stopped fitting the screen without
scrolling. It is reached from System → Web tiles, which is where "how does
Salon launch things" belongs.
"""

from __future__ import annotations

import shlex

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon.services import launcher  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    GroupRow,
    InfoRow,
    Keyed,
    SettingsRow,
    TextRow,
    opens_panel,
)

_FAILURES = {
    launcher.BrowserAvailability.NOT_INSTALLED: "No supported browser is installed.",
    launcher.BrowserAvailability.HOST_EXECUTION_FAILED: "Host browser detection failed.",
}


def browser_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    resolution = launcher.BrowserResolution(launcher.BrowserAvailability.NOT_INSTALLED)
    started = False

    def on_preflight(result: launcher.BrowserResolution) -> bool:
        nonlocal resolution
        resolution = result
        context.rebuild()
        return GLib.SOURCE_REMOVE

    def build() -> list[SettingsRow]:
        nonlocal started
        if not started:
            started = True
            launcher.preflight_browser(on_preflight)
        detected = resolution.argv
        failure = _FAILURES.get(resolution.availability, "")
        return [
            GroupRow("Browser"),
            InfoRow(
                "Detected",
                " ".join(detected) if detected else "None",
            ),
            ActionRow(
                "Test browser configuration",
                lambda: context.toast(
                    f"Browser ready: {' '.join(detected)}"
                    if detected
                    else failure or "Browser check is still running."
                ),
            ),
            GroupRow("Streaming"),
            InfoRow(
                "Maximum quality",
                "720p on Linux",
                detail=(
                    "Chrome on Linux uses software Widevine, so Netflix, Prime Video "
                    "and Disney+ cap resolution. This is a licensing limit, not a setting."
                ),
            ),
            GroupRow("This section"),
            opens_panel(
                "Custom command and flags",
                lambda: context.push(_advanced_browser_panel(context, settings)),
            ),
        ]

    return Panel(
        title="Web tiles",
        build=build,
        panel_id="browser",
        icon_name="web-browser-symbolic",
    )


def _advanced_browser_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    keyed = Keyed(settings)

    def build() -> list[SettingsRow]:
        return [
            keyed.text(
                "browser-command",
                "Browser command",
                lambda: _edit_browser(context, settings),
                placeholder="Autodetect",
            ),
            _flags_row(context, settings),
        ]

    return Panel(title="Custom browser", build=build)


def _flags_row(context: SettingsContext, settings: Gio.Settings) -> SettingsRow:
    """A `as` key, so `Keyed.text` cannot own it — the stored type is a
    string list and the row edits a space-separated line."""
    return TextRow(
        "Extra flags",
        lambda: " ".join(settings.get_strv("browser-extra-flags")),
        lambda: _edit_flags(context, settings),
        placeholder="None",
        default=" ".join(settings.get_default_value("browser-extra-flags").unpack()),
    )


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
