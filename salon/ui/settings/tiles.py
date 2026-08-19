# SPDX-License-Identifier: GPL-3.0-or-later
"""The tile editor (§6.8's Tiles section).

M8's acceptance criterion in one screen: a tile can be created, given
artwork, reordered and deleted without touching a text editor. Three
levels, each a panel:

    Tiles ─ rows ──▶ one row ─ its tiles ──▶ one tile

Every mutation goes through `core/editing.py` and is written straight to
`tiles.json`. Nothing here touches the running catalogue: the home screen
already watches that file and rebuilds on change (§5's hot reload), so an
in-app edit and a hand edit take exactly the same path. That's one reload
mechanism to get right instead of two, and it means the editor cannot leave
the screen showing something the file doesn't say.

Artwork is assigned by *naming the drop folder file*, not by a file picker:
§7.4 makes `$XDG_DATA_HOME/salon/artwork/<tile_id>.{jpg,png,webp}` the
primary path, and a D-pad file browser over the whole filesystem would be a
worse way to reach the same place. The row tells the user the exact
filename to drop.
"""

from __future__ import annotations

from collections.abc import Callable

from salon.core import editing
from salon.core.model import LaunchKind, Tile
from salon.services.artwork import artwork_drop_dir
from salon.ui.settings.context import Panel, SettingsContext
from salon.ui.settings.widgets import (
    ActionRow,
    ChoiceRow,
    InfoRow,
    SettingsRow,
    TextRow,
    ToggleRow,
)

_ASPECTS = [("wide", "Wide"), ("square", "Square"), ("poster", "Poster")]
_KINDS = [
    (LaunchKind.DESKTOP.value, "Installed app"),
    (LaunchKind.URL.value, "Web address"),
    (LaunchKind.FLATPAK.value, "Flatpak"),
    (LaunchKind.COMMAND.value, "Command"),
]


def rows_panel(context: SettingsContext) -> Panel:
    """Top level: every row in the catalogue, plus "add row"."""

    def build() -> list[SettingsRow]:
        rows: list[SettingsRow] = []
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

    return Panel(title="Tiles", build=build, icon_name="view-grid-symbolic")


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
            ActionRow("Move row up", lambda: _move_row(context, row_id, -1), value="▲"),
            ActionRow("Move row down", lambda: _move_row(context, row_id, 1), value="▼"),
        ]
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

    context.push(_confirm_panel(context, f"Delete {title}?", "Delete row", confirmed))


# --- adding tiles --------------------------------------------------------


def _add_tile_menu(context: SettingsContext, row_id: str) -> None:
    """§6.8: adding a tile offers an installed application, a web address,
    or a custom command."""

    def build() -> list[SettingsRow]:
        return [
            ActionRow(
                "Installed app",
                lambda: context.push(_installed_panel(context, row_id)),
                detail="Pick from everything on this machine",
                value="›",
            ),
            ActionRow(
                "Web address",
                lambda: _add_url(context, row_id),
                detail="Opens in its own browser profile",
            ),
            ActionRow(
                "Command",
                lambda: _add_command(context, row_id),
                detail="Runs an executable directly",
            ),
        ]

    context.push(Panel(title="Add tile", build=build))


def _installed_panel(context: SettingsContext, row_id: str) -> Panel:
    """Populated asynchronously — the desktop-entry scan is far too slow to
    run on the frame clock (§10), so the panel opens saying so and fills in
    when the scan lands."""
    found: list[Tile] = []

    def build() -> list[SettingsRow]:
        if not found:
            context.installed_apps(_on_scanned)
            return [InfoRow("Looking for installed apps…", "")]
        return [
            ActionRow(app.title, lambda a=app: _add_installed(context, row_id, a))
            for app in found
        ]

    def _on_scanned(apps: list[Tile]) -> None:
        if found:
            return
        found.extend(apps)
        context.rebuild()

    return Panel(title="Installed app", build=build)


def _add_installed(context: SettingsContext, row_id: str, app: Tile) -> None:
    created = editing.new_tile(
        context.config,
        row_id,
        title=app.title,
        kind=LaunchKind.DESKTOP,
        target=app.launch.target,
        icon_name=app.icon_name,
    )
    editing.add_tile(context.config, row_id, created)
    context.save_config()
    context.pop()  # the installed-app list
    context.pop()  # the "Add tile" menu
    context.toast(f"Added {created.title}")


def _add_url(context: SettingsContext, row_id: str) -> None:
    def got_title(title: str | None) -> None:
        if title is None or not title.strip():
            return

        def got_url(url: str | None) -> None:
            if url is None or not url.strip():
                return
            target = url.strip()
            if not target.startswith(("http://", "https://")):
                target = f"https://{target}"
            created = editing.new_tile(
                context.config,
                row_id,
                title=title.strip(),
                kind=LaunchKind.URL,
                target=target,
                icon_name="web-browser-symbolic",
            )
            editing.add_tile(context.config, row_id, created)
            context.save_config()
            context.pop()
            context.toast(f"Added {created.title}")

        context.edit_text("Web address", "https://", got_url)

    context.edit_text("Tile name", "", got_title)


def _add_command(context: SettingsContext, row_id: str) -> None:
    def got_title(title: str | None) -> None:
        if title is None or not title.strip():
            return

        def got_command(command: str | None) -> None:
            if command is None or not command.strip():
                return
            created = editing.new_tile(
                context.config,
                row_id,
                title=title.strip(),
                kind=LaunchKind.COMMAND,
                target=command.strip(),
                icon_name="application-x-executable-symbolic",
            )
            editing.add_tile(context.config, row_id, created)
            context.save_config()
            context.pop()
            context.toast(f"Added {created.title}")

        context.edit_text("Command to run", "", got_command)

    context.edit_text("Tile name", "", got_title)


# --- editing one tile ----------------------------------------------------


def tile_panel(context: SettingsContext, row_id: str, tile_id: str) -> Panel:
    def build() -> list[SettingsRow]:
        tile = editing.find_tile(context.config, row_id, tile_id)
        if tile is None:
            return [InfoRow("This tile no longer exists", "")]

        rows: list[SettingsRow] = [
            TextRow("Name", lambda: tile.title, lambda: _edit_title(context, row_id, tile_id)),
            TextRow(
                "Subtitle",
                lambda: tile.subtitle or "",
                lambda: _edit_subtitle(context, row_id, tile_id),
            ),
            ChoiceRow(
                "Type",
                _KINDS,
                lambda: tile.launch.kind.value,
                lambda value: _set_kind(context, row_id, tile_id, value),
            ),
            TextRow(
                _target_label(tile),
                lambda: tile.launch.target,
                lambda: _edit_target(context, row_id, tile_id),
            ),
            TextRow(
                "Accent colour",
                lambda: tile.accent or "",
                lambda: _edit_accent(context, row_id, tile_id),
                placeholder="From artwork",
            ),
            InfoRow(
                "Artwork",
                "Set" if tile.artwork else "Drop folder",
                detail=f"Drop an image at {artwork_drop_dir()}/{tile.id}.png",
            ),
            TextRow(
                "Artwork path or URL",
                lambda: tile.artwork or "",
                lambda: _edit_artwork(context, row_id, tile_id),
                placeholder="Not set",
            ),
        ]
        if tile.launch.kind is LaunchKind.URL:
            rows.append(
                ToggleRow(
                    "Open fullscreen",
                    lambda: tile.launch.fullscreen,
                    lambda value: _set_fullscreen(context, row_id, tile_id, value),
                    detail="Starts the browser window with no chrome around the page.",
                )
            )
            rows.append(
                ToggleRow(
                    "Spatial navigation",
                    lambda: tile.launch.spatial_nav,
                    lambda value: _set_spatial_nav(context, row_id, tile_id, value),
                    detail="Arrow keys move to the nearest element. Off for sites it breaks.",
                )
            )
        rows += [
            ActionRow("Move left", lambda: _move_tile(context, row_id, tile_id, -1), value="◀"),
            ActionRow("Move right", lambda: _move_tile(context, row_id, tile_id, 1), value="▶"),
            ActionRow("Move to another row", lambda: _move_to_row(context, row_id, tile_id)),
            ActionRow(
                "Delete tile",
                lambda: _delete_tile(context, row_id, tile_id),
                danger=True,
            ),
        ]
        return rows

    return Panel(title="Tile", build=build)


def _target_label(tile: Tile) -> str:
    return {
        LaunchKind.URL: "Web address",
        LaunchKind.DESKTOP: "Application id",
        LaunchKind.FLATPAK: "Flatpak id",
        LaunchKind.COMMAND: "Command",
    }.get(tile.launch.kind, "Target")


def _with_tile(
    context: SettingsContext, row_id: str, tile_id: str
) -> Tile | None:
    return editing.find_tile(context.config, row_id, tile_id)


def _edit_title(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return

    def done(value: str | None) -> None:
        if value is None or not value.strip():
            return
        tile.title = value.strip()
        context.save_config()
        context.rebuild()

    context.edit_text("Tile name", tile.title, done)


def _edit_subtitle(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return

    def done(value: str | None) -> None:
        if value is None:
            return
        tile.subtitle = value.strip() or None
        context.save_config()
        context.rebuild()

    context.edit_text("Subtitle", tile.subtitle or "", done)


def _edit_target(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return

    def done(value: str | None) -> None:
        if value is None or not value.strip():
            return
        editing.set_launch_target(tile, value.strip())
        context.save_config()
        context.rebuild()

    context.edit_text(_target_label(tile), tile.launch.target, done)


def _edit_accent(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return

    def done(value: str | None) -> None:
        if value is None:
            return
        text = value.strip()
        if text and not text.startswith("#"):
            text = f"#{text}"
        tile.accent = text or None
        context.save_config()
        context.rebuild()

    context.edit_text("Accent colour, e.g. #E50914", tile.accent or "#", done)


def _edit_artwork(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return

    def done(value: str | None) -> None:
        if value is None:
            return
        tile.artwork = value.strip() or None
        context.save_config()
        context.rebuild()

    context.edit_text("Artwork path or https:// URL", tile.artwork or "", done)


def _set_kind(context: SettingsContext, row_id: str, tile_id: str, value: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return
    editing.set_launch_kind(tile, LaunchKind(value))
    context.save_config()
    context.rebuild()


def _set_fullscreen(
    context: SettingsContext, row_id: str, tile_id: str, enabled: bool
) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return
    editing.set_fullscreen(tile, enabled)
    context.save_config()


def _set_spatial_nav(
    context: SettingsContext, row_id: str, tile_id: str, enabled: bool
) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return
    editing.set_spatial_nav(tile, enabled)
    context.save_config()


def _move_tile(context: SettingsContext, row_id: str, tile_id: str, delta: int) -> None:
    if editing.move_tile(context.config, row_id, tile_id, delta):
        context.save_config()
        context.toast("Tile moved")
    else:
        context.toast("Already at the end of the row")


def _move_to_row(context: SettingsContext, row_id: str, tile_id: str) -> None:
    def build() -> list[SettingsRow]:
        others = [row for row in context.config.rows if row.id != row_id]
        if not others:
            return [InfoRow("No other rows", "Add a row first")]
        return [
            ActionRow(
                row.title or "Unlabelled row",
                lambda r=row.id: _do_move_to_row(context, row_id, tile_id, r),
            )
            for row in others
        ]

    context.push(Panel(title="Move to row", build=build))


def _do_move_to_row(
    context: SettingsContext, row_id: str, tile_id: str, target_row_id: str
) -> None:
    if editing.move_tile_to_row(context.config, row_id, tile_id, target_row_id):
        context.save_config()
        context.pop()  # the row picker
        context.pop()  # the tile panel, whose tile now lives elsewhere
        context.toast("Tile moved")


def _delete_tile(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    title = tile.title if tile else "this tile"

    def confirmed() -> None:
        editing.remove_tile(context.config, row_id, tile_id)
        context.save_config()
        context.pop()

    context.push(_confirm_panel(context, f"Delete {title}?", "Delete tile", confirmed))


def _confirm_panel(
    context: SettingsContext,
    question: str,
    confirm_label: str,
    on_confirm: Callable[[], None],
) -> Panel:
    """Deletion is the one thing here that can't be undone, so it always
    costs a second, deliberate press — and Cancel is what the cursor lands
    on, not the destructive option."""

    def _confirm() -> None:
        context.pop()  # dismiss the confirmation itself
        on_confirm()

    def build() -> list[SettingsRow]:
        return [
            InfoRow(question, ""),
            ActionRow("Cancel", context.pop),
            ActionRow(confirm_label, _confirm, danger=True),
        ]

    return Panel(title="Confirm", build=build)
