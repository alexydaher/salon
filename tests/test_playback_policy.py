# SPDX-License-Identifier: GPL-3.0-or-later
"""A play/pause press with nothing playing does not launch things.

The fallback — start the focused tile, because a television remote's
largest button is play and doing nothing at all is the worse answer —
predates a controller having any play/pause button. Binding one made the
rule reachable from a device that already has OK under the thumb, where
launching whatever the cursor rests on is a surprise rather than a
shortcut. This is the seam that keeps the two apart.
"""

from __future__ import annotations

from salon.core.bindings import CEC, GAMEPAD, KEYBOARD
from salon.ui.home_playback_policy import should_launch_focused


def test_the_televisions_own_remote_still_launches() -> None:
    assert should_launch_focused(may_launch=True, source=CEC)


def test_no_other_source_launches_from_a_play_press() -> None:
    for source in (GAMEPAD, KEYBOARD, "phone"):
        assert not should_launch_focused(may_launch=True, source=source), source


def test_nothing_launches_when_there_is_no_focused_tile_to_launch() -> None:
    """Behind a launched application, and from the click on the readout."""
    for source in (CEC, GAMEPAD, KEYBOARD):
        assert not should_launch_focused(may_launch=False, source=source), source
