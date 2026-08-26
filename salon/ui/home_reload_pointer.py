# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_rows import _is_browser_launch
from salon.ui.home_shared import (
    _DIRECTIONS,
    _RELOAD_DEBOUNCE_MS,
    KEYBOARD,
    Action,
    ConfigError,
    Gdk,
    Gio,
    GLib,
    Gtk,
    action_for_keyval,
    tile_config,
)


class HomeReloadAndPointerController(ServiceComponent):
    def _on_config_dir_changed(
        self,
        monitor: Gio.FileMonitor,
        file: Gio.File,
        other_file: Gio.File | None,
        event_type: Gio.FileMonitorEvent,
    ) -> None:
        if file.get_basename() != self._owner._config_path.name:
            return
        if self._owner._reload_timeout_id is not None:
            GLib.source_remove(self._owner._reload_timeout_id)
        self._owner._reload_timeout_id = GLib.timeout_add(
            _RELOAD_DEBOUNCE_MS, self._reload_from_disk
        )

    def _reload_from_disk(self) -> bool:
        self._owner._reload_timeout_id = None
        try:
            self._owner._config = tile_config.load(self._owner._config_path)
        except ConfigError as exc:
            self._owner._toast(f"Your tiles file couldn't be reloaded, so nothing changed. {exc}")
            return GLib.SOURCE_REMOVE
        # Our own save comes back through here too, as a new Config object;
        # the editor has to be repointed at it or the next edit is applied
        # to a detached copy of the catalogue.
        self._owner._settings_screen.set_config(self._owner._config)
        self._owner._refresh_catalog(preserve_focus=True)
        return GLib.SOURCE_REMOVE

    def _on_artwork_dir_changed(
        self,
        monitor: Gio.FileMonitor,
        file: Gio.File,
        other_file: Gio.File | None,
        event_type: Gio.FileMonitorEvent,
    ) -> None:
        if self._owner._artwork_reload_timeout_id is not None:
            GLib.source_remove(self._owner._artwork_reload_timeout_id)
        self._owner._artwork_reload_timeout_id = GLib.timeout_add(
            _RELOAD_DEBOUNCE_MS, self._on_artwork_reload_timeout
        )

    def _on_artwork_reload_timeout(self) -> bool:
        self._owner._artwork_reload_timeout_id = None
        self._owner._rebuild_row_widgets()
        return GLib.SOURCE_REMOVE

    def _set_pointer_visible(self, visible: bool) -> None:
        """A mouse cursor parked over a TV interface looks like a stuck
        pixel, so it's hidden the moment the user drives with anything else
        and restored as soon as the pointer moves again."""
        if visible == self._owner._pointer_visible:
            return
        self._owner._pointer_visible = visible
        self._apply_pointer_state()

    def _apply_pointer_state(self) -> None:
        visible = self._owner._pointer_visible
        # Hover-to-select follows the same flag: GTK delivers a motion event
        # whenever a widget maps or scrolls under a stationary cursor, so
        # acting on hover regardless of whether the pointer is actually in
        # use makes focus jump to wherever the mouse was left sitting.
        self._owner._system_menu.set_hover_enabled(visible)
        self._owner._phone_pairing.set_hover_enabled(visible)
        self._owner._tile_menu.set_hover_enabled(visible)
        self._owner._status_bar.set_hover_enabled(visible)
        self._owner._search.set_pointer_active(visible)
        self._owner._apps_grid.set_pointer_active(visible)
        self._owner._settings_screen.set_pointer_active(visible)
        self._owner._text_entry.set_pointer_active(visible)
        root = self._owner.get_root()
        if isinstance(root, Gtk.Window):
            root.set_cursor(None if visible else Gdk.Cursor.new_from_name("none", None))

    def on_mapped(self) -> None:
        """Called once the window has a surface — the first moment there's a
        root to hang a cursor on."""
        self._owner.grab_focus()
        self._apply_pointer_state()
        if not self._owner._settings.get_boolean("onboarding-complete"):
            self._owner._onboarding.start()
        self._prewarm_pointer_session()

    def _finish_onboarding(self) -> None:
        self._owner._settings.set_boolean("onboarding-complete", True)
        self._owner.grab_focus()

    def _prewarm_pointer_session(self) -> None:
        """Take the RemoteDesktop grant now rather than mid-launch.

        The portal's consent dialog appears once — after that the restore
        token reopens the session silently — but *where* that once lands
        matters. Asking here puts it over Salon's own home screen, anchored
        to Salon's window, while nothing is launching; asking at child-focus
        time put it on top of Netflix the moment it opened, which is what it
        used to do.

        Nothing is launching yet, so the dialog stealing focus can't be
        mistaken for the child taking it (LauncherService ignores
        active-state changes while idle). Skipped entirely when there is no
        browser tile to point at, so a catalogue of native apps never sees a
        permission prompt at all.
        """
        if not self._owner._settings.get_boolean("gamepad-pointer"):
            return
        if not any(
            _is_browser_launch(tile) for row in self._owner._catalog.rows for tile in row.tiles
        ):
            return
        self._owner._start_pointer_session()

    def _on_pointer_motion(self, controller: Gtk.EventControllerMotion, x: float, y: float) -> None:
        """Only *movement* counts as the pointer being in use.

        GTK delivers a motion event when a window maps under a stationary
        cursor, and taking that at face value meant Salon started up with
        the cursor revealed and hover-to-focus armed — so the first widget
        rebuild under the parked mouse silently stole focus. Comparing
        against the last position is what tells a real move from that.
        """
        previous = self._owner._last_pointer_xy
        self._owner._last_pointer_xy = (x, y)
        if previous is None:
            return
        if abs(x - previous[0]) < 1.0 and abs(y - previous[1]) < 1.0:
            return
        self._owner.wake()
        self._set_pointer_visible(True)

    def _on_scroll(self, controller: Gtk.EventControllerScroll, dx: float, dy: float) -> bool:
        self._owner.wake()
        if self._owner._system_menu.get_visible():
            self._owner._handle_action(Action.DOWN if dy > 0 else Action.UP)
            return True
        if dy:
            self._owner._handle_action(Action.DOWN if dy > 0 else Action.UP)
        if dx:
            self._owner._handle_action(Action.RIGHT if dx > 0 else Action.LEFT)
        return True

    def _on_key_pressed(
        self,
        controller: Gtk.EventControllerKey,
        keyval: int,
        keycode: int,
        state: object,
    ) -> bool:
        self._owner._note_input_source(KEYBOARD)
        if keyval == Gdk.KEY_Escape:
            overlays = (
                self._owner._onboarding,
                self._owner._phone_pairing,
                self._owner._system_menu,
                self._owner._tile_menu,
                self._owner._text_entry,
                self._owner._settings_screen,
                self._owner._apps_grid,
                self._owner._search,
            )
            if any(surface.get_visible() for surface in overlays):
                self._owner._handle_action(Action.BACK)
                return True
            # Dev-only quit shortcut, deliberately outside the Action
            # pipeline — a real TV launcher shouldn't be closeable by a
            # single button, and this must never be reachable from the
            # gamepad (B already means BACK, not quit).
            root = self._owner.get_root()
            if isinstance(root, Gtk.Window):
                root.close()
            return True
        if self._owner._binding_capture is not None:
            self._owner._on_raw_input(KEYBOARD, keyval)
            return True
        if self._owner._text_entry.get_visible() and self._owner._text_entry.handle_keyval(
            keyval, state
        ):
            return True
        if self._owner._search.get_visible() and self._owner._search.handle_keyval(keyval, state):
            return True
        action = action_for_keyval(keyval, self._owner._bindings)
        if action is None:
            return False
        self._set_pointer_visible(False)
        if action in _DIRECTIONS:
            if keyval in self._owner._held_keyvals:
                return True  # OS auto-repeat re-fire — our own Repeater drives repeats
            self._owner._held_keyvals.add(keyval)
            self._owner._start_repeat(action)
        self._owner._handle_action(action)
        return True

    def _on_key_released(
        self,
        controller: Gtk.EventControllerKey,
        keyval: int,
        keycode: int,
        state: object,
    ) -> None:
        self._owner._held_keyvals.discard(keyval)
        action = action_for_keyval(keyval, self._owner._bindings)
        if action is not None:
            self._owner._stop_repeat(action)
