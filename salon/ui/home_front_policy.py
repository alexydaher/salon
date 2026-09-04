# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure rule for whether another application is covering the television."""


def app_covers_screen(
    *, child_active: bool, pointer_mode: bool, has_child: bool, salon_focused: bool
) -> bool:
    """Whether something Salon launched is in front of Salon's own window.

    The three flags are all set from *edges* — `notify::is-active` going
    false as a child takes focus, a spawn being recorded — and an edge that
    is never emitted leaves them standing forever. Three ways that happens
    in practice: a launch that never produces a window (`has_child` is then
    true for the life of the process), a return switch injected while Salon
    was already in front (there is no active edge to see), and a child that
    goes away without the compositor handing focus back through a
    transition Salon witnessed.

    `salon_focused` is the one fact about this question that cannot go
    stale, because it is read rather than remembered: if Salon's window has
    the compositor's focus then nothing is covering it, whatever the flags
    say. It is deliberately a veto and not a source — Salon's window is also
    unfocused for reasons that are nobody's child (a portal dialog, the
    overview), and those must not start claiming an app is in front.
    """
    return (child_active or pointer_mode or has_child) and not salon_focused


def child_state_is_stale(
    *, child_active: bool, pointer_mode: bool, has_child: bool, salon_focused: bool
) -> bool:
    """Whether those flags describe a television that has already returned.

    The complement of `app_covers_screen` over the case where there is
    something to say at all: flags standing, Salon in front. This is what a
    press acts on — the flags are corrected rather than masked, because a
    masked one still routes the *next* launch through "return from the app
    first" and hands the compositor an alt-tab away from Salon.
    """
    return (child_active or pointer_mode or has_child) and salon_focused
