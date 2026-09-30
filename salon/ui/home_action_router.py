# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.core.front import PointerOff, QueuePower, Route, route
from salon.services.component import ServiceComponent
from salon.ui.home_shared import (
    _DIRECTIONS,
    Action,
    audio,
    onscreen_keyboard_available,
    onscreen_keyboard_enabled,
    set_onscreen_keyboard_enabled,
    time,
)


class HomeActionRouter(ServiceComponent):
    def _dispatch_action(self, action: Action) -> None:
        self._owner._last_input = time.monotonic()
        front_route = route(self._owner._front, action)
        if self._owner._screensaver.showing:
            # Swallowed, not acted on. Someone reaching for the remote to
            # see the clock must not launch Netflix by doing so.
            self._owner._screensaver.hide()
            return

        if self._owner._onboarding.get_visible():
            # Ahead of even MENU: the introduction is what explains that
            # MENU exists, and there is nothing behind it worth reaching.
            self._owner._onboarding.handle_action(action)
            return

        if action is Action.MENU:
            # Highest priority, deliberately ahead of every other mode —
            # this is the only reachable way to suspend/shut down or exit
            # Salon on a fullscreen, keyboard-less kiosk, so it must never
            # be one of the things a stuck launch or an active pointer
            # session can swallow.
            if front_route is Route.RETURN_HOME:
                # ...and while something else is in front of Salon it means
                # "bring me home", because a menu drawn in Salon's own
                # window would appear underneath Netflix where nobody can
                # see it. See _return_from_child. `route` answers from one
                # state, launch phase 1 included — the flags this replaced
                # missed the case where Salon's window was already inactive
                # at launch, and MENU then opened a menu under the app.
                self._owner._return_from_child()
                return
            if self._owner._text_entry.get_visible():
                # Cancel the edit before putting the global menu above the
                # Settings surface that owns it.
                self._owner._text_entry.handle_action(Action.BACK)
            if self._owner._phone_pairing.get_visible():
                self._owner._phone_pairing.close()
            if self._owner._system_menu.get_visible():
                self._owner._system_menu.hide()
            else:
                self._owner._show_system_menu()
            return

        if action is Action.POWER:
            # POWER is as global as MENU on every surface Salon owns. If an
            # external application is covering Salon, return from it first and
            # present Power as soon as the compositor returns us.
            if front_route is Route.RETURN_THEN_POWER:
                self._owner._feed_front(QueuePower())
                self._owner._return_from_child()
                return
            if self._owner._text_entry.get_visible():
                self._owner._text_entry.handle_action(Action.BACK)
            if self._owner._phone_pairing.get_visible():
                self._owner._phone_pairing.close()
            self._owner._show_power_menu()
            return

        # Above the menus it is opened from, and below MENU, which returns
        # to Salon: a screen showing a code is not a place MENU should
        # stop working.
        if self._owner._phone_pairing.get_visible():
            self._owner._phone_pairing.handle_action(action)
            return

        for menu in (self._owner._system_menu, self._owner._tile_menu):
            if not menu.get_visible():
                continue
            if action is Action.UP:
                menu.move(-1)
            elif action is Action.DOWN:
                menu.move(1)
            elif action is Action.OK:
                menu.activate_selected()
            elif action is Action.RIGHT:
                item = menu.selected_item
                if item is not None and item.submenu is not None:
                    menu.activate_selected()
            elif action is Action.LEFT:
                if menu.has_back:
                    menu.back()
            elif action in (Action.BACK, Action.OPTIONS):
                # `back`, not `hide`: the power list is a second level and
                # BACK there means the menu it was opened from, the same as
                # it does everywhere else in Salon.
                menu.back()
            return

        # Innermost first: text entry is opened *by* Settings, on top of
        # it, so it has to be offered the action before Settings is.
        if self._owner._text_entry.get_visible():
            self._owner._text_entry.handle_action(action)
            return

        if self._owner._settings_screen.get_visible():
            self._owner._settings_screen.note_action(action)
            self._owner._settings_screen.handle_action(action)
            return

        if self._owner._apps_grid.get_visible():
            if action is Action.SEARCH:
                self._owner._apps_grid.close()
                self._owner._open_search()
            elif self._owner._nav_focused:
                self._owner._handle_nav_action(action)
            elif action is Action.OPTIONS:
                self._owner._open_tile_menu(self._owner._apps_grid.focused_tile, from_grid=True)
            else:
                self._owner._apps_grid.handle_action(action)
            return

        if self._owner._search.get_visible():
            self._owner._search.handle_action(action)
            return

        # Volume is the one group that is true whatever is on screen: it
        # acts on the system's audio, not on a window, so it stays above
        # the "something else is in front" guards below.
        # `_on_volume_read` rather than the OSD directly: it shows the OSD
        # *and* carries the new level to the phone, so a slider in someone's
        # hand does not sit at the old position until they drag it.
        if action is Action.VOLUME_UP:
            audio.adjust_volume(1, lambda: audio.get_volume(self._owner._on_volume_read))
            return
        if action is Action.VOLUME_DOWN:
            audio.adjust_volume(-1, lambda: audio.get_volume(self._owner._on_volume_read))
            return
        if action is Action.MUTE:
            audio.toggle_mute(lambda: audio.get_volume(self._owner._on_volume_read))
            return
        # Skip belongs to the same group and for the same reason: it is a
        # command to whatever is playing over MPRIS, not to a window, so it
        # is as true inside Settings or behind Netflix as it is on Home.
        # PLAY_PAUSE deliberately stays *below* the guards instead, because
        # it alone carries the "nothing is playing, so start the focused
        # tile" fallback, and that is a statement about Home.
        if action in (Action.NEXT, Action.PREVIOUS):
            self._owner._skip_track(forward=action is Action.NEXT)
            return

        # Everything from here down draws or acts on Salon's own window, so
        # what is in front comes first. It used not to, and SEARCH, POWER and
        # PLAY_PAUSE all misfired from behind a launched app: search opened
        # where nobody could see it and took every press, and PLAY_PAUSE with
        # nothing playing launched the focused tile on top of the app that
        # was already running.
        if front_route is not Route.SALON:
            self._behind_app(front_route)
            return

        # The rail's card. Above the BACK handler below, because BACK is
        # one of the presses it owns; see ui/home_now_playing.
        if self._owner._card_takes(action):
            return

        if action is Action.SEARCH:
            self._owner._open_search()
            return
        if action is Action.PLAY_PAUSE:
            self._owner._play_pause(may_launch=True)
            return
        if action is Action.BACK:
            # A no-op: there's no parent screen at the top level yet, and
            # BACK must never quit Salon outright — see _on_key_pressed's
            # dev-only Escape shortcut, or MENU -> Exit Salon, for that.
            return

        if self._owner._nav_focused:
            self._owner._handle_nav_action(action)
            return

        if action is Action.OPTIONS:
            self._owner._open_tile_menu(
                self._owner._catalog.tile_at(self._owner._focus.row, self._owner._focus.col),
                from_grid=False,
            )
            return

        if action in _DIRECTIONS:
            self._owner._move_focus(action)
        elif action is Action.OK:
            self._owner._launch_focused()

    def _behind_app(self, front_route: Route) -> None:
        """A press while a launch is in flight or an application is in front.

        Salon's own screens are not what it is for, so the only things that
        happen here are the ones that reach the *other* window or the launch.
        """
        if front_route is Route.TRANSPORT:
            self._owner._play_pause()
        elif front_route is Route.CANCEL_LAUNCH:
            self._owner._launcher.cancel()
        elif front_route is Route.POINTER_CLICK:
            self._owner._pointer.click()
        elif front_route is Route.POINTER_OFF:
            self._owner._feed_front(PointerOff())
            self._owner._toast("Cursor off. Press MENU to return to Salon.")
        elif front_route is Route.POINTER_OSK:
            # While the cursor is being driven over a browser window, Salon's
            # own search is the wrong thing to open — the text field being
            # aimed at belongs to Chrome, so SEARCH toggles GNOME's on-screen
            # keyboard for it instead.
            if onscreen_keyboard_available():
                set_onscreen_keyboard_enabled(not onscreen_keyboard_enabled())
            else:
                self._owner._toast(
                    "The desktop keyboard isn't available; use the phone's Type tab."
                )
        # SWALLOW: a native app reads the gamepad device directly, bypassing
        # window focus, so Salon goes quiet rather than fight it for the
        # buttons. Resumes on exit, or on MENU, which is routed above.
