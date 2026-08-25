# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_shared import _HINT_HOLDER, _REMOTE_HOLDER


class HomePhoneLifecycleController(ServiceComponent):
    def phone_remote_running(self) -> bool:
        return self._owner._pairing.holds(_REMOTE_HOLDER)

    def phone_remote_hint(self) -> str:
        if not self.phone_remote_running():
            # The server can still be up: the corner pairing card holds it
            # too, and saying "Off" over a code that is on screen right now
            # is the kind of small lie that makes a settings screen useless.
            if self._owner._pairing.holds(_HINT_HOLDER):
                return "Off — but running while the corner pairing code is showing"
            return "Off"
        if self._owner._pairing.locked:
            return "Locked — too many wrong codes. Turn it off and on again."
        if self._owner._pairing.connected:
            return "A phone is connected. MENU → Phone remote shows the code again."
        url = self._owner._pairing.url or "this machine"
        return (
            f"Scan the code under MENU → Phone remote, or open {url} and enter "
            f"{self._owner._pairing.code}"
        )

    def set_phone_remote(self, enabled: bool) -> bool:
        """Returns False if the server refused to start, so Settings can say
        so rather than leaving a toggle that lies."""
        if not enabled:
            self._owner._pairing.release(_REMOTE_HOLDER)
            return True
        return self._start_remote(_REMOTE_HOLDER)

    def _start_remote(self, holder: str, *, take_pointer: bool = True) -> bool:
        """Start the server on behalf of `holder` *and* fill in everything a
        phone needs to be useful the moment it connects.

        Taken out of `set_phone_remote` when the corner pairing card became
        a second reason to start it: a phone that scanned the card's code
        arrived at an empty catalogue and a volume slider reading nothing,
        because the setup below only ran on the Settings toggle's path.

        `take_pointer` is what the two paths do *not* share. Asking the
        portal for a remote-control grant puts a permission dialog on screen
        the first time, and that is fair when the user has just switched the
        remote on and unreasonable when Salon started it by itself because
        nothing was plugged in. The card's session takes the pointer when a
        phone actually turns up instead — see `_update_remote_hint`.
        """
        started = self._owner._pairing.acquire(holder)
        if started:
            # The two things the phone needs that Salon does not otherwise
            # keep to hand: the installed-app list its search ranks against,
            # and where the volume actually is.
            self._owner._scan_apps_for_phone()
            self._owner._refresh_phone_volume()
            # The first snapshot, so a phone that connects immediately has
            # something to draw rather than an empty catalogue until the
            # cursor next moves.
            self._owner._publish_remote_state()
            # And the pointer session, which the phone's trackpad injects
            # into. It is normally taken only when the catalogue has a
            # browser tile — that test is about the *gamepad* stick, which
            # exists to aim at a web page. A phone trackpad is useful over
            # anything, including Salon itself, so switching the remote on
            # is its own reason to ask. Still gated on the same consent
            # setting: this is the user saying whether Salon may move the
            # system pointer at all.
            if (
                take_pointer
                and self._owner._settings.get_boolean("gamepad-pointer")
                and not self._owner._pointer.ready
            ):
                self._owner._start_pointer_session()
        return started
