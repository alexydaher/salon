# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path

import pytest

from salon.core import config
from salon.core.errors import ConfigError
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile


def test_load_missing_file_yields_empty_config(tmp_path: Path) -> None:
    cfg = config.load(tmp_path / "does-not-exist.json")
    assert cfg.schema == config.CURRENT_SCHEMA_VERSION
    assert cfg.rows == []


def test_load_corrupt_json_raises_config_error(tmp_path: Path) -> None:
    path = tmp_path / "tiles.json"
    path.write_text("{not valid json")
    with pytest.raises(ConfigError):
        config.load(path)


def test_load_missing_schema_field_raises_config_error(tmp_path: Path) -> None:
    path = tmp_path / "tiles.json"
    path.write_text(json.dumps({"rows": []}))
    with pytest.raises(ConfigError):
        config.load(path)


def test_load_future_schema_raises_config_error(tmp_path: Path) -> None:
    path = tmp_path / "tiles.json"
    path.write_text(json.dumps({"schema": config.CURRENT_SCHEMA_VERSION + 1, "rows": []}))
    with pytest.raises(ConfigError, match="newer version"):
        config.load(path)


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "tiles.json"
    tile = Tile(
        id="chrome-nf",
        title="GeForce NOW",
        subtitle="Cloud gaming",
        launch=LaunchSpec(
            kind=LaunchKind.URL,
            target="https://play.geforcenow.com",
            browser_profile="geforce-now",
        ),
        artwork="https://example.com/art.png",
        icon_name=None,
        accent="#E8A33D",
        tags=("games",),
    )
    row = Row(id="games", title="Games", tiles=[tile], provider_id="static")
    original = config.Config(rows=[row])

    config.save(original, path)
    loaded = config.load(path)

    assert loaded.schema == config.CURRENT_SCHEMA_VERSION
    assert len(loaded.rows) == 1
    loaded_row = loaded.rows[0]
    assert loaded_row.id == "games"
    assert len(loaded_row.tiles) == 1
    loaded_tile = loaded_row.tiles[0]
    assert loaded_tile.id == "chrome-nf"
    assert loaded_tile.launch.kind is LaunchKind.URL
    assert loaded_tile.launch.target == "https://play.geforcenow.com"
    assert loaded_tile.launch.browser_profile == "geforce-now"
    assert loaded_tile.tags == ("games",)


def test_save_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "tiles.json"
    config.save(config.Config(), path)
    assert path.exists()
    assert json.loads(path.read_text())["schema"] == config.CURRENT_SCHEMA_VERSION
