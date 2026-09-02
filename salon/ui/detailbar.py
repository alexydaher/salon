# SPDX-License-Identifier: GPL-3.0-or-later
"""The bottom band: what the cursor is on, and what OK will do to it.

Two problems, one strip.

The first is that a tile's card carries about twenty characters of title at
three metres, and a great many things a launcher can start are not
distinguishable in twenty characters — two `.desktop` entries called
"Document Scanner" and "Document Viewer" render identically, and a URL tile
called "Sport" says nothing about which site it opens. The card is the
wrong place to fix that: making it wider costs a column, and making the
type smaller costs the sofa. A single full-width line under the rows costs
neither.

The second is that Salon's home screen was measured using 21% of the panel
it was drawn on. The rows sit against the top, the last one rises to the
anchor line, and everything below it was empty — on a television, in a dark
room, that reads as an interface that failed to finish loading. The
backdrop now lights that space; this gives it something to say.

It is deliberately *not* a hero panel with big artwork. A hero would
duplicate the tile the cursor is already on, one row above it, at three
times the size — and it would have to animate on every cursor move, which
is exactly the motion §7.3 says to spend sparingly. One line of text that
changes is enough, and it stays legible while a held direction races
through a row.

Two things left this widget on 2026-08-25, for the same reason: a strip
that costs a seventh of the screen's height has to spend all of it on
things the card cannot say.

* **The subtitle is no longer drawn on the tile face** (`show_subtitle` in
  `ui/tile.py`, off for home rows). It was on the card *and* here, two
  lines apart, so a third of this strip was an echo. The tile keeps the
  artwork and the title; the second line of prose lives down here, once.
* **The button legend moved out** to `ui/legend.py`. It was line three
  here, which meant it was rebuilt on every cursor move to say something
  that had not changed, and that it could only ever be a fact about the
  selection when it is really a fact about the mode.

There is no card behind it any more either — no border, no fill, no
shadow. The rows are inset out of this band (`_apply_viewport_insets`), so
nothing is drawn behind the strip for a scrim to separate it from, and a
bordered box floating in the corner reads as a dialog that failed to close.

The strip reserves its own height in `HomeView`'s bottom inset, so the rows
never scroll underneath it. Now-playing status lives independently at the
top centre, leaving this band to describe the cursor and its controls.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gtk, Pango  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.core.model import LaunchKind, Tile  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


def describe(tile: Tile) -> str:
    """What pressing OK on this tile is going to do, in the user's terms.

    Says the *destination*, not the mechanism: "Opens netflix.com" rather
    than naming a browser binary and a flag set the user never chose. The
    one case that names the tool is a raw command, where the command is the
    only true answer.
    """
    launch = tile.launch
    if launch.kind is LaunchKind.URL:
        site = launch.target.split("://", 1)[-1].split("/", 1)[0]
        opened = f"Opens {site or launch.target}"
        return f"{opened} · full screen" if launch.fullscreen else opened
    if launch.kind is LaunchKind.DESKTOP:
        return "Starts an installed application"
    if launch.kind is LaunchKind.FLATPAK:
        return "Starts a Flatpak application"
    if launch.kind is LaunchKind.COMMAND:
        return f"Runs {launch.target}"
    if launch.kind is LaunchKind.BUILTIN:
        return "Opens a part of Salon"
    return ""


class DetailBar(Gtk.Box):
    """A title and description on one baseline, pinned bottom-left."""

    def __init__(self, scale: Scale) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class("salon-detail-bar")
        self.set_valign(Gtk.Align.END)
        self.set_halign(Gtk.Align.FILL)
        # Takes whatever the legend beside it does not, and ellipsizes
        # there. It used to ask for a fixed 760du and grow past it, because
        # a size request is a minimum: at 1280 wide the description ran
        # straight through the legend's first chip.
        self.set_hexpand(True)
        self.set_can_target(False)
        # Announced by the container that owns the cursor instead: this is a
        # readout of the selection, and a screen reader that read it as well
        # would say the focused tile's name twice.
        self.set_accessible_role(Gtk.AccessibleRole.PRESENTATION)

        self._title = Gtk.Label()
        self._title.add_css_class("salon-detail-title")
        self._title.set_halign(Gtk.Align.START)
        self._title.set_xalign(0.0)
        self._title.set_ellipsize(Pango.EllipsizeMode.END)
        self._title.set_valign(Gtk.Align.BASELINE)
        self.append(self._title)

        self._detail = Gtk.Label()
        self._detail.add_css_class("salon-detail-body")
        self._detail.set_halign(Gtk.Align.START)
        self._detail.set_xalign(0.0)
        self._detail.set_ellipsize(Pango.EllipsizeMode.END)
        self._detail.set_valign(Gtk.Align.BASELINE)
        self.append(self._detail)

        self._tile: Tile | None = None
        self._nav: tuple[str, str] | None = None
        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        safe_margin = scale.safe_margin_px
        self.set_margin_start(safe_margin)
        self.set_margin_end(safe_margin)
        self.set_margin_bottom(scale.px(tokens.BOTTOM_CHROME_MARGIN_DU))
        # Clear air above the strip, and deliberately part of the widget's
        # own height: HomeView reserves whatever this measures, so keeping
        # the gap here means there is exactly one place that decides how
        # much room the strip takes. Without it the last row's title and
        # the strip's title touch, which reads as one broken paragraph.
        self.set_margin_top(0)
        self.set_spacing(scale.px(16.0))

    def set_tile(self, tile: Tile | None) -> None:
        self._tile = tile
        self._refresh()

    def set_nav_target(self, title: str, _detail: str) -> None:
        """Describe the top bar's button instead of the tiles.

        Outranks both of the others while it is set, because it is the only
        one of the three that the ring is actually on: with the cursor up in
        the corner the strip was still describing whichever tile had been
        left behind, which is a readout of the selection pointing at
        something that is no longer selected.
        """
        self._nav = (title, "")
        self._refresh()

    def clear_nav_target(self) -> None:
        self._nav = None
        self._refresh()

    def _refresh(self) -> None:
        tile = self._tile
        if self._nav is not None:
            title, detail = self._nav
            self._title.set_label(title)
            self._detail.set_label(detail)
            return
        if tile is None:
            # Empty rather than hidden: a strip that comes and goes moves
            # every row on the screen by its own height as it does.
            self._title.set_label("")
            self._detail.set_label("")
            return
        # The subtitle is here instead of on the card. Repeat the title only
        # when a compact card is likely to have truncated it.
        self._title.set_label(tile.title if len(tile.title) > 22 else "")
        parts = [part for part in (tile.subtitle, describe(tile)) if part]
        self._detail.set_label(" · ".join(parts))
