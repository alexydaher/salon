# SPDX-License-Identifier: GPL-3.0-or-later
"""Load/save/migrate the tile catalogue config (~/.config/salon/tiles.json).

GSettings owns scalar preferences (see data/rocks.salon.Salon.gschema.xml);
this module owns only the tile/row catalogue, which is why it lives in
salon.core and stays gi-free and testable headlessly.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from salon.core.errors import ConfigError
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile

CURRENT_SCHEMA_VERSION = 1


def default_config_path() -> Path:
    xdg_config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return xdg_config_home / "salon" / "tiles.json"


@dataclass(slots=True)
class Config:
    schema: int = CURRENT_SCHEMA_VERSION
    rows: list[Row] = field(default_factory=list)


def load(path: Path) -> Config:
    """Load config from path. A missing file yields an empty, valid config."""
    if not path.exists():
        return Config()
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file at {path} is not valid JSON: {exc}") from exc
    return _parse(raw, path)


def save(config: Config, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _config_to_dict(config)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def _parse(raw: Any, path: Path) -> Config:
    if not isinstance(raw, dict) or "schema" not in raw:
        raise ConfigError(f"Config file at {path} is missing a 'schema' field.")
    schema = raw["schema"]
    if not isinstance(schema, int):
        raise ConfigError(f"Config file at {path} has a non-integer 'schema' field.")
    if schema > CURRENT_SCHEMA_VERSION:
        raise ConfigError(
            f"Config file at {path} was written by a newer version of Salon "
            f"(schema {schema}, this build supports up to {CURRENT_SCHEMA_VERSION}). "
            "Upgrade Salon, or remove the file to start fresh."
        )
    raw = _migrate(raw, schema)
    return _config_from_dict(raw)


def _migrate(raw: dict[str, Any], schema: int) -> dict[str, Any]:
    # CURRENT_SCHEMA_VERSION is 1; there is nothing to migrate from yet.
    # Future migrations get chained in here, each bumping raw["schema"].
    del schema
    return raw


def _config_from_dict(raw: dict[str, Any]) -> Config:
    rows = [_row_from_dict(r) for r in raw.get("rows", [])]
    return Config(schema=CURRENT_SCHEMA_VERSION, rows=rows)


def _row_from_dict(raw: dict[str, Any]) -> Row:
    tiles = [_tile_from_dict(t) for t in raw.get("tiles", [])]
    return Row(
        id=raw["id"],
        title=raw.get("title"),
        tiles=tiles,
        provider_id=raw.get("provider_id", "static"),
        tile_aspect=raw.get("tile_aspect", "wide"),
    )


def _tile_from_dict(raw: dict[str, Any]) -> Tile:
    launch_raw = raw["launch"]
    launch = LaunchSpec(
        kind=LaunchKind(launch_raw["kind"]),
        target=launch_raw["target"],
        args=tuple(launch_raw.get("args", ())),
        env=dict(launch_raw.get("env", {})),
        browser_profile=launch_raw.get("browser_profile"),
        user_agent=launch_raw.get("user_agent"),
        spatial_nav=launch_raw.get("spatial_nav", True),
        fullscreen=launch_raw.get("fullscreen", True),
    )
    return Tile(
        id=raw["id"],
        title=raw["title"],
        subtitle=raw.get("subtitle"),
        launch=launch,
        artwork=raw.get("artwork"),
        icon_name=raw.get("icon_name"),
        accent=raw.get("accent"),
        tags=tuple(raw.get("tags", ())),
    )


def _config_to_dict(config: Config) -> dict[str, Any]:
    return {
        "schema": config.schema,
        "rows": [_row_to_dict(r) for r in config.rows],
    }


def _row_to_dict(row: Row) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "provider_id": row.provider_id,
        "tile_aspect": row.tile_aspect,
        "tiles": [_tile_to_dict(t) for t in row.tiles],
    }


def _tile_to_dict(tile: Tile) -> dict[str, Any]:
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


def _launch_to_dict(launch: LaunchSpec) -> dict[str, Any]:
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
