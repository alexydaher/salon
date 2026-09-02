# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression checks for dependencies extracted from the former monolithic UI."""

import ast
from pathlib import Path

import pytest


def test_home_rows_has_its_spring_dependency() -> None:
    path = Path(__file__).resolve().parent.parent / "salon/ui/home_rows.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "salon.ui.home_spring"
        and any(alias.name == "_AxisSpring" for alias in node.names)
        for node in tree.body
    )


def test_only_scale_computes_the_default_safe_area() -> None:
    ui = Path(__file__).resolve().parent.parent / "salon/ui"
    offenders = [
        path.relative_to(ui).as_posix()
        for path in ui.rglob("*.py")
        if path.name != "scale.py" and "SAFE_AREA_DEFAULT_PERCENT" in path.read_text()
    ]
    assert offenders == []


def test_console_sidebar_natural_width_cannot_follow_long_media_text() -> None:
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    from salon.core import tokens
    from salon.ui.console_sidebar import ConsoleSidebar
    from salon.ui.scale import Scale

    if not Gtk.init_check():
        pytest.skip("no display; GTK widgets cannot be measured")
    status = Gtk.Label(label="System")
    playing = Gtk.Label(label="A media title that is much wider than the console rail " * 8)
    sidebar = ConsoleSidebar(Scale(1080), status, playing)

    minimum, natural, _minimum_baseline, _natural_baseline = sidebar.measure(
        Gtk.Orientation.HORIZONTAL, -1
    )

    assert minimum == natural == round(tokens.CONSOLE_WIDTH_DU)


def test_phone_pairing_hint_maximises_qr_inside_a_fixed_rail_card() -> None:
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    from salon.core import tokens
    from salon.ui.remote_hint_host import RemoteHintHost
    from salon.ui.remotehint import RemoteHint
    from salon.ui.scale import Scale

    if not Gtk.init_check():
        pytest.skip("no display; GTK widgets cannot be measured")

    class Pairing:
        locked = False
        pair_url = "http://192.168.1.151:8437/?code=1234"
        url = "http://192.168.1.151:8437"
        code = "1234"

    scale = Scale(1080)
    card = RemoteHint(scale, Pairing(), lambda: None)  # type: ignore[arg-type]
    host = RemoteHintHost(card, scale)
    assert host.refresh()
    host.set_visible(True)

    minimum, natural, _minimum_baseline, _natural_baseline = host.measure(
        Gtk.Orientation.HORIZONTAL, -1
    )
    # GTK includes the 30du leading margin in a widget's measured footprint;
    # the card itself is 276du and therefore ends at the 306du mark.
    assert minimum == natural == round(tokens.CONSOLE_WIDTH_DU - 30.0)
    assert card._qr._size == 246  # noqa: SLF001
    assert host._height == 364  # noqa: SLF001
    assert host.get_margin_bottom() == 22
    assert card._title.get_label() == "Phone remote"  # noqa: SLF001
    assert card._instruction.get_label() == ""  # noqa: SLF001


def test_top_bar_horizontal_edges_do_not_animate_an_app_row() -> None:
    path = Path(__file__).resolve().parent.parent / "salon/ui/home_navigation.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_handle_nav_action"
    )
    horizontal_branch = next(
        node
        for node in handler.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and any(
            isinstance(comparator, ast.Tuple)
            and {
                element.attr
                for element in comparator.elts
                if isinstance(element, ast.Attribute)
            }
            == {"LEFT", "RIGHT"}
            for comparator in node.test.comparators
        )
    )
    calls = [
        node.func.attr
        for node in ast.walk(horizontal_branch)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "move" in calls
    assert "_rubber_band" not in calls


def test_vertical_home_move_explicitly_suppresses_horizontal_reveal() -> None:
    path = Path(__file__).resolve().parent.parent / "salon/ui/home_landing.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_move_focus"
    )
    update = next(
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_update_focus"
    )
    reveal = next(
        keyword.value for keyword in update.keywords if keyword.arg == "reveal_horizontal"
    )

    assert isinstance(reveal, ast.UnaryOp)
    assert isinstance(reveal.op, ast.Not)
