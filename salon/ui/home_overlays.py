# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_shared import (
    Callable,
    MenuFrame,
    SystemMenuItem,
    Tile,
    editing,
    favourites,
    replace,
)


class HomeOverlayController(ServiceComponent):
    def _clear_global_surfaces(self, keep: str) -> None:
        self._owner._system_menu.hide()
        self._owner._tile_menu.hide()
        if keep != "search" and self._owner._search.get_visible():
            self._owner._search.close()
        if keep != "apps" and self._owner._apps_grid.get_visible():
            self._owner._apps_grid.close()
        if keep != "settings" and self._owner._settings_screen.get_visible():
            self._owner._settings_screen.close()
        if keep != "phone" and self._owner._phone_pairing.get_visible():
            self._owner._phone_pairing.close()

    def _confirmation_frame(self, label: str, action: Callable[[], None]) -> MenuFrame:
        return MenuFrame(
            f"confirm-{label.casefold().replace(' ', '-')}",
            f"{label}?",
            [
                SystemMenuItem(
                    "Cancel",
                    self._owner._system_menu.back,
                    icon_name="process-stop-symbolic",
                    detail="Return without making a change",
                    closes=False,
                ),
                SystemMenuItem(
                    label,
                    action,
                    danger=True,
                    icon_name="dialog-warning-symbolic",
                    detail=f"Confirm {label.casefold()}",
                ),
            ],
        )

    def _confirm_system_action(self, label: str, action: Callable[[], None]) -> None:
        """Require a second deliberate OK, with Cancel selected first.

        The one place Cancel is still a row: everywhere else BACK is enough,
        but a card whose other option powers the machine off should not have
        its safe answer be a button nobody told you about.
        """
        if not self._owner._system_menu.get_visible():
            self._owner._show_power_menu()
        self._owner._system_menu.push_frame(self._confirmation_frame(label, action))

    def _open_search(self) -> None:
        self._owner._clear_global_surfaces("search")
        self._owner._set_nav_focused(False)
        self._owner._search.open(self._searchable_tiles())
        self._sync_shell_chrome()

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
        for row in self._owner._catalog.rows:
            for tile in row.tiles:
                if tile.id not in seen:
                    seen.add(tile.id)
                    tiles.append(tile)
        return tiles

    def _open_apps(self) -> None:
        """The all-apps grid, from the top bar's grid button."""
        self._owner._clear_global_surfaces("apps")
        self._owner._set_nav_focused(False)
        self._owner._apps_grid.open()
        self._sync_shell_chrome()

    def _open_tile_menu(self, tile: Tile | None, *, from_grid: bool) -> None:
        """OPTIONS over a tile: what else can be done with this one thing.

        Deliberately not MENU. MENU has to keep meaning "system menu" at
        every depth — it is the escape hatch — so per-item actions need
        their own button, and every input source grew one (X on a pad, F10
        or `o` on a keyboard, contents-menu on a CEC remote).
        """
        if tile is None:
            return
        pinned = favourites.is_favourite(self._owner._settings, tile.id)
        items: list[SystemMenuItem] = [
            SystemMenuItem(
                "Remove from Favourites" if pinned else "Add to Favourites",
                lambda: self._toggle_favourite(tile),
                icon_name=("starred-symbolic" if pinned else "non-starred-symbolic"),
                detail=(
                    "Remove the shortcut from Favourites"
                    if pinned
                    else "Add a shortcut to Favourites"
                ),
            )
        ]
        located = self._owner._locate_in_config(tile.id)
        if located is None and self._owner._config.rows:
            items.append(
                SystemMenuItem(
                    "Add to a row…",
                    icon_name="list-add-symbolic",
                    detail=f"Choose from {len(self._owner._config.rows)} Home rows",
                    submenu=lambda: self._add_to_row_frame(tile),
                )
            )
        if from_grid:
            items.append(
                SystemMenuItem(
                    f"Open {tile.title}",
                    lambda: self._owner._launch_tile(tile),
                    icon_name="media-playback-start-symbolic",
                    detail="Launch this application",
                )
            )
        if located is not None:
            row_id, tile_id = located
            items.append(
                SystemMenuItem(
                    f"Edit {tile.title}…",
                    lambda: self._owner._settings_screen_open_tile(row_id, tile_id),
                    icon_name="document-edit-symbolic",
                    detail="Open this tile in Settings",
                )
            )
            items.append(
                SystemMenuItem(
                    "Remove from Home…",
                    danger=True,
                    icon_name="user-trash-symbolic",
                    detail="Remove this tile from its editable Home row",
                    submenu=lambda: self._remove_from_home_frame(tile, row_id, tile_id),
                )
            )
        if not from_grid:
            items.append(
                SystemMenuItem(
                    "Edit Tiles…",
                    lambda: self._owner._open_settings("tiles"),
                    icon_name="view-list-symbolic",
                    detail="Open the complete Home layout editor",
                )
            )
        # No Cancel row. BACK closes it, OPTIONS closes it, a click on the
        # scrim closes it, and the legend at the bottom of the screen names
        # the button — a row that does nothing is one more thing for an
        # accelerating repeat to land on.
        self._owner._tile_menu.set_items(
            items, title=tile.title, frame_id=f"tile-{tile.id}"
        )
        self._owner._tile_menu.show()

    def _remove_from_home_frame(
        self, tile: Tile, row_id: str, tile_id: str
    ) -> MenuFrame:
        return MenuFrame(
            "confirm-remove-home",
            "Remove from Home?",
            [
                SystemMenuItem(
                    "Cancel",
                    self._owner._tile_menu.back,
                    icon_name="process-stop-symbolic",
                    detail="Keep this tile on Home",
                    closes=False,
                ),
                SystemMenuItem(
                    "Remove from Home",
                    lambda: self._remove_tile_from_home(tile, row_id, tile_id),
                    danger=True,
                    icon_name="user-trash-symbolic",
                    detail=f"Remove {tile.title} from Home",
                ),
            ],
        )

    def _remove_tile_from_home(self, tile: Tile, row_id: str, tile_id: str) -> None:
        fallback = self._owner._focus.position
        if not editing.remove_tile(self._owner._config, row_id, tile_id):
            self._owner._toast(f"{tile.title} couldn't be removed from Home.")
            return
        self._owner._save_config()
        self._owner._toast(f"{tile.title} removed from Home.")
        # Do not preserve by id: Recents/Favourites may still expose the
        # same id and would pull focus into a provider-owned row. The old
        # coordinate clamps to the next tile, then the previous at an end.
        self._owner._refresh_catalog(
            preserve_focus=False, fallback_position=fallback
        )

    def _toggle_favourite(self, tile: Tile) -> None:
        pinned = favourites.toggle_favourite(self._owner._settings, tile.id)
        self._owner._toast(
            f"{tile.title} pinned to Favourites"
            if pinned
            else f"{tile.title} removed from Favourites"
        )
        self._owner._refresh_catalog(preserve_focus=True)

    def _add_to_row_frame(self, tile: Tile) -> MenuFrame:
        return MenuFrame(
            f"add-{tile.id}",
            "Add to a row",
            [
                SystemMenuItem(
                    row.title or "Untitled row",
                    lambda r=row: self._add_tile_to_row(tile, r.id, r.title),
                    icon_name="list-add-symbolic",
                    detail=f"Copy {tile.title} into this Home row",
                )
                for row in self._owner._config.rows
            ],
        )

    def _add_tile_to_row(self, tile: Tile, row_id: str, row_title: str) -> None:
        if any(t.id == tile.id for row in self._owner._config.rows for t in row.tiles):
            self._owner._toast(f"{tile.title} is already on the home screen.")
            return
        if editing.add_tile(self._owner._config, row_id, replace(tile)) is None:
            self._owner._toast(f"{tile.title} couldn't be added.")
            return
        self._owner._save_config()
        self._owner._toast(f"{tile.title} added to {row_title or 'the selected row'}.")
