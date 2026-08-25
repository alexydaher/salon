# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused catalogue-editing panel builder."""

from __future__ import annotations

from salon.core import editing
from salon.core.model import LaunchKind, Tile
from salon.ui.settings.context import Panel, SettingsContext, confirm_panel
from salon.ui.settings.reorder_panels import reorder_rows_panel, reorder_tiles_panel
from salon.ui.settings.widgets import (
    ActionRow,
    ChoiceRow,
    InfoRow,
    SettingsRow,
    TextRow,
)

_ASPECTS = [("wide", "Wide"), ("square", "Square"), ("poster", "Poster")]
_KINDS = [
    (LaunchKind.DESKTOP.value, "Installed app"),
    (LaunchKind.URL.value, "Web address"),
    (LaunchKind.FLATPAK.value, "Flatpak"),
    (LaunchKind.COMMAND.value, "Command"),
]
from salon.ui.settings.add_tile_panels import _add_tile_menu  # noqa: E402
from salon.ui.settings.tile_panel import tile_panel  # noqa: E402


def rows_panel(context: SettingsContext) -> Panel:
    """Top level: every row in the catalogue, plus "add row"."""

    def build() -> list[SettingsRow]:
        rows: list[SettingsRow] = []
        if len(context.config.rows) > 1:
            rows.append(
                ActionRow(
                    "Reorder rows",
                    lambda: context.push(reorder_rows_panel(context)),
                    detail="Choose a row, then its new position",
                    value="›",
                )
            )
        for row in context.config.rows:
            count = len(row.tiles)
            captured = row.id
            rows.append(
                ActionRow(
                    row.title or "Unlabelled row",
                    lambda r=captured: context.push(row_panel(context, r)),
                    detail=f"{count} tile{'s' if count != 1 else ''}",
                    value="›",
                )
            )
        rows.append(ActionRow("Add row", lambda: _add_row(context), value="+"))
        if not context.config.rows:
            rows.insert(0, InfoRow("Nothing here yet", "Add a row to get started"))
        return rows

    return Panel(title="Tiles", build=build, panel_id="tiles", icon_name="view-grid-symbolic")


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
    """One row: its own properties, then its tiles."""

    def build() -> list[SettingsRow]:
        row = editing.find_row(context.config, row_id)
        if row is None:
            # The row was deleted underneath us (hand edit, or this panel
            # left on the stack after a delete). Say so rather than crash.
            return [InfoRow("This row no longer exists", "")]

        rows: list[SettingsRow] = [
            TextRow(
                "Name",
                lambda: row.title or "",
                lambda: _rename_row(context, row_id),
                placeholder="Unlabelled",
            ),
            ChoiceRow(
                "Tile shape",
                _ASPECTS,
                lambda: row.tile_aspect,
                lambda value: _set_aspect(context, row_id, value),
            ),
        ]
        if len(row.tiles) > 1:
            rows.append(
                ActionRow(
                    "Reorder tiles",
                    lambda: context.push(reorder_tiles_panel(context, row_id)),
                    detail="Choose a tile, then its new position",
                    value="›",
                )
            )
        for tile in row.tiles:
            captured = tile.id
            rows.append(
                ActionRow(
                    tile.title,
                    lambda t=captured: context.push(tile_panel(context, row_id, t)),
                    detail=_describe_launch(tile),
                    value="›",
                )
            )
        rows.append(ActionRow("Add tile", lambda: _add_tile_menu(context, row_id), value="+"))
        rows.append(
            ActionRow(
                "Delete row",
                lambda: _delete_row(context, row_id),
                detail="Removes the row and every tile in it",
                danger=True,
            )
        )
        return rows

    return Panel(title="Row", build=build)


def _describe_launch(tile: Tile) -> str:
    kind = tile.launch.kind
    if kind is LaunchKind.URL:
        return tile.launch.target
    if kind is LaunchKind.BUILTIN:
        return f"Built in: {tile.launch.target}"
    return f"{dict(_KINDS).get(kind.value, kind.value)}: {tile.launch.target}"


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


def _move_row(context: SettingsContext, row_id: str, delta: int) -> None:
    if editing.move_row(context.config, row_id, delta):
        context.save_config()
        context.toast("Row moved")
    else:
        context.toast("Already at the end")


def _delete_row(context: SettingsContext, row_id: str) -> None:
    row = editing.find_row(context.config, row_id)
    title = (row.title if row else None) or "this row"

    def confirmed() -> None:
        editing.remove_row(context.config, row_id)
        context.save_config()
        context.pop()

    context.push(confirm_panel(context, f"Delete {title}?", "Delete row", confirmed))
