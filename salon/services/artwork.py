# SPDX-License-Identifier: GPL-3.0-or-later
"""Artwork resolution, caching and accent extraction (§7.4).

Resolution order per tile, first hit wins:

1. the tile's explicit `artwork` field — a local path, or an `https://` URL
   fetched async into $XDG_CACHE_HOME/salon/art/<sha256>.png;
2. the drop folder, $XDG_DATA_HOME/salon/artwork/<tile_id>.{jpg,png,webp} —
   the primary practical path, since it needs no editor and no config edit;
3. for a URL tile, the icon the site itself declares — its
   apple-touch-icon or favicon, fetched once into the same cache. See
   core/siteicon.py for why this exists and why it is not scraping;
4. the application icon, which ui/tile.py composites onto a gradient built
   from the icon's own dominant colour;
5. nothing — ui/tile.py generates a card from a hash of the tile id.

Levels 4 and 5 are *not* failure states. A tile with no artwork at all has
to look deliberate, so this module always returns an accent colour for the
tile to build a card around: the explicit `accent` field if set, else the
dominant colour of whatever image or icon was found, else a hue derived
from the tile id.

Salon never goes looking for artwork on the internet beyond the site a tile
already points at — no TMDB, no fanart.tv, no icon CDN, no search (§7.4,
explicitly out of scope). Asking netflix.com for netflix.com's own icon is
a different act from asking a third party about Netflix, and it is the
difference between a streaming row that looks like itself and one where
every tile is the same browser glyph. `fetch-site-icons` turns it off.
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

from salon import config as app_config  # noqa: E402
from salon.core import siteicon  # noqa: E402
from salon.core.model import LaunchKind, Tile  # noqa: E402

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

# How much of a page to scan for <link rel=icon>. Measured, not guessed:
# primevideo.com's icon declarations sit at byte 147,000 of a 642 KB
# document, behind a wall of inline script, and a 96 KiB window missed them
# entirely — which is how the one tile this feature exists for was the one
# tile it failed on. The scan stops at </head> when it finds one, so the
# cap only bites on pages that never close their head.
_HTML_SNIFF_BYTES = 512 * 1024

# Sent only to a site the user has already put on their home screen and is
# about to open in a real browser anyway. It is here because several large
# sites serve a cut-down page to an unrecognised agent, and that page is
# precisely the one with no icon declarations left in it.
_SITE_ICON_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Salon/1.0"
)


def artwork_drop_dir() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "salon" / "artwork"


def artwork_cache_dir() -> Path:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_home / "salon" / "art"


def site_icon_cache_dir() -> Path:
    """Kept apart from the explicit-URL cache so "forget the icons you
    guessed" can be one directory removal that leaves artwork the user
    actually chose alone."""
    return artwork_cache_dir() / "site"


def _site_icon_path(url: str) -> Path:
    root = siteicon.origin(url) or url
    digest = hashlib.sha256(root.encode("utf-8")).hexdigest()
    return site_icon_cache_dir() / f"{digest}.png"


def _site_icon_miss_path(url: str) -> Path:
    """A zero-byte marker meaning "this origin was asked and had nothing".

    Without it, a site with no usable icon costs two HTTP requests on every
    catalogue rebuild — and the catalogue rebuilds on every launch, every
    config save and every artwork drop.
    """
    return _site_icon_path(url).with_suffix(".miss")


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


def to_hex(color: Gdk.RGBA) -> str:
    """`#rrggbb`, for the one consumer that isn't GTK: the phone remote
    draws its own cards in CSS and needs the accent as a string."""
    red, green, blue = (
        round(max(0.0, min(1.0, channel)) * 255)
        for channel in (color.red, color.green, color.blue)
    )
    return f"#{red:02x}{green:02x}{blue:02x}"


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
        self._settings = Gio.Settings.new(app_config.APP_ID)
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

        site_icon = self._site_icon_for(tile)
        if site_icon is not None:
            texture = self._texture_for(site_icon)
            if texture is not None:
                accent = explicit_accent or self._color_for(site_icon) or hashed_accent(tile.id)
                return Artwork(accent=accent, icon_texture=texture)

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
        path = _local_artwork_path(tile) or self._site_icon_for(tile)
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

    # --- site icons ------------------------------------------------------

    def _site_icons_enabled(self) -> bool:
        return bool(self._settings.get_boolean("fetch-site-icons"))

    def _site_icon_for(self, tile: Tile) -> Path | None:
        """The cached icon for a URL tile's own site, if one was found.

        Also the place the fetch is *started* from, because this is the one
        function that runs for exactly the tiles that need it — resolve()
        calls it on every URL tile with no artwork of its own.
        """
        if tile.launch.kind is not LaunchKind.URL:
            return None
        url = tile.launch.target
        if siteicon.origin(url) is None:
            return None
        cached = _site_icon_path(url)
        if cached.is_file():
            return cached
        if self._site_icons_enabled():
            self._maybe_fetch_site_icon(url)
        return None

    def _maybe_fetch_site_icon(self, url: str) -> None:
        key = f"site:{siteicon.origin(url)}"
        if key in self._in_flight or _site_icon_miss_path(url).exists():
            return
        self._in_flight.add(key)
        message = Soup.Message.new("GET", url)
        if message is None:
            self._in_flight.discard(key)
            return
        # A desktop UA, because a handful of large sites serve a stripped
        # page to anything they do not recognise — and that stripped page is
        # exactly the one with no icon declarations in it.
        message.get_request_headers().append("User-Agent", _SITE_ICON_USER_AGENT)
        self._session_for().send_and_read_async(
            message, GLib.PRIORITY_LOW, None, self._on_page_fetched, url
        )

    def _on_page_fetched(self, session: Soup.Session, result: Gio.AsyncResult, url: str) -> None:
        key = f"site:{siteicon.origin(url)}"
        candidates: list[str] = []
        try:
            body = session.send_and_read_finish(result)
        except GLib.Error:
            body = None
        if body is not None:
            html = _head_of(bytes(body.get_data() or b""))
            usable = siteicon.MIN_USEFUL_SIZE
            candidates = [
                candidate.url
                for candidate in siteicon.icon_candidates(html, url)
                if candidate.svg or candidate.size == 0 or candidate.size >= usable
            ]
        fallback = siteicon.default_favicon(url)
        if fallback is not None:
            candidates.append(fallback)
        self._in_flight.discard(key)
        self._try_site_icons(url, candidates)

    def _try_site_icons(self, url: str, candidates: list[str]) -> None:
        """Walk the candidate list until one of them decodes to an image.

        Sequential rather than parallel on purpose: the first candidate is
        very nearly always right, and firing five requests at a site to
        throw four away is rude in a way a launcher should not be.
        """
        if not candidates:
            # Remember the failure, or every catalogue rebuild asks again.
            miss = _site_icon_miss_path(url)
            miss.parent.mkdir(parents=True, exist_ok=True)
            miss.touch()
            return
        head, rest = candidates[0], candidates[1:]
        message = Soup.Message.new("GET", head)
        if message is None:
            self._try_site_icons(url, rest)
            return
        message.get_request_headers().append("User-Agent", _SITE_ICON_USER_AGENT)
        self._session_for().send_and_read_async(
            message, GLib.PRIORITY_LOW, None, self._on_site_icon_fetched, (url, rest)
        )

    def _on_site_icon_fetched(
        self, session: Soup.Session, result: Gio.AsyncResult, data: tuple[str, list[str]]
    ) -> None:
        url, rest = data
        pixbuf = None
        try:
            body = session.send_and_read_finish(result)
        except GLib.Error:
            body = None
        if body is not None:
            pixbuf = _decode(body.get_data())
        # An .ico that decoded to 16x16 is a favicon, not artwork: keep
        # walking rather than putting a blurred postage stamp on a tile.
        if pixbuf is not None and max(pixbuf.get_width(), pixbuf.get_height()) >= (
            siteicon.MIN_USEFUL_SIZE
        ):
            if _save_png(pixbuf, _site_icon_path(url)) and self._on_fetched is not None:
                self._on_fetched()
            return
        self._try_site_icons(url, rest)

    # --- explicit artwork URLs -------------------------------------------

    def _session_for(self) -> Soup.Session:
        if self._session is None:
            self._session = Soup.Session()
            self._session.set_timeout(_FETCH_TIMEOUT_SECONDS)
        return self._session

    def _maybe_fetch(self, tile: Tile) -> None:
        url = tile.artwork
        if not url or not url.startswith(("http://", "https://")):
            return
        if url in self._in_flight or _cached_remote_path(url).is_file():
            return
        self._in_flight.add(url)
        message = Soup.Message.new("GET", url)
        if message is None:
            self._in_flight.discard(url)
            return
        self._session_for().send_and_read_async(
            message, GLib.PRIORITY_LOW, None, self._on_fetch_done, url
        )

    def _on_fetch_done(self, session: Soup.Session, result: Gio.AsyncResult, url: str) -> None:
        self._in_flight.discard(url)
        try:
            body = session.send_and_read_finish(result)
        except GLib.Error:
            return
        pixbuf = _decode(body.get_data())
        if pixbuf is None:
            return
        if _save_png(pixbuf, _cached_remote_path(url)) and self._on_fetched is not None:
            self._on_fetched()


def _head_of(data: bytes) -> str:
    """The document's <head>, decoded leniently. Bounded twice: at </head>
    if there is one, and at _HTML_SNIFF_BYTES if there isn't."""
    window = data[:_HTML_SNIFF_BYTES]
    end = window.lower().find(b"</head>")
    if end != -1:
        window = window[:end]
    return window.decode("utf-8", errors="replace")


def _decode(data: object) -> GdkPixbuf.Pixbuf | None:
    """Bytes off the network to a pixbuf, or None. Never raises: the input
    is whatever a web server chose to send, including an HTML error page
    with an image/png content type."""
    if not data:
        return None
    try:
        loader = GdkPixbuf.PixbufLoader()
        loader.write(bytes(data))
        loader.close()
        return loader.get_pixbuf()
    except GLib.Error:
        return None


def _save_png(pixbuf: GdkPixbuf.Pixbuf, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        pixbuf.savev(str(destination), "png", [], [])
    except GLib.Error:
        return False
    return True


def _is_symbolic(icon: Gtk.IconPaintable) -> bool:
    """Symbolic icons are single-colour stencils and have to be recoloured
    when drawn, or they render as flat mid-grey on the tile."""
    icon_file = icon.get_file()
    path = icon_file.get_path() if icon_file is not None else None
    return bool(path and path.endswith("-symbolic.svg"))
