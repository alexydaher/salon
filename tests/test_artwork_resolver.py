# SPDX-License-Identifier: GPL-3.0-or-later
"""Artwork lookup must tolerate host apps that Flatpak cannot see."""

from __future__ import annotations

from salon.services import desktop_entry


def test_missing_desktop_entry_is_an_artless_tile_not_an_exception() -> None:
    # Gio's C API documents a nullable return.  PyGObject 3.54 raises
    # ``TypeError: constructor returned NULL`` for this exact call instead;
    # the helper must normalize that binding detail to the API contract.
    assert desktop_entry.load("org.example.SalonDefinitelyMissing.desktop") is None
