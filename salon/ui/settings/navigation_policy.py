# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure controller-navigation policy for Settings."""

from salon.input.actions import Action


def is_settings_back(action: Action) -> bool:
    """Only the semantic BACK action owns Settings history."""
    return action is Action.BACK


def section_target(index: int, count: int, action: Action) -> int | None:
    """The adjacent section selected by a group action, without wrapping."""
    if action is Action.PREV_GROUP:
        target = index - 1
    elif action is Action.NEXT_GROUP:
        target = index + 1
    else:
        return None
    return target if 0 <= target < count else None
