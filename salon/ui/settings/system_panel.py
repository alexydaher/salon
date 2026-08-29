# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → System: the computer, then Salon, then power.

Three different kinds of row used to share one flat column — six that leave
for gnome-control-center, two that are Salon's own preferences, and five
that end the session. "Display and resolution" and "Shut Down" were the
same shape of row, which is the sort of resemblance that gets a television
turned off by somebody looking for the picture settings.
"""

from __future__ import annotations

import shutil

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon.core import sandbox  # noqa: E402
from salon.services import autostart  # noqa: E402
from salon.ui.settings.browser_panel import browser_panel  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.power_panel import power_panel  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    GroupRow,
    Keyed,
    SettingsRow,
    ToggleRow,
    opens_gnome,
    opens_panel,
    restore_defaults_row,
)


def system_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    keyed = Keyed(settings)

    def gnome(label: str, panel: str, detail: str = "") -> SettingsRow:
        return opens_gnome(label, lambda: context.open_control_center(panel), detail=detail)

    def build() -> list[SettingsRow]:
        return [
            GroupRow("This computer"),
            gnome("Display and resolution", "display", "Resolution, refresh rate and scaling"),
            gnome("Date and time", "datetime", "What the clock in the top bar shows"),
            gnome("Region and language", "region"),
            gnome("Accessibility", "a11y", "Larger text, high contrast, screen reader"),
            gnome("Power and screen blanking", "power", "When the display sleeps by itself"),
            _updates_row(context),
            GroupRow("Salon"),
            opens_panel(
                "Web tiles",
                lambda: context.push(browser_panel(context, settings)),
                detail="Which browser opens them, and the streaming quality it can reach",
            ),
            _autostart_row(context, settings),
            keyed.ranged(
                "idle-inhibit-seconds",
                "Keep screen awake after launching",
                minimum=0,
                maximum=600,
                step=15,
                fmt=lambda v: "Off" if v == 0 else f"{v:.0f} s",
                off_at=0.0,
                detail="Covers the gap before the app issues its own inhibit",
            ),
            GroupRow("Ending the session"),
            opens_panel(
                "Power",
                lambda: context.push(power_panel(context)),
                detail="Suspend, log out, restart, shut down",
            ),
            GroupRow("This section"),
            restore_defaults_row(keyed, context.toast, context.rebuild),
        ]

    return Panel(
        title="System",
        build=build,
        subtitle="The computer, and startup",
        panel_id="system",
        icon_name="preferences-system-symbolic",
    )


def _updates_row(context: SettingsContext) -> SettingsRow:
    installed = bool(shutil.which("gnome-software"))
    row = opens_gnome(
        "Software updates",
        lambda: _open_updates(context),
        detail="Opens GNOME Software",
    )
    if not installed:
        row.make_unavailable("GNOME Software isn't installed")
    return row


def _autostart_row(context: SettingsContext, settings: Gio.Settings) -> SettingsRow:
    """Start with the desktop session — not the same as the Salon session.

    Unavailable rather than silently ineffective inside Flatpak: the entry
    has to land in the *host's* config directory, and the sandbox cannot
    write there.
    """
    row = ToggleRow(
        "Start Salon at login",
        lambda: settings.get_boolean("autostart"),
        lambda value: _set_autostart(context, settings, value),
        detail="Launches Salon inside your normal desktop session",
        default=bool(settings.get_default_value("autostart").unpack()),
    )
    if not sandbox.capabilities().autostart:
        row.make_unavailable("Unavailable in Flatpak; enable autostart from the host desktop.")
    return row


def _set_autostart(context: SettingsContext, settings: Gio.Settings, enabled: bool) -> None:
    problem = autostart.set_enabled(enabled)
    if problem:
        context.toast(problem)
        return
    settings.set_boolean("autostart", enabled)


def _open_updates(context: SettingsContext) -> None:
    if not shutil.which("gnome-software"):
        context.toast("GNOME Software isn't installed, so updates can't be opened from here.")
        return
    try:
        Gio.Subprocess.new(
            ["gnome-software", "--mode=updates"],
            Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
        )
    except GLib.Error as exc:
        context.toast(f"Couldn't open GNOME Software: {exc.message}")
