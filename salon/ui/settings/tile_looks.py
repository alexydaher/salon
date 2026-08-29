# SPDX-License-Identifier: GPL-3.0-or-later
"""How one tile looks: its accent colour and its artwork.

Split from `tile_details.py`, which holds the tile's *identity* — what it
is called and what it opens. These two are the rows that had no way to show
what they were setting: a hex string and a filesystem path, both typed on
an on-screen keyboard, both judged by leaving Settings.
"""

from __future__ import annotations

from salon.core.model import Tile
from salon.services.artwork import artwork_drop_dir
from salon.ui.settings.context import SettingsContext
from salon.ui.settings.tile_edits import edit_field
from salon.ui.settings.widgets import (
    ChoiceRow,
    SettingsRow,
    TextRow,
    opens_picker,
)

# Keyed by the colour, so the row and its list draw it. The empty key is
# "take it from the artwork", which is what a tile does when it is told
# nothing — a real choice, and the default one.
_FROM_ARTWORK = ""
_TILE_ACCENTS: list[tuple[str, str]] = [
    (_FROM_ARTWORK, "From the artwork"),
    ("#E50914", "Red"),
    ("#E8A33D", "Amber"),
    ("#4C9BE8", "Blue"),
    ("#5FBF7F", "Green"),
    ("#B77BE8", "Violet"),
    ("#F0F0F0", "White"),
]


def accent_row(
    context: SettingsContext, row_id: str, tile_id: str, tile: Tile
) -> SettingsRow:
    """The tile's accent, as colours rather than as `#D9584B`.

    A hex string typed on an on-screen keyboard is six presses of a D-pad
    per digit to set a colour you cannot see until you leave. The palette
    covers what anyone actually picks; `custom_accent_row` keeps the
    typed form for a brand colour that has to be exact.
    """

    def choose(value: str) -> None:
        tile.accent = value or None
        context.save_config()
        context.rebuild()

    options = list(_TILE_ACCENTS)
    current = (tile.accent or _FROM_ARTWORK).strip()
    if current and current not in dict(options):
        options.append((current, "Custom"))
    return ChoiceRow("Accent colour", options, lambda: current, choose)


def custom_accent_row(context: SettingsContext, row_id: str, tile_id: str, tile: Tile) -> TextRow:
    def apply(text: str) -> None:
        cleaned = text.strip()
        if cleaned and not cleaned.startswith("#"):
            cleaned = f"#{cleaned}"
        tile.accent = cleaned or None

    return TextRow(
        "Custom colour",
        lambda: tile.accent or "",
        lambda: edit_field(context, "Accent colour, e.g. #E50914", tile.accent or "#", apply),
        placeholder="From the artwork",
        detail="A hex colour, for a brand that has to be exact",
    )


def artwork_rows(
    context: SettingsContext, row_id: str, tile_id: str, tile: Tile
) -> list[SettingsRow]:
    """Pick a picture, or type where one lives.

    There was no picker at all: `Artwork path or URL` opened the on-screen
    keyboard, so setting a local image meant typing an absolute path with a
    D-pad — on a screen that already had a file picker two rows above it,
    for the wallpaper.
    """

    def picked(value: str | None) -> None:
        if not value:
            return
        tile.artwork = value
        context.save_config()
        context.toast("Artwork set.")
        context.rebuild()

    return [
        opens_picker(
            "Choose an image…",
            lambda: context.choose_path("Choose artwork for this tile", False, picked),
            detail=f"Or drop one at {artwork_drop_dir()}/{tile.id}.png",
        ),
        TextRow(
            "Artwork path or URL",
            lambda: tile.artwork or "",
            lambda: edit_field(
                context,
                "Artwork path or https:// URL",
                tile.artwork or "",
                lambda text: setattr(tile, "artwork", text or None),
            ),
            placeholder="From the icon",
            detail="A local file or an https:// address, fetched once and cached",
        ),
    ]



__all__ = ["accent_row", "artwork_rows", "custom_accent_row"]
