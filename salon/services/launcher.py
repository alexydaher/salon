# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Compatibility facade for launching and child-window lifecycle."""

from __future__ import annotations

from typing import Any

from salon.services.component import component_attribute
from salon.services.launcher_execution import LauncherExecution
from salon.services.launcher_lifecycle import ChildWindowLifecycle
from salon.services.launcher_shared import *


class LauncherService:
    def __init__(
        self,
        application: Gtk.Application,
        idle_inhibit_seconds: int = _DEFAULT_IDLE_INHIBIT_SECONDS,
        browser_scale_factor: float = 1.0,
    ) -> None:
        self._application = application
        self._idle_inhibit_seconds = idle_inhibit_seconds
        # Set from the du scale (§6.3) so a 4K TV doesn't get web UI sized
        # for a desktop monitor; ui/home.py updates it if the window moves
        # to a monitor with a different height.
        self.browser_scale_factor = browser_scale_factor

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

        self._components = (LauncherExecution(self), ChildWindowLifecycle(self))

    def __getattr__(self, name: str) -> Any:
        return component_attribute(self._components, name)

    @property
    def child_title(self) -> str | None:
        """The tile whose child is in front, or None if nothing is out
        there. The UI names it in the 'return to Salon' confirmation."""
        return self._launching_tile.title if self._launching_tile is not None else None

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
