# SPDX-License-Identifier: GPL-3.0-or-later
"""Compatibility facade for settings panel builders."""

from salon.ui.settings.about_panel import about_panel
from salon.ui.settings.appearance_panel import appearance_panel
from salon.ui.settings.audio_panel import audio_panel
from salon.ui.settings.browser_panel import browser_panel
from salon.ui.settings.input_panel import input_panel
from salon.ui.settings.network_panel import network_panel
from salon.ui.settings.system_panel import system_panel

__all__ = [
    "about_panel",
    "appearance_panel",
    "audio_panel",
    "browser_panel",
    "input_panel",
    "network_panel",
    "system_panel",
]
