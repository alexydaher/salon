"""Minimal process launcher for the proof-of-concept.

Full lifecycle tracking (launching overlay, dual return detection, idle
inhibit, recents) is M5 in the implementation plan. This resolves a
LaunchSpec to argv, spawns it, and hands back the Gio.Subprocess so the
caller can track when it exits — needed because a gamepad's input bypasses
window focus entirely (unlike keyboard/mouse), so a native app like a game
client reads the same raw controller Salon does; Salon has to know when
that app is gone to stop fighting it for input.
"""

from __future__ import annotations

import shutil

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core import launchspec  # noqa: E402
from salon.core.model import LaunchSpec  # noqa: E402

_BROWSER_CANDIDATES = ("google-chrome-stable", "chromium", "chromium-browser")


def detect_browser() -> tuple[str, ...]:
    for name in _BROWSER_CANDIDATES:
        path = shutil.which(name)
        if path:
            return (path,)
    # Flatpak fallback per the brief's detection order.
    if shutil.which("flatpak"):
        return ("flatpak", "run", "com.google.Chrome")
    return ()


class LauncherService:
    def launch(self, spec: LaunchSpec) -> tuple[Gio.Subprocess | None, str | None]:
        """Spawn spec. Returns (subprocess_or_None, error_message_or_None).

        subprocess is None either on error, or for BUILTIN specs that don't
        spawn a process at all — check error first.
        """
        try:
            argv = launchspec.resolve(spec, browser_command=detect_browser())
        except Exception as exc:  # noqa: BLE001 — POC: surface any resolution failure
            return None, str(exc)
        if argv is None:
            return None, None
        try:
            # Silence the child's stdout/stderr — Chrome/GeForce NOW/etc. are
            # noisy on the console by default, and that's not Salon's log.
            flags = Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE
            subprocess = Gio.Subprocess.new(argv, flags)
        except GLib.Error as exc:
            return None, f"Couldn't start {spec.target}: {exc.message}"
        return subprocess, None
