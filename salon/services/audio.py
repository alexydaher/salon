# SPDX-License-Identifier: GPL-3.0-or-later
"""Volume/mute via wpctl (PipeWire), with pactl as a fallback (§8).

Never Gvc (no stable public API) and never a shell — every call here is a
plain argv, run async via Gio.Subprocess so a slow or hung mixer can't
block the compositor frame (see the "no blocking I/O on the main loop"
quality gate).
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib  # noqa: E402

_SINK = "@DEFAULT_AUDIO_SINK@"
_DEFAULT_VOLUME_STEP_PERCENT = 5

# Settings owns the step; this is the value the OSD path actually uses, kept
# module-level so every caller changes together rather than each passing it.
_volume_step_percent = _DEFAULT_VOLUME_STEP_PERCENT


def set_volume_step(percent: int) -> None:
    global _volume_step_percent
    _volume_step_percent = max(1, min(25, percent))


def volume_step() -> int:
    return _volume_step_percent


@dataclass(frozen=True, slots=True)
class Sink:
    """One output. `id` is WirePlumber's node id, which is *not* stable
    across reboots — the description is what Settings persists, and the id
    is re-resolved from it each time (§8: getting audio out of the right
    HDMI port is a top-three real-world failure, so this has to survive a
    restart)."""

    id: int
    description: str
    is_default: bool


# " │  *   59. Speaker [vol: 0.42]" — the star marks the current default.
_WPCTL_SINK_RE = re.compile(r"^\s*\S*\s*(\*)?\s*(\d+)\.\s+(.*?)\s+\[vol:")


def parse_sinks(status: str) -> list[Sink]:
    """Pull the sink list out of `wpctl status`.

    Split out as a plain function so the parsing — the part that breaks
    when WirePlumber changes its output — is testable without a mixer.
    """
    sinks: list[Sink] = []
    in_sinks = False
    for line in status.splitlines():
        if "Sinks:" in line:
            if in_sinks:
                break  # the second "Sinks:" belongs to the Video section
            in_sinks = True
            continue
        if not in_sinks:
            continue
        if "Sources:" in line or "Filters:" in line:
            break
        match = _WPCTL_SINK_RE.match(line)
        if match is None:
            continue
        sinks.append(
            Sink(
                id=int(match.group(2)),
                description=match.group(3),
                is_default=bool(match.group(1)),
            )
        )
    return sinks


def list_sinks(on_result: Callable[[list[Sink]], None]) -> None:
    if not _have_wpctl():
        on_result([])
        return

    def on_output(stdout: str | None) -> None:
        on_result(parse_sinks(stdout) if stdout else [])

    _run_async(["wpctl", "status"], on_output)


def set_default_sink(sink_id: int, on_done: Callable[[], None] | None = None) -> None:
    if not _have_wpctl():
        if on_done is not None:
            on_done()
        return
    _run_async(["wpctl", "set-default", str(sink_id)], lambda _out: on_done() if on_done else None)

# "Volume: 0.45" or "Volume: 0.45 [MUTED]"
_WPCTL_VOLUME_RE = re.compile(r"Volume:\s*([\d.]+)\s*(\[MUTED\])?")


def _have_wpctl() -> bool:
    return shutil.which("wpctl") is not None


def _run_async(argv: list[str], on_done: Callable[[str | None], None]) -> None:
    try:
        launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDOUT_PIPE)
        subprocess = launcher.spawnv(argv)
    except GLib.Error:
        on_done(None)
        return

    def on_communicated(proc: Gio.Subprocess, result: Gio.AsyncResult) -> None:
        try:
            ok, stdout, _stderr = proc.communicate_utf8_finish(result)
        except GLib.Error:
            on_done(None)
            return
        on_done(stdout if ok else None)

    subprocess.communicate_utf8_async(None, None, on_communicated)


def get_volume(on_result: Callable[[float, bool], None]) -> None:
    """Reports (volume 0..1, muted). Calls on_result(1.0, False) if the
    mixer can't be reached at all — a missing sink is a real-world top
    failure mode (§11) and shouldn't crash the OSD."""
    if not _have_wpctl():
        on_result(1.0, False)
        return

    def on_output(stdout: str | None) -> None:
        if stdout is None:
            on_result(1.0, False)
            return
        match = _WPCTL_VOLUME_RE.search(stdout)
        if match is None:
            on_result(1.0, False)
            return
        on_result(float(match.group(1)), match.group(2) is not None)

    _run_async(["wpctl", "get-volume", _SINK], on_output)


def adjust_volume(direction: int, on_done: Callable[[], None] | None = None) -> None:
    """direction: +1 or -1, one configured volume step."""
    sign = "+" if direction > 0 else "-"
    if _have_wpctl():
        argv = ["wpctl", "set-volume", _SINK, f"{_volume_step_percent}%{sign}"]
    elif shutil.which("pactl") is not None:
        argv = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{sign}{_volume_step_percent}%"]
    else:
        if on_done is not None:
            on_done()
        return
    _run_async(argv, lambda _stdout: on_done() if on_done is not None else None)


def set_volume(level: float, on_done: Callable[[], None] | None = None) -> None:
    """Set the sink to an absolute 0..1 level.

    For the phone's slider. `adjust_volume` steps by the user's configured
    increment, which is the right model for a button and the wrong one for
    a finger dragged to a particular place — expressing "a third of the way
    along" as nineteen step presses is how a volume control ends up lagging
    behind the thumb moving it.
    """
    level = min(1.0, max(0.0, level))
    if _have_wpctl():
        argv = ["wpctl", "set-volume", _SINK, f"{level:.3f}"]
    elif shutil.which("pactl") is not None:
        argv = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{round(level * 100)}%"]
    else:
        if on_done is not None:
            on_done()
        return
    _run_async(argv, lambda _stdout: on_done() if on_done is not None else None)


def toggle_mute(on_done: Callable[[], None] | None = None) -> None:
    if _have_wpctl():
        argv = ["wpctl", "set-mute", _SINK, "toggle"]
    elif shutil.which("pactl") is not None:
        argv = ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"]
    else:
        if on_done is not None:
            on_done()
        return
    _run_async(argv, lambda _stdout: on_done() if on_done is not None else None)
