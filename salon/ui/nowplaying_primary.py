# SPDX-License-Identifier: GPL-3.0-or-later
"""The now-playing card's own readout: cover, track, artist, application.

One arrangement, always: the cover beside the text. There used to be a
second, taller one — the cover standing above the text at the column's full
width — chosen against whatever height the rail had left, which meant the
same television drew a different card depending on whether the pairing card
was standing under it. See `core/nowplaying_card`.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gtk, Pango  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.ui.nowplaying_progress import SquareCover  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


class PrimaryReadout(Gtk.Box):
    """What is playing, and the one part of the card a press anywhere in
    toggles — the transport keys and the source rows below it address
    particular things, and a container gesture over them would make "which
    source did I just pause?" depend on pixels."""

    def __init__(self, scale: Scale, on_activate: Callable[[], None] | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class("salon-now-playing-primary")
        # STATUS keeps track changes announced without taking Salon's cursor.
        self.set_accessible_role(Gtk.AccessibleRole.STATUS)
        self._on_activate = on_activate
        if on_activate is not None:
            self.add_css_class("salon-now-playing-active")
            self.set_cursor(Gdk.Cursor.new_from_name("pointer", None))
            click = Gtk.GestureClick()
            click.connect("released", self._on_click)
            self.add_controller(click)

        # Cover art stays clean — the play/pause state lives in the
        # transport row below, not on the artwork.
        self._art = SquareCover()
        self.append(self._art)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        labels.set_valign(Gtk.Align.CENTER)
        labels.set_hexpand(True)
        self.append(labels)
        self._labels = labels
        self._title = Gtk.Label()
        self._title.add_css_class("salon-now-playing-title")
        self._title.set_halign(Gtk.Align.START)
        self._title.set_xalign(0.0)
        # Two lines, then ellipsize. The column is 275px wide and a track
        # title is the one string in it that cannot be shortened without
        # losing the answer: "Nick Cave & The Bad S…" was the measurement
        # that put this here.
        self._title.set_wrap(True)
        self._title.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self._title.set_lines(2)
        self._title.set_ellipsize(Pango.EllipsizeMode.END)
        labels.append(self._title)
        self._detail = Gtk.Label()
        self._detail.add_css_class("salon-now-playing-detail")
        self._detail.set_halign(Gtk.Align.START)
        self._detail.set_xalign(0.0)
        self._detail.set_ellipsize(Pango.EllipsizeMode.END)
        labels.append(self._detail)
        # The application is a different kind of fact from the artist — it
        # says where the sound is coming from, not who made it — so it is a
        # badge rather than a third clause joined on with a "·".
        self._badge = Gtk.Label()
        self._badge.add_css_class("salon-now-playing-badge-label")
        self._badge.set_ellipsize(Pango.EllipsizeMode.END)
        # The pill is the box; the label inside it carries only type. With
        # the padding on the label itself, GTK4's content box came out one
        # pixel short of the text it had just measured and the ellipsis ate
        # two characters — "Spoti…". The box's natural width is its padding
        # plus the label's own, which loses nothing.
        badge_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        badge_row.add_css_class("salon-now-playing-badge")
        badge_row.set_halign(Gtk.Align.START)
        badge_row.append(self._badge)
        badge_row.set_visible(False)
        self._badge_row = badge_row
        labels.append(badge_row)
        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self.set_spacing(scale.px(14.0))
        self._labels.set_spacing(scale.px(3.0))
        self._art.set_size(scale.px(tokens.NOW_PLAYING_COVER_DU))

    def set_track(self, title: str, detail: str, badge: str, *, playing: bool) -> None:
        self._title.set_label(title)
        self._detail.set_label(detail)
        self._detail.set_visible(bool(detail))
        self._badge.set_label(badge)
        self._badge_row.set_visible(bool(badge))
        phrase = f"{'Playing' if playing else 'Paused'} {title}"
        for part in (detail, badge):
            if part:
                phrase += f", {part}"
        self.update_property([Gtk.AccessibleProperty.LABEL], [phrase])

    def set_artwork(self, artwork: Gdk.Paintable | None) -> None:
        self._art.set_paintable(artwork)

    def _on_click(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        """A press on the readout toggles the player it is describing.

        On release rather than on press, and only the first of a double:
        the second click of an accidental double would otherwise pause and
        resume, which looks exactly like nothing happening.
        """
        if n_press != 1 or self._on_activate is None:
            return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self._on_activate()
