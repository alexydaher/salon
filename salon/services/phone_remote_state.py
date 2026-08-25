# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused phone-remote server component."""

from __future__ import annotations

from salon.services.phone_remote_shared import (
    _CONNECTED_SECONDS,
    Callable,
    PhoneRemoteComponent,
    RemoteState,
    local_address,
    time,
)


class PhoneRemoteState(PhoneRemoteComponent):
    def acquire(self, holder: str) -> bool:
        """Start the server on behalf of `holder`, or note that it already
        wants it. Returns False only if starting actually failed."""
        self._owner._holders.add(holder)
        return self._owner.start()

    def release(self, holder: str) -> None:
        self._owner._holders.discard(holder)
        if not self._owner._holders:
            self._owner.stop()

    def holds(self, holder: str) -> bool:
        return holder in self._owner._holders

    def set_text_sink(self, sink: Callable[[str], None] | None) -> None:
        """Where typed text lands, or None when nothing on screen wants it."""
        self._owner._text_sink = sink

    def release_text_sink(self, sink: Callable[[str], None]) -> None:
        """Give the sink back, but only if it is still ours.

        Screens hand the sink over as they appear and take it back as they
        go, and GTK maps the incoming one before it unmaps the outgoing —
        so an unconditional clear on the way out would leave the phone
        typing into nothing on the screen that just arrived.
        """
        if self._owner._text_sink is sink:
            self._owner._text_sink = None

    # --- what the phone sees ---------------------------------------------

    def publish(self, state: RemoteState) -> bool:
        """Offer a new snapshot to whatever phones are polling.

        Cheap enough to call from every focus move and every catalogue
        rebuild: an unchanged state costs one dataclass comparison, and even
        a changed one is not serialised until someone asks.

        A phone holding an event stream open counts as asking, so a real
        change is serialised once here and written to all of them. That is
        the whole difference between the stream and the poll: the poll
        cannot be told, it can only ask, and a second is a long time to
        wait to see that the button you pressed did something.
        """
        changed = self._owner._feed.publish(state)
        if changed and self._owner._streams:
            self._owner._broadcast(self._owner._feed.payload())
        return changed

    @property
    def running(self) -> bool:
        return self._owner._server is not None

    @property
    def code(self) -> str:
        return self._owner._code

    @property
    def token(self) -> str:
        return self._owner._token

    @property
    def locked(self) -> bool:
        """Too many wrong codes. The server keeps listening — refusing every
        request is the point — but nothing it is sent can be typed any
        more."""
        return self._owner._locked

    @property
    def connected(self) -> bool:
        """Has an authenticated request arrived recently?

        There is no session to be connected *to* — the credential travels
        with each request — so "connected" is the only thing that can
        honestly be said: something with the token was talking to us a
        moment ago. The window is a little over the phone's one-second poll,
        so a phone with the page open reads as connected and one that has
        been closed stops doing so within a few seconds.
        """
        return self.running and (time.monotonic() - self._owner._talked_at) < _CONNECTED_SECONDS

    @property
    def url(self) -> str | None:
        """The address to type in by hand. Pairs with the four-digit code."""
        address = local_address()
        return f"http://{address}:{self._owner._port}" if address else None

    @property
    def pair_url(self) -> str | None:
        """The address to put in the QR code: the same page, carrying the
        session token in its fragment so that scanning it is the whole of
        connecting. See the module docstring on why the fragment."""
        base = self.url
        if base is None or not self._owner._token:
            return None
        return f"{base}/#k={self._owner._token}"
