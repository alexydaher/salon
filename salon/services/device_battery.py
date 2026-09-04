# SPDX-License-Identifier: GPL-3.0-or-later
"""Battery levels for connected Bluetooth controllers and audio devices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon.services.bluetooth_shared import (  # noqa: E402
    _BUS,
    _DEVICE,
    _OBJECT_MANAGER,
    _PROPS,
    describe_device,
)

_BATTERY = "org.bluez.Battery1"
_RELEVANT_KINDS = ("audio", "controller", "gamepad", "headphone", "headset", "joystick", "remote")


@dataclass(frozen=True, slots=True)
class DeviceBatteryStatus:
    name: str
    kind: str
    percent: int

    @property
    def icon_name(self) -> str:
        words = f"{self.kind} {self.name}".casefold()
        return "audio-headphones-symbolic" if any(
            word in words for word in ("audio", "headphone", "headset", "buds")
        ) else "input-gaming-symbolic"


def statuses_from_objects(objects: dict[str, object]) -> tuple[DeviceBatteryStatus, ...]:
    statuses: list[DeviceBatteryStatus] = []
    for interfaces in objects.values():
        if not isinstance(interfaces, dict):
            continue
        device = interfaces.get(_DEVICE)
        battery = interfaces.get(_BATTERY)
        if not isinstance(device, dict) or not isinstance(battery, dict):
            continue
        kind = describe_device(device)
        if not bool(device.get("Connected", False)) or not any(
            word in kind.casefold() for word in _RELEVANT_KINDS
        ):
            continue
        try:
            percent = max(0, min(100, int(battery["Percentage"])))
        except (KeyError, TypeError, ValueError):
            continue
        name = str(device.get("Alias") or device.get("Name") or kind)
        statuses.append(DeviceBatteryStatus(name, kind, percent))
    return tuple(sorted(statuses, key=lambda status: (status.percent, status.name.casefold())))


class DeviceBatteryWatcher:
    """Observe BlueZ and report only devices whose charge is actually known."""

    def __init__(
        self, on_change: Callable[[tuple[DeviceBatteryStatus, ...]], None], *, interval_s: int = 60
    ) -> None:
        self._on_change = on_change
        self._interval_s = interval_s
        self._connection: Gio.DBusConnection | None = None
        self._subscriptions: list[int] = []
        self._timer = 0
        self._last: tuple[DeviceBatteryStatus, ...] | None = None

    def start(self) -> None:
        try:
            self._connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error:
            self._deliver(())
            return
        for interface, member in (
            (_PROPS, "PropertiesChanged"),
            (_OBJECT_MANAGER, "InterfacesAdded"),
            (_OBJECT_MANAGER, "InterfacesRemoved"),
        ):
            self._subscriptions.append(
                self._connection.signal_subscribe(
                    _BUS,
                    interface,
                    member,
                    None,
                    None,
                    Gio.DBusSignalFlags.NONE,
                    lambda *_: self.refresh(),
                )
            )
        self._timer = GLib.timeout_add_seconds(self._interval_s, self._on_tick)
        self.refresh()

    def stop(self) -> None:
        if self._connection is not None:
            for subscription in self._subscriptions:
                self._connection.signal_unsubscribe(subscription)
        self._subscriptions.clear()
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = 0

    def refresh(self) -> None:
        if self._connection is None:
            self._deliver(())
            return

        def on_objects(connection: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                objects = connection.call_finish(result).unpack()[0]
                self._deliver(statuses_from_objects(objects))
            except (GLib.Error, TypeError, ValueError):
                self._deliver(())

        self._connection.call(
            _BUS,
            "/",
            _OBJECT_MANAGER,
            "GetManagedObjects",
            None,
            GLib.VariantType("(a{oa{sa{sv}}})"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            on_objects,
        )

    def _deliver(self, statuses: tuple[DeviceBatteryStatus, ...]) -> None:
        if statuses != self._last:
            self._last = statuses
            self._on_change(statuses)

    def _on_tick(self) -> bool:
        self.refresh()
        return bool(GLib.SOURCE_CONTINUE)
