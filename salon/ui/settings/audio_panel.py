# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F401
"""Focused settings panel builder."""
from __future__ import annotations

import shutil
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon import config as app_config  # noqa: E402
from salon.core import sandbox, tokens  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.services import artwork, audio, bluetooth, launcher, netinfo, wifi  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext, confirm_panel  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    ChoiceRow,
    InfoRow,
    RangeRow,
    SettingsRow,
    TextRow,
    ToggleRow,
)


def audio_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    """§8 calls the wrong HDMI sink a top-three real-world failure on an
    HTPC, so the picker is one level deep and shows the current output by
    name rather than hiding it behind a submenu."""
    sinks: list[audio.Sink] = []

    def build() -> list[SettingsRow]:
        audio.list_sinks(_on_sinks)
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
            rows.append(InfoRow("No outputs found", "", detail="Is PipeWire running?"))
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

    def _on_sinks(found: list[audio.Sink]) -> None:
        if [s.id for s in found] == [s.id for s in sinks]:
            return
        sinks[:] = found
        context.rebuild()

    return Panel(
        title="Audio", build=build, panel_id="audio", icon_name="audio-speakers-symbolic"
    )


def _select_sink(context: SettingsContext, settings: Gio.Settings, sink: audio.Sink) -> None:
    # Persist the description, not the id: WirePlumber node ids are not
    # stable across reboots, so the id is re-resolved on each startup.
    settings.set_string("audio-sink", sink.description)
    audio.set_default_sink(sink.id, lambda: context.rebuild())
    context.toast(f"Output set to {sink.description}")
