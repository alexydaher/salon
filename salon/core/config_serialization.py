# SPDX-License-Identifier: GPL-3.0-or-later
"""Stable JSON serialization for the tile configuration model."""
from __future__ import annotations

from typing import Protocol

from salon.core.model import LaunchSpec, Row, Tile


class ConfigLike(Protocol):
    schema: int
    rows: list[Row]


def config_to_dict(config: ConfigLike) -> dict[str, object]:
    return {"schema": config.schema, "rows": [_row_to_dict(row) for row in config.rows]}


def _row_to_dict(row: Row) -> dict[str, object]:
    return {
        "id": row.id,
        "title": row.title,
        "provider_id": row.provider_id,
        "tile_aspect": row.tile_aspect,
        "tiles": [_tile_to_dict(tile) for tile in row.tiles],
    }


def _tile_to_dict(tile: Tile) -> dict[str, object]:
    return {
        "id": tile.id,
        "title": tile.title,
        "subtitle": tile.subtitle,
        "artwork": tile.artwork,
        "icon_name": tile.icon_name,
        "accent": tile.accent,
        "tags": list(tile.tags),
        "launch": _launch_to_dict(tile.launch),
    }


def _launch_to_dict(launch: LaunchSpec) -> dict[str, object]:
    return {
        "kind": launch.kind.value,
        "target": launch.target,
        "args": list(launch.args),
        "env": dict(launch.env),
        "browser_profile": launch.browser_profile,
        "user_agent": launch.user_agent,
        "spatial_nav": launch.spatial_nav,
        "fullscreen": launch.fullscreen,
    }
