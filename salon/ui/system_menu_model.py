# SPDX-License-Identifier: GPL-3.0-or-later
"""Data carried by the television menu's navigation stack."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SystemMenuItem:
    label: str
    action: Callable[[], None] | None = None
    danger: bool = False
    icon_name: str = ""
    detail: str = ""
    trailing: str = ""
    submenu: Callable[[], MenuFrame] | None = None
    closes: bool = True


@dataclass(slots=True)
class MenuFrame:
    """One stable level in a menu hierarchy."""

    frame_id: str
    title: str
    items: list[SystemMenuItem]
    selected: int = 0
