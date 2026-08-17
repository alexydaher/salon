"""Minimal process launcher for the proof-of-concept.

Full lifecycle tracking (launching overlay, dual return detection, idle
inhibit, recents) is M5 in the implementation plan. This just resolves a
LaunchSpec to argv and spawns it.
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
    def launch(self, spec: LaunchSpec) -> str | None:
        """Spawn spec. Returns a human-readable error message, or None on success."""
        try:
            argv = launchspec.resolve(spec, browser_command=detect_browser())
        except Exception as exc:  # noqa: BLE001 — POC: surface any resolution failure
            return str(exc)
        if argv is None:
            return None
        try:
            Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE)
        except GLib.Error as exc:
            return f"Couldn't start {spec.target}: {exc.message}"
        return None
