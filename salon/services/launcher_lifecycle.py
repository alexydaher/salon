# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused launcher responsibility."""

from salon.services.component import ServiceComponent
from salon.services.launcher_shared import *


class ChildWindowLifecycle(ServiceComponent):
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
