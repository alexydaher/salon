# SPDX-License-Identifier: GPL-3.0-or-later
"""Slow, alert-only machine-health checks, kept off GTK's main loop."""

from __future__ import annotations

import threading
from collections.abc import Callable

from gi.repository import GLib

from salon.core.health import StorageReading, TemperatureReading
from salon.services import health_probe


class SystemHealthWatcher:
    def __init__(
        self,
        on_change: Callable[[StorageReading | None, TemperatureReading | None], None],
        *,
        interval_s: int = 60,
    ) -> None:
        self._on_change = on_change
        self._interval_s = interval_s
        self._timer = 0
        self._running = False
        self._last: tuple[StorageReading | None, TemperatureReading | None] | None = None

    def start(self) -> None:
        self.refresh()
        self._timer = GLib.timeout_add_seconds(self._interval_s, self._on_tick)

    def stop(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = 0

    def refresh(self) -> None:
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._worker, name="salon-system-health", daemon=True).start()

    def _worker(self) -> None:
        result = health_probe.probe()
        GLib.idle_add(self._deliver, result)

    def _deliver(
        self, result: tuple[StorageReading | None, TemperatureReading | None]
    ) -> bool:
        self._running = False
        if result != self._last:
            self._last = result
            self._on_change(*result)
        return bool(GLib.SOURCE_REMOVE)

    def _on_tick(self) -> bool:
        self.refresh()
        return bool(GLib.SOURCE_CONTINUE)
