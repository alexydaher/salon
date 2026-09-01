# SPDX-License-Identifier: GPL-3.0-or-later
"""Semantic legend keys follow the controller used on every surface."""

from __future__ import annotations

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from salon.core import buttons  # noqa: E402
from salon.core.actions import Action  # noqa: E402
from salon.core.bindings import GAMEPAD  # noqa: E402
from salon.ui.controller_glyph import ControllerGlyph  # noqa: E402
from salon.ui.legend import Legend  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


def _legend(family: str) -> Legend:
    Gtk.init()
    legend = Legend(Scale(1080))
    legend.set_input_device(GAMEPAD, family)
    return legend


def test_playstation_actions_become_vector_prompts() -> None:
    key = _legend(buttons.PLAYSTATION)._present_key(Action.BACK)
    assert key == ControllerGlyph("playstation-circle", "Circle")


def test_xbox_actions_become_vector_prompts() -> None:
    key = _legend(buttons.XBOX)._present_key(Action.MENU)
    assert key == ControllerGlyph("xbox-menu", "Menu")


def test_literal_direction_groups_stay_readable() -> None:
    assert _legend(buttons.XBOX)._present_key("LEFT/RIGHT") == "LEFT/RIGHT"
