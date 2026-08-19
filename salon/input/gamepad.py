# SPDX-License-Identifier: GPL-3.0-or-later
"""Gamepad input source via libmanette. Normalizes to Action.

Handles hotplug (Manette.Monitor's device-connected/disconnected signals —
a controller plugged in after startup works without restart) and covers
the D-pad reported either as digital buttons (BTN_DPAD_*) or as a hat
switch (ABS_HAT0X/Y), since controllers disagree about which they use.

The right stick is also exposed as continuous, unquantized motion via
on_right_stick, polled on a timer rather than only on evdev change events —
holding the stick at a steady deflection can stop generating events, and a
mouse cursor needs continuous motion while held. What it reports is
dead-zoned and rescaled by `actions.stick_deflection`, because a stick at
rest is not at zero: a DualSense idles at +0.11..+0.15 on both Y axes. Everything else (D-pad,
left stick, face buttons) goes through the quantized Action stream.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Manette", "0.2")
gi.require_version("GLib", "2.0")

from gi.repository import GLib, Manette  # noqa: E402

from salon.input.actions import Action, stick_deflection  # noqa: E402

# Linux evdev codes (linux/input-event-codes.h) — stable across vendors.
# This is what libmanette hands back via Event.get_hardware_code().
_BTN_SOUTH = 0x130  # A / Cross
_BTN_EAST = 0x131  # B / Circle
_BTN_WEST = 0x134  # X / Square
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
    _BTN_WEST: Action.OPTIONS,
    _BTN_START: Action.MENU,
    _BTN_DPAD_UP: Action.UP,
    _BTN_DPAD_DOWN: Action.DOWN,
    _BTN_DPAD_LEFT: Action.LEFT,
    _BTN_DPAD_RIGHT: Action.RIGHT,
}

# evdev ABS_* axis codes.
_ABS_X = 0  # left stick
_ABS_Y = 1
_ABS_Z = 2  # left trigger, on some pads
_ABS_RX = 3  # right stick, on most pads
_ABS_RY = 4
_ABS_RZ = 5  # right trigger, on some pads
_ABS_HAT0X = 16  # alternate D-pad reporting
_ABS_HAT0Y = 17

_RIGHT_STICK_AXES = (_ABS_RX, _ABS_RY)

_DEAD_ZONE = 0.35
_RETRIGGER_THRESHOLD = 0.2
# Wider than the 0.35 above looks necessary, and it is: a DualSense at rest
# reports +0.11..+0.15 on both Y axes, sixty times a second, with nobody
# touching it (measured 2026-08-19). 0.15 left a margin of 0.016 against a
# cursor that drifts down the screen by itself. `stick_deflection` rescales
# what's left, so a wider dead zone doesn't cost slow-speed control.
_STICK_DEAD_ZONE = 0.25
_POLL_INTERVAL_MS = 16  # ~60fps


class GamepadSource:
    """Emits Action values (and optionally raw right-stick motion) from
    all connected gamepads.

    on_action_release fires when a D-pad direction (button- or
    axis-reported) is let go, so a caller can drive its own accelerating
    repeat (input.actions.Repeater) while it's held — libmanette itself
    only reports discrete press/axis-change events, not "held"."""

    def __init__(
        self,
        on_action: Callable[[Action], None],
        on_right_stick: Callable[[float, float], None] | None = None,
        on_action_release: Callable[[Action], None] | None = None,
    ) -> None:
        self._on_action = on_action
        self._on_right_stick = on_right_stick
        self._on_action_release = on_action_release
        self._axis_state: dict[tuple[Manette.Device, int], int] = {}
        self._right_stick_raw: dict[tuple[Manette.Device, int], float] = {}
        self._monitor = Manette.Monitor.new()

        it = self._monitor.iterate()
        while True:
            ok, device = it.next()
            if not ok:
                break
            self._connect_device(device)

        self._monitor.connect("device-connected", self._on_device_connected)

        if self._on_right_stick is not None:
            GLib.timeout_add(_POLL_INTERVAL_MS, self._poll_right_stick)

    def _on_device_connected(self, monitor: Manette.Monitor, device: Manette.Device) -> None:
        self._connect_device(device)

    def _connect_device(self, device: Manette.Device) -> None:
        device.connect("button-press-event", self._on_button_press)
        device.connect("button-release-event", self._on_button_release)
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

    def _on_button_release(self, device: Manette.Device, event: Manette.Event) -> None:
        ok, button = event.get_button()
        if not ok:
            return
        action = _BUTTON_ACTIONS.get(button)
        if action is not None and self._on_action_release is not None:
            self._on_action_release(action)

    def _on_axis(self, device: Manette.Device, event: Manette.Event) -> None:
        ok, axis, value = event.get_absolute()
        if not ok:
            return
        if axis in (_ABS_HAT0X, _ABS_X):
            self._quantize(device, axis, value, negative=Action.LEFT, positive=Action.RIGHT)
        elif axis in (_ABS_HAT0Y, _ABS_Y):
            self._quantize(device, axis, value, negative=Action.UP, positive=Action.DOWN)
        elif axis in _RIGHT_STICK_AXES:
            key = (device, axis)
            self._right_stick_raw[key] = stick_deflection(value, _STICK_DEAD_ZONE)

    def _poll_right_stick(self) -> bool:
        if self._on_right_stick is not None and self._right_stick_raw:
            x = sum(v for (d, a), v in self._right_stick_raw.items() if a == _ABS_RX)
            y = sum(v for (d, a), v in self._right_stick_raw.items() if a == _ABS_RY)
            if x or y:
                self._on_right_stick(x, y)
        return bool(GLib.SOURCE_CONTINUE)

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

        previous = self._axis_state.get(key, 0)
        if state != previous:
            self._axis_state[key] = state
            if state == -1:
                self._on_action(negative)
            elif state == 1:
                self._on_action(positive)
            elif self._on_action_release is not None:
                # Back to centre: released whichever direction was latched.
                self._on_action_release(negative if previous == -1 else positive)
