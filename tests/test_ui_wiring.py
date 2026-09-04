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


def _rail() -> tuple[object, object, object]:
    """A real rail, because the card in it is what the width has to survive."""
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    from salon.ui.console_sidebar import ConsoleSidebar
    from salon.ui.nowplaying_status import NowPlayingStatus
    from salon.ui.scale import Scale
    from salon.ui.status_info import StatusInfo

    if not Gtk.init_check():
        pytest.skip("no display; GTK widgets cannot be measured")
    scale = Scale(1080)
    status = StatusInfo(scale)
    playing = NowPlayingStatus(scale, on_activate=lambda _source: None)
    return ConsoleSidebar(scale, status, playing), status, playing


def test_console_sidebar_natural_width_cannot_follow_long_media_text() -> None:
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    from salon.core import nowplaying, tokens

    sidebar, _status, playing = _rail()
    playing.set_players(  # type: ignore[attr-defined]
        (
            nowplaying.Player(
                "org.mpris.MediaPlayer2.test",
                "A player whose identity is also far too long for the rail",
                nowplaying.PLAYING,
                title="A media title that is much wider than the console rail " * 8,
                artist="An artist credit of comparable length " * 4,
            ),
        )
    )

    minimum, natural, _minimum_baseline, _natural_baseline = sidebar.measure(
        Gtk.Orientation.HORIZONTAL, -1
    )

    assert minimum == natural == round(tokens.CONSOLE_WIDTH_DU)


def test_the_now_playing_card_fits_the_rail_with_the_pairing_card_under_it() -> None:
    """The card's design must not depend on whether a phone is paired.

    It used to: the rail handed the card a height budget and the card
    answered by rebuilding itself into one of two arrangements, so the same
    television drew a tall card with a big cover, or a short one with a
    small cover beside the text, according to whether the QR was standing
    at the bottom of the same column. The card is one fixed design now and
    the number of media sources no longer changes its height — this is the
    measurement that says so, and the one that would fail if some later
    addition to either card made them stop fitting.
    """
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    from salon.core import nowplaying, tokens
    from salon.ui.remote_hint_host import RemoteHintHost
    from salon.ui.remotehint import RemoteHint
    from salon.ui.scale import Scale

    def player(index: int) -> object:
        return nowplaying.Player(
            f"org.mpris.MediaPlayer2.p{index}",
            f"Player {index}",
            nowplaying.PLAYING,
            title="Bright Horses and the Fields of Amber Grass",
            artist="Nick Cave & The Bad Seeds",
            position_us=61_000_000,
            length_us=250_000_000,
            can_go_next=True,
            can_go_previous=True,
        )

    sidebar, _status, playing = _rail()
    scale = Scale(1080)
    width = scale.px(tokens.CONSOLE_WIDTH_DU)

    playing.set_players((player(0),))  # type: ignore[attr-defined]
    one = sidebar.measure(Gtk.Orientation.VERTICAL, width)[1]
    playing.set_players(tuple(player(index) for index in range(4)))  # type: ignore[attr-defined]
    four = sidebar.measure(Gtk.Orientation.VERTICAL, width)[1]

    # One source drawn at a time, so a fourth player registering costs the
    # rail nothing at all: only the picker's own line, and only once.
    assert four - one <= scale.px(40.0)

    class Pairing:
        locked = False
        pair_url = "http://192.168.1.151:8437/?code=1234"
        url = "http://192.168.1.151:8437"
        code = "1234"

    host = RemoteHintHost(RemoteHint(scale, Pairing(), lambda: None), scale)  # type: ignore[arg-type]
    assert host.refresh()
    host.set_visible(True)
    reserved = (
        host.measure(Gtk.Orientation.VERTICAL, width)[1] + host.get_margin_bottom()
    )
    usable = 1080 - reserved - scale.px(tokens.CONSOLE_GAP_DU)

    assert four <= usable, (
        f"the rail wants {four}px and has {usable}px above the pairing card"
    )


def test_the_rail_takes_presses_because_the_card_in_it_is_a_transport() -> None:
    """The whole column used to refuse pointer events.

    `set_can_target(False)` on a widget takes its children with it, so the
    now-playing card's click-to-toggle and every secondary source button in
    it were unreachable — `pick()` at the card's own centre returned the
    overlay underneath. Nothing scrolls behind the rail, so the blocks that
    only report facts are the ones that stay out of the way.
    """
    sidebar, status, playing = _rail()

    assert sidebar.get_can_target()  # type: ignore[attr-defined]
    assert playing.get_can_target()  # type: ignore[attr-defined]
    assert not status.get_can_target()  # type: ignore[attr-defined]


def test_left_off_the_first_column_reaches_the_rail_before_rubber_banding() -> None:
    """The rail's now-playing card has exactly one route in.

    LEFT at the first column used to be a wall with a rubber-band on it, so
    the card's transport keys were pointer-only on a machine whose whole
    point is that it is driven with a remote. The order matters as much as
    the branch: `_rubber_band` first would make the new one unreachable.
    """
    path = Path(__file__).resolve().parent.parent / "salon/ui/home_landing.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_move_focus"
    )
    calls = [
        node.func.attr
        for node in ast.walk(handler)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "_enter_now_playing" in calls
    assert calls.index("_enter_now_playing") < calls.index("_rubber_band")


def test_the_card_takes_back_and_gives_the_rest_of_the_remote_back() -> None:
    """The card is a mode, and a mode that swallows SEARCH or MENU is a
    place the remote quietly stops working. It also has to be consulted
    above the router's BACK handler, which returns before any mode is."""
    root = Path(__file__).resolve().parent.parent
    mode = root / "salon/ui/home_now_playing.py"
    actions = next(
        node
        for node in ast.parse(mode.read_text(), filename=str(mode)).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_CARD_ACTIONS"
            for target in node.targets
        )
    )
    named = {
        element.attr
        for element in ast.walk(actions.value)
        if isinstance(element, ast.Attribute)
    }
    assert named == {"OK", "BACK"}  # the rest is _DIRECTIONS, starred in

    router = root / "salon/ui/home_action_router.py"
    dispatch = next(
        node
        for node in ast.walk(ast.parse(router.read_text(), filename=str(router)))
        if isinstance(node, ast.FunctionDef) and node.name == "_dispatch_action"
    )

    def branch(needle: str) -> int:
        """Where a top-level `if` on `action` sits in the dispatch chain."""
        return next(
            index
            for index, statement in enumerate(dispatch.body)
            if isinstance(statement, ast.If) and needle in ast.dump(statement.test)
        )

    assert branch("_card_takes") < branch("'BACK'")


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


def test_settings_section_pane_stays_visible_in_nested_panels() -> None:
    path = Path(__file__).resolve().parent.parent / "salon/ui/settings/screen_navigation.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    update = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_update_pane_style"
    )
    visibility = next(
        node
        for node in ast.walk(update)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "set_visible"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "_sections_host"
    )

    assert len(visibility.args) == 1
    assert isinstance(visibility.args[0], ast.Constant)
    assert visibility.args[0].value is True
