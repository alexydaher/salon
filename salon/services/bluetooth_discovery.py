# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused Bluetooth D-Bus operations."""

from salon.services.bluetooth_shared import (
    _ADAPTER,
    _BUS,
    _DEVICE,
    _OBJECT_MANAGER,
    _TIMEOUT_MS,
    Callable,
    Device,
    Gio,
    GLib,
    _readable,
    describe_device,
)
from salon.services.component import ServiceComponent


class BluetoothDiscovery(ServiceComponent):
    def list_devices(self, on_done: Callable[[list[Device], str], None]) -> None:
        bus = self._owner._bus()
        if bus is None:
            on_done([], "Salon can't reach the Bluetooth service on this machine.")
            return
        self._owner._ensure_agent()

        def on_objects(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                (objects,) = conn.call_finish(result).unpack()
            except GLib.Error:
                on_done([], "Salon can't reach the Bluetooth service on this machine.")
                return
            adapters = [p for p, ifaces in objects.items() if _ADAPTER in ifaces]
            if not adapters:
                on_done([], "This machine has no Bluetooth adapter.")
                return
            self._owner._adapter = adapters[0]
            devices = [
                Device(
                    path=path,
                    name=str(ifaces[_DEVICE].get("Alias") or ifaces[_DEVICE].get("Name") or "")
                    or "Unnamed device",
                    kind=describe_device(ifaces[_DEVICE]),
                    paired=bool(ifaces[_DEVICE].get("Paired", False)),
                    connected=bool(ifaces[_DEVICE].get("Connected", False)),
                )
                for path, ifaces in objects.items()
                if _DEVICE in ifaces
            ]
            # Paired first, then by name: the thing someone is most likely
            # to want is the controller they already own.
            devices.sort(key=lambda d: (not d.paired, d.name.casefold()))
            on_done(devices, "")

        bus.call(
            _BUS,
            "/",
            _OBJECT_MANAGER,
            "GetManagedObjects",
            None,
            GLib.VariantType("(a{oa{sa{sv}}})"),
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            on_objects,
        )

    def start_discovery(self, on_done: Callable[[bool, str], None]) -> None:
        self._adapter_call("StartDiscovery", on_done, "Looking for devices…")

    def stop_discovery(self) -> None:
        self._adapter_call("StopDiscovery", None, "")

    def _adapter_call(
        self, method: str, on_done: Callable[[bool, str], None] | None, ok_message: str
    ) -> None:
        bus = self._owner._bus()
        adapter = self._owner._adapter
        if bus is None or adapter is None:
            if on_done is not None:
                on_done(False, "This machine has no Bluetooth adapter.")
            return

        def finished(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                conn.call_finish(result)
            except GLib.Error as error:
                if on_done is not None:
                    on_done(False, _readable(error))
                return
            if on_done is not None:
                on_done(True, ok_message)

        bus.call(
            _BUS,
            adapter,
            _ADAPTER,
            method,
            None,
            None,
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            finished,
        )
