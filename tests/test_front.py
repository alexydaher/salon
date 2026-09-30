# SPDX-License-Identifier: GPL-3.0-or-later
"""The front-of-television state machine, checked over every pair.

The state space is four fronts and two queue flags; the events are a dozen.
Enumerating all of it is cheaper than reasoning about any of it, which is
how the flags this replaced went wrong.
"""

from __future__ import annotations

import itertools

import pytest

from salon.core.actions import Action
from salon.core.front import (
    ChildFocused,
    DropQueued,
    Effect,
    Event,
    Front,
    FrontState,
    LaunchStarted,
    PointerOff,
    QueueLaunch,
    QueuePower,
    Returned,
    Route,
    SalonFocus,
    blocks_idle,
    covers_screen,
    route,
    step,
)

ALL_STATES = [
    FrontState(front, power, pending)
    for front, power, pending in itertools.product(Front, (False, True), (False, True))
]
ALL_EVENTS: list[Event] = [
    LaunchStarted(),
    ChildFocused(pointer=False),
    ChildFocused(pointer=True),
    Returned(),
    SalonFocus(True),
    SalonFocus(False),
    PointerOff(),
    QueueLaunch(),
    QueuePower(),
    DropQueued(),
]
IN_FRONT = (Front.APP, Front.APP_POINTER)


@pytest.mark.parametrize("state", ALL_STATES)
@pytest.mark.parametrize("event", ALL_EVENTS)
def test_step_is_total_and_never_mutates(state: FrontState, event: Event) -> None:
    before = state
    new_state, effects = step(state, event)
    assert state == before
    assert isinstance(new_state, FrontState)
    assert len(effects) <= 1


@pytest.mark.parametrize("state", ALL_STATES)
def test_focus_lost_never_changes_anything(state: FrontState) -> None:
    # Salon is unfocused for a portal dialog or the overview as well, and
    # neither is an application in front.
    assert step(state, SalonFocus(False)) == (state, ())


@pytest.mark.parametrize("state", [s for s in ALL_STATES if s.front in IN_FRONT])
def test_a_focused_salon_ends_an_app_in_front(state: FrontState) -> None:
    new_state, effects = step(state, SalonFocus(True))
    assert new_state.front is Front.HOME
    assert effects == (Effect.MARK_RETURNED,)
    # Queued work waits for the launcher's own `Returned`, which the
    # MARK_RETURNED effect causes.
    assert (new_state.power_on_return, new_state.pending_launch) == (
        state.power_on_return,
        state.pending_launch,
    )


@pytest.mark.parametrize("state", [s for s in ALL_STATES if s.front is Front.LAUNCHING])
def test_a_focused_salon_does_not_abandon_a_launch(state: FrontState) -> None:
    # Regression: focus is what Salon has for the whole of phase 1, and any
    # press used to be taken for "the flags are stale" and finished the
    # launch it was made during.
    assert step(state, SalonFocus(True)) == (state, ())


@pytest.mark.parametrize("state", [s for s in ALL_STATES if s.front is Front.HOME])
def test_a_focused_salon_at_home_is_already_home(state: FrontState) -> None:
    assert step(state, SalonFocus(True)) == (state, ())


@pytest.mark.parametrize("state", ALL_STATES)
def test_returned_always_lands_home_and_does_at_most_one_queued_thing(
    state: FrontState,
) -> None:
    new_state, effects = step(state, Returned())
    assert new_state.front is Front.HOME
    if state.power_on_return:
        assert effects == (Effect.SHOW_POWER,)
        assert not new_state.power_on_return
        assert new_state.pending_launch == state.pending_launch
    elif state.pending_launch:
        assert effects == (Effect.START_PENDING_LAUNCH,)
        assert not new_state.pending_launch
    else:
        assert effects == ()


@pytest.mark.parametrize(
    "state", [s for s in ALL_STATES if not (s.power_on_return or s.pending_launch)]
)
def test_a_second_return_with_nothing_queued_does_nothing(state: FrontState) -> None:
    home, _ = step(state, Returned())
    assert step(home, Returned()) == (home, ())


def test_a_launch_walks_through_launching_to_the_app_and_home() -> None:
    state = FrontState()
    state, _ = step(state, LaunchStarted())
    assert state.front is Front.LAUNCHING
    state, _ = step(state, ChildFocused(pointer=False))
    assert state.front is Front.APP
    state, _ = step(state, Returned())
    assert state.front is Front.HOME


def test_a_browser_tile_puts_the_cursor_on_and_back_takes_only_the_cursor_off() -> None:
    state = FrontState(Front.LAUNCHING)
    state, _ = step(state, ChildFocused(pointer=True))
    assert state.front is Front.APP_POINTER
    state, _ = step(state, PointerOff())
    # Chrome is still in front. Salon must not go back to routing presses to
    # a home screen nobody can see.
    assert state.front is Front.APP


@pytest.mark.parametrize("front", [Front.HOME, Front.LAUNCHING, Front.APP])
def test_pointer_off_outside_pointer_mode_is_nothing(front: Front) -> None:
    # The grant being refused at startup arrives with Salon at home.
    state = FrontState(front)
    assert step(state, PointerOff()) == (state, ())


def test_queueing_and_dropping() -> None:
    state, _ = step(FrontState(Front.APP), QueueLaunch())
    state, _ = step(state, QueuePower())
    assert (state.pending_launch, state.power_on_return) == (True, True)
    state, _ = step(state, DropQueued())
    assert (state.pending_launch, state.power_on_return) == (False, False)
    assert state.front is Front.APP


@pytest.mark.parametrize("state", ALL_STATES)
@pytest.mark.parametrize("action", list(Action))
def test_route_never_reaches_salon_behind_an_app(state: FrontState, action: Action) -> None:
    # The bug the flags allowed: SEARCH, POWER and PLAY_PAUSE acted on a
    # window nobody could see.
    result = route(state, action)
    assert (result is Route.SALON) == (state.front is Front.HOME)


@pytest.mark.parametrize("front", [f for f in Front if f is not Front.HOME])
def test_menu_and_power_always_bring_salon_home_first(front: Front) -> None:
    state = FrontState(front)
    assert route(state, Action.MENU) is Route.RETURN_HOME
    assert route(state, Action.POWER) is Route.RETURN_THEN_POWER


@pytest.mark.parametrize("front", [f for f in Front if f is not Front.HOME])
def test_play_pause_behind_an_app_is_transport_only(front: Front) -> None:
    assert route(FrontState(front), Action.PLAY_PAUSE) is Route.TRANSPORT


def test_back_gives_up_a_launch_and_everything_else_waits() -> None:
    state = FrontState(Front.LAUNCHING)
    assert route(state, Action.BACK) is Route.CANCEL_LAUNCH
    for action in (Action.OK, Action.UP, Action.SEARCH, Action.OPTIONS):
        assert route(state, action) is Route.SWALLOW


def test_pointer_mode_keeps_its_three_presses() -> None:
    state = FrontState(Front.APP_POINTER)
    assert route(state, Action.OK) is Route.POINTER_CLICK
    assert route(state, Action.SEARCH) is Route.POINTER_OSK
    assert route(state, Action.BACK) is Route.POINTER_OFF
    assert route(state, Action.LEFT) is Route.SWALLOW


def test_a_native_app_gets_the_pad_to_itself() -> None:
    state = FrontState(Front.APP)
    for action in (Action.OK, Action.BACK, Action.SEARCH, Action.UP, Action.OPTIONS):
        assert route(state, action) is Route.SWALLOW


@pytest.mark.parametrize("state", ALL_STATES)
def test_a_focused_salon_is_never_covered(state: FrontState) -> None:
    assert covers_screen(state, salon_focused=True) is False


@pytest.mark.parametrize("state", ALL_STATES)
def test_an_unfocused_salon_is_covered_only_when_something_was_launched(
    state: FrontState,
) -> None:
    # Focus is a veto, not a source: an unfocused Salon at home is a portal
    # dialog or the overview, not an application.
    assert covers_screen(state, salon_focused=False) is (state.front is not Front.HOME)


@pytest.mark.parametrize("state", ALL_STATES)
def test_idle_holds_off_for_a_launch_and_for_an_app(state: FrontState) -> None:
    assert blocks_idle(state) is (state.front is not Front.HOME)
