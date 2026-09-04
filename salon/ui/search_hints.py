# SPDX-License-Identifier: GPL-3.0-or-later
"""What the buttons do on each half of the search screen.

Its own module because `search.py` builds the bar and `search_results.py`
decides which set is showing, and one importing the other for a constant
would close a cycle.
"""

from __future__ import annotations

from salon.core.actions import Action
from salon.ui.legend import Hint

# Per pane, because the two halves of this screen do different things with
# the same buttons: OK types a letter on the left and opens an application
# on the right.
_KEYBOARD_HINTS: tuple[Hint, ...] = (
    (Action.OK, "Type"),
    ("D-PAD", "Keys"),
    (Action.RIGHT, "Results"),
    (Action.BACK, "Close"),
)
_RESULT_HINTS: tuple[Hint, ...] = (
    (Action.OK, "Open"),
    (Action.OPTIONS, "More"),
    (Action.LEFT, "Keyboard"),
    (Action.BACK, "Close"),
)

__all__ = ["_KEYBOARD_HINTS", "_RESULT_HINTS"]
