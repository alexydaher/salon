# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolved artwork value used by tile presentation."""
from __future__ import annotations

from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402


@dataclass(frozen=True, slots=True)
class Artwork:
    """What ui/tile.py needs to draw a tile.

    Exactly one of `texture` (levels 1-2), `icon_texture` (level 3) or
    `icon` (level 4) is set, or none of them (level 5, the generated card).
    `accent` is always set.

    `icon_texture` is separate from `texture` and not an optimisation: a
    texture is *cover-fit*, cropped to fill the whole card, which is right
    for a 1280x720 still and catastrophic for the 64x64 icon a site hands
    back — blown up five times and cropped to a corner of itself. An icon
    is drawn small and centred on the generated gradient instead. The
    distinction is the image's kind, not its size, so it is recorded rather
    than guessed from the pixel count.
    """

    accent: Gdk.RGBA
    texture: Gdk.Texture | None = None
    icon_texture: Gdk.Texture | None = None
    icon: Gtk.IconPaintable | None = None
    icon_is_symbolic: bool = False

    @property
    def level(self) -> int:
        if self.texture is not None:
            return 1
        if self.icon_texture is not None:
            return 3
        if self.icon is not None:
            return 4
        return 5
