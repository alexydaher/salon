# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Appearance: everything you judge by looking at the screen."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.ui.settings.background_rows import background_rows  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    GroupRow,
    Keyed,
    SettingsRow,
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

# What colours a card that has no artwork of its own. Worded as what you
# see rather than as the mechanism: "accent" is Salon's word for the tile's
# colour, and on a card with no explicit accent that colour *is* the icon's.
_TILE_BACKGROUNDS: tuple[tuple[str, str], ...] = (
    ("icon", "Match each icon"),
    ("uniform", "The same for all"),
)

_THEMES: tuple[tuple[str, str], ...] = (
    ("midnight", "Midnight"),
    ("graphite", "Graphite"),
    ("ember", "Ember"),
    ("contrast", "High contrast"),
)

# The date's order — day before month, or the other way round — always
# follows the region and is deliberately not offered here: nobody wants a
# television where the date is written one way and every other clock in the
# house writes it the other. Only the dial is a preference, because 24-hour
# is a common personal choice inside a 12-hour region and vice versa.
_CLOCK_FORMATS: tuple[tuple[str, str], ...] = (
    ("automatic", "Automatic"),
    ("12-hour", "12-hour"),
    ("24-hour", "24-hour"),
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
            # Beside the accent, because the two are the same question asked
            # of different things — the accent is the one colour the whole
            # screen shares, this is whether each tile keeps its own.
            keyed.choice(
                "tile-background",
                "Tile background",
                _TILE_BACKGROUNDS,
                detail="Tiles with their own artwork are unaffected",
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
            GroupRow("Clock"),
            keyed.choice(
                "clock-format",
                "Time",
                _CLOCK_FORMATS,
                detail="Automatic follows this computer's region",
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
            *background_rows(context, settings, keyed),
            GroupRow("Tile artwork"),
            keyed.toggle(
                "fetch-site-icons",
                "Use each site's own icon",
            ),
            ActionRow(
                "Look for site icons again",
                context.refresh_artwork,
                detail="Forgets what was fetched, and what failed",
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
