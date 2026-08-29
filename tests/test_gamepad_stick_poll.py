# SPDX-License-Identifier: GPL-3.0-or-later
"""The right-stick poll follows the pads in and out.

`GamepadSource` reads the right stick by polling at 60Hz, because
libmanette reports axis *changes* and a stick held off-centre stops
producing events. That poll used to be installed once in `__init__`, gated
only on there being a consumer for it — never on a controller being
present. With nothing plugged in it woke the main loop 62 times a second to
look at an empty dict: 0.5% of a core, about half of Salon's whole idle
cost, on an appliance whose normal state is sitting on a television doing
nothing.

Nothing caught it because it is invisible in every functional sense — the
poll did no work and broke nothing. These tests pin the arming rule rather
than the symptom: armed while at least one pad is connected, not armed
otherwise.
"""

from __future__ import annotations

import gi

gi.require_version("Manette", "0.2")
from gi.repository import GLib  # noqa: E402

from salon.input.gamepad import GamepadSource  # noqa: E402


def _bare_source(on_right_stick: object | None) -> GamepadSource:
    """A GamepadSource with just the attributes the poll rules touch.

    Built without `__init__` on purpose: the real one opens a
    `Manette.Monitor` and adopts whatever is plugged into the machine
    running the tests, which is exactly the variable these tests are about.
    """
    source = object.__new__(GamepadSource)
    source._devices = set()  # noqa: SLF001
    source._right_stick_raw = {}  # noqa: SLF001
    source._stick_poll_id = None  # noqa: SLF001
    source._on_right_stick = on_right_stick  # noqa: SLF001
    return source


def test_no_poll_runs_with_no_controller_connected() -> None:
    # The regression itself: this is the state a television sits in for
    # hours, and it must cost no timer at all.
    source = _bare_source(lambda x, y: None)
    source._arm_stick_poll()  # noqa: SLF001
    assert source._stick_poll_id is None  # noqa: SLF001


def test_a_connected_pad_arms_the_poll() -> None:
    source = _bare_source(lambda x, y: None)
    source._devices = {object()}  # noqa: SLF001
    source._arm_stick_poll()  # noqa: SLF001
    assert source._stick_poll_id is not None  # noqa: SLF001
    GLib.source_remove(source._stick_poll_id)  # noqa: SLF001


def test_poll_is_armed_only_once_for_several_pads() -> None:
    source = _bare_source(lambda x, y: None)
    source._devices = {object()}  # noqa: SLF001
    source._arm_stick_poll()  # noqa: SLF001
    first = source._stick_poll_id  # noqa: SLF001
    source._devices.add(object())  # noqa: SLF001
    source._arm_stick_poll()  # noqa: SLF001
    assert source._stick_poll_id == first  # noqa: SLF001
    GLib.source_remove(source._stick_poll_id)  # noqa: SLF001


def test_arming_does_nothing_without_a_stick_consumer() -> None:
    source = _bare_source(None)
    source._devices = {object()}  # noqa: SLF001
    source._arm_stick_poll()  # noqa: SLF001
    assert source._stick_poll_id is None  # noqa: SLF001


def test_poll_stops_itself_when_the_last_pad_goes() -> None:
    source = _bare_source(lambda x, y: None)
    source._stick_poll_id = 1234  # noqa: SLF001
    # No devices: the poll must retire rather than reschedule. This is the
    # only thing that stops it after an unplug — there is no disarm.
    assert source._poll_right_stick() == bool(GLib.SOURCE_REMOVE)  # noqa: SLF001
    assert source._stick_poll_id is None  # noqa: SLF001


def test_poll_keeps_running_while_a_pad_is_connected() -> None:
    seen: list[tuple[float, float]] = []
    source = _bare_source(lambda x, y: seen.append((x, y)))
    source._devices = {object()}  # noqa: SLF001
    assert source._poll_right_stick() == bool(GLib.SOURCE_CONTINUE)  # noqa: SLF001
    assert seen == []  # nothing deflected, so nothing reported
