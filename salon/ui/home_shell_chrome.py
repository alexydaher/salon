# SPDX-License-Identifier: GPL-3.0-or-later
"""Visibility and geometry for the root-owned Aurora Console frame."""

from salon.core import tokens
from salon.services.component import ServiceComponent


class HomeShellChrome(ServiceComponent):
    def _on_global_surface_closed(self) -> None:
        self._owner.grab_focus()
        self._sync_shell_chrome()

    def _sync_shell_chrome(self) -> None:
        apps = self._owner._apps_grid.get_visible()
        settings = self._owner._settings_screen.get_visible()
        search = self._owner._search.get_visible()
        phone = self._owner._phone_pairing.get_visible()
        full_surface = settings or search or phone
        # Without a compositor blur, leaving Home's labels below a smoked
        # surface produces sharp, unreadable ghosts. Keep the shared Aurora
        # backdrop, but only reveal Home's content when it is the active
        # surface (or while Settings explicitly asks for a live preview).
        self._owner._viewport_host.set_visible(not (apps or full_surface))
        self._owner._console_sidebar.set_visible(not full_surface)
        self._owner._home_title.set_visible(not full_surface and not apps)
        self._owner._status_bar.set_visible(not full_surface)
        self._owner._status_bar.set_apps_active(apps)
        self._owner._bottom_bar.set_visible(not full_surface and not apps)
        self._owner._update_remote_hint()

    def _apply_shell_scale(self, scale) -> None:
        self._owner._console_sidebar.set_scale(scale)
        self._owner._home_title.set_margin_start(
            scale.px(tokens.CONSOLE_WIDTH_DU) + scale.safe_margin_px
        )
        self._owner._home_title.set_margin_top(max(0, scale.safe_margin_px - scale.px(18.0)))
        self._owner._bottom_bar.set_margin_start(scale.px(tokens.CONSOLE_WIDTH_DU))

    def _apply_shell_viewport_inset(self) -> None:
        self._owner._viewport_host.set_margin_start(
            self._owner._scale.px(tokens.CONSOLE_WIDTH_DU)
        )

    def _set_preview_chrome(self, previewing: bool) -> None:
        """Reveal Home's stable shell behind Settings' live preview."""
        self._owner._bottom_bar.set_opacity(0.0 if previewing else 1.0)
        if previewing:
            self._owner._viewport_host.set_visible(True)
            self._owner._console_sidebar.set_visible(True)
            self._owner._home_title.set_visible(True)
            self._owner._status_bar.set_visible(True)
        else:
            self._owner._sync_shell_chrome()

    def _remote_hint_unobscured(self) -> bool:
        phone = getattr(self._owner, "_phone_pairing", None)
        onboarding = getattr(self._owner, "_onboarding", None)
        return not (phone is not None and phone.get_visible()) and not (
            onboarding is not None and onboarding.get_visible()
        )
