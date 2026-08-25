# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view construction stage."""

from salon.services.component import ServiceComponent
from salon.ui.home_rows import *
from salon.ui.home_shared import *
from salon.ui.home_spring import *
from salon.ui.home_viewport import *


class HomeCatalogSetup(ServiceComponent):
    def _setup_catalog(
        self, application: Gtk.Application, scale_manager: ScaleManager, theme_manager: ThemeManager
    ) -> None:
        self._config = self._load_config()
        self._provider_registry = ProviderRegistry(self._settings)
        self._provider_outcomes: tuple[ProviderOutcome, ...] = ()
        self._catalog_generation = 0
        self._settings_screen = SettingsScreen(
            self._scale,
            self._settings,
            config=self._config,
            save_config=self._save_config,
            toast=self._toast,
            edit_text=self._edit_text,
            installed_apps=appinfo.list_installed_async,
            provider_registry=self._provider_registry,
            provider_outcomes=lambda: self._provider_outcomes,
            reload_catalog=lambda: self._refresh_catalog(preserve_focus=True),
            quit_app=self._application.quit,
            on_close=self.grab_focus,
            phone_remote_running=self.phone_remote_running,
            set_phone_remote=self.set_phone_remote,
            phone_remote_hint=self.phone_remote_hint,
            pointer_backend=lambda: self._pointer.backend,
            bindings=self.bindings,
            capture_binding=self.begin_binding_capture,
            cancel_capture=self.cancel_binding_capture,
            rebind=self.rebind,
            reset_bindings=self.reset_bindings,
            version=app_config.VERSION,
            config_path=str(self._config_path),
        )
        self._overlay.add_overlay(self._settings_screen)
        self._system_menu = SystemMenu(self._build_system_menu_items(), self._scale)
        self._overlay.add_overlay(self._system_menu)
        self._tile_menu = SystemMenu([], self._scale)
        self._overlay.add_overlay(self._tile_menu)
        self._phone_pairing = PhonePairing(
            self._scale,
            self._pairing,
            on_start=lambda: self.set_phone_remote(True),
            on_close=self._close_phone_pairing,
            on_stop=self._stop_phone_remote,
        )
        self._overlay.add_overlay(self._phone_pairing)
        self._text_entry = TextEntryOverlay(self._scale, self._pairing)
        self._overlay.add_overlay(self._text_entry)
        self._onboarding = Onboarding(self._scale, self._finish_onboarding)
        self._overlay.add_overlay(self._onboarding)
        motion.set_animation_speed(self._settings.get_double("animation-scale"))
        self._return_fade = motion.FadeIn(self._overlay, motion.RETURN_FADE_MS)
        self._faded_surfaces: tuple[motion.Fadable, ...] = (
            self._search,
            self._apps_grid,
            self._settings_screen,
            self._system_menu,
            self._tile_menu,
            self._phone_pairing,
            self._launching_overlay,
        )
        self._catalog = Catalog([])
        self._focus = FocusModel([])
        self._apply_metrics()
        self._rebuild_row_widgets()
        self._refresh_catalog(preserve_focus=False)
        self._repeater = Repeater(time.monotonic, self._repeat_timing())
        self._repeat_action: Action | None = None
        self._repeat_timer_id: int | None = None
        self._held_keyvals: set[int] = set()
