# SPDX-License-Identifier: GPL-3.0-or-later
"""Battery state from UPower, for the top bar (§6.9).

UPower publishes a composite `DisplayDevice` — the one battery a user
interface should show, already merged across however many cells the machine
really has — so this reads that and nothing else. On a machine with no
battery (which is what Salon is actually for: a box under a television) the
display device reports `Type` 1, "line power", and the watcher reports
nothing at all rather than a permanent full battery. An absent glyph is the
honest answer; a 100% icon on a desktop is a lie that never changes.

Asynchronous like everything else that touches D-Bus from the UI thread, and
live: UPower emits `PropertiesChanged` on the display device for every
percentage step and state change, so there is no timer here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core import status as status_tokens  # noqa: E402

_BUS_NAME = "org.freedesktop.UPower"
_DISPLAY_PATH = "/org/freedesktop/UPower/devices/DisplayDevice"
_DEVICE_IFACE = "org.freedesktop.UPower.Device"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"

# UPowerDeviceType and UPowerDeviceState, the two enums that decide whether
# there is anything to draw.
_TYPE_BATTERY = 2
_STATE_CHARGING = 1
_STATE_FULLY_CHARGED = 4
_STATE_PENDING_CHARGE = 5


@dataclass(frozen=True, slots=True)
class BatteryStatus:
    """`present` is False on any machine without a battery, and on every
    error path — there is no partial answer worth drawing."""

    percent: float = 0.0
    charging: bool = False
    full: bool = False
    present: bool = False

    @property
    def icon_name(self) -> str:
        if not self.present:
            return ""
        return status_tokens.battery_glyph(self.percent, charging=self.charging, full=self.full)

    @property
    def phrase(self) -> str:
        return status_tokens.battery_phrase(self.percent, charging=self.charging, full=self.full)

    @property
    def low(self) -> bool:
        return (
            self.present
            and not self.charging
            and not self.full
            and self.percent <= status_tokens.BATTERY_LOW_PERCENT
        )


_ABSENT = BatteryStatus()


def status_async(callback: Callable[[BatteryStatus], None]) -> None:
    try:
        connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    except GLib.Error:
        callback(_ABSENT)
        return
    _read(connection, callback)


def _read(connection: Gio.DBusConnection, callback: Callable[[BatteryStatus], None]) -> None:
    def on_all(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            props = conn.call_finish(result).unpack()[0]
        except GLib.Error:
            # No UPower on the bus. Not an error: a set-top box needn't run
            # one, and the bar just has one fewer glyph.
            callback(_ABSENT)
            return
        callback(_from_properties(props))

    connection.call(
        _BUS_NAME,
        _DISPLAY_PATH,
        _PROPS_IFACE,
        "GetAll",
        GLib.Variant("(s)", (_DEVICE_IFACE,)),
        GLib.VariantType("(a{sv})"),
        Gio.DBusCallFlags.NONE,
        -1,
        None,
        on_all,
    )


def _from_properties(props: dict[str, object]) -> BatteryStatus:
    if int(props.get("Type", 0)) != _TYPE_BATTERY or not bool(props.get("IsPresent", False)):
        return _ABSENT
    state = int(props.get("State", 0))
    return BatteryStatus(
        percent=float(props.get("Percentage", 0.0)),
        charging=state in (_STATE_CHARGING, _STATE_PENDING_CHARGE),
        full=state == _STATE_FULLY_CHARGED,
        present=True,
    )


class BatteryWatcher:
    """A live feed of `BatteryStatus`. `on_change` fires once at startup —
    with `present=False` on a machine that has no battery, which is what
    tells the bar to leave the glyph out."""

    def __init__(self, on_change: Callable[[BatteryStatus], None]) -> None:
        self._on_change = on_change
        self._last: BatteryStatus | None = None
        self._subscription = 0
        self._connection: Gio.DBusConnection | None = None

    def start(self) -> None:
        try:
            self._connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error:
            self._deliver(_ABSENT)
            return
        self._subscription = self._connection.signal_subscribe(
            _BUS_NAME,
            _PROPS_IFACE,
            "PropertiesChanged",
            _DISPLAY_PATH,
            _DEVICE_IFACE,
            Gio.DBusSignalFlags.NONE,
            lambda *_: self.refresh(),
        )
        self.refresh()

    def stop(self) -> None:
        if self._subscription and self._connection is not None:
            self._connection.signal_unsubscribe(self._subscription)
        self._subscription = 0

    def refresh(self) -> None:
        if self._connection is None:
            status_async(self._deliver)
            return
        _read(self._connection, self._deliver)

    def _deliver(self, status: BatteryStatus) -> None:
        if status == self._last:
            return
        self._last = status
        self._on_change(status)
