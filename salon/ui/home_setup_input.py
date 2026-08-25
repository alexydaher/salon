# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view construction stage."""

from salon.services.component import ServiceComponent
from salon.ui.home_rows import *
from salon.ui.home_shared import *
from salon.ui.home_spring import *
from salon.ui.home_viewport import *


class HomeInputSetup(ServiceComponent):
    def _setup_input(
        self, application: Gtk.Application, scale_manager: ScaleManager, theme_manager: ThemeManager
    ) -> None:
        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        controller.connect("key-released", self._on_key_released)
        self.add_controller(controller)
        self.set_can_focus(True)
        self.set_focusable(True)
        self.set_accessible_role(Gtk.AccessibleRole.GRID)
        self.update_property([Gtk.AccessibleProperty.LABEL], ["Home"])
        scroll = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES | Gtk.EventControllerScrollFlags.DISCRETE
        )
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)
        pointer_motion = Gtk.EventControllerMotion()
        pointer_motion.connect("motion", self._on_pointer_motion)
        self.add_controller(pointer_motion)
        self._last_pointer_xy: tuple[float, float] | None = None
        self._pointer_visible = False
        self._pointer_mode = False
        self._child_active = False
        self._pending_launch: Tile | None = None
        self._current_launch_is_browser = False
        self._pointer = PointerInjector(
            on_ready=self._on_pointer_ready,
            load_restore_token=lambda: self._settings.get_string("remote-desktop-restore-token"),
            save_restore_token=lambda token: self._settings.set_string(
                "remote-desktop-restore-token", token
            ),
            backend=self._settings.get_string("input-injection"),
        )
        self._launcher = LauncherService(
            application,
            idle_inhibit_seconds=self._settings.get_int("idle-inhibit-seconds"),
            browser_scale_factor=tokens.browser_scale_factor(self._scale.viewport_height_px),
        )
        self._launcher.on_launch_started = self._on_launch_started
        self._launcher.on_child_focused = self._on_child_focused
        self._launcher.on_launch_timed_out = self._on_launch_timed_out
        self._launcher.on_returned = self._on_returned
        self._launcher.on_error = self._on_launch_error
        self._gamepad = GamepadSource(
            self._on_gamepad_action,
            on_right_stick=self._on_right_stick,
            on_action_release=self._stop_repeat,
            bindings=self._bindings,
            on_raw=lambda code: self._on_raw_input(GAMEPAD, code),
            on_devices_changed=self._on_gamepads_changed,
        )
        self._gamepad_count = self._gamepad.device_count
        self._cec = CecSource(
            self._on_cec_action,
            bindings=self._bindings,
            on_raw=lambda code: self._on_raw_input(CEC, code),
        )
        self._apply_cec_setting()
        self._settings.connect("changed::cec-enabled", lambda *_: self._apply_cec_setting())
        self._settings.connect(
            "changed::screensaver-minutes", lambda *_: self._apply_screensaver_setting()
        )
        self._reload_timeout_id: int | None = None
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
