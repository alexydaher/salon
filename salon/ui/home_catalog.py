# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.core import starter
from salon.services.component import ServiceComponent
from salon.ui.home_shared import (
    Adw,
    Callable,
    Catalog,
    CatalogBuild,
    ConfigError,
    Gio,
    Gtk,
    sanitize,
    tile_config,
)


class HomeCatalogController(ServiceComponent):
    def _toast(self, message: str) -> None:
        self._owner._toast_overlay.add_toast(Adw.Toast(title=message))

    def _load_config(self) -> tile_config.Config:
        if not self._owner._config_path.exists():
            config = starter.pending_starter_config()
            self._owner._starter_expected = starter.fingerprint(config)
            return config
        try:
            config = tile_config.load(self._owner._config_path)
        except ConfigError as exc:
            self._toast(f"Your tiles file couldn't be read, so none are shown. {exc}")
            self._owner._starter_expected = None
            return tile_config.Config()
        self._owner._starter_expected = (
            starter.fingerprint(config) if starter.is_legacy_seed(config) else None
        )
        return config

    def _finish_starter_discovery(self, discovery: starter.StarterDiscovery) -> None:
        """Persist an async starter only while its original state is untouched."""
        expected = self._owner._starter_expected
        self._owner._starter_expected = None
        if expected is None:
            return
        disk_config = None
        if self._owner._config_path.exists():
            try:
                disk_config = tile_config.load(self._owner._config_path)
            except ConfigError:
                return
        if not starter.can_finalize(self._owner._config, disk_config, expected):
            return
        self._owner._config = starter.build_starter_config(discovery)
        self._owner._settings_screen.set_config(self._owner._config)
        self._save_config()
        self._owner._refresh_catalog(preserve_focus=True)

    def _save_config(self) -> None:
        """The tile editor's only write path.

        It writes the same file a hand edit writes and lets the existing
        directory monitor reload it, so there is exactly one way the
        catalogue ever comes back in — no second, editor-only reload path
        that could drift from the one everybody else uses.
        """
        try:
            tile_config.save(self._owner._config, self._owner._config_path)
        except OSError as exc:
            self._toast(f"That change couldn't be saved. {exc}")

    def _edit_text(self, title: str, initial: str, on_done: Callable[[str | None], None]) -> None:
        self._owner._text_entry.open(title=title, initial=initial, on_done=on_done)

    def _choose_path(self, title: str, folder: bool, on_done: Callable[[str | None], None]) -> None:
        """Pointer-friendly file/folder chooser; remote users keep the text path editor."""
        dialog = Gtk.FileDialog()
        dialog.set_title(title)
        root = self._owner.get_root()
        parent = root if isinstance(root, Gtk.Window) else None

        def chosen(source: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                selected = (
                    source.select_folder_finish(result) if folder else source.open_finish(result)
                )
            except Exception:
                on_done(None)
                return
            on_done(selected.get_path())

        if folder:
            dialog.select_folder(parent, None, chosen)
        else:
            dialog.open(parent, None, chosen)

    def _show_system_menu(self) -> None:
        self._owner._rebuild_system_menu()
        self._owner._system_menu.show()

    def _open_settings(self, panel_id: str = "") -> None:
        self._clear_for_settings()
        if panel_id:
            self._owner._settings_screen.open_at(panel_id)
        else:
            self._owner._settings_screen.open()

    def _clear_for_settings(self) -> None:
        self._owner._system_menu.hide()
        if self._owner._search.get_visible():
            self._owner._search.close()
        if self._owner._apps_grid.get_visible():
            self._owner._apps_grid.close()
        # A mouse can click the top bar's buttons without the D-pad ever
        # having gone up there, and a click that leaves the bar highlighted
        # behind a full-screen overlay is a cursor in two places at once.
        self._owner._set_nav_focused(False)

    def _settings_screen_open_tile(self, row_id: str, tile_id: str) -> None:
        self._clear_for_settings()
        self._owner._settings_screen.open_tile(row_id, tile_id)

    def _locate_in_config(self, tile_id: str) -> tuple[str, str] | None:
        """Where a tile lives in tiles.json, if it lives there at all.

        A tile on screen is not necessarily an entry in the catalogue file:
        Recents, Favourites and the apps grid all produce tiles that no row
        in tiles.json contains, and offering to edit one of those would open
        an editor for a row that does not exist.
        """
        for row in self._owner._config.rows:
            for tile in row.tiles:
                if tile.id == tile_id:
                    return row.id, tile.id
        return None

    def _refresh_catalog(self, *, preserve_focus: bool) -> None:
        """Ask the providers for a fresh catalogue (§6.10).

        Asynchronous, because `collect()` waits up to three seconds and one
        misbehaving provider must not freeze the interface every time a tile
        is launched. The tile to land on is captured *now*, before the
        rebuild, since by the time the answer arrives the focus model may
        have been reset by something else.
        """
        focused_tile = (
            self._owner._catalog.tile_at(self._owner._focus.row, self._owner._focus.col)
            if preserve_focus
            else None
        )
        target_id = focused_tile.id if focused_tile is not None else None
        if target_id is None and not self._owner._catalog.rows:
            # Nothing focused yet — this is the first build, so honour the
            # tile the last session left off on.
            target_id = self._owner._settings.get_string("last-focused-tile") or None

        self._owner._catalog_generation += 1
        generation = self._owner._catalog_generation
        self._owner._provider_registry.build_async(
            self._owner._config,
            lambda build: self._on_catalog_built(build, generation, target_id),
        )

    def _on_catalog_built(
        self, build: CatalogBuild, generation: int, target_id: str | None
    ) -> None:
        # Edits can outrun a slow provider; an older build landing after a
        # newer one would silently undo it.
        if generation != self._owner._catalog_generation:
            return

        self._owner._provider_outcomes = build.outcomes
        # The registry isolated the providers from each other; what's left is
        # a clash *within* one provider's rows, which Catalog rejects.
        # Falling back to an empty catalogue there would blank the screen
        # over one duplicated tile id, so the ambiguous rows are dropped and
        # everything else is kept.
        rows, problems = sanitize(build.rows)
        for message in problems:
            self._toast(message)
        for failure in build.failures:
            self._toast(f"The {failure.provider_id} provider: {failure.reason}")

        # A row with no tiles is a heading with a void under it: there is
        # nothing to focus, nothing to launch, and (before this) landing on
        # one swallowed the focus entirely. They still exist in the config
        # and in the tile editor, which is where an empty row you just
        # created is supposed to be visible — the home screen just doesn't
        # draw them.
        rows = [row for row in rows if row.tiles]

        self._owner._catalog = Catalog(rows)
        self._owner._focus.set_row_lengths(self._owner._catalog.row_lengths())
        if target_id is not None:
            pos = self._owner._catalog.find(target_id)
            if pos is not None:
                self._owner._focus.jump_to(*pos)
        self._owner._rebuild_row_widgets()
