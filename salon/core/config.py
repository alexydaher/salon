# SPDX-License-Identifier: GPL-3.0-or-later
"""Validated load/save support for ``~/.config/salon/tiles.json``."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, NoReturn
from urllib.parse import urlsplit

from salon.core.config_serialization import config_to_dict
from salon.core.errors import ConfigError
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile

CURRENT_SCHEMA_VERSION = 1
_ACCENT_RE = re.compile(r"^#(?P<rgb>[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def default_config_path() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "salon" / "tiles.json"


@dataclass(slots=True)
class Config:
    schema: int = CURRENT_SCHEMA_VERSION
    rows: list[Row] = field(default_factory=list)


def _bad(path: Path, location: str, message: str) -> NoReturn:
    where = f" at {location}" if location else ""
    raise ConfigError(f"Config file at {path}{where}: {message}")


def load(path: Path) -> Config:
    """Load *path*, translating every file/content failure to ``ConfigError``."""
    if not path.exists():
        return Config()
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda value: _bad(path, "", f"invalid JSON constant {value!r}"),
        )
    except ConfigError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Config file at {path} could not be read as JSON: {exc}") from exc
    try:
        return _parse(raw, path)
    except ConfigError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        # This is the public contract: callers only need one error path for
        # any malformed known value, including parser-library edge cases.
        raise ConfigError(f"Config file at {path} is invalid: {exc}") from exc


def save(config: Config, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(config_to_dict(config), indent=2), encoding="utf-8")
    tmp.replace(path)


def _object(value: object, path: Path, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _bad(path, location, "expected an object")
    return value


def _list(value: object, path: Path, location: str) -> list[Any]:
    if not isinstance(value, list):
        _bad(path, location, "expected an array")
    return value


def _string(value: object, path: Path, location: str, *, empty: bool = False) -> str:
    if not isinstance(value, str):
        _bad(path, location, "expected a string")
    result = value.strip()
    if not empty and not result:
        _bad(path, location, "must not be empty")
    return result


def _optional_string(value: object, path: Path, location: str) -> str | None:
    if value is None:
        return None
    return _string(value, path, location, empty=True) or None


def _boolean(value: object, path: Path, location: str) -> bool:
    if not isinstance(value, bool):
        _bad(path, location, "expected a boolean")
    return value


def _required(raw: dict[str, Any], key: str, path: Path, location: str) -> object:
    if key not in raw:
        _bad(path, f"{location}.{key}".lstrip("."), "required field is missing")
    return raw[key]


def _parse(raw: Any, path: Path) -> Config:
    root = _object(raw, path, "")
    schema = _required(root, "schema", path, "")
    if isinstance(schema, bool) or not isinstance(schema, int):
        _bad(path, "schema", "expected an integer")
    if schema > CURRENT_SCHEMA_VERSION:
        _bad(path, "schema", f"was written by a newer version of Salon (schema {schema})")
    if schema < 1:
        _bad(path, "schema", f"unsupported schema version {schema}")
    rows: list[Row] = []
    seen: set[str] = set()
    for index, value in enumerate(_list(root.get("rows", []), path, "rows")):
        location = f"rows[{index}]"
        row = _row_from_dict(_object(value, path, location), path, location)
        if row.id in seen:
            _bad(path, f"{location}.id", f"duplicate row id {row.id!r}")
        seen.add(row.id)
        rows.append(row)
    return Config(rows=rows)


def _string_array(value: object, path: Path, location: str) -> tuple[str, ...]:
    return tuple(
        _string(item, path, f"{location}[{index}]", empty=True)
        for index, item in enumerate(_list(value, path, location))
    )

def _environment(value: object, path: Path, location: str) -> MappingProxyType[str, str]:
    result: dict[str, str] = {}
    for key, item in _object(value, path, location).items():
        if not isinstance(key, str) or not key:
            _bad(path, location, "environment keys must be nonempty strings")
        if not isinstance(item, str):
            _bad(path, f"{location}.{key}", "expected a string")
        result[key] = item
    return MappingProxyType(result)


def _row_from_dict(raw: dict[str, Any], path: Path, location: str) -> Row:
    row_id = _string(_required(raw, "id", path, location), path, f"{location}.id")
    aspect = _string(raw.get("tile_aspect", "wide"), path, f"{location}.tile_aspect")
    if aspect not in ("wide", "square", "poster"):
        _bad(path, f"{location}.tile_aspect", "expected wide, square, or poster")
    tiles: list[Tile] = []
    seen: set[str] = set()
    for index, value in enumerate(_list(raw.get("tiles", []), path, f"{location}.tiles")):
        tile_location = f"{location}.tiles[{index}]"
        tile = _tile_from_dict(_object(value, path, tile_location), path, tile_location)
        if tile.id in seen:
            _bad(path, f"{tile_location}.id", f"duplicate tile id {tile.id!r} in row {row_id!r}")
        seen.add(tile.id)
        tiles.append(tile)
    return Row(
        id=row_id,
        title=_optional_string(raw.get("title"), path, f"{location}.title"),
        tiles=tiles,
        provider_id=_string(raw.get("provider_id", "static"), path, f"{location}.provider_id"),
        tile_aspect=aspect,  # type: ignore[arg-type]
    )


def _accent(value: object, path: Path, location: str) -> str | None:
    value = _optional_string(value, path, location)
    if value is None:
        return None
    match = _ACCENT_RE.fullmatch(value)
    if match is None:
        _bad(path, location, "expected a colour in #RGB or #RRGGBB form")
    rgb = match.group("rgb")
    if len(rgb) == 3:
        rgb = "".join(channel * 2 for channel in rgb)
    return f"#{rgb.upper()}"


def _tile_from_dict(raw: dict[str, Any], path: Path, location: str) -> Tile:
    launch_location = f"{location}.launch"
    launch_raw = _object(_required(raw, "launch", path, location), path, launch_location)
    kind_text = _string(
        _required(launch_raw, "kind", path, launch_location), path, f"{launch_location}.kind"
    )
    try:
        kind = LaunchKind(kind_text)
    except ValueError:
        _bad(path, f"{launch_location}.kind", f"unknown launch kind {kind_text!r}")
    target = _string(
        _required(launch_raw, "target", path, launch_location), path, f"{launch_location}.target"
    )
    if kind is LaunchKind.URL:
        try:
            parts = urlsplit(target)
            port = parts.port
        except ValueError as error:
            _bad(path, f"{launch_location}.target", f"invalid URL: {error}")
        if parts.scheme not in ("http", "https") or not parts.netloc:
            _bad(path, f"{launch_location}.target", "URL launches require an absolute HTTP(S) URL")
        if port is not None and not 1 <= port <= 65535:
            _bad(path, f"{launch_location}.target", "URL port must be between 1 and 65535")
    launch = LaunchSpec(
        kind=kind,
        target=target,
        args=_string_array(launch_raw.get("args", []), path, f"{launch_location}.args"),
        env=_environment(launch_raw.get("env", {}), path, f"{launch_location}.env"),
        browser_profile=_optional_string(
            launch_raw.get("browser_profile"), path, f"{launch_location}.browser_profile"
        ),
        user_agent=_optional_string(
            launch_raw.get("user_agent"), path, f"{launch_location}.user_agent"
        ),
        spatial_nav=_boolean(
            launch_raw.get("spatial_nav", True), path, f"{launch_location}.spatial_nav"
        ),
        fullscreen=_boolean(
            launch_raw.get("fullscreen", True), path, f"{launch_location}.fullscreen"
        ),
    )
    tags: list[str] = []
    for tag in _string_array(raw.get("tags", []), path, f"{location}.tags"):
        if tag and tag not in tags:
            tags.append(tag)
    return Tile(
        id=_string(_required(raw, "id", path, location), path, f"{location}.id"),
        title=_string(_required(raw, "title", path, location), path, f"{location}.title"),
        subtitle=_optional_string(raw.get("subtitle"), path, f"{location}.subtitle"),
        launch=launch,
        artwork=_optional_string(raw.get("artwork"), path, f"{location}.artwork"),
        icon_name=_optional_string(raw.get("icon_name"), path, f"{location}.icon_name"),
        accent=_accent(raw.get("accent"), path, f"{location}.accent"),
        tags=tuple(tags),
    )
