# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused phone-remote server component."""

from __future__ import annotations

from salon.services.phone_remote_delivery import _deliver_level, _finite, _notify
from salon.services.phone_remote_shared import *


class PhoneRemoteCatalog(PhoneRemoteComponent):
    def _handle_search(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """Search the catalogue and every installed application.

        The one thing the phone is unambiguously better at than the remote:
        the television's search screen is a keyboard drawn on a screen, and
        the device in your hand already has one. Results come back in the
        same shape the catalogue does, so they render with the same card,
        the same artwork endpoint and the same launch path.

        Answering synchronously is deliberate. Soup dispatches on the main
        loop, which is where the catalogue and the installed-app cache both
        live, so the handler can simply ask — no thread, no request id, no
        second round trip. The cost is that whatever fills `on_search` must
        stay cheap; see `HomeView._search_for_phone`, which ranks a list it
        already has rather than scanning the disk.
        """
        fields = self._authorize(message)
        if fields is None:
            return
        if self._on_search is None:
            self._refuse(message, Soup.Status.NOT_IMPLEMENTED, "Search isn't available.")
            return
        results = self._on_search(str(fields.get("q", "")))[:MAX_SEARCH_RESULTS]
        # Remembered before they are sent, so the /art request the page
        # makes for each result a moment later is answerable.
        self._offered.offer(tile.id for tile in results)
        self._json(
            message,
            json.dumps({"results": [tile.to_dict() for tile in results]}).encode(),
        )

    def _handle_tile_action(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """Pin, unpin, edit or remove one tile — the phone's long-press.

        `Action.OPTIONS` has opened a per-tile menu on the television since
        the reachability pass, and the phone had no equivalent, so the one
        surface where every tile is visible at once was the one surface
        where none of them could be changed.

        The reply carries a sentence for the phone to show. These are the
        actions with a consequence that is not visible on the phone itself
        — "edit" opens a screen on the television, which is a strange thing
        to have happen with no acknowledgement in your hand.
        """
        fields = self._authorize(message)
        if fields is None:
            return
        tile_id = str(fields.get("id", ""))
        what = str(fields.get("what", ""))
        if self._on_tile_action is None or what not in TILE_ACTIONS:
            self._refuse(message, Soup.Status.BAD_REQUEST, "Unknown tile action.")
            return
        if not self._may_touch(tile_id):
            self._refuse(message, Soup.Status.NOT_FOUND, "That is not on the TV any more.")
            return
        self._json(message, json.dumps({"said": self._on_tile_action(tile_id, what)}).encode())

    def _handle_volume(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """An absolute level from the slider, or the mute toggle.

        Absolute, not a delta, because that is the whole reason the slider
        exists: two repeat-buttons already send VOLUME_UP and VOLUME_DOWN
        as ordinary Actions and will keep doing so. A finger dragged to a
        third of the way along is asking for a third of the way along, and
        expressing that as nineteen presses of a step key is how you get a
        volume control that lags behind the thumb moving it.
        """
        fields = self._authorize(message)
        if fields is None:
            return
        if fields.get("mute"):
            if self._on_mute is not None:
                mute = self._on_mute
                GLib.idle_add(_notify, mute)
            self._ok(message)
            return
        if self._on_volume is None:
            self._refuse(message, Soup.Status.NOT_IMPLEMENTED, "Volume isn't available.")
            return
        level = min(1.0, max(0.0, _finite(fields.get("level"))))
        callback = self._on_volume
        GLib.idle_add(lambda: _deliver_level(callback, level))
        self._ok(message)

    def _may_touch(self, tile_id: str) -> bool:
        """Whether the phone has been shown this tile.

        Two sources, one rule: the ids in the published state, and the ids
        served in a search result. Never the catalogue and never the
        filesystem — which is also why there is no path traversal to get
        wrong anywhere in this file.
        """
        return bool(tile_id) and (tile_id in self._feed.tile_ids() or tile_id in self._offered)

    def _handle_art(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """A tile's own image, straight off disk.

        The id is *matched against the published state*, never joined onto a
        path: the phone can ask for the artwork of something it was shown
        and for nothing else, so there is no traversal to get wrong.
        """
        if not self._authorize_get(message, query):
            return
        escaped = path.removeprefix("/art/") if path.startswith("/art/") else ""
        tile_id = GLib.uri_unescape_string(escaped, None) or "" if escaped else ""
        if not self._may_touch(tile_id) or self._art_for is None:
            message.set_status(Soup.Status.NOT_FOUND, None)
            return
        art = self._art_for(tile_id)
        if art is None:
            message.set_status(Soup.Status.NOT_FOUND, None)
            return
        try:
            if art.stat().st_size > _MAX_ART_BYTES:
                message.set_status(Soup.Status.NOT_FOUND, None)
                return
            data = art.read_bytes()
        except OSError:
            message.set_status(Soup.Status.NOT_FOUND, None)
            return
        message.set_status(Soup.Status.OK, None)
        # Immutable: the URL is keyed by tile id and the images behind it are
        # content the phone will scroll past repeatedly. A tile whose art
        # changes gets a new catalogue generation and a reload anyway.
        message.get_response_headers().append("Cache-Control", "private, max-age=3600")
        message.set_response(
            _ART_TYPES.get(art.suffix.lower(), "application/octet-stream"),
            Soup.MemoryUse.COPY,
            data,
        )
