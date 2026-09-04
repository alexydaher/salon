# SPDX-License-Identifier: GPL-3.0-or-later
"""Which surfaces sit above the console chrome. See DECISIONS 2026-09-04.

A `Gtk.Overlay` draws its children in the order they were added, so depth
is a side effect of which setup stage happens to build a widget. Three
surfaces were stranded under the chrome by that, and the idle screen was
one of them — it did not cover the screen it exists to cover.
"""

from __future__ import annotations

import ast
from pathlib import Path

from salon.ui import overlay_order

SETUP = Path(__file__).resolve().parent.parent / "salon" / "ui" / "home_setup_catalog.py"


def test_the_idle_screen_is_on_top_of_everything() -> None:
    """It is the only surface that has to cover *whatever* was left on
    screen, so it is raised last and nothing may be raised after it."""
    assert overlay_order.RAISED_ABOVE_CHROME[-1] == overlay_order.TOPMOST
    assert overlay_order.TOPMOST == "_screensaver"


def test_the_volume_readout_outranks_the_launch_overlay() -> None:
    """Volume acts on the system's audio rather than on a window — the
    action router keeps it above the "something else is in front" guards
    for the same reason, so its readout must be visible during a launch."""
    order = overlay_order.RAISED_ABOVE_CHROME
    assert order.index("_osd") > order.index("_launching_overlay")


def test_the_list_has_no_duplicates() -> None:
    """A name raised twice is a name whose position is decided by the
    second occurrence, which is not where anyone read it."""
    order = overlay_order.RAISED_ABOVE_CHROME
    assert len(set(order)) == len(order)


def test_every_raised_name_is_private_to_home_view() -> None:
    assert all(name.startswith("_") for name in overlay_order.RAISED_ABOVE_CHROME)


def test_the_chrome_is_raised_before_the_surfaces_that_outrank_it() -> None:
    assert not set(overlay_order.CONSOLE_CHROME) & set(overlay_order.RAISED_ABOVE_CHROME)


def test_the_setup_stage_re_raises_only_through_this_module() -> None:
    """The rule and its application have to be the same object.

    Written out at the call site instead, they drifted: the chrome loop was
    added and the surfaces built before it were simply forgotten, with no
    diagnostic anywhere — the symptom was a screensaver you could see the
    clock through.
    """
    tree = ast.parse(SETUP.read_text())
    raises = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_raise"
    ]
    named = {
        node.args[0].attr
        for node in raises
        if node.args and isinstance(node.args[0], ast.Attribute)
    }
    assert named == {"CONSOLE_CHROME", "RAISED_ABOVE_CHROME"}
