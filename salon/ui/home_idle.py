# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_rows import *
from salon.ui.home_shared import *
from salon.ui.home_spring import *
from salon.ui.home_viewport import *


class HomeIdleController(ServiceComponent):
    def _apply_wallpaper(self) -> None:
        self._backdrop.set_wallpaper(
            self._settings.get_string("wallpaper-path"),
            self._settings.get_double("wallpaper-dim"),
        )

    def _apply_screensaver_setting(self) -> None:
        if self._idle_id is not None:
            GLib.source_remove(self._idle_id)
            self._idle_id = None
        self._screensaver.hide()
        if self._settings.get_int("screensaver-minutes") <= 0:
            return
        # Polled once a second rather than armed for the whole delay: the
        # deadline moves on every button press, and rearming a timer on
        # every press of a held direction is far more work than one cheap
        # comparison a second.
        self._idle_id = GLib.timeout_add_seconds(1, self._check_idle)

    def _check_idle(self) -> bool:
        minutes = self._settings.get_int("screensaver-minutes")
        if minutes <= 0:
            self._idle_id = None
            return bool(GLib.SOURCE_REMOVE)
        if self._screensaver.showing:
            return bool(GLib.SOURCE_CONTINUE)
        # Never over something Salon started. While a child app owns the
        # screen Salon is not being looked at, and the child has its own
        # idea about idling; while a launch is in flight, covering the
        # overlay would hide the only feedback there is.
        if self._child_active or self._pointer_mode or self._launcher.is_launching:
            self._last_input = time.monotonic()
            return bool(GLib.SOURCE_CONTINUE)
        if time.monotonic() - self._last_input >= minutes * 60:
            # The one moment nobody is looking at the home screen, which is
            # exactly when a slideshow should change picture: doing it on a
            # timer would swap the background out from under someone
            # mid-navigation.
            self._backdrop.next_wallpaper()
            self._screensaver.show()
        return bool(GLib.SOURCE_CONTINUE)

    def wake(self) -> None:
        """Any input at all, including the kinds that never become an
        Action — a mouse moving, a click on the status bar."""
        self._last_input = time.monotonic()
        if self._screensaver.showing:
            self._screensaver.hide()

    def _on_now_playing(self, player: nowplaying.Player | None) -> None:
        """Hand the detail strip over to the player, or give it back.

        The strip shows one thing at a time on purpose: a television has
        exactly one place the eye looks for "what is happening right now",
        and splitting it between the cursor and the music would make both
        harder to read from a sofa.
        """
        self._current_player = player
        self._publish_remote_state()
        if player is None:
            self._detail_bar.clear_override()
            return
        title, detail = nowplaying.describe(player)
        self._detail_bar.set_override(title, detail)
