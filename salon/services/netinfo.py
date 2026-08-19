# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only network status from NetworkManager.

A television's settings screen has to be able to answer "am I online, and
over what" without sending the user to a desktop control panel to find out.
Salon deliberately doesn't *configure* networking — §1 says system
configuration delegates to gnome-control-center, and re-implementing a Wi-Fi
picker for a D-pad is a project of its own — but it can and should say what
the current state is before offering that link.

Everything here is asynchronous. NetworkManager lives on the system bus and
a busy or absent daemon would otherwise block the frame clock (§10). A
machine with no NetworkManager at all is not an error: the status simply
reads as unknown, and the link into GNOME Settings still works.

`NetworkWatcher` is the top bar's feed: NetworkManager's own
`PropertiesChanged` covers connect, disconnect and captive-portal
transitions, and a slow timer covers signal strength, which the manager
object doesn't announce — the strength lives on the access point, and
subscribing to *that* means re-subscribing every time the primary
connection changes for a number that only has five buckets.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core import status as status_tokens  # noqa: E402

_BUS_NAME = "org.freedesktop.NetworkManager"
_OBJECT_PATH = "/org/freedesktop/NetworkManager"
_NM_IFACE = "org.freedesktop.NetworkManager"
_ACTIVE_IFACE = "org.freedesktop.NetworkManager.Connection.Active"
_WIRELESS_IFACE = "org.freedesktop.NetworkManager.Device.Wireless"
_AP_IFACE = "org.freedesktop.NetworkManager.AccessPoint"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"

# NMConnectivityState.
_CONNECTIVITY = {
    0: "Unknown",
    1: "No connection",
    2: "Connected, but the portal hasn't been signed in to",
    3: "Connected, but limited",
    4: "Connected",
}

# The `Type` strings NetworkManager reports for an active connection, in the
# words a person would use for them.
_TYPE_NAMES = {
    "802-11-wireless": "Wi-Fi",
    "802-3-ethernet": "Ethernet",
    "wifi": "Wi-Fi",
    "ethernet": "Ethernet",
    "gsm": "Mobile broadband",
    "vpn": "VPN",
    "wireguard": "VPN",
}


@dataclass(frozen=True, slots=True)
class NetworkStatus:
    """What the settings row shows and the top bar draws. `name` is empty
    when nothing is up; `strength` is -1 whenever it doesn't apply or the
    access point didn't answer, which is not the same as no signal."""

    name: str
    kind: str
    connectivity: str
    available: bool = True
    state: int = status_tokens.CONNECTIVITY_UNKNOWN
    strength: int = -1

    @property
    def summary(self) -> str:
        if not self.available:
            return "NetworkManager isn't running"
        if not self.name:
            return "Not connected"
        return f"{self.name} ({self.kind})" if self.kind else self.name

    @property
    def icon_name(self) -> str:
        """Empty when there is nothing honest to draw — see core/status."""
        return status_tokens.network_glyph(
            self.kind, self.strength, self.state, available=self.available
        )

    @property
    def phrase(self) -> str:
        return status_tokens.network_phrase(
            self.name, self.kind, self.state, available=self.available
        )


_UNAVAILABLE = NetworkStatus(name="", kind="", connectivity="Unknown", available=False)


def status_async(callback: Callable[[NetworkStatus], None]) -> None:
    """Ask NetworkManager what's up, and call back on the main loop."""
    try:
        connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    except GLib.Error:
        callback(_UNAVAILABLE)
        return

    def on_manager(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            props = conn.call_finish(result).unpack()[0]
        except GLib.Error:
            callback(_UNAVAILABLE)
            return
        state = int(props.get("Connectivity", status_tokens.CONNECTIVITY_UNKNOWN))
        path = str(props.get("PrimaryConnection", "/"))
        # "/" is NetworkManager's null object path — a live daemon with no
        # active connection, which is a different answer from no daemon.
        if not path or path == "/":
            callback(
                NetworkStatus(
                    name="",
                    kind="",
                    connectivity=_CONNECTIVITY[status_tokens.CONNECTIVITY_NONE],
                    state=status_tokens.CONNECTIVITY_NONE,
                )
            )
            return
        _fetch_active(conn, path, state, callback)

    _get_all(connection, _OBJECT_PATH, _NM_IFACE, on_manager)


def _fetch_active(
    connection: Gio.DBusConnection,
    path: str,
    state: int,
    callback: Callable[[NetworkStatus], None],
) -> None:
    def on_all(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            props = conn.call_finish(result).unpack()[0]
        except GLib.Error:
            callback(_UNAVAILABLE)
            return
        raw_kind = str(props.get("Type", ""))
        status = NetworkStatus(
            name=str(props.get("Id", "")),
            kind=_TYPE_NAMES.get(raw_kind, raw_kind),
            connectivity=_CONNECTIVITY.get(state, "Connected"),
            state=state,
        )
        devices = [str(device) for device in props.get("Devices", [])]
        if status.kind == "Wi-Fi" and devices:
            _fetch_strength(conn, devices[0], status, callback)
        else:
            callback(status)

    _get_all(connection, path, _ACTIVE_IFACE, on_all)


def _fetch_strength(
    connection: Gio.DBusConnection,
    device_path: str,
    status: NetworkStatus,
    callback: Callable[[NetworkStatus], None],
) -> None:
    """Two more hops: the wireless device names its active access point, and
    the access point knows the signal. Either can fail — a device that just
    dropped its AP answers with the null path — and the answer is then the
    connection without a bar count, never no connection at all."""

    def on_ap(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            ap_path = str(conn.call_finish(result).unpack()[0])
        except GLib.Error:
            callback(status)
            return
        if not ap_path or ap_path == "/":
            callback(status)
            return

        def on_strength(inner: Gio.DBusConnection, strength_result: Gio.AsyncResult) -> None:
            try:
                strength = int(inner.call_finish(strength_result).unpack()[0])
            except (GLib.Error, TypeError, ValueError):
                callback(status)
                return
            callback(replace(status, strength=strength))

        _get_property(conn, ap_path, _AP_IFACE, "Strength", on_strength)

    _get_property(connection, device_path, _WIRELESS_IFACE, "ActiveAccessPoint", on_ap)


class NetworkWatcher:
    """A live feed of `NetworkStatus` for the top bar.

    Signals cover everything that changes discretely; the timer exists for
    signal strength alone. Both funnel through one refresh, and an unchanged
    reading is dropped rather than pushed, because the bar rebuilds its
    tooltip and icon on every callback and a 30-second heartbeat of
    identical updates is work nobody asked for.
    """

    def __init__(
        self, on_change: Callable[[NetworkStatus], None], *, interval_s: int = 30
    ) -> None:
        self._on_change = on_change
        self._interval_s = interval_s
        self._last: NetworkStatus | None = None
        self._subscription = 0
        self._timer = 0
        self._connection: Gio.DBusConnection | None = None

    def start(self) -> None:
        try:
            self._connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error:
            # No system bus at all (a broken container). The bar simply
            # never shows a network glyph; nothing else here is affected.
            self._deliver(_UNAVAILABLE)
            return
        self._subscription = self._connection.signal_subscribe(
            _BUS_NAME,
            _PROPS_IFACE,
            "PropertiesChanged",
            _OBJECT_PATH,
            _NM_IFACE,
            Gio.DBusSignalFlags.NONE,
            lambda *_: self.refresh(),
        )
        self._timer = GLib.timeout_add_seconds(self._interval_s, self._on_tick)
        self.refresh()

    def stop(self) -> None:
        if self._subscription and self._connection is not None:
            self._connection.signal_unsubscribe(self._subscription)
        self._subscription = 0
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = 0

    def refresh(self) -> None:
        status_async(self._deliver)

    def _on_tick(self) -> bool:
        self.refresh()
        return bool(GLib.SOURCE_CONTINUE)

    def _deliver(self, status: NetworkStatus) -> None:
        if status == self._last:
            return
        self._last = status
        self._on_change(status)


def _get_property(
    connection: Gio.DBusConnection,
    path: str,
    interface: str,
    name: str,
    on_done: Callable[[Gio.DBusConnection, Gio.AsyncResult], None],
) -> None:
    connection.call(
        _BUS_NAME,
        path,
        _PROPS_IFACE,
        "Get",
        GLib.Variant("(ss)", (interface, name)),
        GLib.VariantType("(v)"),
        Gio.DBusCallFlags.NONE,
        -1,
        None,
        on_done,
    )


def _get_all(
    connection: Gio.DBusConnection,
    path: str,
    interface: str,
    on_done: Callable[[Gio.DBusConnection, Gio.AsyncResult], None],
) -> None:
    connection.call(
        _BUS_NAME,
        path,
        _PROPS_IFACE,
        "GetAll",
        GLib.Variant("(s)", (interface,)),
        GLib.VariantType("(a{sv})"),
        Gio.DBusCallFlags.NONE,
        -1,
        None,
        on_done,
    )
