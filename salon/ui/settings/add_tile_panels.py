# SPDX-License-Identifier: GPL-3.0-or-later
"""Adding a tile: an installed app, a web address, or a command (§6.8).

The installed-app picker used to be an unfiltered A-to-nothing list of
every desktop entry on the machine — two hundred rows of D-pad, which is
the same gap the phone closed on 2026-08-26 with an index rail. Here the
answer is a filter: `core/ranking.rank_best` is already what search uses,
so typing three letters on the keyboard the picker can already open is
both less code and a better fit for a remote than a rail would be.
"""

from __future__ import annotations

from salon.core import ranking, tile_editing
from salon.core.model import LaunchKind, Tile
from salon.ui.settings.context import Panel, SettingsContext
from salon.ui.settings.tile_panel import tile_panel
from salon.ui.settings.widgets import (
    ActionRow,
    GroupRow,
    InfoRow,
    SettingsRow,
    opens_panel,
)

# How many apps to list before asking the user to narrow it down. Above
# this the list stops being something a D-pad can walk and the filter is
# the faster route by a wide margin.
_MAX_LISTED = 40


def add_tile_menu(context: SettingsContext, row_id: str) -> None:
    def build() -> list[SettingsRow]:
        return [
            opens_panel(
                "Installed app",
                lambda: context.push(_installed_panel(context, row_id)),
                detail="Pick from everything on this machine",
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

    context.push(Panel(title="Add a tile", build=build))


def _installed_panel(context: SettingsContext, row_id: str) -> Panel:
    """Populated asynchronously — the desktop-entry scan is far too slow to
    run on the frame clock (§10), so the panel opens saying so and fills in
    when the scan lands."""
    found: list[Tile] = []
    query: list[str] = [""]

    def on_scanned(apps: list[Tile]) -> None:
        if found:
            return
        found.extend(apps)
        context.rebuild()

    def search() -> None:
        def done(value: str | None) -> None:
            if value is None:
                return
            query[0] = value.strip()
            context.rebuild()

        context.edit_text("Find an application", query[0], done)

    def build() -> list[SettingsRow]:
        if not found:
            context.installed_apps(on_scanned)
            return [InfoRow("Looking for installed apps…", "")]
        matches = _matches(found, query[0])
        rows: list[SettingsRow] = [
            ActionRow(
                "Search" if not query[0] else f"Searching for “{query[0]}”",
                search,
                detail=(
                    f"{len(found)} applications installed"
                    if not query[0]
                    else "OK to change it, or clear it to see everything"
                ),
                value=query[0] or "",
            ),
            GroupRow(_heading(matches, found, query[0])),
        ]
        rows.extend(
            ActionRow(app.title, lambda a=app: _add_installed(context, row_id, a))
            for app in matches
        )
        if not matches:
            rows.append(InfoRow("Nothing matched", "", detail="Try fewer letters"))
        return rows

    return Panel(title="Installed app", build=build)


def _matches(apps: list[Tile], query: str) -> list[Tile]:
    """The apps to show: ranked when there is a query, alphabetical when not.

    Truncated rather than paginated. A settings list is walked with a
    direction key, and the honest answer to "there are two hundred of
    these" is to say so and offer the filter, not to make somebody hold
    DOWN through them.
    """
    if not query:
        return apps[:_MAX_LISTED]
    # `rank_best` speaks (id, title) pairs and answers with ids, which is
    # what the search screen and the phone both feed it. Same ranking, same
    # order, one implementation.
    by_id = {app.id: app for app in apps}
    ranked = ranking.rank_best(query, [(app.id, app.title) for app in apps], _MAX_LISTED)
    return [by_id[item_id] for item_id in ranked if item_id in by_id]


def _heading(matches: list[Tile], apps: list[Tile], query: str) -> str:
    if query:
        return f"{len(matches)} match{'es' if len(matches) != 1 else ''}"
    if len(apps) > _MAX_LISTED:
        return f"First {_MAX_LISTED} of {len(apps)} — search to narrow it down"
    return "Applications"


def _add_installed(context: SettingsContext, row_id: str, app: Tile) -> None:
    created = tile_editing.new_tile(
        context.config,
        row_id,
        title=app.title,
        kind=LaunchKind.DESKTOP,
        target=app.launch.target,
        icon_name=app.icon_name,
    )
    _finish(context, row_id, created, pops=2)


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
            created = tile_editing.new_tile(
                context.config,
                row_id,
                title=title.strip(),
                kind=LaunchKind.URL,
                target=target,
                icon_name="web-browser-symbolic",
            )
            _finish(context, row_id, created, pops=1)

        context.edit_text("Web address", "https://", got_url)

    context.edit_text("Tile name", "", got_title)


def _add_command(context: SettingsContext, row_id: str) -> None:
    def got_title(title: str | None) -> None:
        if title is None or not title.strip():
            return

        def got_command(command: str | None) -> None:
            if command is None or not command.strip():
                return
            created = tile_editing.new_tile(
                context.config,
                row_id,
                title=title.strip(),
                kind=LaunchKind.COMMAND,
                target=command.strip(),
                icon_name="application-x-executable-symbolic",
            )
            _finish(context, row_id, created, pops=1)

        context.edit_text("Command to run", "", got_command)

    context.edit_text("Tile name", "", got_title)


def _finish(context: SettingsContext, row_id: str, tile: Tile, *, pops: int) -> None:
    """Add the tile, then open its editor.

    Opening it is the change: a new tile arrived with a generated card and
    no offer to give it artwork, so the one moment when somebody is
    thinking about that tile ended by returning them to a list. The editor
    leads with the preview, so what they land on is the tile they just made.
    """
    tile_editing.add_tile(context.config, row_id, tile)
    context.save_config()
    for _ in range(pops):
        context.pop()
    context.toast(f"Added {tile.title}")
    context.push(tile_panel(context, row_id, tile.id))
