# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_rows import *
from salon.ui.home_shared import *
from salon.ui.home_spring import *
from salon.ui.home_viewport import *


class HomePhoneCatalogController(ServiceComponent):
    def _remote_tile_from(self, tile: Tile, artwork: Artwork) -> RemoteTile:
        return RemoteTile(
            id=tile.id,
            title=tile.title,
            subtitle=tile.subtitle,
            accent=to_hex(artwork.accent),
            has_art=artwork.level <= 4 and not artwork.icon_is_symbolic,
            fit="cover" if artwork.level == 1 else "contain",
            pinned=favourites.is_favourite(self._settings, tile.id),
            removable=self._locate_in_config(tile.id) is not None,
        )

    def _scan_apps_for_phone(self) -> None:
        """The installed-app list the phone's search ranks against.

        Once, when the remote first starts, and never on the request path.
        Scanning every `.desktop` file on the system takes long enough that
        doing it inside `/search` would stall the frame clock on every
        keystroke somebody types on their phone.
        """
        if self._phone_apps_scanned:
            return
        self._phone_apps_scanned = True

        def scanned(tiles: list[Tile]) -> None:
            self._phone_apps = tiles

        appinfo.list_installed_async(scanned)

    def _phone_tile(self, tile_id: str) -> Tile | None:
        """The catalogue tile behind an id from the phone, or the installed
        app if it is one of those — a search result can be either."""
        position = self._catalog.find(tile_id)
        if position is not None:
            return self._catalog.tile_at(*position)
        return next((tile for tile in self._phone_apps if tile.id == tile_id), None)

    def _on_phone_tile_action(self, tile_id: str, what: str) -> str:
        """The phone's long-press menu. Returns what to tell the phone.

        Every one of these already exists behind `Action.OPTIONS` on the
        television; this is the same set reached from the one surface that
        shows every tile at once. `edit` opens the television's own editor
        rather than reimplementing a form with eight fields on a phone —
        and says so, because a screen changing over there with no
        acknowledgement in your hand is indistinguishable from a dead
        button.
        """
        tile = self._phone_tile(tile_id)
        if tile is None:
            return "That isn't on the television any more."
        if what in ("pin", "unpin"):
            pinned = favourites.is_favourite(self._settings, tile_id)
            if (what == "pin") == pinned:
                return f"{tile.title} is already {'pinned' if pinned else 'unpinned'}."
            favourites.toggle_favourite(self._settings, tile_id)
            self._refresh_catalog(preserve_focus=True)
            return f"{tile.title} {'pinned to' if what == 'pin' else 'removed from'} Favourites"
        located = self._locate_in_config(tile_id)
        if located is None:
            # Recents, Favourites and the apps grid all produce tiles that
            # no row in tiles.json contains; there is nothing to edit or
            # delete, and saying so beats a button that quietly fails.
            return f"{tile.title} isn't one of your own tiles, so it can't be changed."
        row_id, located_id = located
        if what == "edit":
            self._settings_screen_open_tile(row_id, located_id)
            return f"Editing {tile.title} on the television."
        if editing.remove_tile(self._config, row_id, located_id):
            self._save_config()
            return f"{tile.title} removed."
        return f"{tile.title} couldn't be removed."

    def _on_phone_volume(self, level: float) -> None:
        """The slider. Absolute, and the OSD comes up on the television too
        — someone else in the room should see why it got quieter."""
        self.wake()
        audio.set_volume(level, lambda: audio.get_volume(self._on_volume_read))

    def _on_phone_mute(self) -> None:
        self.wake()
        audio.toggle_mute(lambda: audio.get_volume(self._on_volume_read))

    def _on_volume_read(self, level: float, muted: bool) -> None:
        self._osd.show_volume(level, muted)
        self._phone_volume = level
        self._phone_muted = muted
        self._publish_remote_state()

    def _refresh_phone_volume(self) -> None:
        """Read the sink so the phone's slider starts in the right place."""
        audio.get_volume(self._on_volume_read)

    def _on_phone_scroll(self, dx: float, dy: float) -> None:
        """Two fingers on the trackpad. Straight through to the same
        RemoteDesktop session the one-finger drag uses."""
        if not self._pointer.ready:
            return
        self._set_pointer_visible(True)
        self.wake()
        self._pointer.scroll(dx, dy)

    def _on_phone_scroll_end(self) -> None:
        if self._pointer.ready:
            self._pointer.scroll_finish()

    def _on_phone_button(self, button: str, what: str) -> None:
        """A named mouse button, clicked or held.

        Held is what a double-tap-and-drag needs: a click that releases
        itself 50ms later cannot move a window or select a line of text,
        and those are the two things a trackpad is for that a D-pad is not.
        """
        if not self._pointer.ready:
            return
        code = pointer_injector.BUTTONS.get(button)
        if code is None:
            return
        self._set_pointer_visible(True)
        self.wake()
        if what == "click":
            self._pointer.click(code)
        elif what == "down":
            self._pointer.press(code)
        else:
            self._pointer.release(code)

    def _on_phone_transport(self, what: str) -> bool:
        """Play/pause, next track, previous track, for the player the phone
        can see. Not routed through `Action`: see the comment on the page's
        transport buttons."""
        if what == "play_pause":
            done = self._now_playing.play_pause()
        elif what == "next":
            done = self._now_playing.next_track()
        else:
            done = self._now_playing.previous_track()
        if not done:
            self._toast("Nothing is playing.")
        return done

    def _art_for_phone(self, tile_id: str) -> Path | None:
        """The image file behind a tile the phone is drawing.

        Through `_phone_tile`, so it covers a search result as well as
        something on the home screen. Looking only in the catalogue — which
        is what this did — meant every installed application in a result
        list reported artwork it could not then serve, and the card fell
        back to a coloured letter after a 404 per tile.
        """
        tile = self._phone_tile(tile_id)
        return None if tile is None else self._artwork.artwork_file(tile)

    def _on_phone_locked(self) -> None:
        self._toast(
            "Phone remote locked — too many wrong codes. "
            "Turn it off and on again in Settings for a new code."
        )
