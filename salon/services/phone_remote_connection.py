# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused phone-remote server component."""

from __future__ import annotations

from salon.services.phone_remote_delivery import _notify, _sse_frame
from salon.services.phone_remote_shared import (
    _STATUS_TOO_MANY_REQUESTS,
    MAX_ATTEMPTS,
    GLib,
    PhoneRemoteComponent,
    Soup,
    json,
    secrets,
)


class PhoneRemoteConnection(PhoneRemoteComponent):
    def _handle_connect(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """The one endpoint that accepts the four-digit code, and the only
        place wrong guesses are counted.

        Answers with the session token, which is what everything else
        wants. A phone that scanned the QR already has it and posts it back
        here anyway — that is how a stale code from a previous session ends
        up on the code screen instead of on a remote whose every button
        fails.
        """
        if not self._owner._from_local_network(message):
            self._owner._refuse(message, Soup.Status.FORBIDDEN, "Not on this network.")
            return
        fields = self._owner._fields(message)
        if fields is None:
            return
        # Checked before the credential is even read: once a session is
        # burned it is burned for the right code too, so that guessing it on
        # the last allowed attempt wins nothing.
        if self._owner._locked:
            self._owner._refuse(
                message,
                _STATUS_TOO_MANY_REQUESTS,
                "Too many wrong codes. The television shows a new code in a few minutes.",
            )
            return

        if self._owner._has_token(fields.get("key")):
            self._owner._touch()
            self._owner._json(message, json.dumps({"key": self._owner._token}).encode())
            return

        if "code" not in fields:
            # A token was offered and it is not ours: this is a phone coming
            # back with what it remembered from a previous session, which is
            # every reload of a page that has been kept. It is not a guess at
            # the code and must not spend one of the five — the page posts a
            # stale key on load, so counting it made an ordinary reload burn
            # an attempt and five of them lock a household out of its own
            # television. 401 is what the page turns into the code screen.
            self._owner._refuse(message, Soup.Status.UNAUTHORIZED, "Not connected any more.")
            return

        # compare_digest, not ==: the code is short enough that a timing
        # oracle is a real (if unglamorous) way to guess it.
        if not secrets.compare_digest(str(fields.get("code", "")), self._owner._code):
            self._owner._wrong_attempts += 1
            if self._owner._wrong_attempts >= MAX_ATTEMPTS:
                self._owner._lock()
                if self._owner._on_locked is not None:
                    GLib.idle_add(_notify, self._owner._on_locked)
            self._owner._refuse(message, Soup.Status.FORBIDDEN, "Wrong code.")
            return

        # A correct code proves whoever is holding the phone was told it, so
        # the earlier fumbles stop counting against them.
        self._owner._wrong_attempts = 0
        self._owner._touch()
        self._owner._json(message, json.dumps({"key": self._owner._token}).encode())

    # --- what is on the television ---------------------------------------

    def _handle_state(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """The poll. Answers 204 when the phone is already current, which is
        most of the time — and matters because this handler runs on the same
        main loop that is animating the tiles."""
        if not self._owner._authorize_get(message, query):
            return
        if self._owner._feed.is_current((query or {}).get("v")):
            message.set_status(Soup.Status.NO_CONTENT, None)
            return
        self._owner._json(message, self._owner._feed.payload())

    def _handle_events(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """The state, pushed instead of polled.

        `text/event-stream`, held open, one `data:` line per real change.
        The poll is not removed and is not deprecated — it is the fallback,
        and it earns its place: a stream is a connection somebody's phone
        keeps open across a screen lock, a Wi-Fi roam and a browser tab
        eviction, and every one of those ends it silently. The page opens a
        stream, and if it ever closes or errors it goes back to asking once
        a second. Both paths read the same `StateFeed`, so they cannot
        disagree about what the television is showing.

        The body does not accumulate. Delivery works either way — measured,
        because the first version of this claimed otherwise — but with
        accumulation on, libsoup keeps every byte it has ever written to
        the response, and this is a response that is meant to live for as
        long as someone has the page open. That is a slow leak per connected
        phone rather than a broken feature, which is exactly the kind of
        thing that is invisible until a television has been on for a week.
        """
        if not self._owner._authorize_get(message, query):
            return
        message.set_status(Soup.Status.OK, None)
        headers = message.get_response_headers()
        headers.set_content_type("text/event-stream", None)
        headers.append("Cache-Control", "no-cache")
        headers.append("Connection", "keep-alive")
        # Chrome and Safari both hold a stream in a buffer until enough
        # bytes arrive to bother with; a proxy in between will do the same.
        # Telling the browser to wait 2s before reconnecting, in a comment
        # line, doubles as the flush.
        headers.set_encoding(Soup.Encoding.EOF)
        body = message.get_response_body()
        body.set_accumulate(False)
        body.append(b": salon\nretry: 2000\n\n")
        # The current state immediately, so a phone that has just connected
        # draws the television rather than an empty page until something
        # over there happens to change.
        body.append(_sse_frame(self._owner._feed.payload()))
        self._owner._streams.append(message)
        message.connect("finished", self._on_stream_finished)

    def _on_stream_finished(self, message: Soup.ServerMessage) -> None:
        try:
            self._owner._streams.remove(message)
        except ValueError:
            pass

    def _broadcast(self, payload: bytes) -> None:
        frame = _sse_frame(payload)
        for message in list(self._owner._streams):
            try:
                message.get_response_body().append(frame)
                message.unpause()
            except (GLib.Error, TypeError):
                # A socket that has gone away between the "finished" signal
                # and now. Dropping it here rather than letting it throw on
                # every future publish.
                self._on_stream_finished(message)

    def _close_streams(self) -> None:
        for message in list(self._owner._streams):
            try:
                message.get_response_body().complete()
                message.unpause()
            except (GLib.Error, TypeError):
                pass
        self._owner._streams.clear()
