# SPDX-License-Identifier: GPL-3.0-or-later
"""Saving and restoring the catalogue.

`tiles.json` is the user's real investment in Salon — the rows, the tiles,
the artwork paths and the accents — and there was no way to copy it, no way
to put a copy back, and no way to start over. Editing it by hand is
documented, which is not the same as being able to recover from having done
so with a D-pad.

Backups are timestamped files beside the config, never a single "backup"
that the next save overwrites: the reason to reach for this is usually that
the last change was a mistake, and one slot means the mistake is already in
it.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from salon.core import config as config_io
from salon.ui.settings.context import Panel, SettingsContext, confirm_panel
from salon.ui.settings.widgets import (
    ActionRow,
    GroupRow,
    InfoRow,
    SettingsRow,
)

_SUFFIX = ".json"
_PREFIX = "tiles-"
# Enough to undo a bad afternoon, few enough that the list stays walkable
# with a D-pad. Older ones are removed on each new backup.
_KEEP = 10


def backup_dir(context: SettingsContext) -> Path:
    return Path(context.config_path).parent / "backups"


def _backups(context: SettingsContext) -> list[Path]:
    directory = backup_dir(context)
    if not directory.is_dir():
        return []
    return sorted(directory.glob(f"{_PREFIX}*{_SUFFIX}"), reverse=True)


def _label(path: Path) -> str:
    """The timestamp, read back out of the name rather than off the file.

    `stat` would be the obvious source and is the wrong one: copying a
    backup off the machine and back again resets it, and the moment that
    matters is when the layout was saved.
    """
    stamp = path.stem[len(_PREFIX) :]
    try:
        return datetime.strptime(stamp, "%Y%m%d-%H%M%S").strftime("%-d %B %Y, %H:%M")
    except ValueError:
        return path.stem


def backup_panel(context: SettingsContext) -> Panel:
    def build() -> list[SettingsRow]:
        saved = _backups(context)
        rows: list[SettingsRow] = [
            GroupRow("Save"),
            ActionRow(
                "Back up this layout now",
                lambda: _save(context),
                detail=f"Writes a dated copy into {backup_dir(context)}",
            ),
            GroupRow("Restore"),
        ]
        if not saved:
            rows.append(
                InfoRow("No backups yet", "", detail="Save one before you make big changes")
            )
        rows.extend(
            ActionRow(
                _label(path),
                lambda p=path: _confirm_restore(context, p),
                detail=f"{_rows_in(path)} — replaces every row and tile you have now",
            )
            for path in saved
        )
        return rows

    return Panel(title="Back up and restore", build=build)


def _rows_in(path: Path) -> str:
    """What is in a backup, so the list is a choice rather than a lottery.

    A backup that no longer parses is still listed and still says so: it
    cannot be restored, and hiding it would leave a file on disk that
    nothing in Salon admits to.
    """
    try:
        saved = config_io.load(path)
    except Exception:  # noqa: BLE001 - config.load raises its own error type
        return "Unreadable"
    tiles = sum(len(row.tiles) for row in saved.rows)
    return f"{len(saved.rows)} rows, {tiles} tiles"


def _save(context: SettingsContext) -> None:
    directory = backup_dir(context)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = directory / f"{_PREFIX}{stamp}{_SUFFIX}"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        config_io.save(context.config, target)
    except OSError as error:
        context.toast(f"Couldn't save a backup: {error.strerror or error}")
        return
    for old in _backups(context)[_KEEP:]:
        old.unlink(missing_ok=True)
    context.toast(f"Layout backed up as {_label(target)}.")
    context.rebuild()


def _confirm_restore(context: SettingsContext, path: Path) -> None:
    context.push(
        confirm_panel(
            context,
            f"Replace your rows and tiles with the backup from {_label(path)}?",
            "Restore",
            lambda: _restore(context, path),
        )
    )


def _restore(context: SettingsContext, path: Path) -> None:
    """Load the backup, then write it out as the live catalogue.

    Written through `save_config` rather than copied over the file, so the
    restore takes exactly the path a hand edit takes: the file monitor
    notices, the catalogue reloads, and there is still only one way the
    home screen ever changes.
    """
    try:
        saved = config_io.load(path)
    except Exception as error:  # noqa: BLE001 - config.load raises its own error type
        context.toast(f"That backup couldn't be read: {error}")
        return
    context.config.rows[:] = list(saved.rows)
    context.save_config()
    context.toast("Layout restored.")
    context.pop()
