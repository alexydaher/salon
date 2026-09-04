# SPDX-License-Identifier: GPL-3.0-or-later
"""The now-playing card's keys, and the D-pad's ring over them.

Two rows of them. The picker rides on the heading line and chooses which of
several media sources the card is describing; the transport sits under the
timeline and acts on whichever one that is. Both are real buttons, because
the rail is inside the pointer's reach and a glyph reporting a state it
cannot change is furniture — and both are D-pad stops, because a pointer is
not what a television is driven with.

`core/nowplaying_card` says where the ring goes and what each key means;
this owns the widgets and nothing else. The card itself never looks a
button up by position, so the two cannot disagree about the order.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.core.actions import Action  # noqa: E402
from salon.core.nowplaying_card import (  # noqa: E402
    KEY_HINTS,
    CardCursor,
    CardKey,
    card_rows,
    clamp_cursor,
    entry_cursor,
    key_at,
    move_cursor,
)
from salon.ui.nowplaying_progress import transport_button  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

# Design units, not pixels: the rail is 336du wide whatever the panel is, so
# a transport drawn at fixed pixel sizes is too wide for its own block on
# anything smaller than a 1080p window — measured, GTK refusing to fit a
# 174px row into 140px of card on a 1024x640 surface.
_SKIP_KEY_DU: float = 20.0
_PLAY_KEY_DU: float = 26.0
# The picker rides on the heading line, so it is sized against that line
# rather than against the transport it has nothing to do with.
_PICK_KEY_DU: float = 15.0

_SIZES: dict[CardKey, float] = {
    CardKey.PREVIOUS_SOURCE: _PICK_KEY_DU,
    CardKey.NEXT_SOURCE: _PICK_KEY_DU,
    CardKey.PREVIOUS_TRACK: _SKIP_KEY_DU,
    CardKey.PLAY_PAUSE: _PLAY_KEY_DU,
    CardKey.NEXT_TRACK: _SKIP_KEY_DU,
}

_ICONS: dict[CardKey, str] = {
    CardKey.PREVIOUS_SOURCE: "go-previous-symbolic",
    CardKey.NEXT_SOURCE: "go-next-symbolic",
    CardKey.PREVIOUS_TRACK: "media-skip-backward-symbolic",
    CardKey.PLAY_PAUSE: "media-playback-pause-symbolic",
    CardKey.NEXT_TRACK: "media-skip-forward-symbolic",
}


class CardKeys:
    """Every control on the card, plus which one the ring is resting on."""

    def __init__(self, scale: Scale, actions: dict[CardKey, Callable[[], None]]) -> None:
        self._actions = actions
        self._buttons = {
            key: transport_button(
                _ICONS[key], KEY_HINTS[key][0], handler, size_px=scale.px(_SIZES[key])
            )
            for key, handler in actions.items()
        }
        self._sources = 0
        self._cursor = CardCursor()
        self._focused = False

        # The picker: two arrows and the pair of numbers they move through.
        # Hidden outright below two sources rather than greyed — there is
        # nothing to pick, and two dead keys on the heading line would be
        # the widest thing on the card that never does anything.
        self.picker = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.picker.add_css_class("salon-now-playing-picker")
        self.picker.set_valign(Gtk.Align.CENTER)
        self.picker.set_visible(False)
        self.position = Gtk.Label(label="")
        self.position.add_css_class("salon-now-playing-position")
        self.picker.append(self[CardKey.PREVIOUS_SOURCE])
        self.picker.append(self.position)
        self.picker.append(self[CardKey.NEXT_SOURCE])
        for key in (CardKey.PREVIOUS_SOURCE, CardKey.NEXT_SOURCE):
            self[key].add_css_class("pick")

        self.transport = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.transport.add_css_class("salon-now-playing-transport")
        self.transport.set_halign(Gtk.Align.CENTER)
        for key in (CardKey.PREVIOUS_TRACK, CardKey.PLAY_PAUSE, CardKey.NEXT_TRACK):
            self.transport.append(self[key])
        self[CardKey.PLAY_PAUSE].add_css_class("primary")
        self.set_scale(scale)

    def __getitem__(self, key: CardKey) -> Gtk.Button:
        return self._buttons[key]

    def set_scale(self, scale: Scale) -> None:
        self.picker.set_spacing(scale.px(6.0))
        self.transport.set_spacing(scale.px(10.0))
        for key, button in self._buttons.items():
            image = button.get_child()
            if isinstance(image, Gtk.Image):
                image.set_pixel_size(scale.px(_SIZES[key]))

    def set_sources(self, count: int) -> None:
        """How many media sources exist, which is what says whether the
        picker is drawn at all — and so how many rows the ring can visit."""
        self._sources = count
        self.picker.set_visible(count > 1)
        self._sync()

    # --- the D-pad path -------------------------------------------------

    @property
    def hint(self) -> tuple[str, str]:
        key = key_at(self._rows, self._cursor)
        return KEY_HINTS[key] if key is not None else ("Now playing", "")

    @property
    def widget(self) -> Gtk.Widget | None:
        key = key_at(self._rows, self._cursor)
        return self._buttons.get(key) if key is not None else None

    def set_focused(self, focused: bool) -> None:
        self._focused = focused
        self._sync()

    def enter(self) -> None:
        """Park the ring where a press in from the tiles should land."""
        self._cursor = entry_cursor(self._rows)
        self._sync()

    def move(self, action: Action) -> bool:
        """Move the ring. False means the press has left the card."""
        moved = move_cursor(self._rows, self._cursor, action)
        if moved is None:
            return False
        self._cursor = moved
        self._sync()
        return True

    def activate(self) -> None:
        """OK on whichever key the ring is resting on.

        A key the player says it cannot serve is greyed, and OK on it does
        nothing: a button that looks unavailable and acts anyway is worse
        than one that looks unavailable.
        """
        key = key_at(self._rows, self._cursor)
        if key is None or not self._buttons[key].get_sensitive():
            return
        self._actions[key]()

    @property
    def _rows(self) -> tuple[tuple[CardKey, ...], ...]:
        return card_rows(self._sources)

    def _sync(self) -> None:
        self._cursor = clamp_cursor(self._rows, self._cursor)
        current = key_at(self._rows, self._cursor) if self._focused else None
        for key, button in self._buttons.items():
            if key is current:
                button.add_css_class("cursor")
            else:
                button.remove_css_class("cursor")
