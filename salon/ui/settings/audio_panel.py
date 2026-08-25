# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused settings panel builder."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio  # noqa: E402

from salon.services import audio  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    InfoRow,
    RangeRow,
    SettingsRow,
)


def audio_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    """§8 calls the wrong HDMI sink a top-three real-world failure on an
    HTPC, so the picker is one level deep and shows the current output by
    name rather than hiding it behind a submenu."""
    sinks: list[audio.Sink] = []
    availability = audio.AudioAvailability.AVAILABLE

    def build() -> list[SettingsRow]:
        audio.list_sinks_result(_on_sinks)
        current = settings.get_string("audio-sink")
        rows: list[SettingsRow] = [
            InfoRow(
                "Current output",
                next((s.description for s in sinks if s.is_default), current or "System default"),
            ),
            RangeRow(
                "Volume step",
                lambda: float(settings.get_int("volume-step-percent")),
                _set_step,
                minimum=1,
                maximum=25,
                step=1,
                fmt=lambda v: f"{v:.0f}%",
            ),
        ]
        if not sinks:
            messages = {
                audio.AudioAvailability.NOT_INSTALLED: (
                    "Audio controls unavailable",
                    "wpctl is not installed",
                ),
                audio.AudioAvailability.HOST_EXECUTION_FAILED: (
                    "Audio controls unavailable",
                    "Could not execute host wpctl",
                ),
                audio.AudioAvailability.PROCESS_FAILED: (
                    "Audio controls unavailable",
                    "wpctl returned an error",
                ),
                audio.AudioAvailability.NO_OUTPUTS: (
                    "No outputs found",
                    "PipeWire reported no audio sinks",
                ),
            }
            title, detail = messages.get(availability, ("No outputs found", "Invalid wpctl output"))
            rows.append(InfoRow(title, "", detail=detail))
        for sink in sinks:
            rows.append(
                ActionRow(
                    sink.description,
                    lambda s=sink: _select_sink(context, settings, s),
                    value="●" if sink.is_default else "",
                )
            )
        return rows

    def _set_step(value: float) -> None:
        settings.set_int("volume-step-percent", int(value))
        audio.set_volume_step(int(value))

    def _on_sinks(result: audio.AudioResult, found: list[audio.Sink]) -> None:
        nonlocal availability
        if availability is result.availability and [s.id for s in found] == [s.id for s in sinks]:
            return
        availability = result.availability
        sinks[:] = found
        context.rebuild()

    return Panel(title="Audio", build=build, panel_id="audio", icon_name="audio-speakers-symbolic")


def _select_sink(context: SettingsContext, settings: Gio.Settings, sink: audio.Sink) -> None:
    # Persist the description, not the id: WirePlumber node ids are not
    # stable across reboots, so the id is re-resolved on each startup.
    def selected(result: audio.AudioResult) -> None:
        if result.availability is audio.AudioAvailability.AVAILABLE:
            settings.set_string("audio-sink", sink.description)
            context.toast(f"Output set to {sink.description}")
        else:
            context.toast(f"Could not set output: {result.error or result.availability.value}")
        context.rebuild()

    audio.set_default_sink_result(sink.id, selected)
