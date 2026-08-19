# SPDX-License-Identifier: GPL-3.0-or-later
"""What a settings panel is, and what it's allowed to reach.

Panels are built lazily from a callback rather than constructed once and
kept: a panel's rows show live state (a GSetting, a row's tile list), and
rebuilding on entry is both simpler and less wrong than trying to keep a
retained widget tree in sync with a catalogue the user is editing.

`SettingsContext` is deliberately explicit plumbing rather than a reference
back to `HomeView`. A panel that could reach the home screen directly would
end up reaching *into* it, and the tile editor's job is to change the config
on disk and let the existing file watcher pick it up — the same path a hand
edit takes, so there is only one way the catalogue ever reloads.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from salon.core.config import Config
from salon.core.model import Tile
from salon.ui.settings.widgets import SettingsRow


@dataclass(frozen=True, slots=True)
class Panel:
    title: str
    build: Callable[[], list[SettingsRow]]
    subtitle: str = ""
    # Shown beside the section name in the left-hand list. A settings screen
    # that is eight identical lines of text gives the eye nothing to aim at
    # from a sofa; the icon is what makes "Audio" findable without reading.
    icon_name: str = ""


@dataclass(slots=True)
class SettingsContext:
    """Everything the panels need, and nothing else."""

    config: Config
    save_config: Callable[[], None]
    toast: Callable[[str], None]
    edit_text: Callable[[str, str, Callable[[str | None], None]], None]
    push: Callable[[Panel], None]
    pop: Callable[[], None]
    rebuild: Callable[[], None]
    quit_app: Callable[[], None]
    close: Callable[[], None]
    installed_apps: Callable[[Callable[[list[Tile]], None]], None]
    open_control_center: Callable[[str], None]
    version: str
    config_path: str
    notes: list[str] = field(default_factory=list)
