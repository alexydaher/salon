# SPDX-License-Identifier: GPL-3.0-or-later
"""Discover MPRIS players and publish the currently relevant one."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core.nowplaying import Player, Selection  # noqa: E402
from salon.services.mpris_metadata import player_from_properties  # noqa: E402
from salon.services.mpris_transport import MprisTransport  # noqa: E402

_PREFIX = "org.mpris.MediaPlayer2."
_PATH = "/org/mpris/MediaPlayer2"
_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
_ROOT_IFACE = "org.mpris.MediaPlayer2"
_PROPERTIES = "org.freedesktop.DBus.Properties"

# A player that does not answer this fast should not hold up the remote.
_TIMEOUT_MS = 1500


class NowPlayingWatcher:
    """Follows every MPRIS player on the session bus and reports the one
    that matters, or None."""

    def __init__(self, on_change: Callable[[Player | None], None]) -> None:
        self._on_change = on_change
        self._selection = Selection()
        self._connection: Gio.DBusConnection | None = None
        self._subscriptions: list[int] = []
        self._last: Player | None = None
        self._last_players: tuple[Player, ...] = ()
        self._transport = MprisTransport(lambda: self._connection, lambda: self.current)

    def start(self) -> None:
        try:
            connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            # No session bus: a valid state (a bare TTY, a test runner), and
            # one that costs the transport keys rather than the launcher.
            return
        self._connection = connection
        # Position does not emit PropertiesChanged; MPRIS sends Seeked.
        for interface, signal in (
            (_PROPERTIES, "PropertiesChanged"),
            (_PLAYER_IFACE, "Seeked"),
        ):
            self._subscriptions.append(
                connection.signal_subscribe(
                    None,
                    interface,
                    signal,
                    _PATH,
                    None,
                    Gio.DBusSignalFlags.NONE,
                    self._on_player_signal,
                )
            )
        # Players coming and going. Without this a closed browser stays on
        # the strip for ever, because a dead player sends no properties.
        self._subscriptions.append(
            connection.signal_subscribe(
                "org.freedesktop.DBus",
                "org.freedesktop.DBus",
                "NameOwnerChanged",
                "/org/freedesktop/DBus",
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_name_owner_changed,
            )
        )
        self._list_names()

    def stop(self) -> None:
        connection = self._connection
        if connection is not None:
            for subscription in self._subscriptions:
                connection.signal_unsubscribe(subscription)
        self._subscriptions.clear()
        self._connection = None
        self._selection = Selection()
        self._last = None
        self._last_players = ()

    @property
    def current(self) -> Player | None:
        return self._selection.current()

    @property
    def players(self) -> tuple[Player, ...]:
        return self._selection.active_players()

    def play_pause(self, bus_name: str | None = None) -> bool:
        return self._transport.call("PlayPause", bus_name)

    def next_track(self, bus_name: str | None = None) -> bool:
        return self._transport.call("Next", bus_name)

    def previous_track(self, bus_name: str | None = None) -> bool:
        return self._transport.call("Previous", bus_name)

    def _list_names(self) -> None:
        connection = self._connection
        if connection is None:
            return
        connection.call(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "ListNames",
            None,
            GLib.VariantType("(as)"),
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            self._on_names,
        )

    def _on_names(self, connection: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            (names,) = connection.call_finish(result).unpack()
        except GLib.Error:
            return
        for name in names:
            if name.startswith(_PREFIX):
                self._refresh(name)

    def _on_name_owner_changed(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        path: str,
        interface: str,
        signal: str,
        parameters: GLib.Variant,
    ) -> None:
        name, _old, new_owner = parameters.unpack()
        if not name.startswith(_PREFIX):
            return
        if new_owner:
            self._refresh(name)
        else:
            self._selection.remove(name)
            self._publish()

    def _on_player_signal(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        path: str,
        interface: str,
        signal: str,
        parameters: GLib.Variant,
    ) -> None:
        if signal == "Seeked":
            if sender:
                self._refresh_by_unique_name(sender)
            return
        changed_interface, _changed, _invalidated = parameters.unpack()
        if changed_interface != _PLAYER_IFACE or not sender:
            return
        # The signal carries only what changed, and `sender` is a unique
        # name (":1.42") rather than the well-known one methods are called
        # on. Re-reading every property keeps one code path and costs one
        # message on an event that fires when a human presses a button.
        self._refresh_by_unique_name(sender)

    def _refresh_by_unique_name(self, unique: str) -> None:
        # Cheap because the set is tiny: match the unique name against the
        # players already known, and only go back to the bus if it is new.
        for name in list(self._selection.players):
            self._refresh(name)
        if not self._selection.players:
            self._list_names()

    def _refresh(self, bus_name: str) -> None:
        connection = self._connection
        if connection is None:
            return
        connection.call(
            bus_name,
            _PATH,
            _PROPERTIES,
            "GetAll",
            GLib.Variant("(s)", (_PLAYER_IFACE,)),
            GLib.VariantType("(a{sv})"),
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            self._on_player_properties,
            bus_name,
        )
        connection.call(
            bus_name,
            _PATH,
            _PROPERTIES,
            "Get",
            GLib.Variant("(ss)", (_ROOT_IFACE, "Identity")),
            GLib.VariantType("(v)"),
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            self._on_identity,
            bus_name,
        )

    def _on_player_properties(
        self, connection: Gio.DBusConnection, result: Gio.AsyncResult, bus_name: str
    ) -> None:
        try:
            (properties,) = connection.call_finish(result).unpack()
        except GLib.Error:
            self._selection.remove(bus_name)
            self._publish()
            return
        previous = self._selection.players.get(bus_name)
        player = player_from_properties(bus_name, properties, previous)
        self._selection.update(player)
        self._publish()

    def _on_identity(
        self, connection: Gio.DBusConnection, result: Gio.AsyncResult, bus_name: str
    ) -> None:
        try:
            (identity,) = connection.call_finish(result).unpack()
        except GLib.Error:
            return
        player = self._selection.players.get(bus_name)
        if player is None or not identity:
            return
        from dataclasses import replace

        self._selection.update(replace(player, identity=str(identity)))
        self._publish()

    def _publish(self) -> None:
        current = self._selection.current()
        players = self._selection.active_players()
        if current == self._last and players == self._last_players:
            return
        self._last = current
        self._last_players = players
        self._on_change(current)
