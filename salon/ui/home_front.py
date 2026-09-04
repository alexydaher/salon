# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_front_policy import app_covers_screen, child_state_is_stale
from salon.ui.home_shared import Gtk


class HomeFrontController(ServiceComponent):
    """Whether another application is in front, and undoing it when not."""

    def _salon_in_front(self) -> bool:
        """Whether Salon's own window has the compositor's focus.

        Read, never remembered — see `home_front_policy`. Answers False
        without a window at all, which keeps every flag meaning exactly what
        it meant before this check existed when there is nothing to ask.
        """
        root = self._owner.get_root()
        if not isinstance(root, Gtk.Window):
            return False
        return bool(root.get_property("is-active"))

    def _app_covering(self) -> bool:
        """Is another application in front of Salon right now?"""
        return app_covers_screen(
            child_active=self._owner._child_active,
            pointer_mode=self._owner._pointer_mode,
            has_child=self._owner._launcher.has_child,
            salon_focused=self._salon_in_front(),
        )

    def _reconcile_child_state(self) -> None:
        """Clear "an app is out there" once Salon is provably back in front.

        Called before a press is routed, because a press is the moment the
        answer has to be right — and because correcting the state is worth
        more than reading around it: the flags also decide that the *next*
        launch must return from the app first, which sends an alt-tab to a
        compositor whose front window is already Salon.
        """
        if not child_state_is_stale(
            child_active=self._owner._child_active,
            pointer_mode=self._owner._pointer_mode,
            has_child=self._owner._launcher.has_child,
            salon_focused=self._salon_in_front(),
        ):
            return
        # Fires on_returned, which is what clears the two flags, republishes
        # the phone's snapshot and picks up any pending launch.
        self._owner._launcher.mark_returned()
        if self._owner._pointer_mode or self._owner._child_active:
            # Nothing was left for the launcher to finish, so nothing called
            # back. Rare, and not worth a second route out of the state.
            self._owner._pointer_mode = False
            self._owner._child_active = False
            self._owner._publish_remote_state()
