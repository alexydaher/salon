# SPDX-License-Identifier: GPL-3.0-or-later
"""Whether an application is covering the television, and when to say so.

The bug behind these: the phone's whole Remote pane is greyed on `app` in
the state snapshot, while the trackpad and the keyboard are not — so a flag
left standing after a return produced exactly the reported symptom, a remote
whose buttons do nothing beside a trackpad that works.
"""

from __future__ import annotations

from salon.ui.home_front_policy import app_covers_screen, child_state_is_stale


def test_a_focused_salon_is_never_behind_an_app() -> None:
    for flag in ("child_active", "pointer_mode", "has_child"):
        flags = {"child_active": False, "pointer_mode": False, "has_child": False}
        flags[flag] = True
        assert app_covers_screen(**flags, salon_focused=True) is False
        assert child_state_is_stale(**flags, salon_focused=True) is True


def test_each_flag_alone_still_covers_an_unfocused_salon() -> None:
    for flag in ("child_active", "pointer_mode", "has_child"):
        flags = {"child_active": False, "pointer_mode": False, "has_child": False}
        flags[flag] = True
        assert app_covers_screen(**flags, salon_focused=False) is True
        assert child_state_is_stale(**flags, salon_focused=False) is False


def test_an_unfocused_salon_with_no_child_is_not_an_app_in_front() -> None:
    # A portal dialog or the overview also takes Salon's focus away, and
    # neither is a launched application. Focus is a veto, not a source.
    quiet = {"child_active": False, "pointer_mode": False, "has_child": False}
    assert app_covers_screen(**quiet, salon_focused=False) is False
    assert child_state_is_stale(**quiet, salon_focused=False) is False
    assert app_covers_screen(**quiet, salon_focused=True) is False
    assert child_state_is_stale(**quiet, salon_focused=True) is False
