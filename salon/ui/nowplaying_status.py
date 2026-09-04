# SPDX-License-Identifier: GPL-3.0-or-later
"""The console rail's now-playing card: a readout that can be operated.

Three things this owes the room, in order. What is playing — cover, title,
artist, and which application it arrived through (`nowplaying_primary`).
Where it has got to — a timeline that advances locally between MPRIS
snapshots. And the ability to do something about it: a real transport row,
plus a pair of arrows on the heading line when there is more than one media
source (`nowplaying_keys`).

**One source is drawn at a time**, and those arrows are how the others are
reached. That is what makes the card a fixed size; `core/nowplaying_card`
has the reasoning for dropping the old stacked arrangement, and for why the
card no longer asks the rail how much room it has been left.

Every control is a D-pad stop as well as a pointer target. LEFT off the
first column of the home screen enters the card; `ui/home_now_playing`
drives that path through `move`, `activate` and `set_card_focused`.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from salon.core.actions import Action  # noqa: E402
from salon.core.nowplaying import PLAYING, Player, describe  # noqa: E402
from salon.core.nowplaying_card import (  # noqa: E402
    HEADING,
    CardKey,
    select_source,
    source_position,
    step_source,
)
from salon.ui.nowplaying_keys import CardKeys  # noqa: E402
from salon.ui.nowplaying_primary import PrimaryReadout  # noqa: E402
from salon.ui.nowplaying_progress import MediaProgress, set_transport_icon  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

_PLAY = ("media-playback-start-symbolic", "Play")
_PAUSE = ("media-playback-pause-symbolic", "Pause")


class NowPlayingStatus(Gtk.Box):
    def __init__(
        self,
        scale: Scale,
        on_activate: Callable[[str], None] | None = None,
        on_skip: Callable[[str, bool], None] | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("salon-now-playing")
        self.add_css_class("salon-console-block")
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.START)
        self.set_visible(False)
        self.set_accessible_role(Gtk.AccessibleRole.GROUP)
        self.update_property([Gtk.AccessibleProperty.LABEL], ["Now playing"])
        self._on_activate = on_activate
        self._on_skip = on_skip
        self._players: tuple[Player, ...] = ()
        self._index = 0
        # The bus name currently drawn, which is what a fresh snapshot is
        # matched against: the card follows the source someone chose, not
        # the slot it happened to be in.
        self._showing = ""
        self._artwork_for: Callable[[str], Gdk.Paintable | None] | None = None

        self._keys = CardKeys(
            scale,
            {
                CardKey.PREVIOUS_SOURCE: lambda: self._pick(forward=False),
                CardKey.NEXT_SOURCE: lambda: self._pick(forward=True),
                CardKey.PREVIOUS_TRACK: lambda: self._skip(forward=False),
                CardKey.PLAY_PAUSE: self._toggle,
                CardKey.NEXT_TRACK: lambda: self._skip(forward=True),
            },
        )
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.add_css_class("salon-now-playing-header")
        heading = Gtk.Label(label=HEADING)
        heading.add_css_class("salon-console-heading")
        heading.set_halign(Gtk.Align.START)
        heading.set_hexpand(True)
        header.append(heading)
        header.append(self._keys.picker)
        self.append(header)

        self._readout = PrimaryReadout(scale, None if on_activate is None else self._toggle)
        self.append(self._readout)
        self._progress = MediaProgress(show_state=False)
        self.append(self._progress)
        self._keys.transport.set_visible(on_activate is not None or on_skip is not None)
        self.append(self._keys.transport)
        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self.set_spacing(scale.px(12.0))
        self._readout.set_scale(scale)
        self._keys.set_scale(scale)

    def set_artwork(self, artwork: Gdk.Paintable | None) -> None:
        self._readout.set_artwork(artwork)

    def clear(self) -> None:
        self.set_artwork(None)
        self._players = ()
        self._index = 0
        self._showing = ""
        self._keys.set_sources(0)
        self._progress.set_snapshot(-1, 0, False)
        self.set_visible(False)

    def set_players(
        self,
        players: tuple[Player, ...],
        *,
        current_source: str = "",
        artwork_for: Callable[[str], Gdk.Paintable | None] | None = None,
    ) -> None:
        """Take a fresh MPRIS snapshot, keeping the source that is showing.

        The players arrive in discovery order and stay in it — sorting the
        chosen one to the front would move every other source out from
        under the picker each time the front one changed.
        """
        if not players:
            self.clear()
            return
        self._artwork_for = artwork_for
        self._players = tuple(players)
        self._index = select_source(
            [player.bus_name for player in self._players], self._showing, current_source
        )
        self._render()

    def _render(self) -> None:
        player = self._players[self._index]
        self._showing = player.bus_name
        playing = player.status == PLAYING
        self._keys.position.set_label(source_position(self._index, len(self._players)))
        self._keys.set_sources(len(self._players))
        title, _detail = describe(player, include_status=False)
        self._readout.set_track(
            title, player.artist.strip(), player.identity.strip(), playing=playing
        )
        set_transport_icon(self._keys[CardKey.PLAY_PAUSE], *(_PAUSE if playing else _PLAY))
        self._progress.set_snapshot(player.position_us, player.length_us, playing)
        if self._artwork_for is not None:
            self.set_artwork(self._artwork_for(player.art_url))
        self._keys[CardKey.PREVIOUS_TRACK].set_sensitive(player.can_go_previous)
        self._keys[CardKey.NEXT_TRACK].set_sensitive(player.can_go_next)
        self.set_visible(True)

    # --- the D-pad path, delegated to the keys ---------------------------

    @property
    def has_media(self) -> bool:
        return bool(self._players)

    @property
    def cursor_hint(self) -> tuple[str, str]:
        return self._keys.hint

    @property
    def cursor_widget(self) -> Gtk.Widget | None:
        return self._keys.widget

    def set_card_focused(self, focused: bool) -> None:
        self._keys.set_focused(focused)

    def enter_cursor(self) -> None:
        self._keys.enter()

    def move(self, action: Action) -> bool:
        return self._keys.move(action)

    def activate(self) -> None:
        self._keys.activate()

    # --- what the keys do ------------------------------------------------

    def _pick(self, *, forward: bool) -> None:
        if len(self._players) <= 1:
            return
        self._index = step_source(self._index, len(self._players), forward=forward)
        self._render()

    def _toggle(self) -> None:
        if self._on_activate is not None:
            self._on_activate(self._showing)

    def _skip(self, *, forward: bool) -> None:
        if self._on_skip is not None:
            self._on_skip(self._showing, forward)
