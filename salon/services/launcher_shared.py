# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F401
"""Process lifecycle (§6.4): launch, dual return detection, bounded idle
inhibit. The UI never launches anything directly — it calls launch() and
reacts to these callbacks; LauncherService owns the child's whole lifetime.

Two phases after a launch, tracked separately because they're genuinely
different waits:

  1. "awaiting child focus" — Salon is still showing the launching overlay,
     waiting for the new process's window to actually appear and take
     focus (Salon's own window going *inactive* is that signal). A 12s
     timeout here means something's stuck, not that we're back.
  2. "awaiting return" — the child has focus and Salon is dormant
     underneath it. Return is detected two ways per §6.4: Salon's window
     going *active* again (primary — debounced so a focus flicker mid
     launch doesn't count) or the child process actually exiting
     (secondary — often the only signal that fires at all, since GNOME
     launches desktop apps into transient systemd scopes and Flatpak forks
     and detaches, so the PID this module gets back frequently belongs to
     a wrapper that's already gone).
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from salon.core import launchspec, sandbox  # noqa: E402
from salon.core.model import LaunchKind, Tile  # noqa: E402

_BROWSER_CANDIDATES = ("google-chrome-stable", "chromium", "chromium-browser")

_OVERLAY_TIMEOUT_SECONDS = 12
_RETURN_DEBOUNCE_MS = 400
_DEFAULT_IDLE_INHIBIT_SECONDS = 90

# A wrapper process that exits this fast has not run anything the user can
# see: `flatpak run` hands off to the portal and exits, and GNOME launches
# desktop apps into transient systemd scopes whose PID is gone immediately
# (§6.4, §11). Treating that as "we're back" tears the launching overlay
# down a fraction of a second after it appears and fires the return handler
# while the app is still starting, so an exit inside this window is ignored
# and Salon keeps waiting for the window-activity signal instead.
_WRAPPER_EXIT_GRACE_MS = 2500

# How long a child gets to shut down cleanly after SIGTERM before it is
# killed outright. Chrome writes its session state on the way out, so the
# polite signal is worth waiting for — but not forever, because the whole
# point of the button that sends it is that the user is stuck.
_CLOSE_GRACE_SECONDS = 4

# How often a closing .desktop child's pid is checked for having actually
# gone. Fast enough that MENU feels like one press rather than two.
_CLOSE_POLL_MS = 400


class BrowserAvailability(StrEnum):
    AVAILABLE = "available"
    NOT_INSTALLED = "not-installed"
    HOST_EXECUTION_FAILED = "host-execution-failed"


@dataclass(frozen=True, slots=True)
class BrowserResolution:
    availability: BrowserAvailability
    argv: tuple[str, ...] = ()
    error: str = ""


def parse_browser_command(value: str) -> tuple[str, ...]:
    """Parse a user command without invoking a shell."""
    try:
        return tuple(shlex.split(value))
    except ValueError as exc:
        raise ValueError(f"Invalid browser command: {exc}") from exc


def detect_browser(*, sandboxed: bool | None = None) -> tuple[str, ...]:
    if sandboxed is None:
        sandboxed = sandbox.in_flatpak()
    if sandboxed:
        # This argv is itself run through flatpak-spawn --host. The host's
        # Flatpak installation is the only browser source we can name
        # without pretending the sandbox can inspect the host PATH.
        return ("flatpak", "run", "com.google.Chrome")
    for name in _BROWSER_CANDIDATES:
        path = shutil.which(name)
        if path:
            return (path,)
    # Flatpak fallback per the brief's detection order.
    if shutil.which("flatpak"):
        return ("flatpak", "run", "com.google.Chrome")
    return ()


def resolve_browser(*, sandboxed: bool | None = None) -> BrowserResolution:
    """Probe browser availability, including the host side of a Flatpak."""
    if sandboxed is None:
        sandboxed = sandbox.in_flatpak()
    if not sandboxed:
        argv = detect_browser(sandboxed=False)
        availability = BrowserAvailability.AVAILABLE if argv else BrowserAvailability.NOT_INSTALLED
        return BrowserResolution(availability, argv)
    if shutil.which("flatpak-spawn") is None:
        return BrowserResolution(
            BrowserAvailability.HOST_EXECUTION_FAILED,
            error="flatpak-spawn is not available",
        )
    try:
        for candidate in _BROWSER_CANDIDATES:
            result = subprocess.run(
                [*sandbox.HOST_SPAWN, "which", candidate],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return BrowserResolution(BrowserAvailability.AVAILABLE, (result.stdout.strip(),))
        result = subprocess.run(
            [*sandbox.HOST_SPAWN, "flatpak", "info", "com.google.Chrome"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return BrowserResolution(BrowserAvailability.HOST_EXECUTION_FAILED, error=str(error))
    if result.returncode == 0:
        return BrowserResolution(
            BrowserAvailability.AVAILABLE, ("flatpak", "run", "com.google.Chrome")
        )
    return BrowserResolution(BrowserAvailability.NOT_INSTALLED)


def preflight_browser(
    on_result: Callable[[BrowserResolution], None], *, sandboxed: bool | None = None
) -> None:
    """Resolve without blocking GTK's main loop and return on that loop."""

    def worker() -> None:
        result = resolve_browser(sandboxed=sandboxed)
        GLib.idle_add(on_result, result)

    threading.Thread(target=worker, name="salon-browser-preflight", daemon=True).start()


__all__ = [name for name in globals() if not name.startswith("__")]
