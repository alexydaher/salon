# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Compatibility facade for Wi-Fi discovery and connection workflows."""

from __future__ import annotations

from typing import Any

from salon.services.component import component_attribute
from salon.services.wifi_connection import WifiConnection
from salon.services.wifi_discovery import WifiDiscovery
from salon.services.wifi_shared import *


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

        self._components = (WifiDiscovery(self), WifiConnection(self))

    def __getattr__(self, name: str) -> Any:
        return component_attribute(self._components, name)

    def _bus(self) -> Gio.DBusConnection | None:
        if self._connection is None:
            try:
                self._connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            except GLib.Error:
                return None
        return self._connection

    # --- listing ---------------------------------------------------------

    # --- joining ---------------------------------------------------------
