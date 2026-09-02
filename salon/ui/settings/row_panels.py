# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Tiles: the catalogue, one row of it, and a way back.

"Reorder rows" is gone. It was a two-step picker — choose a row, then
choose a position — reached from a screen that already lists the rows, and
the row's own panel is where you are standing when you decide to move it.
Position is a value there now, like everything else.
"""

from __future__ import annotations

from salon.core import editing
from salon.core.model import LaunchKind, Tile
from salon.ui.settings.add_tile_panels import add_tile_menu
from salon.ui.settings.backup import backup_panel
from salon.ui.settings.context import Panel, SettingsContext, confirm_panel
from salon.ui.settings.tile_details import ASPECTS, KINDS
from salon.ui.settings.tile_panel import tile_panel
from salon.ui.settings.widgets import (
    ActionRow,
    ChoiceRow,
    GroupRow,
    InfoRow,
    SettingsRow,
    TextRow,
    opens_panel,
)


def rows_panel(context: SettingsContext) -> Panel:
    """Top level: every row in the catalogue, plus adding and backing up."""

    def build() -> list[SettingsRow]:
        rows: list[SettingsRow] = [GroupRow("Your rows")]
        for row in context.config.rows:
            count = len(row.tiles)
            rows.append(
                opens_panel(
                    row.title or "Unlabelled row",
                    lambda r=row.id: context.push(row_panel(context, r)),
                    detail=f"{count} tile{'s' if count != 1 else ''}",
                )
            )
        if not context.config.rows:
            rows.append(InfoRow("Nothing here yet", "", detail="Add a row to get started"))
        rows += [
            GroupRow("Add"),
            ActionRow(
                "Add a row",
                lambda: _add_row(context),
                value="+",
            ),
            GroupRow("This section"),
            opens_panel(
                "Back up and restore",
                lambda: context.push(backup_panel(context)),
            ),
        ]
        return rows

    def summary() -> str:
        count = len(context.config.rows)
        tiles = sum(len(row.tiles) for row in context.config.rows)
        return f"{count} row{'s' if count != 1 else ''}, {tiles} tiles" if count else "Empty"

    return Panel(
        title="Tiles",
        build=build,
        summary=summary,
        panel_id="tiles",
        icon_name="view-grid-symbolic",
    )


def _add_row(context: SettingsContext) -> None:
    def done(title: str | None) -> None:
        if title is None:
            return
        row = editing.add_row(context.config, title.strip() or editing.DEFAULT_ROW_TITLE)
        context.save_config()
        context.rebuild()
        context.push(row_panel(context, row.id))

    context.edit_text("Name the new row", "", done)


def row_panel(context: SettingsContext, row_id: str) -> Panel:
    """One row: what it is called, where it sits, and what is in it."""

    def title() -> str:
        row = editing.find_row(context.config, row_id)
        return (row.title if row is not None else "") or "Unlabelled row"

    def build() -> list[SettingsRow]:
        row = editing.find_row(context.config, row_id)
        if row is None:
            # Deleted underneath us — a hand edit, or this panel left on the
            # stack after a delete. Say so rather than crash.
            return [InfoRow("This row no longer exists", "")]

        rows: list[SettingsRow] = [
            GroupRow("The row"),
            TextRow(
                "Name",
                lambda: row.title or "",
                lambda: _rename_row(context, row_id),
                placeholder="Unlabelled",
            ),
            ChoiceRow(
                "Tile shape",
                ASPECTS,
                lambda: row.tile_aspect,
                lambda value: _set_aspect(context, row_id, value),
                detail="Wide, poster, or square",
            ),
            _position_row(context, row_id),
            GroupRow("Tiles in this row"),
        ]
        rows.extend(
            opens_panel(
                tile.title,
                lambda t=tile.id: context.push(tile_panel(context, row_id, t)),
                detail=_describe_launch(tile),
            )
            for tile in row.tiles
        )
        if not row.tiles:
            rows.append(InfoRow("No tiles yet", "", detail="Add one below"))
        rows += [
            ActionRow(
                "Add a tile",
                lambda: add_tile_menu(context, row_id),
                value="+",
            ),
            GroupRow("Remove"),
            ActionRow(
                "Delete this row",
                lambda: _delete_row(context, row_id),
                detail="Deletes every tile in this row",
                danger=True,
            ),
        ]
        return rows

    return Panel(title=title(), build=build, live_title=title)


def _position_row(context: SettingsContext, row_id: str) -> SettingsRow:
    """Where this row sits on the home screen, top to bottom."""
    all_rows = context.config.rows
    current = next((index for index, row in enumerate(all_rows) if row.id == row_id), 0)

    def move(key: str) -> None:
        target = int(key)
        step = 1 if target > current else -1
        for _ in range(abs(target - current)):
            editing.move_row(context.config, row_id, step)
        context.save_config()
        context.rebuild()

    return ChoiceRow(
        "Position",
        [(str(index), f"{index + 1} of {len(all_rows)}") for index in range(len(all_rows))],
        lambda: str(current),
        move,
    )


def _describe_launch(tile: Tile) -> str:
    kind = tile.launch.kind
    if kind is LaunchKind.URL:
        return tile.launch.target
    if kind is LaunchKind.BUILTIN:
        return f"Built in: {tile.launch.target}"
    return f"{dict(KINDS).get(kind.value, kind.value)}: {tile.launch.target}"


def _rename_row(context: SettingsContext, row_id: str) -> None:
    row = editing.find_row(context.config, row_id)
    if row is None:
        return

    def done(title: str | None) -> None:
        if title is None:
            return
        editing.rename_row(context.config, row_id, title.strip())
        context.save_config()
        context.rebuild()

    context.edit_text("Row name", row.title or "", done)


def _set_aspect(context: SettingsContext, row_id: str, aspect: str) -> None:
    editing.set_row_aspect(context.config, row_id, aspect)
    context.save_config()


def _delete_row(context: SettingsContext, row_id: str) -> None:
    row = editing.find_row(context.config, row_id)
    title = (row.title if row else None) or "this row"

    def confirmed() -> None:
        editing.remove_row(context.config, row_id)
        context.save_config()
        context.pop()

    context.push(confirm_panel(context, f"Delete {title}?", "Delete row", confirmed))
