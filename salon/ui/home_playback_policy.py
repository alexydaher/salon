# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure rule for what a play/pause press means when nothing is playing."""

from salon.core.bindings import CEC


def should_launch_focused(*, may_launch: bool, source: str) -> bool:
    """Whether a play/pause press with no player falls through to a launch.

    Only on the home screen (`may_launch`), and only from the television's
    own remote. That handset's largest button is play, so the useless
    outcome is the one that does nothing at all — but the argument does not
    survive being carried to the other sources. A controller's play button
    is BTN_SELECT: small, beside Start, nowhere near the thumb resting on
    OK. A keyboard's media key sits beside Enter. On either, launching
    whatever the cursor happens to rest on is a surprise, not a shortcut.
    """
    return may_launch and source == CEC
