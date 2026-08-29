# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Audio: which output, how loud, and a way to hear it.

§8 calls the wrong HDMI sink a top-three real-world failure on an HTPC, so
the picker is one level deep. Two things it was missing:

* **the outputs were named by WirePlumber**, which produces four rows of
  fifty-five characters differing in one digit. `core/sink_names.py` names
  the port and keeps the card as the detail line.
* **there was no way to hear the result.** Choosing between three HDMI
  ports blind, with the confirmation two screens away, is the whole of the
  problem this panel exists for.

Volume itself lives here now as well. A television's audio settings without
a volume control is a surprising thing to find, and unlike the sink it is
something you want to set while listening to the test tone.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio  # noqa: E402

from salon.core import sink_names  # noqa: E402
from salon.services import audio, testtone  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    GroupRow,
    InfoRow,
    Keyed,
    RangeRow,
    SettingsRow,
    ToggleRow,
    restore_defaults_row,
)

_UNAVAILABLE = {
    audio.AudioAvailability.NOT_INSTALLED: "wpctl is not installed",
    audio.AudioAvailability.HOST_EXECUTION_FAILED: "Could not execute host wpctl",
    audio.AudioAvailability.PROCESS_FAILED: "wpctl returned an error",
    audio.AudioAvailability.NO_OUTPUTS: "PipeWire reported no audio sinks",
}


def audio_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    keyed = Keyed(settings)
    sinks: list[audio.Sink] = []
    state = {
        "availability": audio.AudioAvailability.AVAILABLE,
        "volume": 0.0,
        "muted": False,
        "read": False,
    }

    def on_sinks(result: audio.AudioResult, found: list[audio.Sink]) -> None:
        if state["availability"] is result.availability and [s.id for s in found] == [
            s.id for s in sinks
        ]:
            return
        state["availability"] = result.availability
        sinks[:] = found
        context.rebuild()

    def on_volume(level: float, muted: bool) -> None:
        if state["read"] and abs(float(state["volume"]) - level) < 1e-3 and state["muted"] is muted:
            return
        state.update(volume=level, muted=muted, read=True)
        context.rebuild()

    def set_volume(level: float) -> None:
        state["volume"] = level
        audio.set_volume(level)

    def set_muted(muted: bool) -> None:
        state["muted"] = muted
        audio.toggle_mute()

    def build() -> list[SettingsRow]:
        audio.list_sinks_result(on_sinks)
        audio.get_volume(on_volume)
        return [
            GroupRow("Output"),
            *_sink_rows(context, settings, sinks, state),
            _test_row(context),
            GroupRow("Volume"),
            RangeRow(
                "Volume",
                lambda: float(state["volume"]) * 100,
                lambda value: set_volume(value / 100),
                minimum=0,
                maximum=100,
                step=5,
                fmt=lambda v: f"{v:.0f}%",
                detail="Changes as you walk the list, so you can set it by ear",
            ),
            ToggleRow("Mute", lambda: bool(state["muted"]), set_muted),
            keyed.ranged(
                "volume-step-percent",
                "Volume step",
                minimum=1,
                maximum=25,
                step=1,
                fmt=lambda v: f"{v:.0f}%",
                detail="How far one press of the volume key moves it",
            ),
            GroupRow("This section"),
            restore_defaults_row(keyed, context.toast, context.rebuild),
        ]

    def summary() -> str:
        current = next((sink for sink in sinks if sink.is_default), None)
        return sink_names.short_name(current.description) if current else ""

    return Panel(
        title="Audio",
        build=build,
        subtitle="Output, volume and testing",
        summary=summary,
        panel_id="audio",
        icon_name="audio-speakers-symbolic",
    )


def _sink_rows(
    context: SettingsContext,
    settings: Gio.Settings,
    sinks: list[audio.Sink],
    state: dict[str, object],
) -> list[SettingsRow]:
    """One row per output, named by its port. The current one is ticked.

    There is no separate "Current output" row any more: it said the same
    thing as the ticked row four lines below it, in a longer form, and the
    cursor opened on it — a read-only row whose legend reads "Nothing to
    change on this row" is a poor first impression for a screen whose
    entire job is a choice.
    """
    if not sinks:
        availability = state["availability"]
        detail = _UNAVAILABLE.get(availability, "Invalid wpctl output")  # type: ignore[arg-type]
        return [InfoRow("No outputs found", "", detail=detail)]
    details = sink_names.device_names([sink.description for sink in sinks])
    return [
        ActionRow(
            sink_names.short_name(sink.description),
            lambda s=sink: _select_sink(context, settings, s),
            detail=detail,
            value="In use" if sink.is_default else "",
        )
        for sink, detail in zip(sinks, details, strict=True)
    ]


def _test_row(context: SettingsContext) -> SettingsRow:
    row = ActionRow(
        "Play a test sound",
        lambda: testtone.play(
            lambda problem: context.toast(problem or "Playing a test sound on the current output.")
        ),
        detail="Confirms the choice above without leaving Settings",
    )
    if not testtone.available():
        row.make_unavailable(testtone.unavailable_reason())
    return row


def _select_sink(context: SettingsContext, settings: Gio.Settings, sink: audio.Sink) -> None:
    # Persist the description, not the id: WirePlumber node ids are not
    # stable across reboots, so the id is re-resolved on each startup.
    def selected(result: audio.AudioResult) -> None:
        if result.availability is audio.AudioAvailability.AVAILABLE:
            settings.set_string("audio-sink", sink.description)
            context.toast(f"Output set to {sink_names.short_name(sink.description)}.")
        else:
            context.toast(f"Could not set output: {result.error or result.availability.value}")
        context.rebuild()

    audio.set_default_sink_result(sink.id, selected)
