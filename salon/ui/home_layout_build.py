# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_rows import _RowWidgets
from salon.ui.home_shared import (
    _EDGE_FADE_DU,
    _FALLBACK_VIEWPORT_HEIGHT_PX,
    Gtk,
    RemoteRow,
    RemoteTile,
    TileWidget,
    metrics_for,
)
from salon.ui.home_viewport import _RowViewport


class HomeLayoutBuilder(ServiceComponent):
    def _rebuild_row_widgets(self) -> None:
        child = self._owner._rows_content.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._owner._rows_content.remove(child)
            child = next_child

        animations = self._owner._animations_enabled
        self._owner._rows = []
        remote_rows: list[RemoteRow] = []
        for row_index, row in enumerate(self._owner._catalog.rows):
            metrics = metrics_for(
                self._owner._scale, row.tile_aspect, size_scale=self._owner._tile_scale
            )

            heading = Gtk.Label(label=row.title or "")
            heading.set_halign(Gtk.Align.START)
            heading.set_xalign(0.0)
            heading.set_yalign(0.5)
            heading.add_css_class("salon-row-heading")
            self._owner._rows_content.put(heading, 0, 0)

            row_viewport = _RowViewport()
            row_viewport.set_overflow(Gtk.Overflow.HIDDEN)
            row_viewport.set_accessible_role(Gtk.AccessibleRole.ROW)
            row_viewport.update_property(
                [Gtk.AccessibleProperty.LABEL], [row.title or "Untitled row"]
            )

            tiles_box = Gtk.Fixed()
            tiles: list[TileWidget] = []
            remote_tiles: list[RemoteTile] = []
            for col, tile in enumerate(row.tiles):
                artwork = self._owner._artwork.resolve(tile, icon_size=round(metrics.height * 0.5))
                # The phone's copy of this tile, built from the artwork that
                # was just resolved rather than resolving it a second time.
                # A symbolic icon is monochrome and reads as a smudge on a
                # phone-sized card, so it counts as no artwork and the
                # accent card is drawn instead — the same judgement the
                # television makes at level 5.
                # Levels: 1 is a real image and fills the card; 3 and 4 are
                # icons drawn small on the accent, exactly as ui/tile.py
                # draws them. Built by the same helper the phone's search
                # results go through, so a result and a home-screen tile are
                # the same card rather than two that drift apart.
                remote_tiles.append(self._owner._remote_tile_from(tile, artwork))
                widget = TileWidget(
                    tile,
                    artwork,
                    metrics,
                    self._owner._scale,
                    animations_enabled=animations,
                    # The detail strip is directly below these rows and
                    # already carries the subtitle in full, unellipsized.
                    # Printing it on the card as well spent the bottom fifth
                    # of every tile echoing a line two rows away.
                    show_subtitle=False,
                )
                self._attach_pointer(widget, row_index, col)
                # Tiles start at x=0, not at -bleed: a child placed at a
                # negative x inside the tiles box is clipped along that
                # edge, which cut the left half of the first tile's bloom
                # clean off. The row's scroll offset carries the bleed
                # instead — see _row_scroll_x.
                tiles_box.put(widget, col * metrics.step, 0.0)
                tiles.append(widget)
            row_viewport.put(tiles_box, 0, 0)
            self._owner._rows_content.put(row_viewport, 0, 0)

            # Never wider than the safe-area margin: the focused tile rests
            # exactly one margin from the left edge, and the last tile of a
            # row rests one from the right, so a wider ramp would be fading
            # the tile the cursor is on.
            widgets = _RowWidgets(
                heading,
                row_viewport,
                tiles_box,
                tiles,
                metrics,
                fade=min(self._owner._scale.du(_EDGE_FADE_DU), self._owner._safe_margin),
            )
            widgets.scroller.set_animations_enabled(animations)
            self._owner._rows.append(widgets)
            remote_rows.append(
                RemoteRow(
                    id=row.id,
                    title=row.title,
                    tiles=tuple(remote_tiles),
                    aspect=row.tile_aspect,
                )
            )

        self._owner._remote_rows = tuple(remote_rows)
        self._owner._row_anchor.set_animations_enabled(animations)
        self._layout_rows()
        # _update_focus publishes, so the phone picks the new catalogue up
        # on its next poll without a second hook here.
        self._owner._update_focus(animate=False)

    def _layout_rows(self) -> None:
        """Position every row at an absolute y, and size the row viewports
        to the full window width so the only horizontal clip is the screen
        edge itself."""
        width = self._owner._viewport_width
        heading_width = max(1, round(width - 2 * self._owner._safe_margin))
        self._owner._recompute_row_tops()
        for index, row in enumerate(self._owner._rows):
            top = self._owner._row_top(index)
            row.heading.set_size_request(heading_width, round(self._owner._heading_height))
            self._owner._rows_content.move(row.heading, self._owner._safe_margin, top)

            row.viewport.set_size_request(width, round(row.metrics.outer_height))
            self._owner._rows_content.move(
                row.viewport, 0.0, self._owner._row_tile_top(index) - row.metrics.bleed
            )
            # The window's width just changed, and the row's fades are a
            # function of it as well as of the scroll offset.
            row.visible_width = float(width)
            row.update_fades()
        self._owner._rows_content.set_size_request(
            width, max(1, round(self._owner._content_height()))
        )
        self._apply_viewport_insets()
        self._update_edge_fades()

    def _update_edge_fades(self) -> None:
        """Fade each band edge by as much as is actually hanging over it.

        A constant fade at both ends is wrong at rest. The band's top is
        exactly where the first row's heading sits when nothing is scrolled,
        so a permanent 40du ramp there dimmed "Favourites" — and only
        "Favourites" — for the whole life of the screen, with no row passing
        under it to justify the softening. The fade exists so a row *leaving*
        the band isn't sliced by a hard clip edge; when nothing is leaving,
        there is nothing to soften.

        So each end fades by min(overflow, 40du): zero when the content ends
        inside the band, ramping in over the first few pixels of travel and
        capping at the full ramp once a row is genuinely passing under a bar.
        """
        fade = self._owner._scale.du(_EDGE_FADE_DU)
        band_height = float(self._owner._viewport_height or _FALLBACK_VIEWPORT_HEIGHT_PX)
        offset = self._owner._row_anchor.value
        above = max(0.0, -offset)
        below = max(0.0, self._owner._content_height() + offset - band_height)
        self._owner._viewport.set_fades(min(fade, above), min(fade, below))

    def _apply_viewport_insets(self) -> None:
        """Shrink the scrolling band to the gap between the two bars.

        The top bar and the detail strip are the two places on this screen
        that *report* — the time, the network, what the cursor is on and
        what OK will do with it — and a row of artwork sliding underneath
        text is unreadable in both directions. This used to be a fade: the
        band covered the whole window and its top and bottom were masked out
        over exactly the bands the bars occupy. That kept them legible and
        still put half-transparent tiles behind them.

        Margins on the viewport host instead, so the clip really happens at
        the bars' edges and no tile pixel is ever drawn in either strip.
        `Gtk.Overflow.HIDDEN` on the viewport does the rest.

        Set here rather than in `_apply_metrics` because the bottom inset is
        *measured* off the detail strip, which changes height with its own
        contents. Assigning an unchanged margin is a no-op in GTK, so the
        steady state costs nothing and this cannot drive a resize loop even
        though `_layout_rows` runs from inside an allocation.
        """
        self._owner._viewport_host.set_margin_top(round(self._owner._top_inset()))
        self._owner._viewport_host.set_margin_bottom(round(self._owner._bottom_inset()))

    def _attach_pointer(self, widget: TileWidget, row: int, col: int) -> None:
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: self._on_tile_clicked(row, col))
        widget.add_controller(click)

        hover = Gtk.EventControllerMotion()
        # `motion`, not `enter`: focus should follow a pointer the user is
        # actually moving, not jump because a row scrolled a different tile
        # under a stationary cursor.
        hover.connect("motion", lambda *_: self._on_tile_hovered(row, col))
        widget.add_controller(hover)

    def _on_tile_clicked(self, row: int, col: int) -> None:
        if self._owner._system_menu.get_visible() or self._owner._launcher.is_launching:
            return
        if (row, col) != self._owner._focus.position:
            self._owner._focus.jump_to(row, col)
            self._owner._update_focus()
        self._owner._launch_focused()

    def _on_tile_hovered(self, row: int, col: int) -> None:
        if not self._owner._pointer_visible:
            return  # a tile scrolled under a parked cursor, not a real hover
        if self._owner._system_menu.get_visible() or self._owner._launcher.is_launching:
            return
        if (row, col) == self._owner._focus.position:
            return
        self._owner._focus.jump_to(row, col)
        self._owner._update_focus()
