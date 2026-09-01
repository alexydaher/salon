# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure, stable action policy for the standing Home legend."""

from salon.core.actions import Action

HOME_ACTION_MEANINGS: tuple[tuple[Action, str], ...] = (
    (Action.OK, "Open"),
    (Action.OPTIONS, "More"),
    (Action.MENU, "System"),
)
