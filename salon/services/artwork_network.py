# SPDX-License-Identifier: GPL-3.0-or-later
"""Asynchronous loading of explicit artwork and site-owned icons."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Soup", "3.0")
from gi.repository import Gio, Soup  # noqa: E402

from salon.core import siteicon  # noqa: E402
from salon.core.model import LaunchKind, Tile  # noqa: E402
from salon.services.artwork_io import decode_image, document_head, save_png  # noqa: E402
from salon.services.artwork_paths import (  # noqa: E402
    cached_remote_path,
    prune_artwork_cache,
    site_icon_miss_is_current,
    site_icon_miss_path,
    site_icon_path,
)
from salon.services.http_bounds import fetch_bytes  # noqa: E402

_HTML_DOWNLOAD_BYTES = 512 * 1024
_IMAGE_DOWNLOAD_BYTES = 8 * 1024 * 1024
_SITE_ICON_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Salon/1.0"
)


class ArtworkNetworkLoader:
    def __init__(
        self,
        *,
        settings: Gio.Settings,
        session_for: Callable[[], Soup.Session],
        in_flight: set[str],
        on_fetched: Callable[[], None] | None,
    ) -> None:
        self._settings = settings
        self._session_for = session_for
        self._in_flight = in_flight
        self._on_fetched = on_fetched

    def site_icons_enabled(self) -> bool:
        return bool(self._settings.get_boolean("fetch-site-icons"))

    def site_icon_for(self, tile: Tile) -> Path | None:
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
        cached = site_icon_path(url)
        if cached.is_file():
            return cached
        if self.site_icons_enabled():
            self.maybe_fetch_site_icon(url)
        return None

    def maybe_fetch_site_icon(self, url: str) -> None:
        key = f"site:{siteicon.origin(url)}"
        if key in self._in_flight or site_icon_miss_is_current(url):
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
        # `prefix=True`: only `<head>` is wanted, and a streaming service's
        # homepage is measured in megabytes. Rejecting on size here is what
        # made every large site resolve no icon.
        fetch_bytes(
            self._session_for(),
            message,
            _HTML_DOWNLOAD_BYTES,
            lambda body: self._on_page_fetched(body, url),
            prefix=True,
        )

    def _on_page_fetched(self, body: bytes | None, url: str) -> None:
        key = f"site:{siteicon.origin(url)}"
        candidates: list[str] = []
        if body is not None:
            html = document_head(body)
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
            miss = site_icon_miss_path(url)
            miss.parent.mkdir(parents=True, exist_ok=True)
            miss.touch()
            prune_artwork_cache()
            return
        head, rest = candidates[0], candidates[1:]
        message = Soup.Message.new("GET", head)
        if message is None:
            self._try_site_icons(url, rest)
            return
        message.get_request_headers().append("User-Agent", _SITE_ICON_USER_AGENT)
        fetch_bytes(
            self._session_for(),
            message,
            _IMAGE_DOWNLOAD_BYTES,
            lambda body: self._on_site_icon_fetched(body, (url, rest)),
        )

    def _on_site_icon_fetched(self, body: bytes | None, data: tuple[str, list[str]]) -> None:
        url, rest = data
        pixbuf = None
        if body is not None:
            pixbuf = decode_image(body)
        # An .ico that decoded to 16x16 is a favicon, not artwork: keep
        # walking rather than putting a blurred postage stamp on a tile.
        if pixbuf is not None and max(pixbuf.get_width(), pixbuf.get_height()) >= (
            siteicon.MIN_USEFUL_SIZE
        ):
            if save_png(pixbuf, site_icon_path(url)) and self._on_fetched is not None:
                prune_artwork_cache()
                self._on_fetched()
            return
        self._try_site_icons(url, rest)

    # --- explicit artwork URLs -------------------------------------------

    def maybe_fetch(self, tile: Tile) -> None:
        url = tile.artwork
        if not url:
            return
        self.maybe_fetch_url(url)

    def maybe_fetch_url(self, url: str) -> None:
        """Cache an arbitrary artwork URL through the same bounded path.

        MPRIS cover art is not attached to a catalogue ``Tile``, but it has
        exactly the same trust boundary as a tile's explicit remote artwork:
        bytes from a player-provided URL still need a timeout, a size limit,
        image validation and the shared cache ceiling.
        """
        if not url.startswith(("http://", "https://")):
            return
        if url in self._in_flight or cached_remote_path(url).is_file():
            return
        self._in_flight.add(url)
        message = Soup.Message.new("GET", url)
        if message is None:
            self._in_flight.discard(url)
            return
        fetch_bytes(
            self._session_for(),
            message,
            _IMAGE_DOWNLOAD_BYTES,
            lambda body: self._on_fetch_done(body, url),
        )

    def _on_fetch_done(self, body: bytes | None, url: str) -> None:
        self._in_flight.discard(url)
        if body is None:
            return
        pixbuf = decode_image(body)
        if pixbuf is None:
            return
        if save_png(pixbuf, cached_remote_path(url)) and self._on_fetched is not None:
            prune_artwork_cache()
            self._on_fetched()
