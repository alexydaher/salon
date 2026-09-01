# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_rows import _is_browser_launch
from salon.ui.home_shared import (
    _RELAUNCH_DELAY_MS,
    GLib,
    LaunchKind,
    MenuFrame,
    SystemMenuItem,
    Tile,
    onscreen_keyboard_available,
    recents,
)


class HomeLaunchController(ServiceComponent):
    def _on_running_changed(self) -> None:
        self._owner._status_info.set_running_count(len(self._owner._launcher.running_apps))
        self._owner._publish_remote_state()

    def _return_from_child(self) -> bool:
        """Come back to Salon while leaving the foreground app alive."""
        title = self._owner._launcher.child_title or "the app"
        if self._owner._pointer.ready and self._owner._launcher.return_to_salon():
            if self._owner._pointer.switch_window():
                self._owner._toast(f"Returning to Salon — {title} stays open.")
                return True
        self._owner._toast(
            "Salon needs the remote-control permission to switch windows without closing the app."
        )
        self._owner._pending_launch = None
        return False

    def _close_running_app(self, app_id: str) -> bool:
        title = next(
            (app.title for app in self._owner._launcher.running_apps if app.id == app_id),
            "the app",
        )
        if self._owner._launcher.close_app(app_id):
            self._owner._toast(f"Closing {title}…")
            return True
        front = app_id == self._owner._launcher.front_child_id
        return self._close_failed(title, return_home=front)

    def _close_front_app(self) -> bool:
        app_id = self._owner._launcher.front_child_id
        if app_id:
            return self._close_running_app(app_id)
        title = self._owner._launcher.child_title or "the app"
        if self._owner._launcher.close_child():
            self._owner._toast(f"Closing {title}…")
            return True
        return self._close_failed(title, return_home=True)

    def _close_failed(self, title: str, *, return_home: bool) -> bool:
        if return_home and self._owner._return_from_child():
            self._owner._toast(f"Salon couldn't close {title}, so it returned home instead.")
        else:
            self._owner._toast(f"Salon can't close {title} — it is still running.")
        return False

    def _launch_focused(self) -> None:
        tile = self._owner._catalog.tile_at(self._owner._focus.row, self._owner._focus.col)
        if tile is not None:
            self._launch_tile(tile)

    def _launch_tile(self, tile: Tile) -> None:
        """The single launch entry point, shared by the home rows and by
        search results — a tile found through search must go through exactly
        the same path as one on the home screen."""
        if tile.launch.kind is LaunchKind.BUILTIN:
            self._handle_builtin(tile.launch.target)
            return
        if self._owner._apps_grid.get_visible():
            self._owner._apps_grid.close()
        if self._owner._search.get_visible():
            self._owner._search.close()
        if self._owner._launcher.has_child:
            # Return to Salon without ending what is there, then open this
            # once the compositor has put Salon back in front.
            self._owner._pending_launch = tile
            self._return_from_child()
            return
        self._owner._launcher.launch(tile)

    def _handle_builtin(self, target: str) -> None:
        if target == "settings":
            self._owner._open_settings()
        elif target == "search":
            self._owner._open_search()
        else:
            self._owner._toast(f"There's nothing behind the {target} tile yet.")

    def _build_system_menu_items(self) -> list[SystemMenuItem]:
        """The authoritative global menu on every Salon-owned surface."""
        items: list[SystemMenuItem] = [
            SystemMenuItem(
                "Search",
                self._owner._open_search,
                icon_name="system-search-symbolic",
                detail="Find a tile or an installed application",
            ),
            SystemMenuItem(
                "All Apps",
                self._owner._open_apps,
                icon_name="view-grid-symbolic",
                detail="Browse every installed application, A to Z",
            ),
            # Named for its state, because this is the only place that says
            # whether the remote is running at all.
            SystemMenuItem(
                "Phone" if self._owner.phone_remote_running() else "Connect a Phone",
                self._owner._open_phone_pairing,
                icon_name="phone-symbolic",
                detail=(
                    "Show the pairing code or manage the connected phone remote"
                    if self._owner.phone_remote_running()
                    else "Use a phone as the remote"
                ),
            ),
            SystemMenuItem(
                "Settings",
                lambda: self._owner._open_settings(),
                icon_name="emblem-system-symbolic",
                detail="Tiles, appearance, input, and system settings",
            ),
        ]
        if self._power_menu_items():
            items.append(
                SystemMenuItem(
                    "Power",
                    icon_name="system-shutdown-symbolic",
                    detail="Suspend, log out, restart, or shut down",
                    submenu=lambda: MenuFrame("power", "Power", self._power_menu_items()),
                )
            )
        items.append(
            SystemMenuItem(
                "About Salon",
                lambda: self._owner._open_settings("about"),
                icon_name="help-about-symbolic",
                detail="Version, configuration path, and project information",
            )
        )
        return items

    def _on_launch_started(self, tile: Tile) -> None:
        self._owner._current_launch_is_browser = _is_browser_launch(tile)
        # Resolved from the tile rather than read off the focused widget:
        # a launch can come from a search result, which has no counterpart
        # in the home rows at all. The resolver caches, so this is cheap.
        artwork = self._owner._artwork.resolve(
            tile, icon_size=round(self._owner._metrics.height * 0.5)
        )
        self._owner._launching_overlay.show_for(
            tile,
            accent=artwork.accent,
            hint=f"{self._close_hint()} to return to Salon; the app keeps running",
        )
        recents.push_recent(self._owner._settings, tile.id)
        self._owner._refresh_catalog(preserve_focus=True)
        self._owner._publish_remote_state()

    def _on_child_focused(self) -> None:
        self._owner._launching_overlay.hide()
        tile_title = self._owner._launcher.child_title or "the app"
        # On by default, but still a preference: the RemoteDesktop grant is
        # taken once at startup and restored silently after that (see
        # _prewarm_pointer_session), which is what made it affordable to
        # default on. Turning it off in Settings → Input leaves a browser
        # tile navigable only by whatever the site itself offers.
        if self._owner._current_launch_is_browser and self._owner._settings.get_boolean(
            "gamepad-pointer"
        ):
            self._owner._pointer_mode = True
            self._owner._start_pointer_session()
            controls = "Right stick = cursor, OK = click"
            if onscreen_keyboard_available():
                controls += ", Search = keyboard"
            self._owner._toast(
                controls
                + ", "
                + (
                    "phone Menu or controller Menu/Start"
                    if self._owner._pairing.connected
                    else "Menu/Start"
                )
                + " = back to Salon"
            )
        else:
            self._owner._child_active = True
            self._owner._toast(f"{self._close_hint()} to return; {tile_title} keeps running.")
        # The child taking focus arrives asynchronously, long after the
        # press that launched it — so without this the phone's header still
        # said "home" while the application was on the television, and only
        # caught up at the *next* button press. It is the one line on the
        # phone that answers "where am I", and it was always one event
        # behind.
        self._owner._publish_remote_state()

    def _on_launch_timed_out(self) -> None:
        self._owner._launching_overlay.show_timed_out()
        self._owner._publish_remote_state()

    def _on_returned(self) -> None:
        self._owner._launching_overlay.hide()
        # Salon's own way back in. Under GNOME Shell this rides on top of
        # the Shell's window-close animation; under GNOME Kiosk, whose
        # compositor hides a destroyed window with no transition at all, it
        # is the entire thing standing between an application and the home
        # screen.
        self._owner._return_fade.play()
        self._owner._pointer_mode = False
        self._owner._child_active = False
        self._owner._publish_remote_state()
        if self._owner._open_power_on_return:
            self._owner._open_power_on_return = False
            GLib.timeout_add(_RELAUNCH_DELAY_MS, self._show_power_after_return)
            return
        pending, self._owner._pending_launch = self._owner._pending_launch, None
        if pending is not None:
            # A tile tapped on the phone while another app was in front. The
            # old one has just gone; give the compositor a moment to hand
            # focus back before spawning the next, because the return
            # detection for *that* launch is the window going inactive and
            # it can only go inactive from active.
            GLib.timeout_add(_RELAUNCH_DELAY_MS, lambda: self._start_pending(pending))

    def _show_power_after_return(self) -> bool:
        self._owner._show_power_menu()
        return bool(GLib.SOURCE_REMOVE)

    def _start_pending(self, tile: Tile) -> bool:
        self._launch_tile(tile)
        return bool(GLib.SOURCE_REMOVE)

    def _close_hint(self) -> str:
        """How to get back out, named for the hardware that is actually
        connected. A phone in someone's hand has a Menu button of its own,
        and telling them to press START on a controller they may not own is
        the difference between a way out and a trapped television."""
        if self._owner._pairing.connected:
            return "Press Menu on your phone, or Menu/Start on the controller,"
        return "Press Menu/Start on the controller"

    def _on_launch_error(self, message: str) -> None:
        self._owner._toast(message)
