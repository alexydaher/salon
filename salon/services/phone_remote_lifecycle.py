# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused phone-remote server component."""

from __future__ import annotations

from salon.services.phone_remote_shared import (
    _AWAKE_CLIPS,
    _IDLE_CHECK_SECONDS,
    _TOKEN_BYTES,
    LOCKOUT_SECONDS,
    SESSION_TIMEOUT_SECONDS,
    GLib,
    PhoneRemoteComponent,
    Soup,
    secrets,
    time,
)


class PhoneRemoteLifecycle(PhoneRemoteComponent):
    def start(self) -> bool:
        if self._owner._server is not None:
            return True
        self._owner._code = f"{secrets.randbelow(10000):04d}"
        self._owner._token = secrets.token_urlsafe(_TOKEN_BYTES)
        self._owner._wrong_attempts = 0
        self._owner._locked = False
        server = Soup.Server()
        server.add_handler("/", self._owner._handle_page)
        server.add_handler("/manifest.webmanifest", self._owner._handle_manifest)
        server.add_handler("/icon.svg", self._owner._handle_icon)
        server.add_handler("/ui", self._owner._handle_asset)
        for clip_path in _AWAKE_CLIPS:
            server.add_handler(clip_path, self._owner._handle_awake)
        server.add_handler("/connect", self._owner._handle_connect)
        server.add_handler("/state", self._owner._handle_state)
        server.add_handler("/events", self._owner._handle_events)
        server.add_handler("/search", self._owner._handle_search)
        server.add_handler("/tile", self._owner._handle_tile_action)
        server.add_handler("/volume", self._owner._handle_volume)
        server.add_handler("/art", self._owner._handle_art)
        server.add_handler("/np-art", self._owner._handle_now_playing_art)
        server.add_handler("/apps", self._owner._handle_apps)
        server.add_handler("/type", self._owner._handle_type)
        server.add_handler("/action", self._owner._handle_action)
        server.add_handler("/launch", self._owner._handle_launch)
        server.add_handler("/transport", self._owner._handle_transport)
        server.add_handler("/tune", self._owner._handle_tune)
        server.add_handler("/pointer", self._owner._handle_pointer)
        try:
            server.listen_all(self._owner._port, Soup.ServerListenOptions(0))
        except GLib.Error:
            # Nothing is listening, so nothing may look as though it is. The
            # credentials were minted above and the corner pairing card asks
            # only for `pair_url` — left set, it draws a QR for a port this
            # process does not hold, which is worse than drawing nothing:
            # scanning it reaches whatever *does* hold the port.
            self._owner._code = ""
            self._owner._token = ""
            return False
        self._owner._server = server
        self._owner._last_seen = time.monotonic()
        self._owner._talked_at = 0.0
        self._owner._idle_id = GLib.timeout_add_seconds(_IDLE_CHECK_SECONDS, self._check_idle)
        return True

    def stop(self) -> None:
        self._owner._close_streams()
        self._cancel_unlock()
        self._owner._offered.clear()
        if self._owner._idle_id is not None:
            GLib.source_remove(self._owner._idle_id)
            self._owner._idle_id = None
        if self._owner._server is not None:
            self._owner._server.disconnect()
            self._owner._server = None
        self._owner._code = ""
        self._owner._token = ""
        self._owner._talked_at = 0.0
        self._owner._wrong_attempts = 0
        self._owner._locked = False
        self._owner._holders.clear()

    def _check_idle(self) -> bool:
        # Someone is holding this open on purpose. A phone with its screen
        # off sends nothing — that is not the same as nobody wanting the
        # remote, and treating it as such is how the remote died mid-film.
        if self._owner._holders:
            return GLib.SOURCE_CONTINUE
        if time.monotonic() - self._owner._last_seen < SESSION_TIMEOUT_SECONDS:
            return GLib.SOURCE_CONTINUE
        self._owner._idle_id = None
        self.stop()
        return GLib.SOURCE_REMOVE

    def lock(self) -> None:
        """Burn the session, and schedule its end.

        Called from `/connect` once the attempts are spent. The unlock mints
        a new code rather than restoring the old one: waiting out a lockout
        must not hand back the four digits that were being guessed at.
        """
        self._owner._locked = True
        self._cancel_unlock()
        self._owner._unlock_id = GLib.timeout_add_seconds(LOCKOUT_SECONDS, self._unlock)

    def _unlock(self) -> bool:
        self._owner._unlock_id = None
        if self._owner._server is None:
            return GLib.SOURCE_REMOVE
        self._owner._locked = False
        self._owner._wrong_attempts = 0
        self._owner._code = f"{secrets.randbelow(10000):04d}"
        # The token is deliberately *not* re-minted: a phone that was paired
        # before the lockout has been refused for five minutes and has no
        # part in what caused it. The code is the credential that was under
        # attack, and it is the one that changes.
        return GLib.SOURCE_REMOVE

    def _cancel_unlock(self) -> None:
        if self._owner._unlock_id is not None:
            GLib.source_remove(self._owner._unlock_id)
            self._owner._unlock_id = None

    def _touch(self) -> None:
        """Push the idle deadline out. Called for every accepted request."""
        self._owner._last_seen = self._owner._talked_at = time.monotonic()
