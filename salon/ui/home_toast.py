# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""The standing message: one at a time, and it owns the bottom of the screen.

Split out of `home_catalog.py`, which is about the catalogue. Toasts grew
three rules of their own — replace rather than queue, yield the action band,
and go away when the surface that raised them does — and none of them are
about tiles.
"""

from salon.services.component import ServiceComponent
from salon.ui.home_shared import Adw


class HomeToastController(ServiceComponent):
    def _toast(self, message: str) -> None:
        """Show *message*, replacing whatever was showing.

        `dismiss()` first because `Adw.ToastOverlay` queues: without it a
        launch failure and the message about it stacked up, and the second
        appeared after the user had already moved on.

        The standing action band goes down while a toast is up. Measured,
        the two genuinely overlap — the toast lands at y 638-696 and the
        band spans 631-720 — so the description of the focused tile and the
        legend's chips were drawn through the message. Moving the toast
        instead was tried twice and rejected twice: a margin on the overlay
        insets the *whole interface*, because that widget wraps it, and a
        CSS margin cannot be made exact because the band's natural height
        (89px, driven by the legend's own padding) is larger than the token
        it is requested at. Yielding the band is also simply right — both
        are status at the bottom of the screen, and the toast is the one
        with something new to say.
        """
        current = self._owner._current_toast
        if current is not None:
            current.dismiss()
        toast = Adw.Toast(title=message)
        toast.connect("dismissed", self._on_toast_dismissed)
        self._owner._current_toast = toast
        self._owner._sync_bottom_band()
        self._owner._toast_overlay.add_toast(toast)

    def _on_toast_dismissed(self, toast: Adw.Toast) -> None:
        if self._owner._current_toast is toast:
            self._owner._current_toast = None
            self._owner._sync_bottom_band()

    def _dismiss_toast(self) -> None:
        """Drop the standing message when the screen it was about goes away.

        A toast outlives the surface that raised it — "Couldn't start Movie
        Night" was still on screen, over the Settings footer, two
        navigations later.
        """
        current = self._owner._current_toast
        if current is not None:
            current.dismiss()
