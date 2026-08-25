# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused Wi-Fi D-Bus operations."""

from salon.services.component import ServiceComponent
from salon.services.wifi_shared import (
    _AP,
    _AP_FLAGS_PRIVACY,
    _BUS,
    _DEVICE,
    _DEVICE_TYPE_WIFI,
    _NM,
    _PATH,
    _PROPS,
    _TIMEOUT_MS,
    _WIRELESS,
    AccessPoint,
    Callable,
    Gio,
    GLib,
    _decode_ssid,
)


class WifiDiscovery(ServiceComponent):
    def list_networks(self, on_done: Callable[[list[AccessPoint], str], None]) -> None:
        """Everything in range, strongest first, one entry per name.

        The second argument is an error to show, or "" — a Wi-Fi list that
        is empty because NetworkManager is not running and one that is
        empty because nothing is in range must not look the same.
        """
        bus = self._owner._bus()
        if bus is None:
            on_done([], "Salon can't reach NetworkManager on this machine.")
            return
        self._find_device(bus, lambda: self._scan_then_list(bus, on_done), on_done)

    def _find_device(
        self,
        bus: Gio.DBusConnection,
        then: Callable[[], None],
        on_done: Callable[[list[AccessPoint], str], None],
    ) -> None:
        if self._owner._device is not None:
            then()
            return

        def on_devices(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                (paths,) = conn.call_finish(result).unpack()
            except GLib.Error:
                on_done([], "Salon can't reach NetworkManager on this machine.")
                return
            self._probe_devices(bus, list(paths), then, on_done)

        bus.call(
            _BUS,
            _PATH,
            _NM,
            "GetDevices",
            None,
            GLib.VariantType("(ao)"),
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            on_devices,
        )

    def _probe_devices(
        self,
        bus: Gio.DBusConnection,
        paths: list[str],
        then: Callable[[], None],
        on_done: Callable[[list[AccessPoint], str], None],
    ) -> None:
        """Ask each device its type until a wireless one turns up.

        One at a time rather than in parallel: there are rarely more than
        three, and sequential keeps "which answer arrived first" from
        deciding which adapter Salon uses on a machine with two.
        """
        if not paths:
            on_done([], "This machine has no wireless adapter.")
            return
        path = paths[0]
        rest = paths[1:]

        def on_type(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                (value,) = conn.call_finish(result).unpack()
            except GLib.Error:
                value = 0
            if value == _DEVICE_TYPE_WIFI:
                self._owner._device = path
                then()
                return
            self._probe_devices(bus, rest, then, on_done)

        bus.call(
            _BUS,
            path,
            _PROPS,
            "Get",
            GLib.Variant("(ss)", (_DEVICE, "DeviceType")),
            GLib.VariantType("(v)"),
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            on_type,
        )

    def _scan_then_list(
        self, bus: Gio.DBusConnection, on_done: Callable[[list[AccessPoint], str], None]
    ) -> None:
        device = self._owner._device
        if device is None:
            on_done([], "This machine has no wireless adapter.")
            return

        def on_scanned(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                conn.call_finish(result)
            except GLib.Error:
                # A scan too soon after the last one is refused, and the
                # cached list is still worth showing.
                pass
            self._list_access_points(bus, device, on_done)

        bus.call(
            _BUS,
            device,
            _WIRELESS,
            "RequestScan",
            GLib.Variant("(a{sv})", ({},)),
            None,
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            on_scanned,
        )

    def _list_access_points(
        self,
        bus: Gio.DBusConnection,
        device: str,
        on_done: Callable[[list[AccessPoint], str], None],
    ) -> None:
        def on_points(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                (paths,) = conn.call_finish(result).unpack()
            except GLib.Error:
                on_done([], "Salon couldn't read the list of networks.")
                return
            self._collect(bus, list(paths), [], on_done)

        bus.call(
            _BUS,
            device,
            _WIRELESS,
            "GetAllAccessPoints",
            None,
            GLib.VariantType("(ao)"),
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            on_points,
        )

    def _collect(
        self,
        bus: Gio.DBusConnection,
        remaining: list[str],
        found: list[AccessPoint],
        on_done: Callable[[list[AccessPoint], str], None],
    ) -> None:
        if not remaining:
            # One entry per name, keeping the strongest: a mesh network
            # publishes the same SSID from every node, and a list with the
            # same name in it five times is unusable with a D-pad.
            best: dict[str, AccessPoint] = {}
            for point in found:
                if not point.ssid:
                    continue
                current = best.get(point.ssid)
                if current is None or point.strength > current.strength:
                    best[point.ssid] = point
            on_done(sorted(best.values(), key=lambda p: -p.strength), "")
            return
        path, rest = remaining[0], remaining[1:]

        def on_props(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                (props,) = conn.call_finish(result).unpack()
            except GLib.Error:
                self._collect(bus, rest, found, on_done)
                return
            flags = int(props.get("Flags", 0) or 0)
            wpa = int(props.get("WpaFlags", 0) or 0)
            rsn = int(props.get("RsnFlags", 0) or 0)
            found.append(
                AccessPoint(
                    ssid=_decode_ssid(props.get("Ssid")),
                    strength=int(props.get("Strength", 0) or 0),
                    secured=bool(flags & _AP_FLAGS_PRIVACY or wpa or rsn),
                    path=path,
                )
            )
            self._collect(bus, rest, found, on_done)

        bus.call(
            _BUS,
            path,
            _PROPS,
            "GetAll",
            GLib.Variant("(s)", (_AP,)),
            GLib.VariantType("(a{sv})"),
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            on_props,
        )
