# SPDX-License-Identifier: GPL-3.0-or-later
"""Core data model: Tile, Row, LaunchSpec. Pure dataclasses, no gi."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class LaunchKind(StrEnum):
    DESKTOP = "desktop"
    FLATPAK = "flatpak"
    COMMAND = "command"
    URL = "url"
    BUILTIN = "builtin"


@dataclass(frozen=True, slots=True)
class LaunchSpec:
    kind: LaunchKind
    target: str
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    browser_profile: str | None = None
    user_agent: str | None = None
    spatial_nav: bool = True
    fullscreen: bool = True


@dataclass(slots=True)
class Tile:
    id: str
    title: str
    subtitle: str | None
    launch: LaunchSpec
    artwork: str | None
    icon_name: str | None
    accent: str | None
    tags: tuple[str, ...] = ()


@dataclass(slots=True)
class Row:
    id: str
    title: str | None
    tiles: list[Tile]
    provider_id: str
    tile_aspect: Literal["wide", "square", "poster"] = "wide"
