# SPDX-License-Identifier: GPL-3.0-or-later
"""Asynchronous loading of explicit artwork and site-owned icons."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import gi

gi.require_version("Soup", "3.0")
from gi.repository import Gio, GLib, Soup  # noqa: E402

from salon.core import siteicon  # noqa: E402
from salon.core.model import LaunchKind, Tile  # noqa: E402
from salon.services.artwork_io import decode_image, document_head, save_png  # noqa: E402
from salon.services.artwork_paths import (  # noqa: E402
    cached_remote_path,
    site_icon_miss_path,
    site_icon_path,
)

_FETCH_TIMEOUT_SECONDS = 15
_SITE_ICON_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Salon/1.0"
)

class ArtworkNetworkLoader:
    def __init__(self, owner: object) -> None:
        self._owner = owner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._owner, name)

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
        if key in self._in_flight or site_icon_miss_path(url).exists():
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
            html = document_head(bytes(body.get_data() or b""))
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
            pixbuf = decode_image(body.get_data())
        # An .ico that decoded to 16x16 is a favicon, not artwork: keep
        # walking rather than putting a blurred postage stamp on a tile.
        if pixbuf is not None and max(pixbuf.get_width(), pixbuf.get_height()) >= (
            siteicon.MIN_USEFUL_SIZE
        ):
            if save_png(pixbuf, site_icon_path(url)) and self._on_fetched is not None:
                self._on_fetched()
            return
        self._try_site_icons(url, rest)

    # --- explicit artwork URLs -------------------------------------------

    def _session_for(self) -> Soup.Session:
        if self._session is None:
            self._session = Soup.Session()
            self._session.set_timeout(_FETCH_TIMEOUT_SECONDS)
        return self._session

    def maybe_fetch(self, tile: Tile) -> None:
        url = tile.artwork
        if not url or not url.startswith(("http://", "https://")):
            return
        if url in self._in_flight or cached_remote_path(url).is_file():
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
        pixbuf = decode_image(body.get_data())
        if pixbuf is None:
            return
        if save_png(pixbuf, cached_remote_path(url)) and self._on_fetched is not None:
            self._on_fetched()
