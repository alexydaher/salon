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
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core import sandbox  # noqa: E402
from salon.core.bindings import CEC, Bindings  # noqa: E402
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
    # Channel up/down: the pair of keys a television remote always has
    # and Salon has nothing else to do with. They jump a whole group.
    0x30: Action.NEXT_GROUP,
    0x31: Action.PREV_GROUP,
    0x41: Action.VOLUME_UP,
    0x42: Action.VOLUME_DOWN,
    0x43: Action.MUTE,
    # Transport keys. A television remote has these whether or not it has
    # anything else, and until now Salon answered none of them.
    0x44: Action.PLAY_PAUSE,
    0x46: Action.PLAY_PAUSE,
    0x45: Action.PLAY_PAUSE,
    # Power. Handled as "open the system menu" rather than as an immediate
    # suspend — see ui/home.py.
    0x40: Action.POWER,
    0x6B: Action.POWER,
}


def available(*, sandboxed: bool | None = None) -> bool:
    """Whether the TV remote can drive Salon on this machine.

    `host_which` rather than `shutil.which`: inside Flatpak the client runs
    on the host, so the sandbox's PATH is the wrong one to ask.
    """
    return sandbox.capabilities(sandboxed).cec and sandbox.host_which(_CLIENT, sandboxed)


def action_for_code(code: int, bindings: Bindings | None = None) -> Action | None:
    """The action a user-control code produces, user override first.

    The table below is the CEC 1.4 list, which is what the specification
    says. Which key on a given television's remote sends which code, or
    whether it sends one at all, is between that manufacturer and nobody —
    so the override layer is not a nicety here, it is the only way a remote
    the default does not fit can be made to work.
    """
    if bindings is not None:
        override = bindings.action_for(CEC, code)
        if override is not None:
            try:
                return Action(override) if override else None
            except ValueError:
                return None
    return _CODE_TO_ACTION.get(code)


def code_in_line(line: str) -> int | None:
    """The raw user-control code, for the settings screen's capture."""
    match = _KEY_RE.search(line)
    return int(match.group("code"), 16) if match else None


def parse_line(line: str, bindings: Bindings | None = None) -> Action | None:
    """Pure, so the keycode mapping is testable without an adapter."""
    code = code_in_line(line)
    return None if code is None else action_for_code(code, bindings)


class CecSource:
    """Reads `cec-client -m` and emits `Action`s.

    Holds the subprocess and the stream reader; the caller must keep a
    reference or the pipe is closed and the reader stops.
    """

    def __init__(
        self,
        on_action: Callable[[Action], None],
        bindings: Bindings | None = None,
        on_raw: Callable[[int], None] | None = None,
    ) -> None:
        self._on_action = on_action
        self._bindings = bindings
        self._on_raw = on_raw
        self._process: Gio.Subprocess | None = None
        self._reader: Gio.DataInputStream | None = None

    def set_bindings(self, bindings: Bindings) -> None:
        self._bindings = bindings

    @property
    def running(self) -> bool:
        return self._process is not None

    def start(self) -> bool:
        if self._process is not None or not available():
            return False
        try:
            process = Gio.Subprocess.new(
                [*sandbox.host_prefix(), _CLIENT, "-m", "-d", "8", "-o", "Salon"],
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
        code = code_in_line(raw)
        if code is not None and self._on_raw is not None:
            self._on_raw(code)
        action = parse_line(raw, self._bindings)
        if action is not None:
            self._on_action(action)
        self._read_next()
