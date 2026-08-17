from __future__ import annotations

from salon.core.model import LaunchKind, LaunchSpec, Row, Tile


def test_launch_spec_defaults() -> None:
    spec = LaunchSpec(kind=LaunchKind.COMMAND, target="mpv")
    assert spec.args == ()
    assert dict(spec.env) == {}
    assert spec.spatial_nav is True
    assert spec.fullscreen is True
    assert spec.browser_profile is None


def test_tile_and_row_construction() -> None:
    tile = Tile(
        id="mpv",
        title="MPV",
        subtitle=None,
        launch=LaunchSpec(kind=LaunchKind.COMMAND, target="mpv"),
        artwork=None,
        icon_name="mpv",
        accent=None,
    )
    row = Row(id="apps", title="Apps", tiles=[tile], provider_id="static")
    assert row.tiles[0] is tile
    assert row.tile_aspect == "wide"
