# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused phone-remote server component."""

from __future__ import annotations

from salon.services.phone_remote_shared import *


class PhoneRemoteLifecycle(PhoneRemoteComponent):
    def start(self) -> bool:
        if self._server is not None:
            return True
        self._code = f"{secrets.randbelow(10000):04d}"
        self._token = secrets.token_urlsafe(_TOKEN_BYTES)
        self._wrong_attempts = 0
        self._locked = False
        server = Soup.Server()
        server.add_handler("/", self._handle_page)
        server.add_handler("/manifest.webmanifest", self._handle_manifest)
        server.add_handler("/icon.svg", self._handle_icon)
        for clip_path in _AWAKE_CLIPS:
            server.add_handler(clip_path, self._handle_awake)
        server.add_handler("/connect", self._handle_connect)
        server.add_handler("/state", self._handle_state)
        server.add_handler("/events", self._handle_events)
        server.add_handler("/search", self._handle_search)
        server.add_handler("/tile", self._handle_tile_action)
        server.add_handler("/volume", self._handle_volume)
        server.add_handler("/art", self._handle_art)
        server.add_handler("/type", self._handle_type)
        server.add_handler("/action", self._handle_action)
        server.add_handler("/launch", self._handle_launch)
        server.add_handler("/transport", self._handle_transport)
        server.add_handler("/pointer", self._handle_pointer)
        try:
            server.listen_all(self._port, Soup.ServerListenOptions(0))
        except GLib.Error:
            return False
        self._server = server
        self._last_seen = time.monotonic()
        self._talked_at = 0.0
        self._idle_id = GLib.timeout_add_seconds(_IDLE_CHECK_SECONDS, self._check_idle)
        return True

    def stop(self) -> None:
        self._close_streams()
        self._offered.clear()
        if self._idle_id is not None:
            GLib.source_remove(self._idle_id)
            self._idle_id = None
        if self._server is not None:
            self._server.disconnect()
            self._server = None
        self._code = ""
        self._token = ""
        self._talked_at = 0.0
        self._wrong_attempts = 0
        self._locked = False
        self._holders.clear()

    def _check_idle(self) -> bool:
        # Someone is holding this open on purpose. A phone with its screen
        # off sends nothing — that is not the same as nobody wanting the
        # remote, and treating it as such is how the remote died mid-film.
        if self._holders:
            return GLib.SOURCE_CONTINUE
        if time.monotonic() - self._last_seen < SESSION_TIMEOUT_SECONDS:
            return GLib.SOURCE_CONTINUE
        self._idle_id = None
        self.stop()
        return GLib.SOURCE_REMOVE

    def _touch(self) -> None:
        """Push the idle deadline out. Called for every accepted request."""
        self._last_seen = self._talked_at = time.monotonic()
