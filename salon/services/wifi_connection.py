# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused Wi-Fi D-Bus operations."""

from salon.services.component import ServiceComponent
from salon.services.wifi_shared import (
    _BUS,
    _CONNECTION,
    _NM,
    _PATH,
    _SETTINGS,
    _SETTINGS_PATH,
    _TIMEOUT_MS,
    AccessPoint,
    Callable,
    Gio,
    GLib,
    _decode_ssid,
    _readable,
)


class WifiConnection(ServiceComponent):
    def connect(
        self, point: AccessPoint, password: str, on_done: Callable[[bool, str], None]
    ) -> None:
        """Join a network. `on_done(ok, message)` either way.

        Tries a saved connection first. Without that, joining a network the
        machine already knows would add a second profile for it every time,
        and NetworkManager would accumulate "SFR_936F 1", "SFR_936F 2" for
        ever — visible in every other network tool on the system.
        """
        bus = self._owner._bus()
        device = self._owner._device
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
            _BUS,
            _SETTINGS_PATH,
            _SETTINGS,
            "ListConnections",
            None,
            GLib.VariantType("(ao)"),
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            on_existing,
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
            _BUS,
            path,
            _CONNECTION,
            "GetSettings",
            None,
            GLib.VariantType("(a{sa{sv}})"),
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            on_settings,
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
            _BUS,
            _PATH,
            _NM,
            "ActivateConnection",
            GLib.Variant("(ooo)", (connection_path, device, point.path)),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            finished,
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
            _BUS,
            _PATH,
            _NM,
            "AddAndActivateConnection",
            GLib.Variant("(a{sa{sv}}oo)", (settings, device, point.path)),
            GLib.VariantType("(oo)"),
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            finished,
        )
