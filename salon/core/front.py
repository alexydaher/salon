# SPDX-License-Identifier: GPL-3.0-or-later
"""What is in front of the television, and what a press means because of it.

This used to be three flags — `_child_active`, `_pointer_mode` and the
launcher's `has_child` — set from window-focus *edges* and read by half a
dozen places that each combined them differently. Two of the bugs that
produced: a press during a launch was read as "Salon is in front, so the
flags are stale" and abandoned the launch it was made during, and a cursor
switched off with BACK left Salon routing presses to a home screen nobody
could see.

Here the answer is one value, changed only by `step`, and the routing that
depended on it is one function, `route`. Nothing in this module knows about
GTK; the UI feeds it events and carries out the effects it returns.

**Focus is a veto, never a source.** `SalonFocus(True)` ends an app that is
in front — Salon plainly is — but `SalonFocus(False)` never starts one:
Salon's window is also unfocused for a portal dialog or the overview, and
neither is anyone's child. It also does nothing during `LAUNCHING`, where
Salon being focused is the *expected* state — the child's window has not
opened yet.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, auto

from salon.core.actions import Action


class Front(Enum):
    HOME = auto()
    # Spawned, no window yet. The launching overlay is up and BACK gives up.
    LAUNCHING = auto()
    # Another application has the screen and Salon goes quiet.
    APP = auto()
    # As APP, but the cursor is being driven over a browser tile.
    APP_POINTER = auto()


@dataclass(frozen=True, slots=True)
class FrontState:
    front: Front = Front.HOME
    # Things asked for while an app was in front, to be done once Salon is.
    power_on_return: bool = False
    pending_launch: bool = False


@dataclass(frozen=True, slots=True)
class LaunchStarted:
    pass


@dataclass(frozen=True, slots=True)
class ChildFocused:
    """The child's window took focus. `pointer` is a browser tile with the
    gamepad-pointer preference on."""

    pointer: bool


@dataclass(frozen=True, slots=True)
class Returned:
    """The launcher finished a return, from an edge or from a level."""


@dataclass(frozen=True, slots=True)
class SalonFocus:
    """Whether Salon's window has the compositor's focus. Read, not remembered."""

    focused: bool


@dataclass(frozen=True, slots=True)
class PointerOff:
    """BACK in pointer mode, or the grant that drives the cursor was refused."""


@dataclass(frozen=True, slots=True)
class QueueLaunch:
    pass


@dataclass(frozen=True, slots=True)
class QueuePower:
    pass


@dataclass(frozen=True, slots=True)
class DropQueued:
    """Returning did not work, so nothing is going to be done afterwards."""


Event = (
    LaunchStarted
    | ChildFocused
    | Returned
    | SalonFocus
    | PointerOff
    | QueueLaunch
    | QueuePower
    | DropQueued
)


class Effect(Enum):
    # Tell the launcher Salon is in front. It calls back with `Returned`.
    MARK_RETURNED = auto()
    SHOW_POWER = auto()
    START_PENDING_LAUNCH = auto()


def step(state: FrontState, event: Event) -> tuple[FrontState, tuple[Effect, ...]]:
    match event:
        case LaunchStarted():
            return replace(state, front=Front.LAUNCHING), ()
        case ChildFocused(pointer=pointer):
            return replace(state, front=Front.APP_POINTER if pointer else Front.APP), ()
        case Returned():
            home = replace(state, front=Front.HOME)
            if state.power_on_return:
                return replace(home, power_on_return=False), (Effect.SHOW_POWER,)
            if state.pending_launch:
                return replace(home, pending_launch=False), (Effect.START_PENDING_LAUNCH,)
            return home, ()
        case SalonFocus(focused=True) if state.front in (Front.APP, Front.APP_POINTER):
            return replace(state, front=Front.HOME), (Effect.MARK_RETURNED,)
        case SalonFocus():
            return state, ()
        case PointerOff():
            # The app is still in front; only the cursor stops. It is an
            # ordinary APP from here, which is what the toast promises:
            # MENU returns, nothing else reaches Salon.
            if state.front is Front.APP_POINTER:
                return replace(state, front=Front.APP), ()
            return state, ()
        case QueueLaunch():
            return replace(state, pending_launch=True), ()
        case QueuePower():
            return replace(state, power_on_return=True), ()
        case DropQueued():
            return replace(state, power_on_return=False, pending_launch=False), ()


def covers_screen(state: FrontState, *, salon_focused: bool) -> bool:
    """Whether something Salon launched is hiding Salon's own window.

    `salon_focused` is the live fact and vetoes the state, so a caller that
    asks before the next `SalonFocus` has been fed still cannot be told an
    app is in front by a Salon that visibly is.
    """
    return state.front is not Front.HOME and not salon_focused


def blocks_idle(state: FrontState) -> bool:
    """Whether the screensaver and wallpaper slideshow must hold off: an app
    owns the screen, or a launch is in flight and its overlay is the only
    feedback there is."""
    return state.front is not Front.HOME


class Route(Enum):
    # Not this module's business: overlays, then the home screen.
    SALON = auto()
    RETURN_HOME = auto()
    RETURN_THEN_POWER = auto()
    CANCEL_LAUNCH = auto()
    # Someone else has the screen; the press means nothing here.
    SWALLOW = auto()
    # The transport half of PLAY_PAUSE only — there is no tile to fall back to.
    TRANSPORT = auto()
    POINTER_CLICK = auto()
    POINTER_OSK = auto()
    POINTER_OFF = auto()


def route(state: FrontState, action: Action) -> Route:
    """What a press means given what is in front.

    The presses that mean the same thing everywhere — volume, mute, skip —
    are answered by the caller before it asks, and the overlays Salon owns
    are asked between the two MENU/POWER routes and the rest.
    """
    front = state.front
    if front is Front.HOME:
        return Route.SALON
    # A menu drawn in Salon's window would appear underneath the app, so
    # these two bring Salon home first, however far the launch has got.
    if action is Action.MENU:
        return Route.RETURN_HOME
    if action is Action.POWER:
        return Route.RETURN_THEN_POWER
    if action is Action.PLAY_PAUSE:
        return Route.TRANSPORT
    if front is Front.LAUNCHING:
        return Route.CANCEL_LAUNCH if action is Action.BACK else Route.SWALLOW
    if front is Front.APP_POINTER:
        if action is Action.SEARCH:
            return Route.POINTER_OSK
        if action is Action.OK:
            return Route.POINTER_CLICK
        if action is Action.BACK:
            return Route.POINTER_OFF
    # A native app reads the same gamepad device directly, bypassing window
    # focus, so Salon goes quiet rather than fight it for the buttons.
    return Route.SWALLOW
