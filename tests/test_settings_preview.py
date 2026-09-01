# SPDX-License-Identifier: GPL-3.0-or-later
"""Live preview: choosing a visual setting shows the home screen behind it."""

from __future__ import annotations

import pytest

from salon.ui.settings import preview_policy

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from salon.input.actions import Action  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings.popup import ValuePopup  # noqa: E402
from salon.ui.settings.screen_preview import SettingsPreviewController  # noqa: E402
from salon.ui.settings.value_rows import ChoiceRow  # noqa: E402

_OPTIONS = [("a", "Amber"), ("b", "Blue"), ("c", "Cold")]


def test_only_previewable_rows_with_a_list_collapse_the_screen() -> None:
    assert preview_policy.previews_home(True, True)
    assert not preview_policy.previews_home(False, True)
    # The collapse leaves nothing but the strip: without a list there is
    # nothing on screen to steer with.
    assert not preview_policy.previews_home(True, False)


def test_the_legend_names_what_ok_does_on_a_previewable_row() -> None:
    assert preview_policy.choosing_hint("OK opens the list", False) == "OK opens the list"
    hint = preview_policy.choosing_hint("OK opens the list", True)
    assert "home" in hint
    # The line has three more clauses to fit and ends in the way out of
    # Settings; spelling this one out pushed "MENU goes home" off the end.
    assert len(hint) <= 30


class _Recorder:
    """Just enough of the widgets the preview controller drives."""

    def __init__(self) -> None:
        self.visible = True
        self.label = ""

    def set_visible(self, visible: bool) -> None:
        self.visible = visible

    def set_label(self, text: str) -> None:
        self.label = text

    def set_row(self, row) -> None:
        self.label = row.label_text

    def set_controls(self, hints) -> None:
        self.controls = hints

    def refresh_values(self) -> None:
        pass


class _Owner:
    def __init__(self) -> None:
        self._preview_row = None
        self._peek_row = None
        self._peek_restore = ""
        self._content = _Recorder()
        self._preview_bar = _Recorder()
        self._preview_bar.visible = False
        self._panel_list = _Recorder()
        self.chrome: list[bool] = []
        self.classes: set[str] = set()

    def _preview_chrome(self, previewing: bool) -> None:
        self.chrome.append(previewing)

    def add_css_class(self, name: str) -> None:
        self.classes.add(name)

    def remove_css_class(self, name: str) -> None:
        self.classes.discard(name)


def _row(store: dict[str, str]) -> ChoiceRow:
    Gtk.init()
    return ChoiceRow(
        "Accent colour",
        _OPTIONS,
        lambda: store["value"],
        lambda value: store.__setitem__("value", value),
        preview=True,
    )


def test_walking_the_list_writes_the_value_so_the_home_screen_answers() -> None:
    store = {"value": "b"}
    owner = _Owner()
    preview = SettingsPreviewController(owner)

    preview._enter_peek(_row(store))
    assert not owner._content.visible and owner._preview_bar.visible
    assert "preview" in owner.classes
    assert owner._preview_bar.label == "Accent colour"
    assert (Action.BACK, "Restore") in owner._preview_bar.controls
    # The home screen's own bottom row wants the same edge of the screen.
    assert owner.chrome == [True]

    preview._peek_candidate("c")
    assert store["value"] == "c"
    assert owner._preview_bar.label == "Accent colour"


def test_leaving_the_list_without_choosing_puts_the_original_back() -> None:
    store = {"value": "b"}
    owner = _Owner()
    preview = SettingsPreviewController(owner)

    preview._enter_peek(_row(store))
    preview._peek_candidate("c")
    preview._leave_peek(commit=False)

    assert store["value"] == "b"
    assert owner._content.visible and not owner._preview_bar.visible
    assert "preview" not in owner.classes
    assert owner.chrome == [True, False]


def test_choosing_keeps_the_previewed_value() -> None:
    store = {"value": "b"}
    owner = _Owner()
    preview = SettingsPreviewController(owner)

    preview._enter_peek(_row(store))
    preview._peek_candidate("c")
    preview._leave_peek(commit=True)

    assert store["value"] == "c"
    assert owner._content.visible


def test_a_second_leave_cannot_undo_a_committed_value() -> None:
    """Every navigation out of a panel closes the list, and the list
    reports its own dismissal — so `_leave_peek` is reached more than once
    for one press and has to be idempotent."""
    store = {"value": "b"}
    owner = _Owner()
    preview = SettingsPreviewController(owner)

    preview._enter_peek(_row(store))
    preview._peek_candidate("c")
    preview._leave_peek(commit=True)
    preview._leave_peek(commit=False)

    assert store["value"] == "c"


def test_the_popup_reports_candidates_and_dismissal_but_not_a_choice() -> None:
    Gtk.init()
    store = {"value": "b"}
    row = ChoiceRow(
        "Accent colour",
        _OPTIONS,
        lambda: store["value"],
        lambda value: store.__setitem__("value", value),
        preview=True,
    )
    # A popover has to be inside a toplevel before it can be popped up.
    window = Gtk.Window()
    box = Gtk.Box()
    box.append(row)
    window.set_child(box)

    candidates: list[str] = []
    dismissals: list[int] = []
    chosen: list[int] = []
    popup = ValuePopup(
        Scale(1080),
        on_chosen=lambda: chosen.append(1),
        on_candidate=candidates.append,
        on_dismissed=lambda: dismissals.append(1),
    )

    assert popup.open_for(row, anchor=box, position=Gtk.PositionType.TOP)
    popup.handle_action(Action.UP)
    assert candidates == ["a"]
    popup.handle_action(Action.BACK)
    assert dismissals == [1] and not popup.is_open

    popup.open_for(row)
    popup.handle_action(Action.DOWN)
    popup.handle_action(Action.OK)
    # A close that follows a choice is not a dismissal: the value the user
    # picked is exactly what live preview must not undo.
    assert store["value"] == "c"
    assert chosen == [1] and dismissals == [1]
