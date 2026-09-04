# SPDX-License-Identifier: GPL-3.0-or-later
"""Visibility and geometry for the root-owned Aurora Console frame."""

from salon.core import tokens
from salon.services.component import ServiceComponent


class HomeShellChrome(ServiceComponent):
    def _on_global_surface_closed(self) -> None:
        self._owner.grab_focus()
        self._sync_shell_chrome()

    def _sync_shell_chrome(self) -> None:
        # A standing message belongs to the surface that raised it. Left
        # alone, "Couldn't start Movie Night" outlived two navigations and
        # sat over the Settings footer.
        self._owner._dismiss_toast()
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
        self._owner._remote_hint.set_settings_layout(settings)
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

    def _sync_bottom_band(self) -> None:
        """Hide the standing bottom band whenever something else owns it.

        Two things want the bottom-right corner: Home's own legend, and the
        one a menu draws above its scrim (`ui/system_menu.py`).
        `_update_legend` already hands the hints to whichever is in charge
        and blanks the other. What it could not do on its own is stop the
        *detail strip* beside Home's legend from expanding into the space
        the menu's legend now occupies — a `Gtk.Box` gives the hexpanding
        child everything the other one is not asking for, and with Home's
        legend blank that is the whole band. Measured: 846px of description
        drawn straight underneath the menu's first chip.

        Faded to zero rather than hidden, for the same reason as the
        preview strip: `home_scrolling._bottom_inset` measures this row to
        decide where the tile band ends, and a hidden widget measures zero,
        so every row on the screen would jump down by the strip's height
        each time a menu opened.
        """
        menu_open = any(
            menu.get_visible() for menu in (self._owner._system_menu, self._owner._tile_menu)
        )
        hidden = (
            menu_open
            or self._owner._preview_chrome_active
            or self._owner._current_toast is not None
        )
        self._owner._bottom_bar.set_opacity(0.0 if hidden else 1.0)

    def _set_preview_chrome(self, previewing: bool) -> None:
        """Reveal Home's stable shell behind Settings' live preview."""
        self._owner._preview_chrome_active = previewing
        self._sync_bottom_band()
        if previewing:
            self._owner._remote_hint.set_settings_layout(False)
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
