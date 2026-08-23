# SPDX-License-Identifier: GPL-3.0-or-later
"""User button overrides (salon/core/bindings.py).

The override layer is what makes a Nintendo-layout controller and a
television whose remote sends nonstandard CEC codes usable at all. Two
rules carry the weight: an override beats the source's default, and an
override to *nothing* is different from having no override — one silences a
button, the other means "use your default".
"""

from __future__ import annotations

import pytest

from salon.core.bindings import (
    CEC,
    GAMEPAD,
    KEYBOARD,
    BindingError,
    Bindings,
    describe_keys,
    make_key,
    split_key,
)


def test_a_key_round_trips() -> None:
    assert split_key(make_key(GAMEPAD, 0x130)) == (GAMEPAD, 0x130)
    assert split_key(make_key(CEC, 0)) == (CEC, 0)


def test_nonsense_keys_are_refused_on_the_way_in() -> None:
    with pytest.raises(BindingError):
        make_key("telepathy", 1)
    with pytest.raises(BindingError):
        make_key(GAMEPAD, -1)
    with pytest.raises(BindingError):
        make_key(GAMEPAD, True)  # type: ignore[arg-type]


def test_nonsense_keys_are_tolerated_on_the_way_out() -> None:
    """GSettings can be edited by hand. One bad entry must cost that entry,
    not every binding on the machine."""
    assert split_key("nonsense") is None
    assert split_key("pad:not-a-number") is None
    bindings = Bindings({"pad:305": "ok", "garbage": "menu", "": "back"})
    assert bindings.action_for(GAMEPAD, 305) == "ok"
    assert bindings.to_storage() == {"pad:305": "ok"}


def test_no_override_means_use_the_default() -> None:
    """None is the signal the input sources check for; it is not the same
    as a binding that produces nothing."""
    assert Bindings().action_for(GAMEPAD, 0x130) is None


def test_an_override_replaces_the_default() -> None:
    bindings = Bindings()
    bindings.bind(GAMEPAD, 0x131, "ok")
    assert bindings.action_for(GAMEPAD, 0x131) == "ok"


def test_a_silenced_button_is_not_the_same_as_an_unbound_one() -> None:
    """Somebody whose remote sends a stray code needs it to stop doing
    anything — which has to beat the default rather than fall through it."""
    bindings = Bindings()
    bindings.unbind(CEC, 0x0B)
    assert bindings.action_for(CEC, 0x0B) == Bindings.UNBOUND
    assert bindings.action_for(CEC, 0x0B) is not None


def test_clearing_restores_the_default() -> None:
    bindings = Bindings()
    bindings.unbind(KEYBOARD, 0xFF52)
    bindings.clear(KEYBOARD, 0xFF52)
    assert bindings.action_for(KEYBOARD, 0xFF52) is None


def test_a_code_means_nothing_without_its_source() -> None:
    """evdev's BTN_SOUTH is 0x130 and CEC's 0x130 is nothing at all."""
    bindings = Bindings()
    bindings.bind(GAMEPAD, 0x130, "ok")
    assert bindings.action_for(CEC, 0x130) is None


def test_two_buttons_may_share_one_action() -> None:
    """Binding a second button to OK must not silently unbind the first:
    rebinding would then have a broken state in the middle of it."""
    bindings = Bindings()
    bindings.bind(GAMEPAD, 0x130, "ok")
    bindings.bind(KEYBOARD, 0xFF0D, "ok")
    assert bindings.keys_for("ok") == ["key:65293", "pad:304"]


def test_storage_round_trips_through_a_plain_string_map() -> None:
    """What GSettings can hold without inventing a schema."""
    bindings = Bindings()
    bindings.bind(GAMEPAD, 0x131, "ok")
    bindings.unbind(CEC, 0x0B)
    restored = Bindings(bindings.to_storage())
    assert restored.action_for(GAMEPAD, 0x131) == "ok"
    assert restored.action_for(CEC, 0x0B) == Bindings.UNBOUND


def test_describe_prefers_a_real_button_name() -> None:
    assert describe_keys(["pad:304"], {"pad:304": "Cross"}) == "Cross"
    assert describe_keys(["pad:304"]) == "PAD 0x130"
    assert describe_keys(["nonsense"]) == ""
