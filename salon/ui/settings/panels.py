# SPDX-License-Identifier: GPL-3.0-or-later
"""The top-level settings sections, as one import for the screen.

Browser is not here any more: it is reached from System → Web tiles. Nine
sections had stopped fitting the left-hand column without scrolling, and
four rows — two of them read-only, one a verbatim copy of a row in About —
was not a section.
"""

from salon.ui.settings.about_panel import about_panel
from salon.ui.settings.appearance_panel import appearance_panel
from salon.ui.settings.audio_panel import audio_panel
from salon.ui.settings.input_panel import input_panel
from salon.ui.settings.network_panel import network_panel
from salon.ui.settings.setup_panel import setup_panel
from salon.ui.settings.system_panel import system_panel

__all__ = [
    "about_panel",
    "appearance_panel",
    "audio_panel",
    "input_panel",
    "network_panel",
    "setup_panel",
    "system_panel",
]
