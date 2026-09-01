# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused launcher responsibility."""

import os
import signal

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from salon.services.component import ServiceComponent  # noqa: E402
from salon.services.launcher_shared import (  # noqa: E402
    _CLOSE_GRACE_SECONDS,
    _CLOSE_POLL_MS,
    _RETURN_DEBOUNCE_MS,
    _WRAPPER_EXIT_GRACE_MS,
)


class ChildWindowLifecycle(ServiceComponent):
    def close_child(self) -> bool:
        """SIGTERM the foreground child, then force it after a grace period."""
        self._owner._keep_running_on_return = False
        self._owner._closing_current = True
        if self._owner._subprocess is not None:
            self._owner._subprocess.send_signal(signal.SIGTERM)
            proc = self._owner._subprocess
            GLib.timeout_add_seconds(_CLOSE_GRACE_SECONDS, lambda: self._force_exit(proc))
            return True
        if self._owner._child_pid is not None:
            pid = self._owner._child_pid
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                # Already gone, or it belonged to a wrapper that exited the
                # moment it handed off. Either way there is nothing here to
                # close, and the app on screen is not ours to end.
                self._owner._child_pid = None
                self._owner._forget_current_pid(pid)
                return False
            GLib.timeout_add_seconds(_CLOSE_GRACE_SECONDS, lambda: self._force_kill(pid))
            # A .desktop launch has no Gio.Subprocess to watch.
            self._owner._watch_id = GLib.timeout_add(_CLOSE_POLL_MS, lambda: self._poll_closed(pid))
            return True
        return False

    def close_background(self, app_id: str) -> bool:
        child = self._owner._children.get(app_id)
        if child is None:
            return False
        if child.subprocess is not None:
            child.subprocess.send_signal(signal.SIGTERM)
            proc = child.subprocess
            GLib.timeout_add_seconds(_CLOSE_GRACE_SECONDS, lambda: self._force_any(proc))
            return True
        if child.pid is None:
            return False
        try:
            os.kill(child.pid, signal.SIGTERM)
        except OSError:
            self._owner._children.pop(app_id, None)
            self._owner._notify_running_changed()
            return False
        pid = child.pid
        GLib.timeout_add_seconds(_CLOSE_GRACE_SECONDS, lambda: self._force_any_pid(pid))
        GLib.timeout_add(_CLOSE_POLL_MS, lambda: self._poll_background(app_id, pid))
        return True

    @staticmethod
    def _force_any(proc: Gio.Subprocess) -> bool:
        try:
            proc.force_exit()
        except GLib.Error:
            pass
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _force_any_pid(pid: int) -> bool:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        return GLib.SOURCE_REMOVE

    def _poll_background(self, app_id: str, pid: int) -> bool:
        child = self._owner._children.get(app_id)
        if child is None or child.pid != pid:
            return GLib.SOURCE_REMOVE
        try:
            os.kill(pid, 0)
        except OSError:
            self._owner._children.pop(app_id, None)
            self._owner._notify_running_changed()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _poll_closed(self, pid: int) -> bool:
        if pid != self._owner._child_pid:
            self._owner._watch_id = None
            return GLib.SOURCE_REMOVE
        try:
            os.kill(pid, 0)
        except OSError:
            self._owner._watch_id = None
            self._finish_return()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _force_exit(self, proc: Gio.Subprocess) -> bool:
        if proc is self._owner._subprocess:
            proc.force_exit()
        return GLib.SOURCE_REMOVE

    def _force_kill(self, pid: int) -> bool:
        if pid == self._owner._child_pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass  # it took the polite signal, which is what we wanted
        return GLib.SOURCE_REMOVE

    def notify_window_active(self, is_active: bool) -> None:
        """Call this from the window's notify::is-active handler."""
        if self._owner._awaiting_child_focus:
            if not is_active:
                self._child_took_focus()
            return
        if not self._owner._awaiting_return:
            return
        if self._owner._return_debounce_id is not None:
            GLib.source_remove(self._owner._return_debounce_id)
            self._owner._return_debounce_id = None
        if is_active:
            # Focus can return because the user switched windows rather than
            # because the process ended. That is multitasking, not an exit:
            # keep the owned process in the running-app registry unless an
            # explicit Close is already in progress.
            if not self._owner._closing_current:
                self._owner._keep_running_on_return = True
            self._owner._return_debounce_id = GLib.timeout_add(
                _RETURN_DEBOUNCE_MS, self._confirm_return
            )

    def _child_took_focus(self) -> None:
        self._owner._awaiting_child_focus = False
        self._clear_overlay_timeout()
        if self._owner.on_child_focused is not None:
            self._owner.on_child_focused()

    def _on_overlay_timeout(self) -> bool:
        """Resolve a missing focus edge as success or a stalled launch."""
        self._owner._overlay_timeout_id = None
        if not self._owner._awaiting_child_focus:
            return GLib.SOURCE_REMOVE
        if not self._salon_has_focus():
            self._child_took_focus()
            return GLib.SOURCE_REMOVE
        if self._owner.on_launch_timed_out is not None:
            self._owner.on_launch_timed_out()
        return GLib.SOURCE_REMOVE

    def _salon_has_focus(self) -> bool:
        return any(
            window.get_property("is-active") for window in self._owner._application.get_windows()
        )

    def _clear_overlay_timeout(self) -> None:
        if self._owner._overlay_timeout_id is not None:
            GLib.source_remove(self._owner._overlay_timeout_id)
            self._owner._overlay_timeout_id = None

    def _confirm_return(self) -> bool:
        self._owner._return_debounce_id = None
        self._finish_return()
        return GLib.SOURCE_REMOVE

    def _on_subprocess_exited(self, proc: Gio.Subprocess, result: Gio.AsyncResult) -> None:
        try:
            proc.wait_finish(result)
        except GLib.Error:
            pass
        if proc is not self._owner._subprocess:
            self._owner._remove_process(proc)
            return
        elapsed_ms = GLib.get_monotonic_time() // 1000 - self._owner._launched_at_ms
        if self._owner._awaiting_child_focus and elapsed_ms < _WRAPPER_EXIT_GRACE_MS:
            # Almost certainly the wrapper, not the app — keep waiting for
            # the window-activity signal, which §6.4 expects to carry most
            # of the weight anyway. The 12s overlay timeout still bounds it.
            return
        self._owner._remove_process(proc)
        self._finish_return()

    def _finish_return(self) -> None:
        if not self._owner._awaiting_return and not self._owner._awaiting_child_focus:
            return
        self._owner._awaiting_return = False
        self._owner._awaiting_child_focus = False
        self._clear_overlay_timeout()
        if self._owner._watch_id is not None:
            GLib.source_remove(self._owner._watch_id)
            self._owner._watch_id = None
        if self._owner._return_debounce_id is not None:
            GLib.source_remove(self._owner._return_debounce_id)
            self._owner._return_debounce_id = None
        keep_running = self._owner._keep_running_on_return and not self._owner._closing_current
        if not keep_running:
            self._owner._remove_current_record()
        self._owner._subprocess = None
        self._owner._child_pid = None
        self._owner._launching_tile = None
        self._owner._keep_running_on_return = False
        self._owner._closing_current = False
        # The inhibit exists to cover the gap between launching and the
        # child issuing its own; once the user is back in Salon there's
        # nothing left to cover, and holding it until the timer expires
        # would keep the screen awake in front of an idle launcher.
        self._release_idle_inhibit()
        if self._owner.on_returned is not None:
            self._owner.on_returned()

    def _start_idle_inhibit(self) -> None:
        if self._owner._inhibit_cookie is not None or self._owner._idle_inhibit_seconds <= 0:
            return
        self._owner._inhibit_cookie = self._owner._application.inhibit(
            None, Gtk.ApplicationInhibitFlags.IDLE, "Salon: recently launched content"
        )
        self._owner._inhibit_release_id = GLib.timeout_add_seconds(
            self._owner._idle_inhibit_seconds, self._on_inhibit_timeout
        )

    def _on_inhibit_timeout(self) -> bool:
        # Clear the id first: the source is mid-dispatch, so
        # _release_idle_inhibit must not try to remove it as well.
        self._owner._inhibit_release_id = None
        self._release_idle_inhibit()
        return GLib.SOURCE_REMOVE

    def _release_idle_inhibit(self) -> None:
        if self._owner._inhibit_release_id is not None:
            GLib.source_remove(self._owner._inhibit_release_id)
            self._owner._inhibit_release_id = None
        if self._owner._inhibit_cookie is not None:
            self._owner._application.uninhibit(self._owner._inhibit_cookie)
            self._owner._inhibit_cookie = None
