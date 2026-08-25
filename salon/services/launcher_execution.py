# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused launcher responsibility."""

import os

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib  # noqa: E402

from salon.core import launchspec, sandbox  # noqa: E402
from salon.core.model import LaunchKind, Tile  # noqa: E402
from salon.services.component import ServiceComponent  # noqa: E402
from salon.services.launcher_shared import _OVERLAY_TIMEOUT_SECONDS  # noqa: E402


class LauncherExecution(ServiceComponent):
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
                browser_command=self._owner._browser_command(),
                browser_extra_flags=self._owner._browser_extra_flags(),
                scale_factor=self._owner.browser_scale_factor,
                session_type=os.environ.get("XDG_SESSION_TYPE", ""),
                host_prefix=host,
            )
        except Exception as exc:  # noqa: BLE001 — surface any resolution failure to the user
            if self._owner.on_error is not None:
                # Always named: a message with no subject leaves the user
                # guessing which of the tiles on screen it was about.
                self._owner.on_error(f"Couldn't start {tile.title}. {exc}")
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
            if self._owner.on_error is not None:
                self._owner.on_error(f"Couldn't start {tile.title}: {exc.message}")
            return

        self._owner._subprocess = subprocess
        self._owner._child_pid = None
        self._owner._launching_tile = tile
        self._owner._awaiting_child_focus = True
        self._owner._awaiting_return = True
        self._owner._launched_at_ms = GLib.get_monotonic_time() // 1000
        self._owner._start_idle_inhibit()

        if self._owner.on_launch_started is not None:
            self._owner.on_launch_started(tile)
        self._owner._overlay_timeout_id = GLib.timeout_add_seconds(
            _OVERLAY_TIMEOUT_SECONDS, self._owner._on_overlay_timeout
        )
        subprocess.wait_async(None, self._owner._on_subprocess_exited)

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
        self._owner._child_pid = None
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
            if self._owner.on_error is not None:
                self._owner.on_error(f"Couldn't start {tile.title}: {exc.message}")
            return True

        # No Gio.Subprocess to watch here: the PID this hands back belongs to
        # a systemd scope or a D-Bus activation stub and is routinely gone
        # immediately (§11), so return detection rests entirely on the
        # window-activity signal, which §6.4 expects to carry it anyway.
        # _child_pid is *not* cleared here — launch_uris_as_manager has
        # already delivered it through _on_desktop_pid by this point.
        self._owner._subprocess = None
        self._owner._launching_tile = tile
        self._owner._awaiting_child_focus = True
        self._owner._awaiting_return = True
        self._owner._launched_at_ms = GLib.get_monotonic_time() // 1000
        self._owner._start_idle_inhibit()
        if self._owner.on_launch_started is not None:
            self._owner.on_launch_started(tile)
        self._owner._overlay_timeout_id = GLib.timeout_add_seconds(
            _OVERLAY_TIMEOUT_SECONDS, self._owner._on_overlay_timeout
        )
        return True

    def _on_desktop_pid(self, app_info: Gio.AppInfo, pid: int, user_data: object = None) -> None:
        """Required by launch_uris_as_manager.

        Return detection still doesn't use this pid — see above — but
        close_child() does, as its only handle on a .desktop launch. It is
        routinely a wrapper that has already exited, which is why closing
        that way is attempted and reported rather than assumed to work.
        """
        self._owner._child_pid = pid or None

    def cancel(self) -> None:
        """BACK during the launching overlay: give up waiting and force the
        child to exit. Only valid during phase 1 — see is_launching."""
        if not self._owner._awaiting_child_focus:
            return
        if self._owner._subprocess is not None:
            self._owner._subprocess.force_exit()
        self._owner._finish_return()
