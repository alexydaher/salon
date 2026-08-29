# SPDX-License-Identifier: GPL-3.0-or-later
"""Play a short sound, so "which HDMI port?" has an answer in the room.

§8 calls the wrong output a top-three real-world failure on a machine under
a television, and Settings → Audio exists to fix it — but until now the
only way to find out whether a choice was right was to leave Settings and
launch something. That is a slow loop with four candidates.

Nothing here synthesises audio: it hands a file from the freedesktop sound
theme to whichever player is installed. Both halves are optional on a
minimal system, which is why the failure is reported rather than swallowed
— a test tone that silently does nothing is worse than no button, because
silence is also what a wrongly chosen output sounds like.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon.core import sandbox  # noqa: E402

# Short, unmistakably synthetic, and present in the freedesktop sound theme
# that every desktop spin ships. Ordered by how obviously each one is a
# test rather than a notification you might have caused by accident.
_SOUNDS = (
    "/usr/share/sounds/freedesktop/stereo/audio-test-signal.oga",
    "/usr/share/sounds/freedesktop/stereo/bell.oga",
    "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "/usr/share/sounds/alsa/Front_Center.wav",
)
_PLAYERS = ("pw-play", "paplay", "aplay")


def _sound_file() -> str:
    return next((path for path in _SOUNDS if Path(path).exists()), "")


def _player() -> str:
    return next((name for name in _PLAYERS if sandbox.host_which(name)), "")


def available() -> bool:
    return bool(_sound_file() and _player())


def unavailable_reason() -> str:
    if not _player():
        return "No sound player found (pw-play, paplay or aplay)"
    if not _sound_file():
        return "No system sound files are installed"
    return ""


def play(on_done: Callable[[str], None]) -> None:
    """Play the tone on the current default output. "" means it started.

    Spawned through `host_prefix` like every other command Salon runs, so
    inside the sandbox it plays on the host's audio graph — the same one
    the sink picker is choosing between.
    """
    problem = unavailable_reason()
    if problem:
        on_done(problem)
        return
    argv = [*sandbox.host_prefix(), _player(), _sound_file()]
    try:
        Gio.Subprocess.new(
            argv, Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE
        )
    except GLib.Error as exc:
        on_done(f"Couldn't play the test sound: {exc.message}")
        return
    on_done("")
