# SPDX-License-Identifier: GPL-3.0-or-later
"""The Home legend stays stable across full-screen overlays."""

from __future__ import annotations

from salon.core.actions import Action
from salon.ui.home_legend_policy import HOME_ACTION_MEANINGS


def test_home_mapping_keeps_every_action_after_time_away() -> None:
    assert HOME_ACTION_MEANINGS == (
        (Action.OK, "Open"),
        (Action.OPTIONS, "More"),
        (Action.MENU, "System"),
    )
