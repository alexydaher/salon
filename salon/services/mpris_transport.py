# SPDX-License-Identifier: GPL-3.0-or-later
"""Asynchronous MPRIS transport commands."""

from __future__ import annotations

from collections.abc import Callable

from gi.repository import Gio, GLib

from salon.core.nowplaying import Player

_PATH = "/org/mpris/MediaPlayer2"
_PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
_TIMEOUT_MS = 1500


class MprisTransport:
    def __init__(
        self,
        connection: Callable[[], Gio.DBusConnection | None],
        current_player: Callable[[], Player | None],
    ) -> None:
        self._connection = connection
        self._current_player = current_player

    def call(self, method: str) -> bool:
        player = self._current_player()
        connection = self._connection()
        if player is None or connection is None:
            return False
        connection.call(
            player.bus_name,
            _PATH,
            _PLAYER_INTERFACE,
            method,
            None,
            None,
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            self._on_called,
        )
        return True

    @staticmethod
    def _on_called(connection: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            connection.call_finish(result)
        except GLib.Error:
            pass
