# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused Bluetooth D-Bus operations."""

from salon.services.bluetooth_shared import (
    _ADAPTER,
    _BUS,
    _DEVICE,
    _PROPS,
    _TIMEOUT_MS,
    Callable,
    Device,
    Gio,
    GLib,
    _readable,
)
from salon.services.component import ServiceComponent


class BluetoothConnections(ServiceComponent):
    def pair(self, device: Device, on_done: Callable[[bool, str], None]) -> None:
        """Pair, trust and connect, in that order.

        Trust is what makes the controller come back by itself after a
        reboot; without it every session starts with the same dance.
        """
        bus = self._owner._bus()
        if bus is None:
            on_done(False, "Salon can't reach the Bluetooth service on this machine.")
            return
        self._owner._ensure_agent()

        def after_pair(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                conn.call_finish(result)
            except GLib.Error as error:
                message = _readable(error)
                if "already exists" not in message.lower():
                    on_done(False, message)
                    return
            self._trust(bus, device, on_done)

        if device.paired:
            self._trust(bus, device, on_done)
            return
        bus.call(
            _BUS,
            device.path,
            _DEVICE,
            "Pair",
            None,
            None,
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            after_pair,
        )

    def _trust(
        self, bus: Gio.DBusConnection, device: Device, on_done: Callable[[bool, str], None]
    ) -> None:
        def after_trust(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                conn.call_finish(result)
            except GLib.Error:
                # Not fatal: the device is paired, it simply will not
                # reconnect on its own.
                pass
            self._connect(bus, device, on_done)

        bus.call(
            _BUS,
            device.path,
            _PROPS,
            "Set",
            GLib.Variant("(ssv)", (_DEVICE, "Trusted", GLib.Variant("b", True))),
            None,
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            after_trust,
        )

    def _connect(
        self, bus: Gio.DBusConnection, device: Device, on_done: Callable[[bool, str], None]
    ) -> None:
        def finished(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                conn.call_finish(result)
            except GLib.Error as error:
                on_done(False, _readable(error))
                return
            on_done(True, f"{device.name} is paired and connected.")

        bus.call(
            _BUS,
            device.path,
            _DEVICE,
            "Connect",
            None,
            None,
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            finished,
        )

    def disconnect(self, device: Device, on_done: Callable[[bool, str], None]) -> None:
        """Drop the link without forgetting the device.

        The one a controller actually needs: a pad that stays connected to
        the television is a pad that will not pair with anything else, and
        unpairing it to hand it over would mean pairing it again on the way
        back. It stays trusted, so it reconnects on its own.
        """
        bus = self._owner._bus()
        if bus is None:
            on_done(False, "Salon can't reach the Bluetooth service on this machine.")
            return

        def finished(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                conn.call_finish(result)
            except GLib.Error as error:
                on_done(False, _readable(error))
                return
            on_done(True, f"{device.name} disconnected.")

        bus.call(
            _BUS,
            device.path,
            _DEVICE,
            "Disconnect",
            None,
            None,
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            finished,
        )

    def forget(self, device: Device, on_done: Callable[[bool, str], None]) -> None:
        """Unpair and remove. BlueZ disconnects it on the way out.

        `RemoveDevice` is on the *adapter*, not the device — the object at
        `device.path` is what is being destroyed, so it cannot be the one
        asked to do it. That is also why this needs an adapter, and so a
        listing, to have happened first.
        """
        bus = self._owner._bus()
        adapter = self._owner._adapter
        if bus is None or adapter is None:
            on_done(False, "Salon can't reach the Bluetooth service on this machine.")
            return

        def finished(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                conn.call_finish(result)
            except GLib.Error as error:
                on_done(False, _readable(error))
                return
            on_done(True, f"{device.name} has been forgotten.")

        bus.call(
            _BUS,
            adapter,
            _ADAPTER,
            "RemoveDevice",
            GLib.Variant("(o)", (device.path,)),
            None,
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            finished,
        )
