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
from salon.core.model import LaunchKind, Tile  # noqa: E402
from salon.services import desktop_entry  # noqa: E402
from salon.services.artwork_colors import dominant_color, hashed_accent, parse_hex  # noqa: E402
from salon.services.artwork_io import is_symbolic  # noqa: E402
from salon.services.artwork_models import Artwork  # noqa: E402
from salon.services.artwork_network import ArtworkNetworkLoader  # noqa: E402
from salon.services.artwork_paths import (  # noqa: E402
    cached_remote_path,
    local_artwork_path,
    prune_artwork_cache,
)

_FETCH_TIMEOUT_SECONDS = 15


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
        self._entry_icon_cache: dict[str, Gio.Icon | None] = {}
        self._session: Soup.Session | None = None
        self._in_flight: set[str] = set()
        self._network = ArtworkNetworkLoader(
            settings=self._settings,
            session_for=self._session_for,
            in_flight=self._in_flight,
            on_fetched=self._on_fetched,
        )
        prune_artwork_cache()

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

    def texture_for_uri(self, uri: str) -> Gdk.Texture | None:
        """Resolve player-published cover art without blocking GTK.

        Local MPRIS covers are files and can be decoded immediately. Remote
        covers take the same bounded, cached route as explicit tile artwork;
        the resolver's ``on_fetched`` callback asks the UI to try again once
        the download has completed.
        """
        path: Path | None = None
        if uri.startswith("file://"):
            try:
                filename, host = GLib.filename_from_uri(uri)
            except GLib.Error:
                return None
            if host not in (None, "", "localhost"):
                return None
            path = Path(filename)
        elif uri.startswith(("http://", "https://")):
            path = cached_remote_path(uri)
            if not path.is_file():
                self._network.maybe_fetch_url(uri)
                return None
        if path is None or not path.is_file():
            return None
        return self._texture_for(path)

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
        if name and self._icon_theme.has_icon(name):
            return self._icon_theme.lookup_icon(
                name, None, size, 1, Gtk.TextDirection.NONE, Gtk.IconLookupFlags.PRELOAD
            )
        # has_icon() is what keeps a missing icon from becoming a "broken
        # image" glyph on the tile: lookup_icon() would happily hand back
        # image-missing, which reads as a bug rather than as the deliberate
        # generated card level 4 gives us.
        #
        # A tile's icon_name is frequently the application id, and an
        # application id is not an icon name: Chrome's desktop entry is
        # `com.google.Chrome.desktop` while the icon the deb installs is
        # `google-chrome`, so the tile drew a hashed card with a big "C" on
        # it next to a Chrome that was installed and launching fine. The
        # desktop entry is the authority on what an application's icon is
        # called, so ask it before giving up.
        return self._desktop_entry_icon(tile, size)

    def _desktop_entry_icon(self, tile: Tile, size: int) -> Gtk.IconPaintable | None:
        gicon = self._desktop_entry_gicon(tile)
        if gicon is None:
            return None
        return self._icon_theme.lookup_by_gicon(
            gicon, size, 1, Gtk.TextDirection.NONE, Gtk.IconLookupFlags.PRELOAD
        )

    def _desktop_entry_gicon(self, tile: Tile) -> Gio.Icon | None:
        """The `Icon=` of the entry this tile launches, if it names one we
        can actually draw.

        Cached by desktop id: the catalogue is rebuilt on every launch and
        every config save, and this reads a file off disk.
        """
        if tile.launch.kind not in (LaunchKind.DESKTOP, LaunchKind.FLATPAK):
            return None
        target = tile.launch.target
        if not target:
            return None
        if target in self._entry_icon_cache:
            return self._entry_icon_cache[target]
        gicon = self._lookup_entry_gicon(target)
        self._entry_icon_cache[target] = gicon
        return gicon

    def _lookup_entry_gicon(self, target: str) -> Gio.Icon | None:
        desktop_id = target if target.endswith(".desktop") else f"{target}.desktop"
        app_info = desktop_entry.load(desktop_id)
        if app_info is None:
            return None
        gicon = app_info.get_icon()
        if isinstance(gicon, Gio.ThemedIcon):
            # Same reasoning as has_icon() above: lookup_by_gicon() falls
            # back to image-missing for a themed name nothing provides.
            names = gicon.get_names() or []
            return gicon if any(self._icon_theme.has_icon(one) for one in names) else None
        if isinstance(gicon, Gio.FileIcon):
            path = gicon.get_file().get_path()
            return gicon if path and Path(path).exists() else None
        return None

    # --- site icons ------------------------------------------------------

    def _session_for(self) -> Soup.Session:
        if self._session is None:
            self._session = Soup.Session()
            self._session.set_timeout(_FETCH_TIMEOUT_SECONDS)
        return self._session
