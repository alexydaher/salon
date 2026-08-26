# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Two things only the phone has: the whole app list, and cover art."""

from __future__ import annotations

from salon.services.phone_remote_shared import (
    _ART_TYPES,
    _MAX_ART_BYTES,
    MAX_BROWSE_RESULTS,
    Path,
    PhoneRemoteComponent,
    Soup,
    json,
)


class PhoneRemoteBrowse(PhoneRemoteComponent):
    def _handle_apps(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """Every installed application, in the order the page will show it.

        Search has covered the whole system since the phone stopped showing
        only the catalogue, but search needs you to already know the name.
        This is the browse half, and the phone is where it belongs: 200 apps
        at five columns is forty rows of D-pad on the television, and a
        scrollbar with an index rail down here.

        Sorted on the television rather than in the page so the A-Z headings
        follow the same collation the television's own grid uses. Answered
        synchronously off the list scanned when the remote started — the
        same constraint `/search` is under, for the same reason: Soup
        dispatches on the thread that draws the interface.
        """
        fields = self._owner._authorize(message)
        if fields is None:
            return
        if self._owner._on_apps is None:
            self._owner._refuse(
                message, Soup.Status.NOT_IMPLEMENTED, "The app list isn't available."
            )
            return
        apps = self._owner._on_apps()[:MAX_BROWSE_RESULTS]
        # Remembered before they are sent, so the /art and /launch requests
        # the page makes a moment later are answerable. This is the same
        # bounded set search results go into, and it is deliberately bigger
        # than one screenful of either.
        self._owner._offered.offer(tile.id for tile in apps)
        self._owner._json(
            message, json.dumps({"apps": [tile.to_dict() for tile in apps]}).encode()
        )

    def _handle_now_playing_art(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """The cover of whatever is playing, when it is a file on this host.

        There is no id in the request and there deliberately cannot be: the
        only thing this will serve is the artwork of the player named in the
        state the phone has already been shown. A player that publishes an
        `https://` cover is handled entirely without this — the URL goes to
        the phone in the snapshot and the phone fetches it directly, which
        is both faster and not Salon's business to proxy.
        """
        if not self._owner._authorize_get(message, query):
            return
        art = None if self._owner._np_art_for is None else self._owner._np_art_for()
        if art is None:
            message.set_status(Soup.Status.NOT_FOUND, None)
            return
        data = _read_art(art)
        if data is None:
            message.set_status(Soup.Status.NOT_FOUND, None)
            return
        message.set_status(Soup.Status.OK, None)
        # Not cached: unlike a tile's artwork this URL is not keyed by what
        # it holds, so a stale copy would be the previous track's cover.
        message.get_response_headers().append("Cache-Control", "no-store")
        message.set_response(
            _ART_TYPES.get(art.suffix.lower(), "application/octet-stream"),
            Soup.MemoryUse.COPY,
            data,
        )


def _read_art(art: Path) -> bytes | None:
    """Artwork off disk, on the main loop, so a pathological file must not
    become a stall. Nothing legitimate is close to the ceiling."""
    try:
        if art.stat().st_size > _MAX_ART_BYTES:
            return None
        return art.read_bytes()
    except OSError:
        return None
