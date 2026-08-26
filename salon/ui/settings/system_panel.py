# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused settings panel builder."""

from __future__ import annotations

import shutil
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon import config as app_config  # noqa: E402
from salon.core import sandbox, session  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext, confirm_panel  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    RangeRow,
    SettingsRow,
    ToggleRow,
)


def system_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    from salon.services import power

    caps = sandbox.capabilities()
    flatpak_reason = "Unavailable in the Flatpak build; use the desktop's Settings app."

    def host_row(row: SettingsRow) -> SettingsRow:
        return row if caps.control_center else row.make_unavailable(flatpak_reason)

    def build() -> list[SettingsRow]:
        rows: list[SettingsRow] = [
            host_row(
                ActionRow(
                    "Display and resolution",
                    lambda: context.open_control_center("display"),
                    detail="Resolution, refresh rate and scaling",
                )
            ),
            host_row(
                ActionRow(
                    "Date and time",
                    lambda: context.open_control_center("datetime"),
                    detail="What the clock in the top bar shows",
                )
            ),
            host_row(
                ActionRow(
                    "Region and language",
                    lambda: context.open_control_center("region"),
                )
            ),
            host_row(
                ActionRow(
                    "Accessibility",
                    lambda: context.open_control_center("a11y"),
                    detail="Larger text, high contrast, screen reader",
                )
            ),
            host_row(
                ActionRow(
                    "Power and screen blanking",
                    lambda: context.open_control_center("power"),
                )
            ),
            host_row(
                ActionRow(
                    "Software updates",
                    lambda: _open_updates(context),
                    detail=(
                        "Opens GNOME Software"
                        if shutil.which("gnome-software")
                        else "GNOME Software isn't installed"
                    ),
                )
            ),
            (
                ToggleRow(
                    "Start Salon at login",
                    lambda: settings.get_boolean("autostart"),
                    lambda value: _set_autostart(context, settings, value),
                )
                if caps.autostart
                else ToggleRow(
                    "Start Salon at login", lambda: False, lambda _value: None
                ).make_unavailable(
                    "Unavailable in Flatpak; enable autostart from the host desktop."
                )
            ),
            RangeRow(
                "Keep screen awake after launching",
                lambda: float(settings.get_int("idle-inhibit-seconds")),
                lambda value: settings.set_int("idle-inhibit-seconds", int(value)),
                minimum=0,
                maximum=600,
                step=15,
                fmt=lambda v: "Off" if v == 0 else f"{v:.0f} s",
                detail="Covers the gap before the app issues its own inhibit",
            ),
        ]

        # Named in the failure message, because logind refusing to suspend
        # and Salon never having asked look identical from the sofa.
        def fail(what: str) -> Callable[[str], None]:
            return lambda message: context.toast(f"{what} didn't happen: {message}")

        if power.can_suspend():
            rows.append(ActionRow("Suspend", lambda: power.suspend(fail("Suspend"))))
        if power.can_log_out():
            rows.append(
                ActionRow(
                    "Log out",
                    lambda: context.push(
                        confirm_panel(
                            context,
                            "Log out and end this session?",
                            "Log out",
                            lambda: power.log_out(fail("Log out")),
                        )
                    ),
                    detail="Ends the session and returns to the login screen",
                    danger=True,
                )
            )
        if power.can_reboot():
            rows.append(
                ActionRow(
                    "Restart",
                    lambda: context.push(
                        confirm_panel(
                            context,
                            "Restart the computer?",
                            "Restart",
                            lambda: power.reboot(fail("Restart")),
                        )
                    ),
                    danger=True,
                )
            )
        if power.can_power_off():
            rows.append(
                ActionRow(
                    "Shut Down",
                    lambda: context.push(
                        confirm_panel(
                            context,
                            "Shut down the computer?",
                            "Shut Down",
                            lambda: power.power_off(fail("Shut down")),
                        )
                    ),
                    danger=True,
                )
            )
        if not session.is_session():
            rows.append(
                ActionRow(
                    "Exit Salon",
                    lambda: context.push(
                        confirm_panel(
                            context,
                            "Exit Salon and return to the desktop?",
                            "Exit Salon",
                            context.quit_app,
                        )
                    ),
                    danger=True,
                )
            )
        return rows

    return Panel(
        title="System", build=build, panel_id="system", icon_name="preferences-system-symbolic"
    )


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


def _set_autostart(context: SettingsContext, settings: Gio.Settings, enabled: bool) -> None:
    if not sandbox.capabilities().autostart:
        context.toast("Autostart is unavailable in Flatpak; configure it on the host desktop.")
        return
    settings.set_boolean("autostart", enabled)
    path = GLib.build_filenamev(
        [GLib.get_user_config_dir(), "autostart", f"{app_config.APP_ID}.desktop"]
    )
    entry = Gio.File.new_for_path(path)
    if not enabled:
        try:
            entry.delete(None)
        except GLib.Error:
            pass  # already gone, which is the state we wanted
        return
    # Under Flatpak `salon` is not on the host's PATH — the autostart entry
    # runs in the host session, so it has to go back in through flatpak run.
    app_id = sandbox.app_id() or app_config.APP_ID
    exec_line = f"flatpak run {app_id}" if sandbox.in_flatpak() else "salon"
    contents = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Salon\n"
        f"Exec={exec_line}\n"
        f"Icon={app_config.APP_ID}\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    try:
        parent = entry.get_parent()
        if parent is not None:
            parent.make_directory_with_parents(None)
    except GLib.Error:
        pass  # the directory already exists
    try:
        entry.replace_contents(
            contents.encode(), None, False, Gio.FileCreateFlags.REPLACE_DESTINATION, None
        )
    except GLib.Error as exc:
        context.toast(f"Couldn't write the autostart entry: {exc.message}")
