# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_shared import (
    _PHONE_ICON_SIZE_PX,
    _PHONE_SEARCH_RESULTS,
    Action,
    RemoteTile,
    Tile,
    appinfo,
    ranking,
)


class HomePhoneInputController(ServiceComponent):
    def _on_phone_action(self, name: str) -> None:
        """A button on the phone remote. Goes through `_handle_action` like
        every other source, so the phone can do exactly what a controller
        can and nothing more — including MENU, which is the one button that
        has to work when a launched app is covering the screen."""
        try:
            action = Action(name)
        except ValueError:
            return
        # A D-pad press is the phone saying "I am driving now", exactly like
        # a key or a controller button, so the cursor goes away — a mouse
        # left parked over a tile otherwise keeps hover-to-focus armed and
        # yanks the selection back the moment a row scrolls under it. The
        # trackpad brings it straight back. Pointer mode is the exception,
        # same as the gamepad: there the cursor *is* the interface.
        self._owner._set_pointer_visible(self._owner._pointer_mode)
        self._owner._handle_action(action)

    def _on_phone_pointer(self, dx: float, dy: float) -> None:
        """The trackpad. Straight into the same RemoteDesktop session the
        right stick drives, which is what makes a phone useful over a
        browser tile that was never built for a remote.

        The cursor has to be *revealed*, and that is not incidental. Salon
        hides it until a real mouse moves, and the reveal hangs off GTK
        motion events — which portal-injected motion does not reliably
        produce over Salon's own window. So the pointer moved and nothing
        was drawn: a finger dragging something invisible. The gamepad path
        has always said this explicitly; this one never did.
        """
        if not self._owner._pointer.ready:
            return
        self._owner._set_pointer_visible(True)
        self._owner.wake()
        self._owner._pointer.move(dx, dy)

    def _on_phone_click(self) -> None:
        if self._owner._pointer.ready:
            self._owner._set_pointer_visible(True)
            self._owner.wake()
            self._owner._pointer.click()

    def _type_remotely(self, text: str) -> bool:
        """Text from the phone with no Salon field asking for it.

        Goes to whatever the compositor has focused — in practice a search
        box inside a launched browser, which is the one place typing on a
        television is unavoidable and the one place Salon's own keyboard
        cannot reach. Returns False when there is no input grant, so the
        phone is told why rather than watching its keystrokes vanish.
        """
        if not self._owner._pointer.ready:
            return False
        self._owner.wake()
        return self._owner._pointer.type_text(text)

    def _open_phone_pairing(self) -> None:
        self._owner._system_menu.hide()
        if not self._owner._phone_pairing.open():
            self._owner._toast("Couldn't start the phone remote — port 8437 is already in use.")
            return
        self._owner._phone_pairing.set_hover_enabled(self._owner._pointer_visible)
        self._owner._publish_remote_state()

    def _close_phone_pairing(self) -> None:
        # The remote keeps running: connecting a phone and then dismissing
        # the screen is the whole gesture this exists for.
        self._owner.grab_focus()
        self._rebuild_system_menu()

    def _stop_phone_remote(self) -> None:
        self._owner.set_phone_remote(False)
        self._owner.grab_focus()
        self._rebuild_system_menu()
        self._owner._toast("Phone remote off.")

    def _rebuild_system_menu(self) -> None:
        """The first item's label depends on whether the remote is running,
        so the menu is rebuilt rather than built once at startup."""
        self._owner._system_menu.set_items(self._owner._build_system_menu_items())

    def _on_phone_launch(self, tile_id: str) -> None:
        """A tile tapped on the phone. Goes through `_launch_tile`, so it is
        the same launch — recents, the launching overlay, the idle inhibit
        and the way back out — as pressing OK on the television. The server
        has already checked the id against what the phone was shown; this
        checks it against the catalogue, because a rebuild can have landed
        in between."""
        position = self._owner._catalog.find(tile_id)
        if position is None:
            self._owner._toast("That isn't on the television any more.")
            return
        tile = self._owner._catalog.tile_at(*position)
        if tile is None:
            return
        # The cursor follows the phone. Coming back to the television and
        # finding it parked where the last button press left it, rather than
        # on what was actually opened, is the kind of small dishonesty that
        # makes two input methods feel like two applications — and the mouse
        # gets out of the way for the same reason a button press does.
        self._owner._set_pointer_visible(self._owner._pointer_mode)
        self._owner._focus.jump_to(*position)
        self._owner._update_focus()
        self._owner._launch_tile(tile)

    def _search_for_phone(self, query: str) -> list[RemoteTile]:
        """Rank the catalogue and every installed app for the phone.

        Answers on the main loop, inside the HTTP handler, so it must not
        touch the disk — the installed-app list is the one scanned when the
        remote started. Empty query returns the catalogue, exactly as the
        television's search screen does: someone who opened search wants to
        go somewhere, and a blank page makes them type before it will admit
        anything exists.

        `ranking.rank_best` is the same call the television makes, which is
        the point: two search surfaces that ordered results differently
        would be two things to learn.
        """
        catalogue = self._owner._searchable_tiles()
        text = query.strip()
        if not text:
            chosen = catalogue[:_PHONE_SEARCH_RESULTS]
        else:
            by_id = {tile.id: tile for tile in (*catalogue, *self._owner._phone_apps)}
            pairs = appinfo.search_pairs(catalogue) + appinfo.search_pairs(self._owner._phone_apps)
            chosen = [
                by_id[tile_id] for tile_id in ranking.rank_best(text, pairs, _PHONE_SEARCH_RESULTS)
            ]
        return [self._remote_tile(tile) for tile in chosen]

    def _remote_tile(self, tile: Tile) -> RemoteTile:
        """One tile in the shape the phone draws, artwork and all.

        Shared with the catalogue snapshot's own construction so a search
        result and a home-screen tile are the same card with the same
        image — a result that rendered as a bare coloured rectangle would
        read as a different, lesser kind of thing.
        """
        return self._owner._remote_tile_from(
            tile, self._owner._artwork.resolve(tile, icon_size=_PHONE_ICON_SIZE_PX)
        )
