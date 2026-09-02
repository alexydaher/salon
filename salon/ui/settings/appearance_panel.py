# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Appearance: everything you judge by looking at the screen."""

from __future__ import annotations

import shutil

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.services import artwork  # noqa: E402
from salon.ui.settings import wallpaper  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    GroupRow,
    Keyed,
    SettingsRow,
    opens_panel,
    opens_picker,
    restore_defaults_row,
)

# Keyed by the colour itself, so the row and every entry in its list can
# draw the thing rather than describe it — see value_rows._is_colour.
ACCENTS = [
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


def appearance_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    """Five groups, not fifteen rows.

    It was one flat column running theme → accent → safe area → tile size →
    row density → animation → idle → motion → four wallpaper rows → dimming
    → two icon-cache rows, of which about nine fit on the screen. The
    groups are the same rows; what changed is that you can find one.
    """
    keyed = Keyed(settings)

    def build() -> list[SettingsRow]:
        return [
            GroupRow("Colour"),
            keyed.choice(
                "theme",
                "Theme",
                _THEMES,
                preview=True,
            ),
            keyed.choice(
                "accent-color",
                "Accent colour",
                ACCENTS,
                preview=True,
            ),
            GroupRow("Layout"),
            keyed.ranged(
                "safe-area-percent",
                "Safe area",
                minimum=tokens.SAFE_AREA_MIN_PERCENT,
                maximum=tokens.SAFE_AREA_MAX_PERCENT,
                step=0.5,
                fmt=lambda v: f"{v:.1f}%",
                detail="Increase if screen edges are cropped",
                preview=True,
            ),
            keyed.ranged(
                "tile-scale",
                "Tile size",
                minimum=0.5,
                maximum=1.5,
                step=0.05,
                fmt=_percent,
                preview=True,
            ),
            keyed.ranged(
                "row-spacing-scale",
                "Row density",
                minimum=0.45,
                maximum=1.6,
                step=0.05,
                fmt=_percent,
                detail="Lower fits more rows",
                preview=True,
            ),
            GroupRow("Motion"),
            keyed.ranged(
                "animation-scale",
                "Animation speed",
                minimum=0.0,
                maximum=2.0,
                step=0.25,
                fmt=lambda v: "Off" if v == 0 else _percent(v),
                off_at=0.0,
                preview=True,
            ),
            keyed.toggle(
                "reduced-motion",
                "Reduced motion",
                detail="Instant focus changes",
                preview=True,
            ),
            keyed.ranged(
                "screensaver-minutes",
                "Idle screen",
                minimum=0,
                maximum=60,
                step=5,
                fmt=lambda v: "Never" if v == 0 else f"After {v:.0f} min",
                off_at=0.0,
                detail="Drifting clock after inactivity; does not lock",
            ),
            GroupRow("Background"),
            keyed.choice(
                "wallpaper-path",
                "Background",
                wallpaper.choices(settings),
                detail=wallpaper.detail(settings),
                preview=True,
            ),
            opens_picker(
                "Choose a picture…",
                lambda: wallpaper.choose(context, settings, folder=False),
            ),
            opens_picker(
                "Choose a folder…",
                lambda: wallpaper.choose(context, settings, folder=True),
            ),
            keyed.choice(
                "wallpaper-color-treatment",
                "Background colours",
                wallpaper.COLOR_TREATMENTS,
                preview=True,
            ),
            keyed.ranged(
                "wallpaper-dim",
                "Background dimming",
                minimum=0.0,
                maximum=1.0,
                step=0.04,
                fmt=lambda v: "Hidden" if v >= 0.999 else _percent(v),
                preview=True,
            ),
            opens_panel(
                "Type a path…",
                lambda: context.push(_background_path_panel(context, settings)),
                detail="For paths the picker cannot reach",
            ),
            GroupRow("Tile artwork"),
            keyed.toggle(
                "fetch-site-icons",
                "Use each site's own icon",
            ),
            ActionRow(
                "Forget fetched site icons",
                lambda: _forget_site_icons(context),
            ),
            GroupRow("This section"),
            restore_defaults_row(keyed, context.toast, context.rebuild),
        ]

    def summary() -> str:
        theme = dict(_THEMES).get(settings.get_string("theme"), "")
        accent = dict(ACCENTS).get(settings.get_string("accent-color"), "")
        return " · ".join(part for part in (theme, accent) if part)

    return Panel(
        title="Appearance",
        build=build,
        summary=summary,
        panel_id="appearance",
        icon_name="applications-graphics-symbolic",
    )


def _background_path_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    """The typed path, and a way to find out whether it exists.

    A sub-panel rather than two more rows in Appearance: between them they
    serve the one person on the machine who keeps their pictures somewhere
    a file picker will not go, and they were costing everyone else two rows
    in the longest list in Settings.
    """

    def build() -> list[SettingsRow]:
        return [
            Keyed(settings).text(
                "wallpaper-path",
                "Path",
                lambda: wallpaper.edit_path(context, settings),
                placeholder="Salon ambient",
                detail="Image, folder, or - for none",
            ),
            ActionRow(
                "Check this path",
                lambda: context.toast(wallpaper.detail(settings)),
            ),
        ]

    return Panel(title="Background path", build=build)


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
