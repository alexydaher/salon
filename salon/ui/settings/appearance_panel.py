# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused settings panel builder."""

from __future__ import annotations

import shutil
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.services import artwork  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    ChoiceRow,
    RangeRow,
    SettingsRow,
    TextRow,
    ToggleRow,
)

_ACCENTS = [
    ("#E8A33D", "Lamplight amber"),
    ("#D9584B", "Ember"),
    ("#4C9BE8", "Cold blue"),
    ("#5FBF7F", "Green"),
    ("#B77BE8", "Violet"),
]


_THEMES: tuple[tuple[str, str], ...] = (
    ("midnight", "Midnight"),
    ("graphite", "Graphite"),
    ("ember", "Ember"),
    ("contrast", "High contrast"),
)


def _percent(value: float) -> str:
    return f"{value * 100:.0f}%"


# --- appearance ----------------------------------------------------------


def appearance_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    def build() -> list[SettingsRow]:
        return [
            ChoiceRow(
                "Theme",
                _THEMES,
                lambda: settings.get_string("theme"),
                lambda value: settings.set_string("theme", value),
                detail="What colour the surfaces and text are. The accent is separate.",
                preview=True,
            ),
            ChoiceRow(
                "Accent colour",
                _ACCENTS,
                lambda: settings.get_string("accent-color"),
                lambda value: settings.set_string("accent-color", value),
                detail="Used for focus, selection and the tile glow",
                preview=True,
            ),
            RangeRow(
                "Safe area",
                lambda: settings.get_double("safe-area-percent"),
                lambda value: settings.set_double("safe-area-percent", value),
                minimum=tokens.SAFE_AREA_MIN_PERCENT,
                maximum=tokens.SAFE_AREA_MAX_PERCENT,
                step=0.5,
                fmt=lambda v: f"{v:.1f}%",
                detail="Inset from the screen edges. Televisions still overscan.",
                preview=True,
            ),
            RangeRow(
                "Tile size",
                lambda: settings.get_double("tile-scale"),
                lambda value: settings.set_double("tile-scale", value),
                minimum=0.5,
                maximum=1.5,
                step=0.05,
                fmt=_percent,
                detail="How large each tile is drawn",
                preview=True,
            ),
            RangeRow(
                "Row density",
                lambda: settings.get_double("row-spacing-scale"),
                lambda value: settings.set_double("row-spacing-scale", value),
                minimum=0.45,
                maximum=1.6,
                step=0.05,
                fmt=_percent,
                detail="Lower packs more rows onto the screen",
                preview=True,
            ),
            RangeRow(
                "Animation speed",
                lambda: settings.get_double("animation-scale"),
                lambda value: settings.set_double("animation-scale", value),
                minimum=0.0,
                maximum=2.0,
                step=0.25,
                fmt=lambda v: "Off" if v == 0 else _percent(v),
            ),
            RangeRow(
                "Idle screen",
                lambda: float(settings.get_int("screensaver-minutes")),
                lambda value: settings.set_int("screensaver-minutes", int(value)),
                minimum=0,
                maximum=60,
                step=5,
                fmt=lambda v: "Never" if v == 0 else f"After {v:.0f} min",
                detail="Fades to a drifting clock. Configure screen locking separately.",
            ),
            ToggleRow(
                "Reduced motion",
                lambda: settings.get_boolean("reduced-motion"),
                lambda value: settings.set_boolean("reduced-motion", value),
                detail="Focus changes instantly; the highlight stays unmistakable",
            ),
            TextRow(
                "Background image",
                lambda: settings.get_string("wallpaper-path") or "Salon ambient",
                lambda: _edit_wallpaper(context, settings),
                detail="A picture, a rotating folder, or empty for Salon ambient. Use - for none.",
            ),
            ActionRow(
                "Choose background image…",
                lambda: _choose_wallpaper(context, settings, folder=False),
                detail="Open a file picker for pointer or mouse users",
            ),
            ActionRow(
                "Choose background folder…",
                lambda: _choose_wallpaper(context, settings, folder=True),
                detail="Rotate through the images in a folder",
            ),
            ActionRow(
                "Check background path",
                lambda: _check_wallpaper(context, settings),
                detail="Verify that the current image or folder can be found",
            ),
            RangeRow(
                "Background dimming",
                lambda: settings.get_double("wallpaper-dim"),
                lambda value: settings.set_double("wallpaper-dim", value),
                minimum=0.0,
                maximum=1.0,
                step=0.04,
                fmt=lambda v: "Hidden" if v >= 0.999 else _percent(v),
                detail="How far the background image is pushed behind the tiles",
                preview=True,
            ),
            ToggleRow(
                "Use each site's own icon",
                lambda: settings.get_boolean("fetch-site-icons"),
                lambda value: settings.set_boolean("fetch-site-icons", value),
                detail="Web tiles ask their own site for its icon, once. Off makes them all alike.",
            ),
            ActionRow(
                "Forget fetched site icons",
                lambda: _forget_site_icons(context),
                detail="Ask every site again the next time its tile is drawn",
            ),
        ]

    return Panel(
        title="Appearance",
        build=build,
        panel_id="appearance",
        icon_name="applications-graphics-symbolic",
    )


# --- network -------------------------------------------------------------


def _edit_wallpaper(context: SettingsContext, settings: Gio.Settings) -> None:
    def done(value: str | None) -> None:
        if value is None:
            return
        settings.set_string("wallpaper-path", value.strip())
        context.rebuild()

    context.edit_text(
        "Path to an image, or a folder of images",
        settings.get_string("wallpaper-path"),
        done,
    )


def _choose_wallpaper(context: SettingsContext, settings: Gio.Settings, *, folder: bool) -> None:
    def done(value: str | None) -> None:
        if value:
            settings.set_string("wallpaper-path", value)
            context.rebuild()

    context.choose_path(
        "Choose a background folder" if folder else "Choose a background image", folder, done
    )


def _check_wallpaper(context: SettingsContext, settings: Gio.Settings) -> None:
    value = settings.get_string("wallpaper-path").strip()
    if not value:
        context.toast("Salon ambient background is active.")
    elif value == "-":
        context.toast("The background image is disabled.")
    elif Path(value).exists():
        context.toast("Background path is available.")
    else:
        context.toast("Background path could not be found.")


def _forget_site_icons(context: SettingsContext) -> None:
    """Drop the guessed icons without touching artwork the user chose.

    They live in their own directory precisely so this can be one removal:
    a site that has since changed its logo, or one that was asked before it
    had an icon at all, is otherwise cached for good.
    """
    directory = artwork.site_icon_cache_dir()
    try:
        shutil.rmtree(directory)
    except FileNotFoundError:
        context.toast("There were no fetched icons to forget.")
        return
    except OSError as error:
        context.toast(f"Couldn't clear the icon cache: {error.strerror or error}")
        return
    context.toast("Fetched site icons cleared. They'll be asked for again.")
    context.rebuild()
