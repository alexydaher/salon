# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view construction stage."""

from salon.services.component import ServiceComponent
from salon.ui.home_shared import (
    _HINT_POLL_MS,
    Gio,
    GLib,
    Gtk,
    ScaleManager,
    ThemeManager,
    artwork_drop_dir,
    audio,
)


class HomeMonitorSetup(ServiceComponent):
    def _setup_monitors(
        self, application: Gtk.Application, scale_manager: ScaleManager, theme_manager: ThemeManager
    ) -> None:
        config_dir = Gio.File.new_for_path(str(self._owner._config_path.parent))
        self._owner._config_monitor = config_dir.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self._owner._config_monitor.connect("changed", self._owner._on_config_dir_changed)
        self._owner._artwork_reload_timeout_id: int | None = None
        artwork_dir = artwork_drop_dir()
        artwork_dir.mkdir(parents=True, exist_ok=True)
        self._owner._artwork_monitor = Gio.File.new_for_path(str(artwork_dir)).monitor_directory(
            Gio.FileMonitorFlags.NONE, None
        )
        self._owner._artwork_monitor.connect("changed", self._owner._on_artwork_dir_changed)
        self._owner._scale_manager.subscribe(self._owner._on_scale_changed)
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.connect(
                "notify::gtk-enable-animations", lambda *_: self._owner._apply_animation_setting()
            )
        for key in ("reduced-motion", "animation-scale"):
            self._owner._settings.connect(
                f"changed::{key}", lambda *_: self._owner._apply_animation_setting()
            )
        self._owner._apply_animation_setting()
        for key in ("tile-scale", "row-spacing-scale", "safe-area-percent"):
            self._owner._settings.connect(
                f"changed::{key}", lambda *_: self._owner._apply_layout_settings()
            )
        for key in ("key-repeat-initial-ms", "key-repeat-interval-ms"):
            self._owner._settings.connect(
                f"changed::{key}", lambda *_: self._owner._apply_repeat_settings()
            )
        self._owner._settings.connect(
            "changed::volume-step-percent",
            lambda *_: audio.set_volume_step(self._owner._settings.get_int("volume-step-percent")),
        )
        self._owner._settings.connect(
            "changed::audio-sink", lambda *_: self._owner._apply_preferred_sink()
        )
        self._owner._theme_manager.subscribe(self._owner._on_accent_changed)
        audio.set_volume_step(self._owner._settings.get_int("volume-step-percent"))
        self._owner._apply_preferred_sink()
        self._owner._settings.connect(
            "changed::remote-hint", lambda *_: self._owner._update_remote_hint()
        )
        self._owner._update_remote_hint()
        GLib.timeout_add(_HINT_POLL_MS, self._owner._poll_remote_hint)
        # Last, because it reads the state every stage above has just set.
        self._owner._update_legend()
