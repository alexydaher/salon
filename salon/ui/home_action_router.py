# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

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
            if (
                self._owner._child_active
                or self._owner._pointer_mode
                or self._owner._launcher.has_child
            ):
                # ...and while something else is in front of Salon it means
                # "bring me home", because a menu drawn in Salon's own
                # window would appear underneath Netflix where nobody can
                # see it. See _return_from_child.
                #
                # `has_child` is asked as well as the two mode flags, and it
                # is the one that makes MENU *reliable*. Those flags are set
                # from `on_child_focused`, which needs Salon's window to go
                # from active to inactive — an edge that never happens when
                # the window was already inactive at launch, which is what
                # the phone does every time it opens a tile while another
                # app is in front. Without this, MENU fell through to
                # opening the system menu underneath the app: invisible,
                # swallowing the next press to close itself again, and
                # looking for all the world like a button that works every
                # other time.
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
            if (
                self._owner._child_active
                or self._owner._pointer_mode
                or self._owner._launcher.has_child
            ):
                self._owner._open_power_on_return = True
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
        # the guards for "an app is covering it" come first. They used not
        # to, and the three actions that sat above them all misfired from
        # behind a launched app: SEARCH opened the search overlay where
        # nobody could see it and then took every press, POWER opened the
        # system menu the same way, and PLAY_PAUSE with nothing playing fell
        # through to *launching the focused tile* on top of the app that was
        # already running — which is also what left MENU with no child to
        # return from. The rule the MENU handler above states ("a menu drawn in
        # Salon's own window would appear underneath Netflix") is this one.
        if self._owner._pointer_mode or self._owner._child_active:
            if action is Action.PLAY_PAUSE:
                # The transport half only: there is no focused tile to fall
                # back to behind an application.
                self._owner._play_pause()
                return
            if self._owner._pointer_mode:
                if action is Action.SEARCH:
                    # While the cursor is being driven over a browser
                    # window, Salon's own search is the wrong thing to open
                    # — the text field the user is aiming at belongs to
                    # Chrome, so SEARCH toggles GNOME's on-screen keyboard
                    # for it instead.
                    if onscreen_keyboard_available():
                        set_onscreen_keyboard_enabled(not onscreen_keyboard_enabled())
                    else:
                        self._owner._toast(
                            "The desktop keyboard isn't available; use the phone's Type tab."
                        )
                elif action is Action.OK:
                    self._owner._pointer.click()
                elif action is Action.BACK:
                    self._owner._pointer_mode = False
                    self._owner._toast("Cursor off. Press MENU to return to Salon.")
                return
            # A native app (e.g. a game client) reads the same raw gamepad
            # device directly — that input bypasses window focus entirely,
            # unlike keyboard/mouse, so Salon has to deliberately go quiet
            # rather than fight it for button presses. Resumes on exit, or
            # on MENU, which is handled above.
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
            if self._owner._launcher.is_launching:
                self._owner._launcher.cancel()
            # Otherwise a no-op: there's no parent screen at the top level
            # yet (no search overlay stack built), and BACK must never quit
            # Salon outright — see _on_key_pressed's dev-only Escape
            # shortcut, or MENU -> Exit Salon, for that.
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
