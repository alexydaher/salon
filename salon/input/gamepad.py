"""Gamepad input source via libmanette. Normalizes to Action.

Handles hotplug (Manette.Monitor's device-connected/disconnected signals —
a controller plugged in after startup works without restart) and covers
the D-pad reported either as digital buttons (BTN_DPAD_*) or as a hat
switch (ABS_HAT0X/Y), since controllers disagree about which they use.

Cursor/click/on-screen-keyboard for browser-hosted tiles is handled inside
the page itself via the standard Web Gamepad API (see
data/browser-extension) rather than through this module — that sidesteps
Wayland's restrictions on cross-process input injection entirely, so this
class stays focused on the one thing it needs to do: emit Action for tile
navigation.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Manette", "0.2")

from gi.repository import Manette  # noqa: E402

from salon.input.actions import Action  # noqa: E402

# Linux evdev codes (linux/input-event-codes.h) — stable across vendors.
# This is what libmanette hands back via Event.get_hardware_code().
_BTN_SOUTH = 0x130  # A / Cross
_BTN_EAST = 0x131  # B / Circle
_BTN_NORTH = 0x133  # Y / Triangle
_BTN_START = 0x13B
_BTN_DPAD_UP = 0x220
_BTN_DPAD_DOWN = 0x221
_BTN_DPAD_LEFT = 0x222
_BTN_DPAD_RIGHT = 0x223

_BUTTON_ACTIONS: dict[int, Action] = {
    _BTN_SOUTH: Action.OK,
    _BTN_EAST: Action.BACK,
    _BTN_NORTH: Action.SEARCH,
    _BTN_START: Action.MENU,
    _BTN_DPAD_UP: Action.UP,
    _BTN_DPAD_DOWN: Action.DOWN,
    _BTN_DPAD_LEFT: Action.LEFT,
    _BTN_DPAD_RIGHT: Action.RIGHT,
}

# evdev ABS_* axis codes for the left stick and the alternate D-pad
# reporting (a hat switch).
_ABS_X = 0
_ABS_Y = 1
_ABS_HAT0X = 16
_ABS_HAT0Y = 17

_DEAD_ZONE = 0.35
_RETRIGGER_THRESHOLD = 0.2


class GamepadSource:
    """Emits Action values from all connected gamepads via on_action."""

    def __init__(self, on_action: Callable[[Action], None]) -> None:
        self._on_action = on_action
        self._axis_state: dict[tuple[Manette.Device, int], int] = {}
        self._monitor = Manette.Monitor.new()

        it = self._monitor.iterate()
        while True:
            ok, device = it.next()
            if not ok:
                break
            self._connect_device(device)

        self._monitor.connect("device-connected", self._on_device_connected)

    def _on_device_connected(self, monitor: Manette.Monitor, device: Manette.Device) -> None:
        self._connect_device(device)

    def _connect_device(self, device: Manette.Device) -> None:
        device.connect("button-press-event", self._on_button_press)
        device.connect("absolute-axis-event", self._on_axis)

    def _on_button_press(self, device: Manette.Device, event: Manette.Event) -> None:
        # get_button() is libmanette's normalized button id — unlike
        # get_hardware_code(), it correctly distinguishes hat-derived D-pad
        # directions (confirmed empirically: a Stadia controller's D-pad
        # reports the *same* hardware_code for both directions on an axis,
        # but distinct get_button() values matching BTN_DPAD_*).
        ok, button = event.get_button()
        if ok:
            action = _BUTTON_ACTIONS.get(button)
            if action is not None:
                self._on_action(action)

    def _on_axis(self, device: Manette.Device, event: Manette.Event) -> None:
        ok, axis, value = event.get_absolute()
        if not ok:
            return
        if axis in (_ABS_HAT0X, _ABS_X):
            self._quantize(device, axis, value, negative=Action.LEFT, positive=Action.RIGHT)
        elif axis in (_ABS_HAT0Y, _ABS_Y):
            self._quantize(device, axis, value, negative=Action.UP, positive=Action.DOWN)

    def _quantize(
        self,
        device: Manette.Device,
        axis: int,
        value: float,
        *,
        negative: Action,
        positive: Action,
    ) -> None:
        key = (device, axis)
        state = self._axis_state.get(key, 0)
        if state == 0:
            if value <= -_DEAD_ZONE:
                state = -1
            elif value >= _DEAD_ZONE:
                state = 1
        elif abs(value) < _RETRIGGER_THRESHOLD:
            # Hysteresis: only clear the latch once the stick is back near
            # centre, so it doesn't double-step right at the dead zone edge.
            state = 0

        if state != self._axis_state.get(key, 0):
            self._axis_state[key] = state
            if state == -1:
                self._on_action(negative)
            elif state == 1:
                self._on_action(positive)
