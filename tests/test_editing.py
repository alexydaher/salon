# SPDX-License-Identifier: GPL-3.0-or-later
"""Catalogue mutation (§6.8's tile editor).

The acceptance criterion for M8 is that a tile can be created, given
artwork, reordered and deleted without touching a text editor. These tests
cover the part of that which isn't a widget: that the resulting catalogue
is still one `core/catalog.py` will load.
"""

from __future__ import annotations

import pytest

from salon.core import editing
from salon.core.catalog import Catalog
from salon.core.config import Config
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile


def tile(tile_id: str, title: str = "T") -> Tile:
    return Tile(
        id=tile_id,
        title=title,
        subtitle=None,
        launch=LaunchSpec(kind=LaunchKind.COMMAND, target="/bin/true"),
        artwork=None,
        icon_name=None,
        accent=None,
    )


def config_with(*row_specs: tuple[str, list[str]]) -> Config:
    return Config(
        rows=[
            Row(id=row_id, title=row_id, tiles=[tile(t) for t in tiles], provider_id="static")
            for row_id, tiles in row_specs
        ]
    )


# --- ids -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("GeForce NOW", "geforce-now"),
        ("  Spaces  ", "spaces"),
        ("Prime Video!", "prime-video"),
        ("!!!", "item"),
        ("日本語", "item"),
    ],
)
def test_slugify(text: str, expected: str) -> None:
    assert editing.slugify(text) == expected


def test_uniquify_numbers_collisions() -> None:
    assert editing.uniquify("netflix", set()) == "netflix"
    assert editing.uniquify("netflix", {"netflix"}) == "netflix-2"
    assert editing.uniquify("netflix", {"netflix", "netflix-2"}) == "netflix-3"


# --- rows ----------------------------------------------------------------


def test_add_row_gets_a_unique_id() -> None:
    config = config_with(("apps", []))
    first = editing.add_row(config, "Apps")
    assert first.id == "apps-2"
    assert len(config.rows) == 2


def test_move_row_refuses_to_run_off_the_end() -> None:
    config = config_with(("a", []), ("b", []))
    assert editing.move_row(config, "a", -1) is False
    assert editing.move_row(config, "b", 1) is False
    assert editing.move_row(config, "a", 1) is True
    assert [r.id for r in config.rows] == ["b", "a"]


def test_remove_row() -> None:
    config = config_with(("a", []), ("b", []))
    assert editing.remove_row(config, "a") is True
    assert editing.remove_row(config, "a") is False
    assert [r.id for r in config.rows] == ["b"]


def test_rename_row_keeps_the_id() -> None:
    """The id is what recents and focus restoration are keyed on, so
    renaming a row must not quietly relocate the user."""
    config = config_with(("apps", []))
    editing.rename_row(config, "apps", "Applications")
    assert config.rows[0].id == "apps"
    assert config.rows[0].title == "Applications"


def test_empty_row_title_becomes_none_not_empty_string() -> None:
    config = config_with(("apps", []))
    editing.rename_row(config, "apps", "")
    assert config.rows[0].title is None  # renders as an unlabelled row (§5)


def test_set_row_aspect_rejects_unknown_values() -> None:
    config = config_with(("apps", []))
    assert editing.set_row_aspect(config, "apps", "poster") is True
    assert editing.set_row_aspect(config, "apps", "circular") is False
    assert config.rows[0].tile_aspect == "poster"


# --- tiles ---------------------------------------------------------------


def test_add_tile_renames_on_collision_within_the_row() -> None:
    config = config_with(("apps", ["netflix"]))
    stored = editing.add_tile(config, "apps", tile("netflix"))
    assert stored is not None
    assert stored.id == "netflix-2"
    Catalog(config.rows)  # must still load


def test_the_same_tile_id_may_live_in_two_rows() -> None:
    """Catalog only requires uniqueness within a row — recents relies on
    that — so adding to a different row must not rename."""
    config = config_with(("apps", ["netflix"]), ("fav", []))
    stored = editing.add_tile(config, "fav", tile("netflix"))
    assert stored is not None
    assert stored.id == "netflix"
    Catalog(config.rows)


def test_move_tile_within_a_row() -> None:
    config = config_with(("apps", ["a", "b", "c"]))
    assert editing.move_tile(config, "apps", "c", -1) is True
    assert [t.id for t in config.rows[0].tiles] == ["a", "c", "b"]
    assert editing.move_tile(config, "apps", "a", -1) is False


def test_remove_tile() -> None:
    config = config_with(("apps", ["a", "b"]))
    assert editing.remove_tile(config, "apps", "a") is True
    assert editing.remove_tile(config, "apps", "a") is False
    assert [t.id for t in config.rows[0].tiles] == ["b"]


def test_move_tile_to_another_row_renames_on_collision() -> None:
    config = config_with(("apps", ["netflix"]), ("fav", ["netflix"]))
    assert editing.move_tile_to_row(config, "apps", "netflix", "fav") is True
    assert [t.id for t in config.rows[0].tiles] == []
    assert [t.id for t in config.rows[1].tiles] == ["netflix", "netflix-2"]
    Catalog(config.rows)


def test_move_tile_to_the_same_row_is_refused() -> None:
    config = config_with(("apps", ["a"]))
    assert editing.move_tile_to_row(config, "apps", "a", "apps") is False


def test_operations_on_missing_rows_and_tiles_report_failure() -> None:
    config = config_with(("apps", ["a"]))
    assert editing.remove_row(config, "nope") is False
    assert editing.move_row(config, "nope", 1) is False
    assert editing.rename_row(config, "nope", "x") is False
    assert editing.add_tile(config, "nope", tile("t")) is None
    assert editing.remove_tile(config, "nope", "a") is False
    assert editing.move_tile(config, "apps", "nope", 1) is False


# --- tile construction ---------------------------------------------------


def test_new_tile_gives_url_tiles_their_own_browser_profile() -> None:
    """§6.3: one --user-data-dir per service, so one sign-in can't disturb
    another's."""
    config = config_with(("web", []))
    created = editing.new_tile(
        config, "web", title="Prime Video", kind=LaunchKind.URL, target="https://primevideo.com"
    )
    assert created.id == "prime-video"
    assert created.launch.browser_profile == "prime-video"


def test_new_tile_avoids_colliding_with_the_row_it_targets() -> None:
    config = config_with(("web", ["prime-video"]))
    created = editing.new_tile(
        config, "web", title="Prime Video", kind=LaunchKind.URL, target="https://primevideo.com"
    )
    assert created.id == "prime-video-2"


def test_non_url_tiles_get_no_browser_profile() -> None:
    config = config_with(("apps", []))
    created = editing.new_tile(
        config, "apps", title="Files", kind=LaunchKind.DESKTOP, target="org.gnome.Nautilus"
    )
    assert created.launch.browser_profile is None


def test_set_launch_target_preserves_every_other_field() -> None:
    spec = LaunchSpec(
        kind=LaunchKind.URL,
        target="https://old",
        args=("--x",),
        browser_profile="p",
        user_agent="UA",
        spatial_nav=False,
        fullscreen=False,
    )
    subject = tile("t")
    subject.launch = spec
    editing.set_launch_target(subject, "https://new")
    assert subject.launch.target == "https://new"
    assert subject.launch.args == ("--x",)
    assert subject.launch.browser_profile == "p"
    assert subject.launch.user_agent == "UA"
    assert subject.launch.spatial_nav is False
    assert subject.launch.fullscreen is False


def test_changing_kind_away_from_url_drops_the_browser_profile() -> None:
    """A browser profile on a non-URL tile is meaningless state that would
    silently come back if the kind were switched to URL again."""
    config = config_with(("web", []))
    created = editing.new_tile(
        config, "web", title="Site", kind=LaunchKind.URL, target="https://x"
    )
    editing.set_launch_kind(created, LaunchKind.COMMAND)
    assert created.launch.browser_profile is None


def test_set_spatial_nav_toggles_only_that_field() -> None:
    config = config_with(("web", []))
    created = editing.new_tile(
        config, "web", title="Site", kind=LaunchKind.URL, target="https://x"
    )
    editing.set_spatial_nav(created, False)
    assert created.launch.spatial_nav is False
    assert created.launch.target == "https://x"


def test_set_fullscreen_leaves_everything_else_alone() -> None:
    config = Config(rows=[Row(id="r", title="R", provider_id="static", tiles=[])])
    tile = editing.new_tile(
        config,
        "r",
        title="Netflix",
        kind=LaunchKind.URL,
        target="https://netflix.com",
    )
    editing.add_tile(config, "r", tile)
    assert tile.launch.fullscreen is True

    editing.set_fullscreen(tile, False)
    assert tile.launch.fullscreen is False
    assert tile.launch.spatial_nav is True
    assert tile.launch.target == "https://netflix.com"
    assert tile.launch.browser_profile is not None
