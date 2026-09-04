# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view construction stage."""

from salon.services.component import ServiceComponent
from salon.ui import overlay_order
from salon.ui.home_shared import (
    Action,
    Catalog,
    FocusModel,
    Gtk,
    Onboarding,
    PhonePairing,
    ProviderOutcome,
    ProviderRegistry,
    Repeater,
    ScaleManager,
    SettingsScreen,
    SystemMenu,
    TextEntryOverlay,
    ThemeManager,
    app_config,
    appinfo,
    motion,
    time,
)


class HomeCatalogSetup(ServiceComponent):
    def _setup_catalog(
        self, application: Gtk.Application, scale_manager: ScaleManager, theme_manager: ThemeManager
    ) -> None:
        self._owner._config = self._owner._load_config()
        self._owner._provider_registry = ProviderRegistry(self._owner._settings)
        self._owner._provider_outcomes: tuple[ProviderOutcome, ...] = ()
        self._owner._catalog_generation = 0
        self._owner._settings_screen = SettingsScreen(
            self._owner._scale,
            self._owner._settings,
            config=self._owner._config,
            save_config=self._owner._save_config,
            toast=self._owner._toast,
            edit_text=self._owner._edit_text,
            choose_path=self._owner._choose_path,
            installed_apps=appinfo.list_installed_async,
            artwork=self._owner._artwork,
            provider_registry=self._owner._provider_registry,
            provider_outcomes=lambda: self._owner._provider_outcomes,
            reload_catalog=lambda: self._owner._refresh_catalog(preserve_focus=True),
            quit_app=self._owner._application.quit,
            on_close=self._owner._on_global_surface_closed,
            preview_chrome=self._owner._set_preview_chrome,
            phone_remote_running=self._owner.phone_remote_running,
            set_phone_remote=self._owner.set_phone_remote,
            phone_remote_hint=self._owner.phone_remote_hint,
            pointer_backend=lambda: self._owner._pointer.backend,
            bindings=self._owner.bindings,
            capture_binding=self._owner.begin_binding_capture,
            cancel_capture=self._owner.cancel_binding_capture,
            rebind=self._owner.rebind,
            reset_bindings=self._owner.reset_bindings,
            version=app_config.VERSION,
            config_path=str(self._owner._config_path),
        )
        self._owner._overlay.add_overlay(self._owner._settings_screen)
        # Above both content surfaces, below the dialogs and menus built
        # after this point. `overlay_order` is the one statement of depth.
        self._raise(overlay_order.CONSOLE_CHROME)
        self._owner._system_menu = SystemMenu(
            self._owner._build_system_menu_items(),
            self._owner._scale,
            on_visibility_changed=self._owner._on_menu_changed,
            on_selection_changed=self._owner._on_menu_selection_changed,
        )
        self._owner._overlay.add_overlay(self._owner._system_menu)
        self._owner._tile_menu = SystemMenu(
            [],
            self._owner._scale,
            on_visibility_changed=self._owner._on_menu_changed,
            on_selection_changed=self._owner._on_menu_selection_changed,
        )
        self._owner._overlay.add_overlay(self._owner._tile_menu)
        self._owner._phone_pairing = PhonePairing(
            self._owner._scale,
            self._owner._pairing,
            on_start=lambda: self._owner.set_phone_remote(True),
            on_close=self._owner._close_phone_pairing,
            on_stop=self._owner._stop_phone_remote,
        )
        self._owner._overlay.add_overlay(self._owner._phone_pairing)
        self._owner._text_entry = TextEntryOverlay(self._owner._scale, self._owner._pairing)
        self._owner._overlay.add_overlay(self._owner._text_entry)
        self._owner._onboarding = Onboarding(self._owner._scale, self._owner._finish_onboarding)
        self._owner._overlay.add_overlay(self._owner._onboarding)
        # The pairing code is the one global card that must remain above a
        # scrim. Visibility policy hides it on the full pairing/onboarding
        # surfaces where another QR or explanation owns the screen.
        self._owner._overlay.add_overlay(self._owner._remote_hint)
        # And these above the chrome, which is where the setup stages that
        # build them cannot put them — see `overlay_order`.
        self._raise(overlay_order.RAISED_ABOVE_CHROME)
        motion.set_animation_speed(self._owner._settings.get_double("animation-scale"))
        self._owner._return_fade = motion.FadeIn(self._owner._overlay, motion.RETURN_FADE_MS)
        self._owner._faded_surfaces: tuple[motion.Fadable, ...] = (
            self._owner._search,
            self._owner._apps_grid,
            self._owner._settings_screen,
            self._owner._system_menu,
            self._owner._tile_menu,
            self._owner._phone_pairing,
            self._owner._launching_overlay,
        )
        self._owner._catalog = Catalog([])
        self._owner._focus = FocusModel([])
        self._owner._apply_metrics()
        self._owner._apply_scale_to_surfaces(self._owner._scale)
        self._owner._rebuild_row_widgets()
        self._owner._refresh_catalog(preserve_focus=False)
        if self._owner._starter_expected is not None:
            appinfo.discover_starter_async(self._owner._finish_starter_discovery)
        self._owner._repeater = Repeater(time.monotonic, self._owner._repeat_timing())
        self._owner._repeat_action: Action | None = None
        self._owner._repeat_timer_id: int | None = None
        self._owner._held_keyvals: set[int] = set()

    def _raise(self, names: tuple[str, ...]) -> None:
        """Move each named surface to the top of the overlay, in order.

        Depth in a `Gtk.Overlay` is construction order, and construction
        order is decided by dependencies rather than by what belongs on
        top. This is the only way anything is re-raised, so the rule in
        `overlay_order` and what is applied cannot drift apart.
        """
        for name in names:
            surface = getattr(self._owner, name)
            self._owner._overlay.remove_overlay(surface)
            self._owner._overlay.add_overlay(surface)
