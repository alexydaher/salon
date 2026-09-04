# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow: the D-pad inside the rail's now-playing card.

The card is a transport, and until this existed it was a transport only a
pointer could reach — on a machine whose whole point is that it is driven
from a sofa. LEFT off the first column of the tiles is the way in, RIGHT
off the end of a row is the way out, and the ring in the card is the same
one cursor the top bar and the tiles pass between themselves: never two of
them lit at once.

`core/nowplaying_card` owns where the cursor goes; this owns when the card
has it.
"""

from salon.services.component import ServiceComponent
from salon.ui.home_shared import _DIRECTIONS, Action

# The presses the card takes while it holds the ring. Deliberately short:
# SEARCH, PLAY_PAUSE, OPTIONS and MENU mean the same thing wherever the ring
# is resting, and a mode that swallows them is a place the rest of the
# remote quietly stops working.
_CARD_ACTIONS = (*_DIRECTIONS, Action.OK, Action.BACK)


class HomeNowPlayingCursor(ServiceComponent):
    @property
    def _card(self):
        return self._owner._now_playing_status

    def _enter_now_playing(self) -> bool:
        """LEFT off the first column: into the rail's card, if there is one.

        False when nothing is playing, and the caller rubber-bands instead
        — which is what LEFT there has always done and is still the right
        answer for an empty rail.
        """
        if not self._card.has_media:
            return False
        self._card.enter_cursor()
        self._set_card_focused(True)
        return True

    def _set_card_focused(self, focused: bool) -> None:
        self._owner._card_focused = focused
        self._card.set_card_focused(focused)
        if focused:
            # One ring on screen at a time, the same rule the top bar and
            # the tiles already keep between themselves.
            self._owner._nav_focused = False
            self._owner._status_bar.set_nav_focused(False)
            self._publish_card_detail()
        else:
            self._owner._detail_bar.clear_nav_target()
        self._owner._update_focus()
        widget = self._card.cursor_widget if focused else self._owner._focused_widget()
        if widget is not None:
            self._owner._publish_active_descendant(widget)
        self._owner._update_legend()

    def _drop_card_focus(self) -> None:
        if not self._owner._card_focused:
            return
        self._owner._card_focused = False
        self._card.set_card_focused(False)

    def _sync_card_focus(self) -> None:
        """The card can go away under the ring — the last player quits and
        the whole block hides. Put the ring back on the tiles rather than
        leaving it on a widget nobody is drawing."""
        if self._owner._card_focused and not self._card.has_media:
            self._set_card_focused(False)

    def _publish_card_detail(self) -> None:
        title, detail = self._card.cursor_hint
        self._owner._detail_bar.set_nav_target(title, detail)

    def _card_takes(self, action: Action) -> bool:
        """Whether the card wants this press — and act on it if it does."""
        if not (self._owner._card_focused and action in _CARD_ACTIONS):
            return False
        self._handle_card_action(action)
        return True

    def _handle_card_action(self, action: Action) -> None:
        if action is Action.BACK:
            self._set_card_focused(False)
            return
        if action is Action.OK:
            self._card.activate()
            self._publish_card_detail()
            self._owner._publish_remote_state()
            return
        if not self._card.move(action):
            # RIGHT off the end of a row is the only press that leaves, and
            # it lands back on the tiles it came from.
            self._set_card_focused(False)
            return
        self._publish_card_detail()
        widget = self._card.cursor_widget
        if widget is not None:
            self._owner._publish_active_descendant(widget)
