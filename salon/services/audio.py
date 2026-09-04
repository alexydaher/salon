# SPDX-License-Identifier: GPL-3.0-or-later
"""Volume, mute and output selection through one ``wpctl`` backend.

Never Gvc (no stable public API) and never a shell — every call here is a
plain argv, run async via Gio.Subprocess so a slow or hung mixer can't
block the compositor frame (see the "no blocking I/O on the main loop"
quality gate).
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core import sandbox  # noqa: E402
from salon.services.audio_types import (  # noqa: E402
    AudioAvailability,
    AudioResult,
    Sink,
)

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
    list_sinks_result(lambda _status, sinks: on_result(sinks))


def list_sinks_result(
    on_result: Callable[[AudioResult, list[Sink]], None],
) -> None:
    def on_output(result: AudioResult) -> None:
        if result.availability is not AudioAvailability.AVAILABLE:
            on_result(result, [])
            return
        sinks = parse_sinks(result.output)
        if not sinks:
            availability = (
                AudioAvailability.NO_OUTPUTS
                if "Sinks:" in result.output
                else AudioAvailability.MALFORMED_OUTPUT
            )
            on_result(AudioResult(availability), [])
            return
        on_result(result, sinks)

    run_wpctl(("status",), on_output)


def set_default_sink(sink_id: int, on_done: Callable[[], None] | None = None) -> None:
    set_default_sink_result(
        sink_id, lambda _result: on_done() if on_done is not None else None
    )


def set_default_sink_result(sink_id: int, on_done: Callable[[AudioResult], None]) -> None:
    run_wpctl(("set-default", str(sink_id)), on_done)


# "Volume: 0.45" or "Volume: 0.45 [MUTED]"
_WPCTL_VOLUME_RE = re.compile(r"Volume:\s*([\d.]+)\s*(\[MUTED\])?")


def parse_volume(output: str) -> tuple[float, bool] | None:
    match = _WPCTL_VOLUME_RE.search(output)
    if match is None:
        return None
    return (float(match.group(1)), match.group(2) is not None)


def _have_wpctl() -> bool:
    if sandbox.in_flatpak():
        return shutil.which("flatpak-spawn") is not None
    return shutil.which("wpctl") is not None


def wpctl_argv(*args: str, sandboxed: bool | None = None) -> list[str]:
    return [*sandbox.host_prefix(sandboxed), "wpctl", *args]


def _run_async(argv: list[str], on_done: Callable[[str | None], None]) -> None:
    def finish(result: AudioResult) -> None:
        on_done(result.output if result.availability is AudioAvailability.AVAILABLE else None)

    _run_async_result(argv, finish)


def run_wpctl(args: tuple[str, ...], on_done: Callable[[AudioResult], None]) -> None:
    """Run one mixer operation and report why it was unavailable or failed."""
    if not _have_wpctl():
        on_done(AudioResult(AudioAvailability.NOT_INSTALLED, error="wpctl is not installed"))
        return
    _run_async_result(wpctl_argv(*args), on_done)


def _run_async_result(argv: list[str], on_done: Callable[[AudioResult], None]) -> None:
    try:
        launcher = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
        )
        subprocess = launcher.spawnv(argv)
    except GLib.Error as error:
        availability = (
            AudioAvailability.HOST_EXECUTION_FAILED
            if sandbox.in_flatpak()
            else AudioAvailability.PROCESS_FAILED
        )
        on_done(AudioResult(availability, error=error.message))
        return

    def on_communicated(proc: Gio.Subprocess, result: Gio.AsyncResult) -> None:
        try:
            ok, stdout, _stderr = proc.communicate_utf8_finish(result)
        except GLib.Error as error:
            on_done(AudioResult(AudioAvailability.PROCESS_FAILED, error=error.message))
            return
        if not ok or not proc.get_successful():
            availability = (
                AudioAvailability.HOST_EXECUTION_FAILED
                if sandbox.in_flatpak()
                else AudioAvailability.PROCESS_FAILED
            )
            on_done(AudioResult(availability, error=_stderr or "wpctl failed"))
            return
        on_done(AudioResult(AudioAvailability.AVAILABLE, output=stdout or ""))

    subprocess.communicate_utf8_async(None, None, on_communicated)


def get_volume(on_result: Callable[[float, bool], None]) -> None:
    """Reports (volume 0..1, muted). Calls on_result(1.0, False) if the
    mixer can't be reached at all — a missing sink is a real-world top
    failure mode (§11) and shouldn't crash the OSD."""
    def finished(result: AudioResult, volume: float, muted: bool) -> None:
        if result.availability is AudioAvailability.AVAILABLE:
            on_result(volume, muted)
        else:
            on_result(1.0, False)

    get_volume_result(finished)


def get_volume_result(on_result: Callable[[AudioResult, float, bool], None]) -> None:
    def on_output(result: AudioResult) -> None:
        if result.availability is not AudioAvailability.AVAILABLE:
            on_result(result, 0.0, False)
            return
        parsed = parse_volume(result.output)
        if parsed is None:
            on_result(AudioResult(AudioAvailability.MALFORMED_OUTPUT), 0.0, False)
            return
        on_result(result, *parsed)

    run_wpctl(("get-volume", _SINK), on_output)


def adjust_volume(direction: int, on_done: Callable[[], None] | None = None) -> None:
    """direction: +1 or -1, one configured volume step."""
    sign = "+" if direction > 0 else "-"
    if _have_wpctl():
        argv = wpctl_argv("set-volume", _SINK, f"{_volume_step_percent}%{sign}")
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
        argv = wpctl_argv("set-volume", _SINK, f"{level:.3f}")
    else:
        if on_done is not None:
            on_done()
        return
    _run_async(argv, lambda _stdout: on_done() if on_done is not None else None)


def toggle_mute(on_done: Callable[[], None] | None = None) -> None:
    if _have_wpctl():
        argv = wpctl_argv("set-mute", _SINK, "toggle")
    else:
        if on_done is not None:
            on_done()
        return
    _run_async(argv, lambda _stdout: on_done() if on_done is not None else None)
