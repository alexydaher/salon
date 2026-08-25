# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import re
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


def _valid() -> dict[str, object]:
    return {
        "schema": 1,
        "rows": [
            {
                "id": " streaming ",
                "title": " Streaming ",
                "tiles": [
                    {
                        "id": " video ",
                        "title": " Video ",
                        "subtitle": " ",
                        "accent": "#abc",
                        "tags": [" media ", "media", ""],
                        "launch": {"kind": "url", "target": "https://example.com"},
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    ("mutate", "location"),
    [
        (lambda value: value.update(schema=True), "schema"),
        (lambda value: value.update(rows={}), "rows"),
        (lambda value: value["rows"][0].update(id=4), "rows[0].id"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0].update(tile_aspect="tall"), "tile_aspect"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0]["tiles"][0].update(accent="red"), "accent"),  # type: ignore[index]
        (lambda value: value["rows"][0]["tiles"][0]["launch"].update(kind="nope"), "launch.kind"),  # type: ignore[index,union-attr]
        (
            lambda value: value["rows"][0]["tiles"][0]["launch"].update(  # type: ignore[index,union-attr]
                target="file:///tmp/x"
            ),
            "launch.target",
        ),
        (lambda value: value["rows"][0]["tiles"][0]["launch"].update(args="--x"), "launch.args"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0]["tiles"][0]["launch"].update(env={"A": 1}), "launch.env.A"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0].update(title=False), "rows[0].title"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0].update(provider_id=[]), "provider_id"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0].update(tiles={}), "rows[0].tiles"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0]["tiles"][0].pop("id"), "tiles[0].id"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0]["tiles"][0].pop("title"), "tiles[0].title"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0]["tiles"][0].update(subtitle=1), "subtitle"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0]["tiles"][0].update(artwork=False), "artwork"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0]["tiles"][0].update(icon_name=[]), "icon_name"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0]["tiles"][0].update(tags=["ok", 1]), "tags[1]"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0]["tiles"][0].update(launch=[]), "launch"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0]["tiles"][0]["launch"].pop("target"), "launch.target"),  # type: ignore[index,union-attr]
        (
            lambda value: value["rows"][0]["tiles"][0]["launch"].update(browser_profile=1),
            "browser_profile",
        ),  # type: ignore[index,union-attr]
        (
            lambda value: value["rows"][0]["tiles"][0]["launch"].update(user_agent=False),
            "user_agent",
        ),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0]["tiles"][0]["launch"].update(spatial_nav=1), "spatial_nav"),  # type: ignore[index,union-attr]
        (lambda value: value["rows"][0]["tiles"][0]["launch"].update(fullscreen=0), "fullscreen"),  # type: ignore[index,union-attr]
    ],
)
def test_every_bad_known_value_is_a_path_aware_config_error(
    tmp_path: Path, mutate, location: str
) -> None:
    value = _valid()
    mutate(value)
    path = tmp_path / "tiles.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ConfigError, match=re.escape(location)):
        config.load(path)


def test_normalizes_strings_colours_tags_and_optional_values(tmp_path: Path) -> None:
    value = _valid()
    value["future"] = {"ignored": True}
    path = tmp_path / "tiles.json"
    path.write_text(json.dumps(value))
    loaded = config.load(path)
    row = loaded.rows[0]
    tile = row.tiles[0]
    assert (row.id, row.title) == ("streaming", "Streaming")
    assert (tile.id, tile.title, tile.subtitle) == ("video", "Video", None)
    assert tile.accent == "#AABBCC"
    assert tile.tags == ("media",)
    saved = tmp_path / "round-trip.json"
    config.save(loaded, saved)
    assert "future" not in json.loads(saved.read_text())


def test_duplicate_ids_are_rejected_at_their_location(tmp_path: Path) -> None:
    value = _valid()
    value["rows"].append(value["rows"][0].copy())  # type: ignore[union-attr,index]
    path = tmp_path / "tiles.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ConfigError, match=r"rows\[1\]\.id"):
        config.load(path)


def test_malformed_utf8_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "tiles.json"
    path.write_bytes(b'\xff{"schema": 1}')
    with pytest.raises(ConfigError):
        config.load(path)


def test_non_finite_json_constant_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "tiles.json"
    path.write_text('{"schema": 1, "rows": [], "future": NaN}')
    with pytest.raises(ConfigError):
        config.load(path)


def test_root_must_be_an_object(tmp_path: Path) -> None:
    path = tmp_path / "tiles.json"
    path.write_text("[]")
    with pytest.raises(ConfigError, match="expected an object"):
        config.load(path)


def test_unreadable_file_failure_is_a_config_error(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "tiles.json"
    path.write_text("{}")
    monkeypatch.setattr(
        Path, "read_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("denied"))
    )
    with pytest.raises(ConfigError, match="denied"):
        config.load(path)
