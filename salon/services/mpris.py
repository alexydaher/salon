# SPDX-License-Identifier: GPL-3.0-or-later
"""What is playing, over MPRIS, and the three buttons that control it.

Salon starts things and then gets out of the way, which leaves one gap a
television notices: something is playing, the remote has a play/pause key,
and pressing it does nothing because the keypress goes to Salon rather than
to whatever is playing. `Action.PLAY_PAUSE` existed in the vocabulary from
the beginning and was handled nowhere.

MPRIS closes it without Salon knowing anything about media. Every player
that matters on Linux — Firefox, Chrome, Spotify, VLC, mpv, GNOME's own —
registers `org.mpris.MediaPlayer2.*` on the session bus, and the remote's
transport keys become three method calls.

The part worth being careful about is *which* player, which is
`core/nowplaying.py`'s job and is tested there. This file does D-Bus:
finding the players, following them, and calling on them.

Everything is asynchronous. A player that has wedged must cost a message
that never arrives, not a frozen interface — `Gio.DBusConnection.call` with
a short timeout and a callback that tolerates failure is the whole
strategy.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core.nowplaying import Player, Selection  # noqa: E402

_PREFIX = "org.mpris.MediaPlayer2."
_PATH = "/org/mpris/MediaPlayer2"
_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
_ROOT_IFACE = "org.mpris.MediaPlayer2"
_PROPERTIES = "org.freedesktop.DBus.Properties"

# Short: a player that does not answer this fast is one the remote should
# not be waiting on.
_TIMEOUT_MS = 1500


def _artist_of(metadata: GLib.Variant | None) -> str:
    """`xesam:artist` is an array of strings in the specification and a
    plain string in several real players."""
    if metadata is None:
        return ""
    value = metadata.get("xesam:artist")
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value if item)
    return ""


class NowPlayingWatcher:
    """Follows every MPRIS player on the session bus and reports the one
    that matters, or None."""

    def __init__(self, on_change: Callable[[Player | None], None]) -> None:
        self._on_change = on_change
        self._selection = Selection()
        self._connection: Gio.DBusConnection | None = None
        self._subscriptions: list[int] = []
        self._last: Player | None = None

    # --- lifecycle -------------------------------------------------------

    def start(self) -> None:
        try:
            connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            # No session bus: a valid state (a bare TTY, a test runner), and
            # one that costs the transport keys rather than the launcher.
            return
        self._connection = connection
        # Property changes from any player, on the one path they all use.
        self._subscriptions.append(
            connection.signal_subscribe(
                None,
                _PROPERTIES,
                "PropertiesChanged",
                _PATH,
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_properties_changed,
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

    # --- control ---------------------------------------------------------

    @property
    def current(self) -> Player | None:
        return self._selection.current()

    def play_pause(self) -> bool:
        return self._call_player("PlayPause")

    def next_track(self) -> bool:
        return self._call_player("Next")

    def previous_track(self) -> bool:
        return self._call_player("Previous")

    def _call_player(self, method: str) -> bool:
        """Returns whether there was anything to call, so the caller can
        fall back — pressing play with nothing playing should do whatever
        the screen would otherwise do, not nothing."""
        player = self.current
        connection = self._connection
        if player is None or connection is None:
            return False
        connection.call(
            player.bus_name,
            _PATH,
            _PLAYER_IFACE,
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
            # A player that refuses PlayPause (some browsers do, for a tab
            # that has since navigated away) is not worth a message on the
            # television.
            pass

    # --- discovery -------------------------------------------------------

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

    def _on_properties_changed(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        path: str,
        interface: str,
        signal: str,
        parameters: GLib.Variant,
    ) -> None:
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
        metadata = properties.get("Metadata") or {}
        previous = self._selection.players.get(bus_name)
        status = str(properties.get("PlaybackStatus", ""))
        title = str(metadata.get("xesam:title", "") or "")
        player = Player(
            bus_name=bus_name,
            identity=previous.identity if previous else _fallback_identity(bus_name),
            status=status,
            title=title,
            artist=_artist_of(metadata),
            # Only bumped when something actually changed, so that a
            # periodic refresh cannot promote a paused player above the one
            # that is playing.
            changed_at=(
                previous.changed_at
                if previous is not None
                and previous.status == status
                and previous.title == title
                else time.monotonic()
            ),
            can_go_next=bool(properties.get("CanGoNext", False)),
            can_go_previous=bool(properties.get("CanGoPrevious", False)),
        )
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
        if current == self._last:
            return
        self._last = current
        self._on_change(current)


def _fallback_identity(bus_name: str) -> str:
    """Something readable before `Identity` comes back — and for the
    players that never answer it."""
    tail = bus_name.removeprefix(_PREFIX).split(".")[0]
    return tail.replace("_", " ").title() if tail else "Media"
