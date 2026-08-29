# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_rows import _RowWidgets
from salon.ui.home_shared import (
    Gtk,
    RemoteNowPlaying,
    RemoteState,
    TileWidget,
    nowplaying,
    tokens,
)


class HomeFocusController(ServiceComponent):
    def _update_focus(self, *, animate: bool = True) -> None:
        menu_focused = (
            self._owner._system_menu.get_visible() or self._owner._tile_menu.get_visible()
        )
        for r, row in enumerate(self._owner._rows):
            focused_row = r == self._owner._focus.row
            for c, widget in enumerate(row.tiles):
                # Nothing in the rows carries the ring while the top bar
                # holds the cursor: two full-strength highlights on screen
                # leaves no answer to "what does OK do right now".
                widget.set_focused(
                    not self._owner._nav_focused
                    and not menu_focused
                    and focused_row
                    and c == self._owner._focus.col
                )
            if focused_row and not self._owner._nav_focused and not menu_focused:
                row.heading.add_css_class("row-focused")
            else:
                row.heading.remove_css_class("row-focused")

        tile = self._owner._catalog.tile_at(self._owner._focus.row, self._owner._focus.col)
        self._owner._detail_bar.set_tile(tile)
        if tile is not None:
            self._owner._settings.set_string("last-focused-tile", tile.id)
            focused_widget = self._focused_widget()
            if focused_widget is not None and not menu_focused:
                self._owner._backdrop.set_focus(focused_widget.artwork_accent)
                self._publish_active_descendant(focused_widget)
        self._update_backdrop_position()
        # Every row follows the one column the cursor carries, so the grid
        # stays aligned and moving down lands on the tile that was already
        # under the cursor rather than sliding sideways on arrival. A row
        # already at its target is a no-op inside the spring, so this costs
        # nothing for the rows the press did not move.
        for index in range(len(self._owner._rows)):
            self._update_row_scroll(
                index, self._owner._focus.column_for(index), animate=animate
            )
        self._owner._update_row_anchor(animate=animate)
        self._publish_remote_state()

    def _publish_remote_state(self) -> None:
        """Offer the phone a fresh snapshot of the television.

        Called from every place the phone's view could have changed — the
        cursor moving, the catalogue rebuilding, a player appearing, a
        screen opening. That is a lot of call sites, and it is affordable
        because `StateFeed` compares the snapshot to the last one and does
        nothing if they match: no JSON is produced until a phone actually
        polls for a version it has not seen.

        Skipped outright when the server is down, which is most of the time.
        """
        if not self._owner._pairing.running:
            return
        player = self._owner._current_player
        playing: RemoteNowPlaying | None = None
        if player is not None:
            title, detail = nowplaying.describe(player)
            # An `https://` cover goes to the phone as it stands, because
            # the phone has the network and proxying someone else's CDN
            # through the television buys nothing. A `file://` one becomes
            # `has_art`, and Salon serves the bytes at /np-art.
            remote_cover = player.art_url.startswith(("http://", "https://"))
            playing = RemoteNowPlaying(
                title=title,
                detail=detail,
                playing=player.status == nowplaying.PLAYING,
                can_next=player.can_go_next,
                can_previous=player.can_go_previous,
                art_url=player.art_url if remote_cover else "",
                # Not a stat: this runs on every cursor movement, and
                # /np-art answers 404 for a file that turns out to be
                # unreadable — which the phone's card already falls back
                # from rather than drawing a broken glyph.
                has_art=player.art_url.startswith("file://"),
            )
        timing = self._owner._repeat_timing()
        self._owner._pairing.publish(
            RemoteState(
                rows=self._owner._remote_rows,
                now_playing=playing,
                focus=(self._owner._focus.row, self._owner._focus.col),
                screen=self._current_screen(),
                # The phone opens its keyboard by itself when the television
                # puts a field on screen, rather than making someone find
                # the tab for it while an empty box blinks at them.
                wants_text=self._owner._text_entry.get_visible()
                or self._owner._search.get_visible(),
                # And what is in it, so the phone's own field can show the
                # same thing rather than an empty box whose Send appends a
                # second copy of a half-typed title.
                text=self._field_text(),
                remote_input=self._owner._pointer.ready,
                repeat_delay_ms=round(timing.initial_delay * 1000),
                repeat_interval_ms=round(timing.interval * 1000),
                accent=self._owner._settings.get_string("accent-color") or "#E8A33D",
                # Named separately from `screen`, which carries the same
                # string but as one of six reserved words. The page hides
                # half its own controls on this, so it cannot be guessing.
                app=self._app_in_front(),
                volume=self._owner._phone_volume,
                muted=self._owner._phone_muted,
            )
        )

    def _field_text(self) -> str:
        """What the television's on-screen field currently holds, or "".

        Only ever a field Salon is itself drawing. Text going to a launched
        application through the input grant has no readable box at the other
        end, and claiming otherwise would put a stale mirror on the phone.
        """
        if self._owner._text_entry.get_visible():
            return self._owner._text_entry.current_text()
        if self._owner._search.get_visible():
            return self._owner._search.current_text()
        return ""

    def _app_in_front(self) -> str:
        """The title of the application covering the television, or "".

        Same test `_current_screen` makes, named on its own because the
        phone reshapes itself around the answer: with an app up, the D-pad
        and Search do nothing at all, and only the trackpad, the volume and
        Menu still mean something.
        """
        if (
            self._owner._child_active
            or self._owner._pointer_mode
            or self._owner._launcher.has_child
        ):
            return self._owner._launcher.child_title or "an app"
        return ""

    def _current_screen(self) -> str:
        """Which screen is in front, for the phone's title bar.

        Ordered the way `_handle_action` is: the thing that would take the
        next press is the thing the phone should be naming.
        """
        if self._owner._system_menu.get_visible() or self._owner._tile_menu.get_visible():
            return "menu"
        if self._owner._text_entry.get_visible():
            return "keyboard"
        if self._owner._settings_screen.get_visible():
            return "settings"
        if self._owner._search.get_visible():
            return "search"
        if self._owner._apps_grid.get_visible():
            return "apps"
        if self._owner._launcher.is_launching:
            return f"Opening {self._owner._launcher.child_title or 'an app'}…"
        # pointer_mode as well as child_active: a *browser* tile puts Salon
        # behind Chrome without ever setting child_active, so testing only
        # the latter told the phone it was on the home screen while Netflix
        # was on the television.
        if self._owner._child_active or self._owner._pointer_mode:
            return self._owner._launcher.child_title or "app"
        return "home"

    def _publish_active_descendant(self, widget: Gtk.Widget) -> None:
        """aria-activedescendant, the standard answer for a composite widget
        that keeps the keyboard focus and moves a cursor inside itself. The
        top bar takes it while the cursor is up there, so what is announced
        and what is drawn with the ring are never two different things."""
        menu = next(
            (
                menu
                for menu in (self._owner._system_menu, self._owner._tile_menu)
                if menu.get_visible()
            ),
            None,
        )
        if menu is not None and menu.selected_row is not None:
            target = menu.selected_row
        elif self._owner._nav_focused and self._owner._status_bar.selected_button is not None:
            target = self._owner._status_bar.selected_button
        else:
            target = widget
        self._owner.update_relation([Gtk.AccessibleRelation.ACTIVE_DESCENDANT], [target])

    def _focused_widget(self) -> TileWidget | None:
        if not (0 <= self._owner._focus.row < len(self._owner._rows)):
            return None
        tiles = self._owner._rows[self._owner._focus.row].tiles
        if not (0 <= self._owner._focus.col < len(tiles)):
            return None
        return tiles[self._owner._focus.col]

    def _update_backdrop_position(self) -> None:
        """Put the ambient pool of light roughly behind the focused tile."""
        if (
            not self._owner._rows
            or self._owner._viewport_width <= 0
            or self._owner._viewport_height <= 0
        ):
            return
        metrics = self._owner._rows[min(self._owner._focus.row, len(self._owner._rows) - 1)].metrics
        x = (self._owner._safe_margin + metrics.width / 2.0) / self._owner._viewport_width
        y = tokens.ROW_ANCHOR_FRACTION
        self._owner._backdrop.set_focus_position(x, y)

    def _row_scroll_x(self, row: _RowWidgets, col: int) -> float:
        """Left-anchor the focused tile's *card* at the safe-area margin, but
        never scroll past the end of the row — stranding empty space at the
        right edge looks broken, and the last screenful of a row reads better
        flush-right than left-anchored with a void beside it.

        Offsets are in tiles-box coordinates, where a tile's card sits one
        bleed to the right of the tile widget's own origin.
        """
        bleed = row.metrics.bleed
        max_offset = self._owner._safe_margin - bleed
        desired = max_offset - col * row.metrics.step
        min_offset = min(
            max_offset,
            self._owner._viewport_width - self._owner._safe_margin - bleed - row.content_width,
        )
        return max(min_offset, min(max_offset, desired))

    def _update_row_scroll(self, row_index: int, col: int, *, animate: bool) -> None:
        if not (0 <= row_index < len(self._owner._rows)):
            return
        row = self._owner._rows[row_index]
        target = self._row_scroll_x(row, col)
        row.scroller.animate_to(target) if animate else row.scroller.jump_to(target)
