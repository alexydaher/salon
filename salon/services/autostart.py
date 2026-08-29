# SPDX-License-Identifier: GPL-3.0-or-later
"""Starting Salon with the desktop session, by writing an autostart entry.

Lifted out of the System settings panel, which was carrying fifty lines of
desktop-entry plumbing among its rows. This is a service: it writes a file
into the host's config directory and reports what happened.

Note the entry is *not* the same thing as the systemd unit in
`data/systemd/` — that one runs Salon as its own session, chosen at the
login screen. This is for someone who logs into an ordinary GNOME session
and wants Salon to come up inside it.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon import config as app_config  # noqa: E402
from salon.core import sandbox  # noqa: E402

_TEMPLATE = (
    "[Desktop Entry]\n"
    "Type=Application\n"
    "Name=Salon\n"
    "Exec={exec_line}\n"
    "Icon={icon}\n"
    "X-GNOME-Autostart-enabled=true\n"
)


def entry_path() -> str:
    return GLib.build_filenamev(
        [GLib.get_user_config_dir(), "autostart", f"{app_config.APP_ID}.desktop"]
    )


def _exec_line() -> str:
    """Under Flatpak `salon` is not on the host's PATH — the autostart entry
    runs in the host session, so it has to go back in through flatpak run."""
    if not sandbox.in_flatpak():
        return "salon"
    return f"flatpak run {sandbox.app_id() or app_config.APP_ID}"


def set_enabled(enabled: bool) -> str:
    """Write or remove the entry. Returns "" on success, or what went wrong.

    A message rather than a bool: the two ways this fails — no permission
    to write the config directory, and Flatpak's sandbox not reaching the
    host's — are different problems and the row has room to say which.
    """
    if not sandbox.capabilities().autostart:
        return "Autostart is unavailable in Flatpak; configure it on the host desktop."
    entry = Gio.File.new_for_path(entry_path())
    if not enabled:
        try:
            entry.delete(None)
        except GLib.Error:
            pass  # already gone, which is the state we wanted
        return ""
    try:
        parent = entry.get_parent()
        if parent is not None:
            parent.make_directory_with_parents(None)
    except GLib.Error:
        pass  # the directory already exists
    try:
        entry.replace_contents(
            _TEMPLATE.format(exec_line=_exec_line(), icon=app_config.APP_ID).encode(),
            None,
            False,
            Gio.FileCreateFlags.REPLACE_DESTINATION,
            None,
        )
    except GLib.Error as exc:
        return f"Couldn't write the autostart entry: {exc.message}"
    return ""
