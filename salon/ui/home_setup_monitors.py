# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view construction stage."""

from salon.services.component import ServiceComponent
from salon.ui.home_rows import *
from salon.ui.home_shared import *
from salon.ui.home_spring import *
from salon.ui.home_viewport import *


class HomeMonitorSetup(ServiceComponent):
    def _setup_monitors(
        self, application: Gtk.Application, scale_manager: ScaleManager, theme_manager: ThemeManager
    ) -> None:
        config_dir = Gio.File.new_for_path(str(self._config_path.parent))
        self._config_monitor = config_dir.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self._config_monitor.connect("changed", self._on_config_dir_changed)
        self._artwork_reload_timeout_id: int | None = None
        artwork_dir = artwork_drop_dir()
        artwork_dir.mkdir(parents=True, exist_ok=True)
        self._artwork_monitor = Gio.File.new_for_path(str(artwork_dir)).monitor_directory(
            Gio.FileMonitorFlags.NONE, None
        )
        self._artwork_monitor.connect("changed", self._on_artwork_dir_changed)
        self._scale_manager.subscribe(self._on_scale_changed)
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.connect(
                "notify::gtk-enable-animations", lambda *_: self._apply_animation_setting()
            )
        for key in ("reduced-motion", "animation-scale"):
            self._settings.connect(f"changed::{key}", lambda *_: self._apply_animation_setting())
        self._apply_animation_setting()
        for key in ("tile-scale", "row-spacing-scale", "safe-area-percent"):
            self._settings.connect(f"changed::{key}", lambda *_: self._apply_layout_settings())
        for key in ("key-repeat-initial-ms", "key-repeat-interval-ms"):
            self._settings.connect(f"changed::{key}", lambda *_: self._apply_repeat_settings())
        self._settings.connect(
            "changed::volume-step-percent",
            lambda *_: audio.set_volume_step(self._settings.get_int("volume-step-percent")),
        )
        self._settings.connect("changed::audio-sink", lambda *_: self._apply_preferred_sink())
        self._theme_manager.subscribe(self._on_accent_changed)
        audio.set_volume_step(self._settings.get_int("volume-step-percent"))
        self._apply_preferred_sink()
        self._settings.connect("changed::remote-hint", lambda *_: self._update_remote_hint())
        self._update_remote_hint()
        GLib.timeout_add(_HINT_POLL_MS, self._poll_remote_hint)
