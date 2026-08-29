# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings row kit, as one import for the panels that use it."""

from salon.ui.settings.action_rows import (
    ActionRow,
    ToggleRow,
    opens_gnome,
    opens_panel,
    opens_picker,
)
from salon.ui.settings.keyed import Keyed, restore_defaults_row
from salon.ui.settings.settings_list import SettingsList
from salon.ui.settings.settings_row import SettingsRow
from salon.ui.settings.static_rows import GroupRow, InfoRow
from salon.ui.settings.value_rows import ChoiceRow, RangeRow, TextRow

__all__ = [
    "ActionRow",
    "ChoiceRow",
    "GroupRow",
    "InfoRow",
    "Keyed",
    "RangeRow",
    "SettingsList",
    "SettingsRow",
    "TextRow",
    "ToggleRow",
    "opens_gnome",
    "opens_panel",
    "opens_picker",
    "restore_defaults_row",
]
