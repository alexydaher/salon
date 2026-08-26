# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view construction stage."""

from salon.services import launcher
from salon.services.component import ServiceComponent
from salon.ui.home_shared import (
    CEC,
    GAMEPAD,
    CecSource,
    GamepadSource,
    Gtk,
    LauncherService,
    PointerInjector,
    ScaleManager,
    ThemeManager,
    Tile,
    tokens,
)


class HomeInputSetup(ServiceComponent):
    def _setup_input(
        self, application: Gtk.Application, scale_manager: ScaleManager, theme_manager: ThemeManager
    ) -> None:
        controller = Gtk.EventControllerKey()
        # Menu rows take real GTK focus for Orca.  Capture keeps the
        # application-wide action router authoritative before a focused
        # Gtk.Button can consume arrows, Enter, MENU, or BACK itself.
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self._owner._on_key_pressed)
        controller.connect("key-released", self._owner._on_key_released)
        self._owner.add_controller(controller)
        self._owner.set_can_focus(True)
        self._owner.set_focusable(True)
        self._owner.set_accessible_role(Gtk.AccessibleRole.GRID)
        self._owner.update_property([Gtk.AccessibleProperty.LABEL], ["Home"])
        scroll = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES | Gtk.EventControllerScrollFlags.DISCRETE
        )
        scroll.connect("scroll", self._owner._on_scroll)
        self._owner.add_controller(scroll)
        pointer_motion = Gtk.EventControllerMotion()
        pointer_motion.connect("motion", self._owner._on_pointer_motion)
        self._owner.add_controller(pointer_motion)
        self._owner._last_pointer_xy: tuple[float, float] | None = None
        self._owner._pointer_visible = False
        self._owner._pointer_mode = False
        self._owner._child_active = False
        self._owner._pending_launch: Tile | None = None
        self._owner._open_power_on_return = False
        self._owner._current_launch_is_browser = False
        self._owner._pointer = PointerInjector(
            on_ready=self._owner._on_pointer_ready,
            load_restore_token=lambda: self._owner._settings.get_string(
                "remote-desktop-restore-token"
            ),
            save_restore_token=lambda token: self._owner._settings.set_string(
                "remote-desktop-restore-token", token
            ),
            backend=self._owner._settings.get_string("input-injection"),
        )
        detected_browser: list[tuple[str, ...]] = [()]
        launcher.preflight_browser(lambda result: detected_browser.__setitem__(0, result.argv))
        self._owner._launcher = LauncherService(
            application,
            idle_inhibit_seconds=self._owner._settings.get_int("idle-inhibit-seconds"),
            browser_scale_factor=tokens.browser_scale_factor(self._owner._scale.viewport_height_px),
            browser_command=lambda: (
                launcher.parse_browser_command(self._owner._settings.get_string("browser-command"))
                or detected_browser[0]
            ),
            browser_extra_flags=lambda: tuple(
                self._owner._settings.get_strv("browser-extra-flags")
            ),
        )
        self._owner._launcher.on_launch_started = self._owner._on_launch_started
        self._owner._launcher.on_child_focused = self._owner._on_child_focused
        self._owner._launcher.on_launch_timed_out = self._owner._on_launch_timed_out
        self._owner._launcher.on_returned = self._owner._on_returned
        self._owner._launcher.on_error = self._owner._on_launch_error
        self._owner._gamepad = GamepadSource(
            self._owner._on_gamepad_action,
            on_right_stick=self._owner._on_right_stick,
            on_action_release=self._owner._stop_repeat,
            bindings=self._owner._bindings,
            on_raw=lambda code: self._owner._on_raw_input(GAMEPAD, code),
            on_devices_changed=self._owner._on_gamepads_changed,
        )
        self._owner._gamepad_count = self._owner._gamepad.device_count
        self._owner._cec = CecSource(
            self._owner._on_cec_action,
            bindings=self._owner._bindings,
            on_raw=lambda code: self._owner._on_raw_input(CEC, code),
        )
        self._owner._apply_cec_setting()
        self._owner._settings.connect(
            "changed::cec-enabled", lambda *_: self._owner._apply_cec_setting()
        )
        self._owner._settings.connect(
            "changed::screensaver-minutes", lambda *_: self._owner._apply_screensaver_setting()
        )
        self._owner._reload_timeout_id: int | None = None
        self._owner._config_path.parent.mkdir(parents=True, exist_ok=True)
