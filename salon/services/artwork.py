# SPDX-License-Identifier: GPL-3.0-or-later
"""Artwork resolution, caching and accent extraction (§7.4).

Resolution order per tile, first hit wins:

1. the tile's explicit `artwork` field — a local path, or an `https://` URL
   fetched async into $XDG_CACHE_HOME/salon/art/<sha256>.png;
2. the drop folder, $XDG_DATA_HOME/salon/artwork/<tile_id>.{jpg,png,webp} —
   the primary practical path, since it needs no editor and no config edit;
3. the application icon, which ui/tile.py composites onto a gradient built
   from the icon's own dominant colour;
4. nothing — ui/tile.py generates a card from a hash of the tile id.

Levels 3 and 4 are *not* failure states. A tile with no artwork at all has
to look deliberate, so this module always returns an accent colour for the
tile to build a card around: the explicit `accent` field if set, else the
dominant colour of whatever image or icon was found, else a hue derived
from the tile id.

Salon never goes looking for artwork on the internet beyond the exact URL a
tile names — no TMDB, no fanart.tv, no scraping (§7.4, explicitly out of
scope).
"""

from __future__ import annotations

import colorsys
import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Soup", "3.0")

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Soup  # noqa: E402

from salon.core.model import Tile  # noqa: E402

_ARTWORK_EXTENSIONS = ("jpg", "jpeg", "png", "webp")

# Sampling grid for dominant-colour extraction. §7.4 says 8x8; 16x16 costs
# nothing extra (the decode dominates) and is noticeably steadier on icons
# with a small saturated logo on a large flat field.
_SAMPLE_SIZE = 16
_MIN_ALPHA = 128
_MIN_LIGHTNESS = 0.18
_MAX_LIGHTNESS = 0.95
_MIN_SATURATION = 0.15

_FETCH_TIMEOUT_SECONDS = 15


def artwork_drop_dir() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "salon" / "artwork"


def artwork_cache_dir() -> Path:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_home / "salon" / "art"


@dataclass(frozen=True, slots=True)
class Artwork:
    """What ui/tile.py needs to draw a tile.

    Exactly one of `texture` (levels 1-2) or `icon` (level 3) is set, or
    neither (level 4, the generated card). `accent` is always set.
    """

    accent: Gdk.RGBA
    texture: Gdk.Texture | None = None
    icon: Gtk.IconPaintable | None = None
    icon_is_symbolic: bool = False

    @property
    def level(self) -> int:
        if self.texture is not None:
            return 1
        if self.icon is not None:
            return 3
        return 4


def _rgba(red: float, green: float, blue: float, alpha: float = 1.0) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.red = red
    color.green = green
    color.blue = blue
    color.alpha = alpha
    return color


def parse_hex(value: str) -> Gdk.RGBA | None:
    color = Gdk.RGBA()
    return color if color.parse(value) else None


def hashed_accent(seed: str) -> Gdk.RGBA:
    """A stable, pleasant hue derived from a tile id — the level-4 card's
    colour. Saturation and lightness are pinned so every generated card sits
    in the same family as the rest of the palette instead of shouting."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    hue = digest[0] / 255.0
    red, green, blue = colorsys.hls_to_rgb(hue, 0.52, 0.42)
    return _rgba(red, green, blue)


def glow_color(accent: Gdk.RGBA) -> Gdk.RGBA:
    """The accent as a *light source* rather than as a surface colour.

    A tile's accent is whatever its artwork happens to be built from, and
    plenty of those are dark or desaturated — the hue hashed from a tile id,
    a muted app icon. Blurred at low alpha against a near-black backdrop,
    such a colour produces no visible bloom at all, which is how the focus
    treatment ended up reading as a flat outline. Lifting lightness and
    saturation to a floor keeps each tile's own hue while guaranteeing the
    bloom actually looks like light falling on the screen.
    """
    hue, lightness, saturation = colorsys.rgb_to_hls(accent.red, accent.green, accent.blue)
    red, green, blue = colorsys.hls_to_rgb(hue, max(lightness, 0.62), max(saturation, 0.65))
    return _rgba(red, green, blue)


def dominant_color(path: Path) -> Gdk.RGBA | None:
    """The most saturated colour in an image, above a lightness floor.

    Downscales to a small grid first (§7.4) so this is cheap enough to run
    synchronously while building tiles; transparent and near-black/near-white
    pixels are skipped so a logo on a transparent field reports the logo's
    colour rather than a muddy average.
    """
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(path), _SAMPLE_SIZE, _SAMPLE_SIZE, True
        )
    except GLib.Error:
        return None

    pixels = pixbuf.get_pixels()
    channels = pixbuf.get_n_channels()
    rowstride = pixbuf.get_rowstride()
    width = pixbuf.get_width()
    height = pixbuf.get_height()
    has_alpha = pixbuf.get_has_alpha()

    best: tuple[float, float, float, float] | None = None  # (saturation, r, g, b)
    total = [0.0, 0.0, 0.0]
    counted = 0

    for y in range(height):
        for x in range(width):
            offset = y * rowstride + x * channels
            if has_alpha and pixels[offset + 3] < _MIN_ALPHA:
                continue
            red = pixels[offset] / 255.0
            green = pixels[offset + 1] / 255.0
            blue = pixels[offset + 2] / 255.0
            _, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
            if not (_MIN_LIGHTNESS <= lightness <= _MAX_LIGHTNESS):
                continue
            total[0] += red
            total[1] += green
            total[2] += blue
            counted += 1
            if saturation >= _MIN_SATURATION and (best is None or saturation > best[0]):
                best = (saturation, red, green, blue)

    if best is not None:
        return _rgba(best[1], best[2], best[3])
    if counted:
        return _rgba(total[0] / counted, total[1] / counted, total[2] / counted)
    return None


def _load_texture(path: Path) -> Gdk.Texture | None:
    try:
        return Gdk.Texture.new_from_filename(str(path))
    except GLib.Error:
        return None


def _drop_folder_path(tile_id: str) -> Path | None:
    drop_dir = artwork_drop_dir()
    for extension in _ARTWORK_EXTENSIONS:
        candidate = drop_dir / f"{tile_id}.{extension}"
        if candidate.is_file():
            return candidate
    return None


def _cached_remote_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return artwork_cache_dir() / f"{digest}.png"


def _local_artwork_path(tile: Tile) -> Path | None:
    """The level-1/2 image for this tile, if one is on disk right now.

    A remote `artwork` URL only resolves here once it has been fetched into
    the cache; until then the tile falls through to its icon and repaints
    when `fetch_remote_artwork` reports the download finished.
    """
    if tile.artwork:
        if tile.artwork.startswith(("http://", "https://")):
            cached = _cached_remote_path(tile.artwork)
            if cached.is_file():
                return cached
        else:
            candidate = Path(tile.artwork).expanduser()
            if candidate.is_file():
                return candidate
    return _drop_folder_path(tile.id)


class ArtworkResolver:
    """Resolves tiles to Artwork, caching decoded textures and extracted
    colours by (path, mtime) so a catalogue rebuild — which happens on every
    launch, config save and artwork drop — doesn't re-decode every image."""

    def __init__(self, icon_theme: Gtk.IconTheme, *, on_fetched: Callable[[], None] | None = None):
        self._icon_theme = icon_theme
        self._on_fetched = on_fetched
        self._texture_cache: dict[tuple[str, float], Gdk.Texture] = {}
        self._color_cache: dict[tuple[str, float], Gdk.RGBA | None] = {}
        self._session: Soup.Session | None = None
        self._in_flight: set[str] = set()

    def resolve(self, tile: Tile, *, icon_size: int) -> Artwork:
        explicit_accent = parse_hex(tile.accent) if tile.accent else None

        path = _local_artwork_path(tile)
        if path is not None:
            texture = self._texture_for(path)
            if texture is not None:
                accent = explicit_accent or self._color_for(path) or hashed_accent(tile.id)
                return Artwork(accent=accent, texture=texture)

        self._maybe_fetch(tile)

        icon = self._icon_for(tile, icon_size)
        if icon is not None:
            accent = explicit_accent
            if accent is None:
                icon_file = icon.get_file()
                icon_path = icon_file.get_path() if icon_file is not None else None
                if icon_path is not None and not _is_symbolic(icon):
                    accent = self._color_for(Path(icon_path))
            return Artwork(
                accent=accent or hashed_accent(tile.id),
                icon=icon,
                icon_is_symbolic=_is_symbolic(icon),
            )

        return Artwork(accent=explicit_accent or hashed_accent(tile.id))

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
            cached = _load_texture(path)
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

    def _maybe_fetch(self, tile: Tile) -> None:
        url = tile.artwork
        if not url or not url.startswith(("http://", "https://")):
            return
        if url in self._in_flight or _cached_remote_path(url).is_file():
            return
        self._in_flight.add(url)
        if self._session is None:
            self._session = Soup.Session()
            self._session.set_timeout(_FETCH_TIMEOUT_SECONDS)
        message = Soup.Message.new("GET", url)
        if message is None:
            self._in_flight.discard(url)
            return
        self._session.send_and_read_async(
            message, GLib.PRIORITY_LOW, None, self._on_fetch_done, url
        )

    def _on_fetch_done(self, session: Soup.Session, result: Gio.AsyncResult, url: str) -> None:
        self._in_flight.discard(url)
        try:
            body = session.send_and_read_finish(result)
        except GLib.Error:
            return
        data = body.get_data()
        if not data:
            return
        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(data)
            loader.close()
            pixbuf = loader.get_pixbuf()
        except GLib.Error:
            return
        if pixbuf is None:
            return
        destination = _cached_remote_path(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            pixbuf.savev(str(destination), "png", [], [])
        except GLib.Error:
            return
        if self._on_fetched is not None:
            self._on_fetched()


def _is_symbolic(icon: Gtk.IconPaintable) -> bool:
    """Symbolic icons are single-colour stencils and have to be recoloured
    when drawn, or they render as flat mid-grey on the tile."""
    icon_file = icon.get_file()
    path = icon_file.get_path() if icon_file is not None else None
    return bool(path and path.endswith("-symbolic.svg"))
