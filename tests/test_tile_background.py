# SPDX-License-Identifier: GPL-3.0-or-later
"""Appearance → Tile background, the two compositions and the fallback.

Both have a real case — identical glass loses five seeded streaming tiles
to one shared compass glyph, tinted glass costs the even row rhythm the
console was drawn with — so this is the user's choice and not a constant.
"""

from __future__ import annotations

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")

from salon.ui import theme  # noqa: E402
from salon.ui.settings.appearance_panel import _TILE_BACKGROUNDS  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_default() -> None:
    yield
    theme._tile_background = theme.TILE_BACKGROUND_ICON


def test_the_shipped_default_keeps_each_tile_its_own_colour() -> None:
    """The starter catalogue is five URL tiles all declaring the same icon
    name, so uniform glass would ship a row of identical rectangles."""
    assert theme.tiles_take_their_icon_colour()


def test_uniform_turns_the_tint_off() -> None:
    theme._tile_background = theme.TILE_BACKGROUND_UNIFORM
    assert not theme.tiles_take_their_icon_colour()


def test_every_offered_value_is_one_the_renderer_recognises() -> None:
    """The row and the drawing code are edited in different files. A choice
    naming something `theme` does not know silently means the default."""
    offered = {value for value, _label in _TILE_BACKGROUNDS}
    assert offered == {theme.TILE_BACKGROUND_ICON, theme.TILE_BACKGROUND_UNIFORM}


def test_the_choices_are_distinct_and_labelled() -> None:
    values = [value for value, _ in _TILE_BACKGROUNDS]
    labels = [label for _, label in _TILE_BACKGROUNDS]
    assert len(set(values)) == len(values)
    assert all(label.strip() for label in labels)


def test_the_key_and_its_schema_agree_on_the_default() -> None:
    """A schema default of "uniform" with a module default of "icon" would
    show one thing on a fresh install and another after the first reload."""
    import re
    from pathlib import Path

    schema = Path(__file__).resolve().parent.parent / "data"
    text = (schema / "io.github.alexydaher.Salon.gschema.xml").read_text()
    block = re.search(r'<key name="tile-background".*?</key>', text, re.S)
    assert block is not None
    assert f"<default>'{theme.TILE_BACKGROUND_ICON}'</default>" in block.group(0)
    for value, _label in _TILE_BACKGROUNDS:
        assert f'<choice value="{value}"/>' in block.group(0)
