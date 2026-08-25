# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Compatibility facade for Bluetooth discovery and connections."""

from __future__ import annotations

from typing import Any

from salon.services.bluetooth_connections import BluetoothConnections
from salon.services.bluetooth_discovery import BluetoothDiscovery
from salon.services.bluetooth_shared import *
from salon.services.component import component_attribute


class BluetoothService:
    """Scanning and pairing on the first adapter BlueZ reports."""

    def __init__(self) -> None:
        self._connection: Gio.DBusConnection | None = None
        self._adapter: str | None = None
        self._agent_id: int | None = None

        self._components = (BluetoothDiscovery(self), BluetoothConnections(self))

    def __getattr__(self, name: str) -> Any:
        return component_attribute(self._components, name)

    def _bus(self) -> Gio.DBusConnection | None:
        if self._connection is None:
            try:
                self._connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            except GLib.Error:
                return None
        return self._connection

    # --- the agent -------------------------------------------------------

    def _ensure_agent(self) -> None:
        """Register a no-input, no-output agent, once.

        Without one, BlueZ has nobody to ask about confirming a pairing and
        refuses. With this one, "just works" pairing succeeds silently —
        which is what a gamepad does — and anything demanding a typed PIN
        is rejected with an error the panel can show.
        """
        bus = self._bus()
        if bus is None or self._agent_id is not None:
            return
        try:
            info = Gio.DBusNodeInfo.new_for_xml(_AGENT_XML)
            self._agent_id = bus.register_object(
                _AGENT_PATH, info.interfaces[0], self._on_agent_call, None, None
            )
        except GLib.Error:
            return
        bus.call(
            _BUS,
            "/org/bluez",
            _AGENT_MANAGER,
            "RegisterAgent",
            GLib.Variant("(os)", (_AGENT_PATH, "NoInputNoOutput")),
            None,
            Gio.DBusCallFlags.NONE,
            _TIMEOUT_MS,
            None,
            _ignore,
        )

    @staticmethod
    def _on_agent_call(
        connection: Gio.DBusConnection,
        sender: str,
        path: str,
        interface: str,
        method: str,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        # Everything that can be agreed to silently, is. Everything needing
        # a human to read or type something is refused with a message,
        # because there is no way to answer it from a sofa.
        if method in ("RequestConfirmation", "RequestAuthorization", "AuthorizeService"):
            invocation.return_value(None)
        elif method in ("Release", "Cancel", "DisplayPinCode", "DisplayPasskey"):
            invocation.return_value(None)
        else:
            invocation.return_dbus_error(
                "org.bluez.Error.Rejected",
                "This device needs a PIN typed in, which Salon can't do. "
                "Pair it in GNOME Settings instead.",
            )

    # --- listing ---------------------------------------------------------

    # --- pairing ---------------------------------------------------------
