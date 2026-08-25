# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_rows import *
from salon.ui.home_shared import *
from salon.ui.home_spring import *
from salon.ui.home_viewport import *


class HomeOverlayController(ServiceComponent):
    def _open_search(self) -> None:
        self._set_nav_focused(False)
        self._search.open(self._searchable_tiles())

    def _searchable_tiles(self) -> list[Tile]:
        """Every catalogue tile, once.

        Deduplicated by id: a tile that is also in Recents legitimately
        appears in the catalogue twice, and listing it twice in the results
        reads as a bug. Shared with the phone's `/search`, which searches
        the same catalogue and would otherwise have its own copy of this to
        get subtly different.
        """
        seen: set[str] = set()
        tiles: list[Tile] = []
        for row in self._catalog.rows:
            for tile in row.tiles:
                if tile.id not in seen:
                    seen.add(tile.id)
                    tiles.append(tile)
        return tiles

    def _open_apps(self) -> None:
        """The all-apps grid, from the top bar's grid button."""
        self._system_menu.hide()
        if self._search.get_visible():
            self._search.close()
        self._set_nav_focused(False)
        self._apps_grid.open()

    def _open_tile_menu(self, tile: Tile | None, *, from_grid: bool) -> None:
        """OPTIONS over a tile: what else can be done with this one thing.

        Deliberately not MENU. MENU has to keep meaning "system menu" at
        every depth — it is the escape hatch — so per-item actions need
        their own button, and every input source grew one (X on a pad, F10
        or `o` on a keyboard, contents-menu on a CEC remote).
        """
        if tile is None:
            return
        pinned = favourites.is_favourite(self._settings, tile.id)
        items: list[SystemMenuItem] = []
        if from_grid:
            items.append(SystemMenuItem(f"Open {tile.title}", lambda: self._launch_tile(tile)))
        items.append(
            SystemMenuItem(
                "Remove from Favourites" if pinned else "Add to Favourites",
                lambda: self._toggle_favourite(tile),
            )
        )
        if from_grid and self._config.rows:
            items.append(SystemMenuItem("Add to Home", lambda: self._add_tile_to_home(tile)))
        if not from_grid:
            # Straight to *this* tile's editor. Landing on the section list
            # instead — which is what this did — means four more navigations
            # to reach the thing the user already had the cursor on.
            located = self._locate_in_config(tile.id)
            if located is not None:
                row_id, tile_id = located
                items.append(
                    SystemMenuItem(
                        f"Edit {tile.title}…",
                        lambda: self._settings_screen_open_tile(row_id, tile_id),
                    )
                )
            items.append(SystemMenuItem("Edit tiles…", lambda: self._open_settings("tiles")))
        items.append(SystemMenuItem("Cancel", lambda: None))
        self._tile_menu.set_items(items, title=tile.title)
        self._tile_menu.show()

    def _toggle_favourite(self, tile: Tile) -> None:
        pinned = favourites.toggle_favourite(self._settings, tile.id)
        self._toast(
            f"{tile.title} pinned to Favourites"
            if pinned
            else f"{tile.title} removed from Favourites"
        )
        self._refresh_catalog(preserve_focus=True)

    def _add_tile_to_home(self, tile: Tile) -> None:
        """Copy an installed app out of the grid and into the catalogue.

        It goes into the first row, which is the one nearest the top of the
        screen and the only choice that doesn't need a second picker in
        front of a user holding a remote. Moving it afterwards is what the
        tile editor is for.
        """
        if any(t.id == tile.id for row in self._config.rows for t in row.tiles):
            self._toast(f"{tile.title} is already on the home screen.")
            return
        row = self._config.rows[0]
        # A copy, because add_tile renames the id it is handed to keep it
        # unique within the row — and the object the grid passed in is the
        # one its own widget is still rendering.
        if editing.add_tile(self._config, row.id, replace(tile)) is None:
            self._toast(f"{tile.title} couldn't be added.")
            return
        self._save_config()
        self._toast(f"{tile.title} added to {row.title or 'the first row'}.")
