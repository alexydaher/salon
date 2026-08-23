# SPDX-License-Identifier: GPL-3.0-or-later
"""Joining a wireless network from the sofa, over NetworkManager.

Salon's Network panel could read the connection and could open
gnome-control-center, and that second half is a dead end on the machine
this is for: gnome-control-center is a mouse-and-keyboard application, its
Wi-Fi list is not focusable with a D-pad, and its password field cannot be
reached by a remote at all. A television that has just been moved to a new
room, or a fresh install, has no other way onto the network — and no way to
reach anything Salon is for.

So this is the list and the password box, in Salon's own language: scan,
show what is in range strongest first, take a password through the same
on-screen keyboard everything else uses, and say what happened.

Scope is deliberately one thing: **join a WPA-PSK network, or an open one.**
Enterprise authentication, hidden SSIDs, captive portals and static
addressing all remain gnome-control-center's job, and the panel still
offers it. Those need a keyboard and a person who knows what they are
doing; this needs a remote and someone who knows their own Wi-Fi password.

Everything is asynchronous, as §10 requires — a scan takes seconds and an
association can take tens of them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core.status import wifi_icon  # noqa: E402

_BUS = "org.freedesktop.NetworkManager"
_PATH = "/org/freedesktop/NetworkManager"
_NM = "org.freedesktop.NetworkManager"
_DEVICE = "org.freedesktop.NetworkManager.Device"
_WIRELESS = "org.freedesktop.NetworkManager.Device.Wireless"
_AP = "org.freedesktop.NetworkManager.AccessPoint"
_SETTINGS_PATH = "/org/freedesktop/NetworkManager/Settings"
_SETTINGS = "org.freedesktop.NetworkManager.Settings"
_CONNECTION = "org.freedesktop.NetworkManager.Settings.Connection"
_PROPS = "org.freedesktop.DBus.Properties"

_DEVICE_TYPE_WIFI = 2

# NM 802-11 security flag bits. Only two questions matter here: is the
# network open, and does it want a passphrase.
_AP_FLAGS_PRIVACY = 0x1

_TIMEOUT_MS = 25_000


@dataclass(frozen=True, slots=True)
class AccessPoint:
    ssid: str
    strength: int
    secured: bool
    path: str

    @property
    def icon_name(self) -> str:
        return wifi_icon(self.strength)

    @property
    def summary(self) -> str:
        return f"{self.strength}%" + (" · password" if self.secured else " · open")


def _decode_ssid(raw: object) -> str:
    """NM hands the SSID back as raw bytes, because that is what it is —
    the standard does not say it is text, and plenty of routers ship one
    that is not valid UTF-8."""
    if not isinstance(raw, (bytes, bytearray, list, tuple)):
        return ""
    return bytes(raw).decode("utf-8", errors="replace").strip()


class WifiService:
    """One wireless device's worth of scanning and joining.

    Holds no state beyond the device path it found, so a machine that gains
    or loses a Wi-Fi adapter is handled by asking again rather than by
    watching for it — this is opened from a settings panel, not run
    continuously.
    """

    def __init__(self) -> None:
        self._connection: Gio.DBusConnection | None = None
        self._device: str | None = None

    def _bus(self) -> Gio.DBusConnection | None:
        if self._connection is None:
            try:
                self._connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            except GLib.Error:
                return None
        return self._connection

    # --- listing ---------------------------------------------------------

    def list_networks(self, on_done: Callable[[list[AccessPoint], str], None]) -> None:
        """Everything in range, strongest first, one entry per name.

        The second argument is an error to show, or "" — a Wi-Fi list that
        is empty because NetworkManager is not running and one that is
        empty because nothing is in range must not look the same.
        """
        bus = self._bus()
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
        if self._device is not None:
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
            _BUS, _PATH, _NM, "GetDevices", None, GLib.VariantType("(ao)"),
            Gio.DBusCallFlags.NONE, _TIMEOUT_MS, None, on_devices,
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
                self._device = path
                then()
                return
            self._probe_devices(bus, rest, then, on_done)

        bus.call(
            _BUS, path, _PROPS, "Get", GLib.Variant("(ss)", (_DEVICE, "DeviceType")),
            GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, _TIMEOUT_MS, None, on_type,
        )

    def _scan_then_list(
        self, bus: Gio.DBusConnection, on_done: Callable[[list[AccessPoint], str], None]
    ) -> None:
        device = self._device
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
            _BUS, device, _WIRELESS, "RequestScan", GLib.Variant("(a{sv})", ({},)),
            None, Gio.DBusCallFlags.NONE, _TIMEOUT_MS, None, on_scanned,
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
            _BUS, device, _WIRELESS, "GetAllAccessPoints", None, GLib.VariantType("(ao)"),
            Gio.DBusCallFlags.NONE, _TIMEOUT_MS, None, on_points,
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
            _BUS, path, _PROPS, "GetAll", GLib.Variant("(s)", (_AP,)),
            GLib.VariantType("(a{sv})"), Gio.DBusCallFlags.NONE, _TIMEOUT_MS, None, on_props,
        )

    # --- joining ---------------------------------------------------------

    def connect(
        self, point: AccessPoint, password: str, on_done: Callable[[bool, str], None]
    ) -> None:
        """Join a network. `on_done(ok, message)` either way.

        Tries a saved connection first. Without that, joining a network the
        machine already knows would add a second profile for it every time,
        and NetworkManager would accumulate "SFR_936F 1", "SFR_936F 2" for
        ever — visible in every other network tool on the system.
        """
        bus = self._bus()
        device = self._device
        if bus is None or device is None:
            on_done(False, "Salon can't reach NetworkManager on this machine.")
            return

        def on_existing(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                (paths,) = conn.call_finish(result).unpack()
            except GLib.Error:
                paths = []
            self._match_saved(bus, list(paths), point, password, device, on_done)

        bus.call(
            _BUS, _SETTINGS_PATH, _SETTINGS, "ListConnections", None,
            GLib.VariantType("(ao)"), Gio.DBusCallFlags.NONE, _TIMEOUT_MS, None, on_existing,
        )

    def _match_saved(
        self,
        bus: Gio.DBusConnection,
        remaining: list[str],
        point: AccessPoint,
        password: str,
        device: str,
        on_done: Callable[[bool, str], None],
    ) -> None:
        if not remaining:
            self._add_and_activate(bus, point, password, device, on_done)
            return
        path, rest = remaining[0], remaining[1:]

        def on_settings(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                (settings,) = conn.call_finish(result).unpack()
            except GLib.Error:
                self._match_saved(bus, rest, point, password, device, on_done)
                return
            wireless = settings.get("802-11-wireless") or {}
            if _decode_ssid(wireless.get("ssid")) == point.ssid:
                self._activate(bus, path, point, device, on_done)
                return
            self._match_saved(bus, rest, point, password, device, on_done)

        bus.call(
            _BUS, path, _CONNECTION, "GetSettings", None, GLib.VariantType("(a{sa{sv}})"),
            Gio.DBusCallFlags.NONE, _TIMEOUT_MS, None, on_settings,
        )

    def _activate(
        self,
        bus: Gio.DBusConnection,
        connection_path: str,
        point: AccessPoint,
        device: str,
        on_done: Callable[[bool, str], None],
    ) -> None:
        def finished(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                conn.call_finish(result)
            except GLib.Error as error:
                on_done(False, _readable(error))
                return
            on_done(True, f"Joining {point.ssid}…")

        bus.call(
            _BUS, _PATH, _NM, "ActivateConnection",
            GLib.Variant("(ooo)", (connection_path, device, point.path)),
            GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, _TIMEOUT_MS, None, finished,
        )

    def _add_and_activate(
        self,
        bus: Gio.DBusConnection,
        point: AccessPoint,
        password: str,
        device: str,
        on_done: Callable[[bool, str], None],
    ) -> None:
        wireless: dict[str, GLib.Variant] = {
            "ssid": GLib.Variant("ay", point.ssid.encode("utf-8")),
            "mode": GLib.Variant("s", "infrastructure"),
        }
        settings: dict[str, dict[str, GLib.Variant]] = {
            "connection": {
                "id": GLib.Variant("s", point.ssid),
                "type": GLib.Variant("s", "802-11-wireless"),
            },
            "802-11-wireless": wireless,
        }
        if point.secured:
            settings["802-11-wireless-security"] = {
                "key-mgmt": GLib.Variant("s", "wpa-psk"),
                "psk": GLib.Variant("s", password),
            }

        def finished(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                conn.call_finish(result)
            except GLib.Error as error:
                on_done(False, _readable(error))
                return
            on_done(True, f"Joining {point.ssid}…")

        bus.call(
            _BUS, _PATH, _NM, "AddAndActivateConnection",
            GLib.Variant("(a{sa{sv}}oo)", (settings, device, point.path)),
            GLib.VariantType("(oo)"), Gio.DBusCallFlags.NONE, _TIMEOUT_MS, None, finished,
        )


def _readable(error: GLib.Error) -> str:
    """A D-Bus error as something worth putting on a television.

    §6.11: no Python reprs, no bus names, no interface paths. What is left
    is usually NetworkManager's own message, which is written for people.
    """
    message = (error.message or "").strip()
    _, _, tail = message.rpartition(": ")
    text = (tail or message).strip()
    if not text:
        return "The network refused the connection."
    if "secrets were required" in text.lower() or "no secrets" in text.lower():
        return "That password wasn't accepted."
    return text[:1].upper() + text[1:]
