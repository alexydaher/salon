# SPDX-License-Identifier: GPL-3.0-or-later
"""A low-frequency, presentation-neutral feed of the current sound route."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from gi.repository import GLib

from salon.services import audio
from salon.services.audio_types import AudioAvailability, AudioResult, Sink


@dataclass(frozen=True, slots=True)
class AudioStatus:
    available: bool = False
    description: str = ""
    muted: bool = False
    no_outputs: bool = False


class AudioStatusWatcher:
    """Poll WirePlumber sparingly; it has no stable D-Bus API to subscribe to."""

    def __init__(self, on_change: Callable[[AudioStatus], None], *, interval_s: int = 30) -> None:
        self._on_change = on_change
        self._interval_s = interval_s
        self._last: AudioStatus | None = None
        self._timer = 0
        self._refreshing = False

    def start(self) -> None:
        self.refresh()
        self._timer = GLib.timeout_add_seconds(self._interval_s, self._on_tick)

    def stop(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = 0

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        audio.list_sinks_result(self._on_sinks)

    def _on_sinks(self, result: AudioResult, sinks: list[Sink]) -> None:
        if result.availability is AudioAvailability.NO_OUTPUTS:
            self._finish(AudioStatus(available=True, no_outputs=True))
            return
        if result.availability is not AudioAvailability.AVAILABLE or not sinks:
            self._finish(AudioStatus())
            return
        sink = next((candidate for candidate in sinks if candidate.is_default), sinks[0])

        def on_volume(volume_result: AudioResult, _level: float, muted: bool) -> None:
            known = volume_result.availability is AudioAvailability.AVAILABLE
            self._finish(AudioStatus(True, sink.description, muted if known else False))

        audio.get_volume_result(on_volume)

    def _finish(self, status: AudioStatus) -> None:
        self._refreshing = False
        if status != self._last:
            self._last = status
            self._on_change(status)

    def _on_tick(self) -> bool:
        self.refresh()
        return bool(GLib.SOURCE_CONTINUE)
