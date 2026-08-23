# SPDX-License-Identifier: GPL-3.0-or-later
"""Characters to X11 keysyms, for the phone keyboard typing into a browser.

`services/pointer_injector.keysym_for` is the one part of that path with a
rule in it rather than a D-Bus call, so it is the part worth testing. The
rule is Appendix A of the X protocol: for U+0020..U+00FF a keysym *is* the
codepoint, everything above is `0x01000000 + codepoint`, and the keys that
are not characters at all have named values.

The values below are checked against `Gdk.unicode_to_keyval`, which
implements the same table — an independent source rather than a restatement
of what the function already says. Getting this wrong does not raise: it
types the wrong character into somebody's search box.
"""

from __future__ import annotations

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk  # noqa: E402

from salon.services.pointer_injector import keysym_for  # noqa: E402


@pytest.mark.parametrize(
    "character",
    ["a", "Z", "0", "9", " ", "-", "/", "@", ".", ":", "?", "&", "=", "é", "ü", "ñ", "£"],
)
def test_it_agrees_with_gdk(character: str) -> None:
    """Every character a URL or a search box is made of."""
    assert keysym_for(character) == Gdk.unicode_to_keyval(ord(character))


@pytest.mark.parametrize("character", ["€", "→", "😀", "中"])
def test_characters_above_latin1_follow_gdk_not_the_obvious_rule(character: str) -> None:
    """The reason this delegates instead of computing.

    "codepoint below U+0100, `0x01000000 + codepoint` above" is the rule
    everyone reaches for, and it is wrong in the middle: several characters
    above Latin-1 have *legacy named* keysyms that the keymap is indexed
    by, so computing the offset would type the wrong thing. This asserts
    agreement with Gdk, whatever Gdk says.
    """
    assert keysym_for(character) == Gdk.unicode_to_keyval(ord(character))


def test_the_obvious_rule_really_is_wrong() -> None:
    """Kept as evidence, so nobody simplifies the delegation away again."""
    assert Gdk.unicode_to_keyval(ord("→")) != 0x01000000 + ord("→")
    # ...while a character with no legacy keysym does follow it.
    assert Gdk.unicode_to_keyval(ord("😀")) == 0x01000000 + ord("😀")


def test_the_keys_that_are_not_characters() -> None:
    """Backspace and Return are why the Type pane has two extra buttons: a
    search box you can fill but not submit, and a typo you cannot take
    back, are both worse than no keyboard at all."""
    assert keysym_for("\n") == Gdk.KEY_Return
    assert keysym_for("\r") == Gdk.KEY_Return
    assert keysym_for("\b") == Gdk.KEY_BackSpace
    assert keysym_for("\t") == Gdk.KEY_Tab
    assert keysym_for("\x7f") == Gdk.KEY_Delete


@pytest.mark.parametrize("character", ["\x00", "\x01", "\x1b", "\x1f"])
def test_control_characters_produce_nothing(character: str) -> None:
    """A control character with no named key above it has no business being
    typed. Sending it as a Unicode keysym would put an invisible glyph in
    the field rather than do nothing, which is worse."""
    assert keysym_for(character) is None
