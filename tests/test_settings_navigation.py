# SPDX-License-Identifier: GPL-3.0-or-later
"""Controller policy for Settings, kept pure and headless."""

from __future__ import annotations

from salon.input.actions import Action
from salon.ui.settings.navigation_policy import is_settings_back, section_target


def test_only_back_owns_settings_history() -> None:
    assert is_settings_back(Action.BACK)
    assert not is_settings_back(Action.LEFT)


def test_shoulders_change_section_without_wrapping() -> None:
    assert section_target(1, 3, Action.PREV_GROUP) == 0
    assert section_target(1, 3, Action.NEXT_GROUP) == 2
    assert section_target(0, 3, Action.PREV_GROUP) is None
    assert section_target(2, 3, Action.NEXT_GROUP) is None


def test_unrelated_actions_do_not_change_section() -> None:
    assert section_target(1, 3, Action.LEFT) is None
    assert section_target(1, 3, Action.RIGHT) is None
