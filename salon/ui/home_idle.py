# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_shared import GLib, nowplaying, time


class HomeIdleController(ServiceComponent):
    def _apply_wallpaper(self) -> None:
        self._owner._backdrop.set_wallpaper(
            self._owner._settings.get_string("wallpaper-path"),
            self._owner._settings.get_double("wallpaper-dim"),
        )

    def _apply_screensaver_setting(self) -> None:
        if self._owner._idle_id is not None:
            GLib.source_remove(self._owner._idle_id)
            self._owner._idle_id = None
        self._owner._screensaver.hide()
        if self._owner._settings.get_int("screensaver-minutes") <= 0:
            return
        # Polled once a second rather than armed for the whole delay: the
        # deadline moves on every button press, and rearming a timer on
        # every press of a held direction is far more work than one cheap
        # comparison a second.
        self._owner._idle_id = GLib.timeout_add_seconds(1, self._check_idle)

    def _check_idle(self) -> bool:
        minutes = self._owner._settings.get_int("screensaver-minutes")
        if minutes <= 0:
            self._owner._idle_id = None
            return bool(GLib.SOURCE_REMOVE)
        if self._owner._screensaver.showing:
            return bool(GLib.SOURCE_CONTINUE)
        # Never over something Salon started. While a child app owns the
        # screen Salon is not being looked at, and the child has its own
        # idea about idling; while a launch is in flight, covering the
        # overlay would hide the only feedback there is.
        if (
            self._owner._child_active
            or self._owner._pointer_mode
            or self._owner._launcher.is_launching
        ):
            self._owner._last_input = time.monotonic()
            return bool(GLib.SOURCE_CONTINUE)
        if time.monotonic() - self._owner._last_input >= minutes * 60:
            # The one moment nobody is looking at the home screen, which is
            # exactly when a slideshow should change picture: doing it on a
            # timer would swap the background out from under someone
            # mid-navigation.
            self._owner._backdrop.next_wallpaper()
            self._owner._screensaver.show()
        return bool(GLib.SOURCE_CONTINUE)

    def wake(self) -> None:
        """Any input at all, including the kinds that never become an
        Action — a mouse moving, a click on the status bar."""
        self._owner._last_input = time.monotonic()
        if self._owner._screensaver.showing:
            self._owner._screensaver.hide()

    def _on_now_playing(self, player: nowplaying.Player | None) -> None:
        """Update the compact player status without erasing tile context."""
        self._owner._current_player = player
        self._owner._publish_remote_state()
        if player is None:
            self._owner._now_playing_status.clear()
            return
        title, detail = nowplaying.describe(player, include_status=False)
        self._owner._now_playing_status.set_track(
            title,
            detail,
            playing=player.status == nowplaying.PLAYING,
        )
