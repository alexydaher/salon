# SPDX-License-Identifier: GPL-3.0-or-later
"""Compatibility facade for launching and child-window lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk  # noqa: E402

from salon.core.model import Tile  # noqa: E402
from salon.services.launcher_execution import LauncherExecution  # noqa: E402
from salon.services.launcher_lifecycle import ChildWindowLifecycle  # noqa: E402
from salon.services.launcher_shared import (  # noqa: E402
    _DEFAULT_IDLE_INHIBIT_SECONDS,
    BrowserAvailability,
    BrowserResolution,
    detect_browser,
    parse_browser_command,
    preflight_browser,
)

__all__ = [
    "BrowserAvailability",
    "BrowserResolution",
    "LauncherService",
    "detect_browser",
    "parse_browser_command",
    "preflight_browser",
]


@dataclass(frozen=True, slots=True)
class RunningApp:
    id: str
    title: str
    front: bool
    closeable: bool


@dataclass(slots=True)
class _RunningChild:
    tile: Tile
    subprocess: Gio.Subprocess | None = None
    pid: int | None = None


class LauncherService:
    def __init__(
        self,
        application: Gtk.Application,
        idle_inhibit_seconds: int = _DEFAULT_IDLE_INHIBIT_SECONDS,
        browser_scale_factor: float = 1.0,
        browser_command: Callable[[], tuple[str, ...]] | None = None,
        browser_extra_flags: Callable[[], tuple[str, ...]] | None = None,
    ) -> None:
        self._application = application
        self._idle_inhibit_seconds = idle_inhibit_seconds
        # Set from the du scale (§6.3) so a 4K TV doesn't get web UI sized
        # for a desktop monitor; ui/home.py updates it if the window moves
        # to a monitor with a different height.
        self.browser_scale_factor = browser_scale_factor
        self._browser_command = browser_command or detect_browser
        self._browser_extra_flags = browser_extra_flags or (lambda: ())

        self._subprocess: Gio.Subprocess | None = None
        # Set for .desktop launches, where there is no Gio.Subprocess to
        # signal. Frequently a systemd scope or a D-Bus activation stub
        # rather than the app itself (§11), so closing by pid is best-effort
        # and says so — see close_child().
        self._child_pid: int | None = None
        self._launching_tile: Tile | None = None
        self._awaiting_child_focus = False
        self._awaiting_return = False
        self._launched_at_ms = 0
        # More than one launched application may remain alive. The three
        # fields above still describe the window currently covering Salon;
        # this registry owns every process returned to the background.
        self._children: dict[str, _RunningChild] = {}
        self._keep_running_on_return = False
        self._closing_current = False

        self._overlay_timeout_id: int | None = None
        self._watch_id: int | None = None
        self._return_debounce_id: int | None = None
        self._inhibit_cookie: int | None = None
        self._inhibit_release_id: int | None = None

        # Assign these from the UI layer; all optional, all fired at most
        # once per launch (except on_error, which doesn't start a launch).
        self.on_launch_started: Callable[[Tile], None] | None = None
        self.on_child_focused: Callable[[], None] | None = None
        self.on_launch_timed_out: Callable[[], None] | None = None
        self.on_returned: Callable[[], None] | None = None
        self.on_error: Callable[[str], None] | None = None
        self.on_running_changed: Callable[[], None] | None = None

        self._execution = LauncherExecution(self)
        self._lifecycle = ChildWindowLifecycle(self)

    def launch(self, tile: Tile) -> None:
        self._execution.launch(tile)

    def cancel(self) -> None:
        self._execution.cancel()

    def close_child(self) -> bool:
        return self._lifecycle.close_child()

    def return_to_salon(self) -> bool:
        """Mark the foreground child as backgrounded, without ending it.

        The compositor switch itself is injected by the UI because the
        launcher deliberately does not own the RemoteDesktop grant. This
        method changes lifecycle semantics for the focus edge that follows.
        """
        if not self.has_child:
            return False
        self._keep_running_on_return = True
        self._closing_current = False
        return True

    def close_app(self, app_id: str) -> bool:
        if app_id == self.front_child_id:
            return self.close_child()
        return self._lifecycle.close_background(app_id)

    def notify_window_active(self, is_active: bool) -> None:
        self._lifecycle.notify_window_active(is_active)

    # Component-to-component calls are deliberately enumerated here. This
    # keeps the facade's supported surface reviewable without changing the
    # state owner during this migration stage.
    def _start_idle_inhibit(self) -> None:
        self._lifecycle._start_idle_inhibit()  # noqa: SLF001

    def _on_overlay_timeout(self) -> bool:
        return self._lifecycle._on_overlay_timeout()  # noqa: SLF001

    def _on_subprocess_exited(self, proc: Gio.Subprocess, result: Gio.AsyncResult) -> None:
        self._lifecycle._on_subprocess_exited(proc, result)  # noqa: SLF001

    def _finish_return(self) -> None:
        self._lifecycle._finish_return()  # noqa: SLF001

    def _register_current(self, tile: Tile) -> None:
        self._children[tile.id] = _RunningChild(tile, self._subprocess, self._child_pid)
        self._keep_running_on_return = False
        self._closing_current = False
        self._notify_running_changed()

    def _remove_process(self, proc: Gio.Subprocess) -> None:
        removed = [key for key, child in self._children.items() if child.subprocess is proc]
        for key in removed:
            self._children.pop(key, None)
        if removed:
            self._notify_running_changed()

    def _remove_current_record(self) -> None:
        if self._launching_tile is not None:
            self._children.pop(self._launching_tile.id, None)
            self._notify_running_changed()

    def _forget_current_pid(self, pid: int) -> None:
        """Stop advertising a dead desktop-launch handle as closeable."""
        child = self._children.get(self.front_child_id)
        if child is None or child.pid != pid:
            return
        child.pid = None
        self._notify_running_changed()

    def _notify_running_changed(self) -> None:
        if self.on_running_changed is not None:
            self.on_running_changed()

    @property
    def child_title(self) -> str | None:
        """The tile whose child is in front, or None if nothing is out
        there. The UI names it in the 'return to Salon' confirmation."""
        return self._launching_tile.title if self._launching_tile is not None else None

    @property
    def front_child_id(self) -> str:
        return self._launching_tile.id if self.has_child and self._launching_tile else ""

    @property
    def running_apps(self) -> tuple[RunningApp, ...]:
        front_id = self.front_child_id
        return tuple(
            RunningApp(
                id=child.tile.id,
                title=child.tile.title,
                front=child.tile.id == front_id,
                closeable=child.subprocess is not None or child.pid is not None,
            )
            for child in self._children.values()
        )

    @property
    def is_launching(self) -> bool:
        """True only during phase 1 (awaiting child focus) — the window
        where BACK should cancel the attempt rather than do nothing."""
        return self._awaiting_child_focus

    @property
    def has_child(self) -> bool:
        """True from the moment something is spawned until return is
        confirmed, across *both* phases.

        The UI's own `_child_active` flag is set from `on_child_focused`,
        which only fires if the window-activity edge is seen — and that edge
        does not exist when Salon's window was already inactive at launch
        time, which is exactly the case when the phone launches a tile while
        another app is in front. MENU asking this instead means "get me out"
        stays true whether or not the focus signal ever arrived.
        """
        return self._awaiting_child_focus or self._awaiting_return

    def abandon(self) -> None:
        """Stop tracking a child Salon has no handle on.

        `close_child()` returning False means the pid was a wrapper that had
        already exited, so nothing here will ever see that app go away.
        Holding `has_child` True on its account would make MENU answer "I
        can't close that" forever, including long after the user closed the
        app themselves.
        """
        self._finish_return()
