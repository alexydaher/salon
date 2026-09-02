# SPDX-License-Identifier: GPL-3.0-or-later
"""Wallpaper policy that does not need a window or renderer."""

import ast
from pathlib import Path

import pytest

from salon.ui import backdrop_wallpaper as wallpaper
from salon.ui.backdrop_renderer import BackdropRenderer, rgba


def test_background_choices_resolve_to_their_advertised_images() -> None:
    assert wallpaper.has_image("")
    assert wallpaper.resolve_source("") == wallpaper.DEFAULT_WALLPAPER
    assert not wallpaper.has_image("-")
    assert wallpaper.resolve_source("-") == ""
    assert wallpaper.has_image("/Pictures/holiday.jpg")


def test_plain_background_keeps_only_a_restrained_focus_glow() -> None:
    class Sample(BackdropRenderer):
        fields = 0
        _focus_x = 0.5
        _focus_y = 0.5

        def _current(self):  # type: ignore[no-untyped-def]
            return rgba(0.8, 0.4, 0.2)

        def _snapshot_ambient_field(self, *_args):  # type: ignore[no-untyped-def]
            self.fields += 1

    class Snapshot:
        def __init__(self) -> None:
            self.gradients = []
            self.colours = 0

        def append_radial_gradient(self, *_args):  # type: ignore[no-untyped-def]
            self.gradients.append(_args[-1])

        def append_color(self, *_args):  # type: ignore[no-untyped-def]
            self.colours += 1

    renderer = Sample()
    snapshot = Snapshot()
    renderer.snapshot_ambient(snapshot, 1920.0, 1080.0, plain=True)  # type: ignore[arg-type]

    assert renderer.fields == 0
    assert snapshot.colours == 0
    assert len(snapshot.gradients) == 1
    assert snapshot.gradients[0][0].color.alpha == pytest.approx(0.06)


def test_automatic_colours_the_bundled_background() -> None:
    assert wallpaper.resolve_treatment("", "automatic") == "focus"


def test_automatic_preserves_a_custom_pictures_colours() -> None:
    assert wallpaper.resolve_treatment("/Pictures/holiday.jpg", "automatic") == "original"
    assert wallpaper.resolve_treatment("/Pictures", "automatic") == "original"


def test_an_explicit_treatment_applies_to_every_background() -> None:
    for treatment in ("original", "focus", "accent"):
        assert wallpaper.resolve_treatment("", treatment) == treatment
        assert wallpaper.resolve_treatment("/Pictures/holiday.jpg", treatment) == treatment


def test_an_unknown_treatment_falls_back_safely() -> None:
    assert wallpaper.resolve_treatment("/Pictures/holiday.jpg", "sepia") == "original"


def test_the_reduced_resolution_cache_never_contains_the_wallpaper() -> None:
    """The cache is quarter-sized in both axes, so putting the photograph
    back into it would quietly restore the blur this feature removed."""
    path = Path(__file__).resolve().parent.parent / "salon" / "ui" / "backdrop.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    methods = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def calls(method: str) -> set[str]:
        return {
            node.func.attr
            for node in ast.walk(methods[method])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

    assert "snapshot_ambient" in calls("_refresh_texture")
    assert "snapshot_wallpaper" not in calls("_refresh_texture")
    assert {"snapshot_wallpaper", "snapshot_ambient"} <= calls("do_snapshot")


def test_plain_mode_is_part_of_the_ambient_texture_identity() -> None:
    """Switching from ambient to plain must invalidate the cached fields."""
    path = Path(__file__).resolve().parent.parent / "salon" / "ui" / "backdrop.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    methods = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    names = {
        node.attr
        for node in ast.walk(methods["_texture_key_now"])
        if isinstance(node, ast.Attribute)
    }
    assert "_plain_background" in names
