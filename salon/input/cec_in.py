# SPDX-License-Identifier: GPL-3.0-or-later
"""HDMI-CEC input: the television's own remote as a Salon controller (§6.11).

A CEC-capable TV forwards its directional pad and OK/Back keys to whichever
input is active, which means the remote already in the room can drive Salon
without pairing anything. `cec-client -m` prints those key presses on
stdout; this reads them line by line and normalises them to `Action`, the
same currency the keyboard and gamepad sources produce.

Off unless `cec-enabled` is set, because starting `cec-client` claims the
CEC adapter and would fight anything else using it.

Untested against hardware: there is no CEC adapter on the development
machine and `cec-client` isn't installed. The keycode table below is from
the CEC 1.4 user-control-code list, which is what cec-client reports.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.input.actions import Action  # noqa: E402

_CLIENT = "cec-client"

# cec-client -m prints e.g. "key pressed: up (1)" — the number is the CEC
# user control code, which is stable where the label is localised.
_KEY_RE = re.compile(r"key pressed:\s*\S+\s*\((?P<code>[0-9a-fA-F]+)\)")

# CEC 1.4 user control codes.
_CODE_TO_ACTION = {
    0x01: Action.UP,
    0x02: Action.DOWN,
    0x03: Action.LEFT,
    0x04: Action.RIGHT,
    0x00: Action.OK,
    0x0D: Action.BACK,
    0x09: Action.MENU,
    # "Contents menu" and the blue function key are the two codes a TV
    # remote is most likely to have spare for a per-item options menu.
    0x0B: Action.OPTIONS,
    0x71: Action.OPTIONS,
    0x41: Action.VOLUME_UP,
    0x42: Action.VOLUME_DOWN,
    0x43: Action.MUTE,
}


def available() -> bool:
    return shutil.which(_CLIENT) is not None


def action_for_code(code: int) -> Action | None:
    return _CODE_TO_ACTION.get(code)


def parse_line(line: str) -> Action | None:
    """Pure, so the keycode mapping is testable without an adapter."""
    match = _KEY_RE.search(line)
    if match is None:
        return None
    return action_for_code(int(match.group("code"), 16))


class CecSource:
    """Reads `cec-client -m` and emits `Action`s.

    Holds the subprocess and the stream reader; the caller must keep a
    reference or the pipe is closed and the reader stops.
    """

    def __init__(self, on_action: Callable[[Action], None]) -> None:
        self._on_action = on_action
        self._process: Gio.Subprocess | None = None
        self._reader: Gio.DataInputStream | None = None

    @property
    def running(self) -> bool:
        return self._process is not None

    def start(self) -> bool:
        if self._process is not None or not available():
            return False
        try:
            process = Gio.Subprocess.new(
                [_CLIENT, "-m", "-d", "8", "-o", "Salon"],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except GLib.Error:
            return False
        self._process = process
        stream = process.get_stdout_pipe()
        if stream is None:
            self.stop()
            return False
        self._reader = Gio.DataInputStream.new(stream)
        self._read_next()
        return True

    def stop(self) -> None:
        if self._process is not None:
            self._process.force_exit()
            self._process = None
        self._reader = None

    def _read_next(self) -> None:
        if self._reader is None:
            return
        self._reader.read_line_async(GLib.PRIORITY_DEFAULT, None, self._on_line)

    def _on_line(self, reader: Gio.DataInputStream, result: Gio.AsyncResult) -> None:
        try:
            raw = reader.read_line_finish_utf8(result)[0]
        except GLib.Error:
            self.stop()
            return
        if raw is None:  # EOF: cec-client exited
            self.stop()
            return
        action = parse_line(raw)
        if action is not None:
            self._on_action(action)
        self._read_next()
