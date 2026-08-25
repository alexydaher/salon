# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve tile artwork from local files, caches, site icons, and app icons."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Soup", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Soup  # noqa: E402

from salon import config as app_config  # noqa: E402
from salon.core.model import Tile  # noqa: E402
from salon.services.artwork_colors import dominant_color, hashed_accent, parse_hex  # noqa: E402
from salon.services.artwork_io import is_symbolic  # noqa: E402
from salon.services.artwork_models import Artwork  # noqa: E402
from salon.services.artwork_network import ArtworkNetworkLoader  # noqa: E402
from salon.services.artwork_paths import local_artwork_path  # noqa: E402


def load_texture(path: Path) -> Gdk.Texture | None:
    try:
        return Gdk.Texture.new_from_filename(str(path))
    except GLib.Error:
        return None

class ArtworkResolver:
    """Resolves tiles to Artwork, caching decoded textures and extracted
    colours by (path, mtime) so a catalogue rebuild — which happens on every
    launch, config save and artwork drop — doesn't re-decode every image."""

    def __init__(self, icon_theme: Gtk.IconTheme, *, on_fetched: Callable[[], None] | None = None):
        self._icon_theme = icon_theme
        self._on_fetched = on_fetched
        self._settings = Gio.Settings.new(app_config.APP_ID)
        self._texture_cache: dict[tuple[str, float], Gdk.Texture] = {}
        self._color_cache: dict[tuple[str, float], Gdk.RGBA | None] = {}
        self._session: Soup.Session | None = None
        self._in_flight: set[str] = set()
        self._network = ArtworkNetworkLoader(self)

    def resolve(self, tile: Tile, *, icon_size: int) -> Artwork:
        explicit_accent = parse_hex(tile.accent) if tile.accent else None

        path = local_artwork_path(tile)
        if path is not None:
            texture = self._texture_for(path)
            if texture is not None:
                accent = explicit_accent or self._color_for(path) or hashed_accent(tile.id)
                return Artwork(accent=accent, texture=texture)

        site_icon = self._network.site_icon_for(tile)
        if site_icon is not None:
            texture = self._texture_for(site_icon)
            if texture is not None:
                accent = explicit_accent or self._color_for(site_icon) or hashed_accent(tile.id)
                return Artwork(accent=accent, icon_texture=texture)

        self._network.maybe_fetch(tile)

        icon = self._icon_for(tile, icon_size)
        if icon is not None:
            accent = explicit_accent
            if accent is None:
                icon_file = icon.get_file()
                icon_path = icon_file.get_path() if icon_file is not None else None
                if icon_path is not None and not is_symbolic(icon):
                    accent = self._color_for(Path(icon_path))
            return Artwork(
                accent=accent or hashed_accent(tile.id),
                icon=icon,
                icon_is_symbolic=is_symbolic(icon),
            )

        return Artwork(accent=explicit_accent or hashed_accent(tile.id))

    def artwork_file(self, tile: Tile) -> Path | None:
        """The image file behind this tile, for something that wants bytes
        rather than a texture — the phone remote serves these over HTTP.

        Deliberately not a render of the composited tile: what the phone
        needs is a file it can hand to an `<img>`, and re-encoding a PNG
        that is already a PNG to produce one would be work on the main loop
        for a worse result. A tile whose art is a themed icon inside a
        GResource has no path at all, and reports none rather than
        pretending; the phone falls back to the accent card, which is what
        the television draws for an artless tile too.
        """
        path = local_artwork_path(tile) or self._network.site_icon_for(tile)
        if path is not None:
            return path
        icon = self._icon_for(tile, 256)
        if icon is None:
            return None
        icon_file = icon.get_file()
        name = icon_file.get_path() if icon_file is not None else None
        return Path(name) if name else None

    # --- internals -------------------------------------------------------

    def _cache_key(self, path: Path) -> tuple[str, float] | None:
        try:
            return (str(path), path.stat().st_mtime)
        except OSError:
            return None

    def _texture_for(self, path: Path) -> Gdk.Texture | None:
        key = self._cache_key(path)
        if key is None:
            return None
        cached = self._texture_cache.get(key)
        if cached is None:
            cached = load_texture(path)
            if cached is None:
                return None
            self._texture_cache[key] = cached
        return cached

    def _color_for(self, path: Path) -> Gdk.RGBA | None:
        key = self._cache_key(path)
        if key is None:
            return None
        if key not in self._color_cache:
            self._color_cache[key] = dominant_color(path)
        return self._color_cache[key]

    def _icon_for(self, tile: Tile, size: int) -> Gtk.IconPaintable | None:
        name = tile.icon_name
        if not name or not self._icon_theme.has_icon(name):
            # has_icon() is what keeps a missing icon from becoming a
            # "broken image" glyph on the tile: lookup_icon() would happily
            # hand back image-missing, which reads as a bug rather than as
            # the deliberate generated card level 4 gives us.
            return None
        return self._icon_theme.lookup_icon(
            name, None, size, 1, Gtk.TextDirection.NONE, Gtk.IconLookupFlags.PRELOAD
        )

    # --- site icons ------------------------------------------------------
