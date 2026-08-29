# SPDX-License-Identifier: GPL-3.0-or-later
"""Backing up and restoring the catalogue.

`tiles.json` is the user's real investment in Salon and there was no way to
copy it, put a copy back, or start over — on a device whose only text input
is an on-screen keyboard driven by a D-pad.
"""

from __future__ import annotations

import os
from pathlib import Path

# GSettings, in memory and nowhere else. A dconf *write* is a D-Bus call to
# the writer daemon, which resolves the user database from its own
# environment — so a harness that redirects the XDG directories still edits
# the live session while reading its own empty copy back. Assigned rather
# than `setdefault`, and before `gi.repository` is imported, which is when
# the backend is chosen. Enforced by tests/test_settings_isolation.py.
os.environ["GSETTINGS_BACKEND"] = "memory"

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")

from salon.core import config as config_io  # noqa: E402
from salon.core.config import Config  # noqa: E402
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile  # noqa: E402
from salon.ui.settings import backup  # noqa: E402


def _tile(tile_id: str, title: str) -> Tile:
    return Tile(
        id=tile_id,
        title=title,
        subtitle=None,
        launch=LaunchSpec(kind=LaunchKind.URL, target="https://example.com"),
        artwork=None,
        icon_name=None,
        accent=None,
    )


def _config() -> Config:
    return Config(
        rows=[
            Row(
                id="entertainment",
                title="Entertainment",
                tiles=[_tile("a", "A")],
                provider_id="static",
            )
        ]
    )


class _Context:
    """The three things `backup.py` reaches for, and nothing else."""

    def __init__(self, path: Path) -> None:
        self.config = _config()
        self.config_path = str(path)
        self.messages: list[str] = []
        self.rebuilds = 0
        self.pops = 0

    def toast(self, message: str) -> None:
        self.messages.append(message)

    def rebuild(self) -> None:
        self.rebuilds += 1

    def pop(self) -> None:
        self.pops += 1

    def push(self, _panel: object) -> None:
        pass

    def save_config(self) -> None:
        config_io.save(self.config, Path(self.config_path))


def test_a_backup_round_trips_through_the_normal_save_path(tmp_path: Path) -> None:
    context = _Context(tmp_path / "tiles.json")
    context.save_config()

    backup._save(context)  # type: ignore[arg-type]
    saved = sorted(backup.backup_dir(context).glob("tiles-*.json"))  # type: ignore[arg-type]
    assert len(saved) == 1

    # Wreck the live catalogue, then put the backup back.
    context.config.rows.clear()
    backup._restore(context, saved[0])  # type: ignore[arg-type]

    assert [row.id for row in context.config.rows] == ["entertainment"]
    # Restored by writing the catalogue, not by copying the file: the file
    # monitor is how the home screen learns about any change, and there is
    # only ever one route to it.
    assert config_io.load(Path(context.config_path)).rows[0].title == "Entertainment"
    assert context.pops == 1


def test_backups_are_dated_rather_than_a_single_overwritten_slot(tmp_path: Path) -> None:
    """The reason to reach for this is usually that the last change was a
    mistake, and one slot means the mistake is already in it."""
    context = _Context(tmp_path / "tiles.json")
    directory = backup.backup_dir(context)  # type: ignore[arg-type]
    directory.mkdir(parents=True)
    for stamp in ("20260101-120000", "20260102-120000"):
        config_io.save(context.config, directory / f"tiles-{stamp}.json")

    listed = backup._backups(context)  # type: ignore[arg-type]
    assert [p.stem for p in listed] == ["tiles-20260102-120000", "tiles-20260101-120000"]
    assert backup._label(listed[0]) == "2 January 2026, 12:00"


def test_only_the_most_recent_backups_are_kept(tmp_path: Path) -> None:
    context = _Context(tmp_path / "tiles.json")
    directory = backup.backup_dir(context)  # type: ignore[arg-type]
    directory.mkdir(parents=True)
    for day in range(1, 15):
        config_io.save(context.config, directory / f"tiles-202601{day:02d}-120000.json")

    backup._save(context)  # type: ignore[arg-type]
    assert len(backup._backups(context)) == backup._KEEP  # type: ignore[arg-type]


def test_an_unreadable_backup_is_listed_and_refuses_to_restore(tmp_path: Path) -> None:
    """Hiding it would leave a file on disk that nothing in Salon admits to."""
    context = _Context(tmp_path / "tiles.json")
    directory = backup.backup_dir(context)  # type: ignore[arg-type]
    directory.mkdir(parents=True)
    broken = directory / "tiles-20260101-120000.json"
    broken.write_text("{ not json", encoding="utf-8")

    assert backup._rows_in(broken) == "Unreadable"
    backup._restore(context, broken)  # type: ignore[arg-type]
    assert context.messages and "couldn't be read" in context.messages[-1]
    # The live catalogue is untouched, which is the part that matters.
    assert [row.id for row in context.config.rows] == ["entertainment"]


def test_the_list_says_what_is_in_each_backup(tmp_path: Path) -> None:
    context = _Context(tmp_path / "tiles.json")
    directory = backup.backup_dir(context)  # type: ignore[arg-type]
    directory.mkdir(parents=True)
    path = directory / "tiles-20260101-120000.json"
    config_io.save(context.config, path)
    assert backup._rows_in(path) == "1 rows, 1 tiles"
