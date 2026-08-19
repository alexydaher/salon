# SPDX-License-Identifier: GPL-3.0-or-later
"""Am I the session, or a window in someone's desktop?

The consequence of getting this wrong is asymmetric, which is why the false
cases are tested more heavily than the true ones. A false negative means a
television keeps its screen lock and needs a keyboard fetched. A false
positive means Salon silently turns off the screen lock of an ordinary
desktop that merely opened it from Show Applications — which is somebody's
laptop in a cafe.
"""

from __future__ import annotations

from salon.core.session import is_session


def test_the_session_entry_sets_both_and_either_is_enough() -> None:
    # DesktopNames=GNOME;Salon; becomes XDG_CURRENT_DESKTOP...
    assert is_session({"XDG_CURRENT_DESKTOP": "GNOME:Salon"})
    # ...and the entry's filename becomes DESKTOP_SESSION.
    assert is_session({"DESKTOP_SESSION": "salon"})
    assert is_session({"XDG_CURRENT_DESKTOP": "GNOME:Salon", "DESKTOP_SESSION": "salon"})


def test_position_in_the_desktop_list_does_not_matter() -> None:
    assert is_session({"XDG_CURRENT_DESKTOP": "Salon"})
    assert is_session({"XDG_CURRENT_DESKTOP": "Salon:GNOME"})
    assert is_session({"XDG_CURRENT_DESKTOP": "GNOME:Salon:Something"})


def test_a_plain_gnome_desktop_is_not_the_salon_session() -> None:
    assert not is_session({})
    assert not is_session({"XDG_CURRENT_DESKTOP": "GNOME"})
    assert not is_session({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "DESKTOP_SESSION": "ubuntu"})
    assert not is_session({"XDG_CURRENT_DESKTOP": "KDE", "DESKTOP_SESSION": "plasma"})


def test_a_substring_is_not_a_match() -> None:
    """`Salonique` is not Salon, and neither is a desktop that merely
    contains the letters. The list is colon-separated and compared whole."""
    assert not is_session({"XDG_CURRENT_DESKTOP": "Salonique"})
    assert not is_session({"XDG_CURRENT_DESKTOP": "GNOME:NotSalon"})
    assert not is_session({"DESKTOP_SESSION": "salon-classic"})


def test_case_is_not_folded() -> None:
    """XDG_CURRENT_DESKTOP is a list of proper desktop names and the entry
    writes `Salon`. Matching `salon` there would also match nothing real,
    but it would widen the false-positive surface for no gain."""
    assert not is_session({"XDG_CURRENT_DESKTOP": "salon"})
    assert not is_session({"DESKTOP_SESSION": "Salon"})


def test_surrounding_whitespace_is_tolerated() -> None:
    assert is_session({"XDG_CURRENT_DESKTOP": "GNOME: Salon "})
    assert is_session({"DESKTOP_SESSION": " salon "})
