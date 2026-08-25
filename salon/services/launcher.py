# SPDX-License-Identifier: GPL-3.0-or-later
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
import shutil
import signal
from collections.abc import Callable

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

    def launch(self, tile: Tile) -> None:
        # Gio.DesktopAppInfo can only see entries inside the sandbox, so
        # under Flatpak the .desktop path has to go out through the host
        # spawn portal like everything else.
        host = sandbox.host_prefix()
        if not host and tile.launch.kind is LaunchKind.DESKTOP and self._launch_desktop(tile):
            return
        try:
            argv = launchspec.resolve(
                tile.launch,
                browser_command=detect_browser(),
                scale_factor=self.browser_scale_factor,
                session_type=os.environ.get("XDG_SESSION_TYPE", ""),
                host_prefix=host,
            )
        except Exception as exc:  # noqa: BLE001 — surface any resolution failure to the user
            if self.on_error is not None:
                # Always named: a message with no subject leaves the user
                # guessing which of the tiles on screen it was about.
                self.on_error(f"Couldn't start {tile.title}. {exc}")
            return
        if argv is None:
            return  # BUILTIN: nothing to spawn, nothing to track

        try:
            # Silence the child's stdout/stderr — Chrome/GeForce NOW/etc.
            # are noisy on the console by default, and that's not Salon's
            # log.
            flags = Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE
            subprocess = Gio.Subprocess.new(argv, flags)
        except GLib.Error as exc:
            if self.on_error is not None:
                self.on_error(f"Couldn't start {tile.title}: {exc.message}")
            return

        self._subprocess = subprocess
        self._child_pid = None
        self._launching_tile = tile
        self._awaiting_child_focus = True
        self._awaiting_return = True
        self._launched_at_ms = GLib.get_monotonic_time() // 1000
        self._start_idle_inhibit()

        if self.on_launch_started is not None:
            self.on_launch_started(tile)
        self._overlay_timeout_id = GLib.timeout_add_seconds(
            _OVERLAY_TIMEOUT_SECONDS, self._on_overlay_timeout
        )
        subprocess.wait_async(None, self._on_subprocess_exited)

    def _launch_desktop(self, tile: Tile) -> bool:
        """Launch a .desktop entry through Gio, not by exec'ing its Exec=.

        §6.3 asks for Gio.DesktopAppInfo specifically, and the reason shows
        up on a real system: an entry marked DBusActivatable has to be
        started over D-Bus rather than spawned, GNOME wants desktop apps in
        their own transient systemd scope, and startup notification only
        happens on this path. Parsing Exec= by hand — which is what this did
        before — bypasses all three.

        Returns False if there's no such entry, so the caller can fall back
        to core.launchspec's argv resolution and surface a real error.
        """
        target = tile.launch.target
        name = target if target.endswith(".desktop") else f"{target}.desktop"
        app_info = Gio.DesktopAppInfo.new(name)
        if app_info is None:
            return False

        context = Gdk.Display.get_default().get_app_launch_context()
        # Cleared before the call, not after: launch_uris_as_manager
        # delivers the new pid synchronously through _on_desktop_pid.
        self._child_pid = None
        try:
            app_info.launch_uris_as_manager(
                [],
                context,
                GLib.SpawnFlags.SEARCH_PATH,
                None,
                None,
                self._on_desktop_pid,
                None,
            )
        except GLib.Error as exc:
            if self.on_error is not None:
                self.on_error(f"Couldn't start {tile.title}: {exc.message}")
            return True

        # No Gio.Subprocess to watch here: the PID this hands back belongs to
        # a systemd scope or a D-Bus activation stub and is routinely gone
        # immediately (§11), so return detection rests entirely on the
        # window-activity signal, which §6.4 expects to carry it anyway.
        # _child_pid is *not* cleared here — launch_uris_as_manager has
        # already delivered it through _on_desktop_pid by this point.
        self._subprocess = None
        self._launching_tile = tile
        self._awaiting_child_focus = True
        self._awaiting_return = True
        self._launched_at_ms = GLib.get_monotonic_time() // 1000
        self._start_idle_inhibit()
        if self.on_launch_started is not None:
            self.on_launch_started(tile)
        self._overlay_timeout_id = GLib.timeout_add_seconds(
            _OVERLAY_TIMEOUT_SECONDS, self._on_overlay_timeout
        )
        return True

    def _on_desktop_pid(
        self, app_info: Gio.AppInfo, pid: int, user_data: object = None
    ) -> None:
        """Required by launch_uris_as_manager.

        Return detection still doesn't use this pid — see above — but
        close_child() does, as its only handle on a .desktop launch. It is
        routinely a wrapper that has already exited, which is why closing
        that way is attempted and reported rather than assumed to work.
        """
        self._child_pid = pid or None

    def cancel(self) -> None:
        """BACK during the launching overlay: give up waiting and force the
        child to exit. Only valid during phase 1 — see is_launching."""
        if not self._awaiting_child_focus:
            return
        if self._subprocess is not None:
            self._subprocess.force_exit()
        self._finish_return()

    def close_child(self) -> bool:
        """Shut the launched app down and come back to Salon.

        This is the *only* way off a fullscreen browser tile with a
        controller. Wayland forbids a client raising itself, so Salon cannot
        put its own window back in front while Netflix is up; what it can do
        is end the process it started, at which point the compositor hands
        focus back on its own. Nothing else in the session has to cooperate.

        SIGTERM first so Chrome closes its profile cleanly, then SIGKILL
        after a grace period if it is still there. Returns False when there
        is no handle to act on — a .desktop launch whose pid was a wrapper —
        so the caller can say so instead of leaving the user pressing a
        button that silently does nothing.
        """
        if self._subprocess is not None:
            self._subprocess.send_signal(signal.SIGTERM)
            proc = self._subprocess
            GLib.timeout_add_seconds(_CLOSE_GRACE_SECONDS, lambda: self._force_exit(proc))
            return True
        if self._child_pid is not None:
            try:
                os.kill(self._child_pid, signal.SIGTERM)
            except OSError:
                # Already gone, or it belonged to a wrapper that exited the
                # moment it handed off. Either way there is nothing here to
                # close, and the app on screen is not ours to end.
                self._child_pid = None
                return False
            pid = self._child_pid
            GLib.timeout_add_seconds(_CLOSE_GRACE_SECONDS, lambda: self._force_kill(pid))
            # And watch it go. A .desktop launch has no Gio.Subprocess to
            # wait on, so the only other thing that would ever notice this
            # app ending is Salon's window going active again — which does
            # not happen if it never went inactive in the first place.
            # Without this the state machine stayed convinced the app was
            # still out there: MENU closed it, and then every following MENU
            # tried to close it again instead of opening the system menu.
            # Measured, with a real child: it took two presses.
            self._watch_id = GLib.timeout_add(_CLOSE_POLL_MS, lambda: self._poll_closed(pid))
            return True
        return False

    def _poll_closed(self, pid: int) -> bool:
        if pid != self._child_pid:
            self._watch_id = None
            return GLib.SOURCE_REMOVE
        try:
            os.kill(pid, 0)
        except OSError:
            self._watch_id = None
            self._finish_return()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _force_exit(self, proc: Gio.Subprocess) -> bool:
        if proc is self._subprocess:
            proc.force_exit()
        return GLib.SOURCE_REMOVE

    def _force_kill(self, pid: int) -> bool:
        if pid == self._child_pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass  # it took the polite signal, which is what we wanted
        return GLib.SOURCE_REMOVE

    def notify_window_active(self, is_active: bool) -> None:
        """Call this from the window's notify::is-active handler."""
        if self._awaiting_child_focus:
            if not is_active:
                self._child_took_focus()
            return
        if not self._awaiting_return:
            return
        if self._return_debounce_id is not None:
            GLib.source_remove(self._return_debounce_id)
            self._return_debounce_id = None
        if is_active:
            self._return_debounce_id = GLib.timeout_add(_RETURN_DEBOUNCE_MS, self._confirm_return)

    def _child_took_focus(self) -> None:
        self._awaiting_child_focus = False
        self._clear_overlay_timeout()
        if self.on_child_focused is not None:
            self.on_child_focused()

    def _on_overlay_timeout(self) -> bool:
        """Twelve seconds without the window-activity edge. Two different
        things look like this, and they need opposite answers.

        If Salon still has focus, nothing is covering it: the app is slow or
        it never started, the overlay says so, and BACK gives up. That is
        the case this timeout was written for.

        If Salon does *not* have focus, something is in front of it and the
        edge was simply never generated — a window that maps while Salon is
        already inactive produces no notify at all, which is what happens
        every time the phone opens a tile from behind another app. Waiting
        longer cannot help; the launch has plainly succeeded. Treating it as
        arrival is what keeps MENU meaning "close this and come back".
        """
        self._overlay_timeout_id = None
        if not self._awaiting_child_focus:
            return GLib.SOURCE_REMOVE
        if not self._salon_has_focus():
            self._child_took_focus()
            return GLib.SOURCE_REMOVE
        if self.on_launch_timed_out is not None:
            self.on_launch_timed_out()
        return GLib.SOURCE_REMOVE

    def _salon_has_focus(self) -> bool:
        return any(window.get_property("is-active") for window in self._application.get_windows())

    def _clear_overlay_timeout(self) -> None:
        if self._overlay_timeout_id is not None:
            GLib.source_remove(self._overlay_timeout_id)
            self._overlay_timeout_id = None

    def _confirm_return(self) -> bool:
        self._return_debounce_id = None
        self._finish_return()
        return GLib.SOURCE_REMOVE

    def _on_subprocess_exited(self, proc: Gio.Subprocess, result: Gio.AsyncResult) -> None:
        try:
            proc.wait_finish(result)
        except GLib.Error:
            pass
        if proc is not self._subprocess:
            return  # a cancelled or superseded launch; its return already fired
        elapsed_ms = GLib.get_monotonic_time() // 1000 - self._launched_at_ms
        if self._awaiting_child_focus and elapsed_ms < _WRAPPER_EXIT_GRACE_MS:
            # Almost certainly the wrapper, not the app — keep waiting for
            # the window-activity signal, which §6.4 expects to carry most
            # of the weight anyway. The 12s overlay timeout still bounds it.
            return
        self._finish_return()

    def _finish_return(self) -> None:
        if not self._awaiting_return and not self._awaiting_child_focus:
            return
        self._awaiting_return = False
        self._awaiting_child_focus = False
        self._clear_overlay_timeout()
        if self._watch_id is not None:
            GLib.source_remove(self._watch_id)
            self._watch_id = None
        if self._return_debounce_id is not None:
            GLib.source_remove(self._return_debounce_id)
            self._return_debounce_id = None
        self._subprocess = None
        self._child_pid = None
        self._launching_tile = None
        # The inhibit exists to cover the gap between launching and the
        # child issuing its own; once the user is back in Salon there's
        # nothing left to cover, and holding it until the timer expires
        # would keep the screen awake in front of an idle launcher.
        self._release_idle_inhibit()
        if self.on_returned is not None:
            self.on_returned()

    def _start_idle_inhibit(self) -> None:
        if self._inhibit_cookie is not None or self._idle_inhibit_seconds <= 0:
            return
        self._inhibit_cookie = self._application.inhibit(
            None, Gtk.ApplicationInhibitFlags.IDLE, "Salon: recently launched content"
        )
        self._inhibit_release_id = GLib.timeout_add_seconds(
            self._idle_inhibit_seconds, self._on_inhibit_timeout
        )

    def _on_inhibit_timeout(self) -> bool:
        # Clear the id first: the source is mid-dispatch, so
        # _release_idle_inhibit must not try to remove it as well.
        self._inhibit_release_id = None
        self._release_idle_inhibit()
        return GLib.SOURCE_REMOVE

    def _release_idle_inhibit(self) -> None:
        if self._inhibit_release_id is not None:
            GLib.source_remove(self._inhibit_release_id)
            self._inhibit_release_id = None
        if self._inhibit_cookie is not None:
            self._application.uninhibit(self._inhibit_cookie)
            self._inhibit_cookie = None
