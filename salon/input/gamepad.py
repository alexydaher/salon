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

from salon.core.bindings import GAMEPAD, Bindings  # noqa: E402
from salon.input.actions import Action, stick_deflection  # noqa: E402
from salon.input.gamepad_mapping import (  # noqa: E402
    ABS_HAT_X,
    ABS_HAT_Y,
    ABS_RX,
    ABS_RY,
    ABS_X,
    ABS_Y,
    BUTTON_ACTIONS,
    RIGHT_STICK_AXES,
)

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
        bindings: Bindings | None = None,
        on_raw: Callable[[int], None] | None = None,
        on_devices_changed: Callable[[int], None] | None = None,
    ) -> None:
        self._on_action = on_action
        self._on_right_stick = on_right_stick
        self._on_action_release = on_action_release
        # The user's overrides, consulted ahead of the table below. None of
        # the defaults are wrong; they are just not right for every pad —
        # Nintendo-layout controllers put the south and east buttons in the
        # other order, so "the bottom one is OK" and "A is OK" disagree.
        self._bindings = bindings or Bindings()
        # Raw codes, for the settings screen's "press the button you want"
        # capture. Delivered whether or not the code maps to anything, which
        # is the point: an unmapped button is exactly what needs binding.
        self._on_raw = on_raw
        # How many pads are plugged in, whenever that changes. The home
        # screen uses it to decide whether anyone has a remote at all —
        # with no controller and no phone there is nothing to drive Salon
        # with, and that is when the pairing code goes on screen.
        self._on_devices_changed = on_devices_changed

        self._devices: set[Manette.Device] = set()
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
        self._monitor.connect("device-disconnected", self._on_device_disconnected)

        if self._on_right_stick is not None:
            GLib.timeout_add(_POLL_INTERVAL_MS, self._poll_right_stick)

    def set_bindings(self, bindings: Bindings) -> None:
        self._bindings = bindings

    @property
    def device_count(self) -> int:
        """Pads currently plugged in. Counted from the monitor's own
        connect/disconnect signals rather than re-walking `iterate()`,
        which is what makes an unplug visible at all: nothing else in
        Salon ever asks libmanette a second time."""
        return len(self._devices)

    def _resolve(self, button: int) -> Action | None:
        override = self._bindings.action_for(GAMEPAD, button)
        if override is not None:
            # Including the empty string, which means the user silenced this
            # button and must beat the default rather than fall through it.
            try:
                return Action(override) if override else None
            except ValueError:
                return None
        return BUTTON_ACTIONS.get(button)

    def _on_device_connected(self, monitor: Manette.Monitor, device: Manette.Device) -> None:
        self._connect_device(device)
        self._notify_devices()

    def _on_device_disconnected(self, monitor: Manette.Monitor, device: Manette.Device) -> None:
        self._devices.discard(device)
        # Whatever it was holding is not coming back. Left latched, an
        # unplugged pad's last direction would repeat forever, because the
        # release event that clears it arrives from a device that is gone.
        for key in [k for k in self._axis_state if k[0] is device]:
            del self._axis_state[key]
        for key in [k for k in self._right_stick_raw if k[0] is device]:
            del self._right_stick_raw[key]
        self._notify_devices()

    def _notify_devices(self) -> None:
        if self._on_devices_changed is not None:
            self._on_devices_changed(len(self._devices))

    def _connect_device(self, device: Manette.Device) -> None:
        self._devices.add(device)
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
            if self._on_raw is not None:
                self._on_raw(button)
            action = self._resolve(button)
            if action is not None:
                self._on_action(action)

    def _on_button_release(self, device: Manette.Device, event: Manette.Event) -> None:
        ok, button = event.get_button()
        if not ok:
            return
        action = self._resolve(button)
        if action is not None and self._on_action_release is not None:
            self._on_action_release(action)

    def _on_axis(self, device: Manette.Device, event: Manette.Event) -> None:
        ok, axis, value = event.get_absolute()
        if not ok:
            return
        if axis in (ABS_HAT_X, ABS_X):
            self._quantize(device, axis, value, negative=Action.LEFT, positive=Action.RIGHT)
        elif axis in (ABS_HAT_Y, ABS_Y):
            self._quantize(device, axis, value, negative=Action.UP, positive=Action.DOWN)
        elif axis in RIGHT_STICK_AXES:
            key = (device, axis)
            self._right_stick_raw[key] = stick_deflection(value, _STICK_DEAD_ZONE)

    def _poll_right_stick(self) -> bool:
        if self._on_right_stick is not None and self._right_stick_raw:
            x = sum(v for (d, a), v in self._right_stick_raw.items() if a == ABS_RX)
            y = sum(v for (d, a), v in self._right_stick_raw.items() if a == ABS_RY)
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
