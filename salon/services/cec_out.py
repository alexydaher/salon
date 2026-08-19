# SPDX-License-Identifier: GPL-3.0-or-later
"""HDMI-CEC output: wake the television and claim its input (§6.11).

Salon runs on a box that is usually powered on before the TV is, or is left
running while the TV sleeps. CEC lets it do the two things a set-top box is
expected to do: turn the screen on, and switch the input to itself. Without
it, "the launcher is running" and "the launcher is on screen" are different
states and the user has to reconcile them with a second remote.

Implemented by driving `cec-client` rather than binding libcec: the tool is
what distributions actually ship, it is optional, and shelling out to it
keeps CEC a soft dependency rather than a build-time one. Everything here
is a no-op when it isn't installed or when `cec-enabled` is off.

Nothing in this module has been exercised against real hardware — there is
no CEC adapter on the development machine and `cec-client` isn't installed.
The command strings are the documented ones; treat the wiring as untested.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

_CLIENT = "cec-client"
# -s: read commands from stdin and exit. -d 1: errors only, so a working run
# is silent. The trailing device number is the adapter, not the TV.
_ARGS = ("-s", "-d", "1")

# CEC opcodes as cec-client's own shorthand.
_POWER_ON_TV = "on 0"
_ACTIVE_SOURCE = "as"
_STANDBY_TV = "standby 0"


def available() -> bool:
    return shutil.which(_CLIENT) is not None


def _send(commands: str, on_done: Callable[[bool], None] | None = None) -> None:
    if not available():
        if on_done is not None:
            on_done(False)
        return
    try:
        process = Gio.Subprocess.new(
            [_CLIENT, *_ARGS],
            Gio.SubprocessFlags.STDIN_PIPE
            | Gio.SubprocessFlags.STDOUT_SILENCE
            | Gio.SubprocessFlags.STDERR_SILENCE,
        )
    except GLib.Error:
        if on_done is not None:
            on_done(False)
        return

    def finished(proc: Gio.Subprocess, result: Gio.AsyncResult) -> None:
        try:
            ok = proc.communicate_utf8_finish(result)[0]
        except GLib.Error:
            ok = False
        if on_done is not None:
            on_done(bool(ok))

    process.communicate_utf8_async(commands, None, finished)


def wake_display(on_done: Callable[[bool], None] | None = None) -> None:
    """Turn the TV on and switch it to this input, in that order — an
    active-source message to a sleeping television is ignored."""
    _send(f"{_POWER_ON_TV}\n{_ACTIVE_SOURCE}\n", on_done)


def standby(on_done: Callable[[bool], None] | None = None) -> None:
    """Put the television to sleep. Deliberately not called on Salon's own
    exit: leaving a session should not switch off the screen someone is
    about to use for something else."""
    _send(f"{_STANDBY_TV}\n", on_done)
