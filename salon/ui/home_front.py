# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.core.front import (
    Effect,
    Event,
    Front,
    Returned,
    SalonFocus,
    covers_screen,
    step,
)
from salon.services.component import ServiceComponent
from salon.ui.home_shared import _RELAUNCH_DELAY_MS, GLib, Gtk, Tile


class HomeFrontController(ServiceComponent):
    """What is in front of Salon: the adapter around `core/front`.

    The state is `HomeView._front`, changed only by `_feed_front`, which runs
    the pure `step` and carries out the effects it returns. Nothing else
    writes it and nothing keeps a second copy of the answer in a flag.
    """

    def _salon_in_front(self) -> bool:
        """Whether Salon's own window has the compositor's focus.

        Read, never remembered — see `core/front`. Answers False without a
        window at all, so with nothing to ask no press is ever taken for a
        return.
        """
        root = self._owner.get_root()
        if not isinstance(root, Gtk.Window):
            return False
        return bool(root.get_property("is-active"))

    def _app_covering(self) -> bool:
        """Is another application in front of Salon right now?"""
        return covers_screen(self._owner._front, salon_focused=self._salon_in_front())

    def _pointer_driving(self) -> bool:
        """Whether the cursor is being driven over an application."""
        return bool(self._owner._front.front is Front.APP_POINTER)

    def _feed_front(self, event: Event) -> None:
        state, effects = step(self._owner._front, event)
        # Before the effects run: one of them calls the launcher, which calls
        # back into `_on_returned`, which feeds this again.
        self._owner._front = state
        for effect in effects:
            self._run_front_effect(effect)

    def _run_front_effect(self, effect: Effect) -> None:
        if effect is Effect.MARK_RETURNED:
            # Fires `on_returned`, which feeds `Returned` and republishes the
            # phone's snapshot. With no child to finish nothing calls back,
            # and whatever was queued would wait for a return that is not
            # coming — so it is fed here.
            had_child = self._owner._launcher.has_child
            self._owner._launcher.mark_returned()
            if not had_child:
                self._feed_front(Returned())
                self._owner._publish_remote_state()
        elif effect is Effect.SHOW_POWER:
            GLib.timeout_add(_RELAUNCH_DELAY_MS, self._show_power)
        elif effect is Effect.START_PENDING_LAUNCH:
            pending, self._owner._pending_launch = self._owner._pending_launch, None
            if pending is not None:
                # The old one has just gone; give the compositor a moment to
                # hand focus back before spawning the next, because return
                # detection for *that* launch is the window going inactive
                # and it can only go inactive from active.
                GLib.timeout_add(_RELAUNCH_DELAY_MS, lambda: self._start_pending(pending))

    def _show_power(self) -> bool:
        self._owner._show_power_menu()
        return bool(GLib.SOURCE_REMOVE)

    def _start_pending(self, tile: Tile) -> bool:
        self._owner._launch_tile(tile)
        return bool(GLib.SOURCE_REMOVE)

    def _reconcile_child_state(self) -> None:
        """Clear "an app is out there" once Salon is provably back in front.

        Called before a press is routed, because a press is the moment the
        answer has to be right — and because correcting the state is worth
        more than reading around it: it also decides that the *next* launch
        must return from the app first, which sends an alt-tab to a
        compositor whose front window is already Salon.
        """
        self._feed_front(SalonFocus(self._salon_in_front()))
