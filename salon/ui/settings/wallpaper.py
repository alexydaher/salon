# SPDX-License-Identifier: GPL-3.0-or-later
"""The background image: what it can be set to, and how it gets set.

Split out of `appearance_panel.py`, which had grown five wallpaper helpers
around one setting. The interesting decision here is that the background is
a *choice* rather than only a typed path.

`wallpaper-path` is a string, so the row was a `TextRow` that opened the
on-screen keyboard — which meant the one setting whose entire content is a
picture could not be previewed, because live preview needs a list to steer
with (`preview_policy.previews_home`). Three named states plus whatever the
user has chosen *is* a list, so it now previews like everything else in
Appearance, and the file pickers stay for saying which picture.
"""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio  # noqa: E402

from salon.ui.settings.context import SettingsContext  # noqa: E402

AMBIENT = ""
NONE = "-"
_KEY = "wallpaper-path"


def choices(settings: Gio.Settings) -> list[tuple[str, str]]:
    """Salon's own backdrop, nothing at all, and the picture in use.

    The third entry only exists once there is one, so the list never offers
    a value that would do nothing.
    """
    options = [(AMBIENT, "Salon ambient"), (NONE, "Plain background")]
    current = settings.get_string(_KEY).strip()
    if current and current not in (AMBIENT, NONE):
        options.append((current, _describe(current)))
    return options


def _describe(path: str) -> str:
    """The picture's own name, or the folder's. A settings row is not the
    place to read an absolute path, and the row's detail line carries the
    full thing for anyone who needs it."""
    name = Path(path).name or path
    return f"{name} (folder)" if Path(path).is_dir() else name


def detail(settings: Gio.Settings) -> str:
    current = settings.get_string(_KEY).strip()
    if not current:
        return "Salon's own drifting backdrop"
    if current == NONE:
        return "No picture behind the tiles"
    if not Path(current).exists():
        return f"Not found: {current}"
    return f"Rotating through {current}" if Path(current).is_dir() else current


def choose(context: SettingsContext, settings: Gio.Settings, *, folder: bool) -> None:
    """Open a file picker, and select what it returns.

    Selecting it as well as storing it is the point: a picture that is set
    but not *chosen* would leave the row still showing "Salon ambient",
    because the choice list is keyed on the stored path.
    """

    def done(value: str | None) -> None:
        if not value:
            return
        settings.set_string(_KEY, value)
        context.toast(f"Background set to {_describe(value)}.")
        context.rebuild()

    context.choose_path(
        "Choose a background folder" if folder else "Choose a background image", folder, done
    )


def edit_path(context: SettingsContext, settings: Gio.Settings) -> None:
    """The typed escape hatch, for a path no picker can reach."""

    def done(value: str | None) -> None:
        if value is None:
            return
        settings.set_string(_KEY, value.strip())
        context.rebuild()

    context.edit_text(
        "Path to an image, or a folder of images", settings.get_string(_KEY), done
    )
