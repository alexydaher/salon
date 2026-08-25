# SPDX-License-Identifier: GPL-3.0-or-later
"""Compatibility facade for the settings widget kit."""

from salon.ui.settings.action_rows import ActionRow, InfoRow, ToggleRow
from salon.ui.settings.settings_list import SettingsList
from salon.ui.settings.settings_row import SettingsRow
from salon.ui.settings.value_rows import ChoiceRow, RangeRow, TextRow

__all__ = [
    "ActionRow",
    "ChoiceRow",
    "InfoRow",
    "RangeRow",
    "SettingsList",
    "SettingsRow",
    "TextRow",
    "ToggleRow",
]
