# SPDX-License-Identifier: GPL-3.0-or-later
"""First run (§6.11): five screens, then out of the way forever.

The problem onboarding solves here is narrow and real. Salon has no visible
menu bar, no window controls and no text anywhere saying what the buttons
do; someone handed a controller in front of a television has no way to
discover that MENU exists, that search is a button, or that the tiles they
see are editable — and, most costly of all, no way to discover how to get
back out of a fullscreen app that has taken the whole screen. A handful of
sentences fix that permanently.

What it deliberately isn't: a wizard. Nothing here asks a question, nothing
here can be got wrong, and every screen is skippable with one press. A
launcher that interrogates you before showing you anything is worse than one
that shows you the wrong tiles.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gtk, Pango  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


@dataclass(frozen=True, slots=True)
class Page:
    title: str
    body: str
    hint: str


PAGES: tuple[Page, ...] = (
    Page(
        title="Welcome to Salon",
        body=(
            "Everything here is built for a remote or a controller across a "
            "room. Move with the direction pad, choose with OK, go back with B."
        ),
        hint="Press OK to continue",
    ),
    Page(
        title="The bar at the top",
        body=(
            "Press UP from the first row to reach search, all your apps, "
            "Settings and power. Search looks through your tiles and every "
            "application on this machine at once — type with the on-screen "
            "keyboard, or open the address it shows on your phone."
        ),
        hint="Press OK to continue",
    ),
    Page(
        title="Getting back",
        body=(
            "When something you started is filling the screen, press START on "
            "the controller to close it and come back to Salon. Salon can "
            "always hear the controller, even when it can't see the screen."
        ),
        hint="Press OK to continue",
    ),
    Page(
        title="Make it yours",
        body=(
            "X over any tile pins it to Favourites or edits it. MENU opens "
            "Settings and power from anywhere. Settings is where you add "
            "tiles, group them into rows, drop in your own artwork, and "
            "change how big everything is — with the home screen live behind "
            "you while you do it."
        ),
        hint="Press OK to continue",
    ),
    Page(
        title="One more thing",
        body=(
            "Salon never asks for a password and never plays anything itself. "
            "It starts the apps and sites you already have. The only thing it "
            "ever fetches is the icon belonging to a site you added, from that "
            "site — nothing is sent to anyone else, and Settings can turn even "
            "that off."
        ),
        hint="Press OK to start",
    ),
)


class Onboarding(Gtk.Box):
    """Shown once, on the first run with no completed onboarding flag."""

    def __init__(self, scale: Scale, on_finished: Callable[[], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("salon-search")  # the same full-bleed dark field
        self.set_visible(False)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self._on_finished = on_finished
        self._index = 0

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._content.set_halign(Gtk.Align.CENTER)
        self._content.set_valign(Gtk.Align.CENTER)
        # A vertical box packs from the top and gives each child its natural
        # height, so valign only centres once there's spare space to centre
        # within (the same trap the system menu and text entry both hit).
        self._content.set_vexpand(True)
        self.append(self._content)

        self._step = Gtk.Label()
        self._step.add_css_class("salon-search-hint")
        self._step.set_halign(Gtk.Align.START)
        self._content.append(self._step)

        self._title = Gtk.Label()
        self._title.add_css_class("salon-search-query")
        self._title.set_halign(Gtk.Align.START)
        self._title.set_xalign(0.0)
        self._content.append(self._title)

        self._body = Gtk.Label()
        self._body.add_css_class("salon-onboarding-body")
        self._body.set_halign(Gtk.Align.START)
        self._body.set_xalign(0.0)
        self._body.set_wrap(True)
        self._body.set_wrap_mode(Pango.WrapMode.WORD)
        # A size request only sets the *minimum*; a wrapping label's natural
        # width is still the whole unwrapped line, and a box hands out
        # natural width. max-width-chars is what actually bounds it, and it
        # has to be in characters because that is the unit the measure is
        # done in.
        self._body.set_max_width_chars(64)
        self._content.append(self._body)

        self._hint = Gtk.Label()
        self._hint.add_css_class("salon-search-hint")
        self._hint.set_halign(Gtk.Align.START)
        self._content.append(self._hint)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        buttons.set_halign(Gtk.Align.START)
        self._content.append(buttons)
        self._buttons = buttons

        # Real buttons, because a mouse is one of the three input paths and
        # "press OK" means nothing to someone holding one.
        self._next_button = Gtk.Button(label="Continue")
        self._next_button.add_css_class("salon-search-phone")
        self._next_button.connect("clicked", lambda _b: self.advance())
        buttons.append(self._next_button)

        self._skip_button = Gtk.Button(label="Skip")
        self._skip_button.add_css_class("salon-search-phone")
        self._skip_button.connect("clicked", lambda _b: self.finish())
        buttons.append(self._skip_button)

        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        margin = scale.px(
            tokens.REFERENCE_VIEWPORT_HEIGHT_PX * tokens.SAFE_AREA_DEFAULT_PERCENT / 100.0
        )
        self._content.set_spacing(scale.px(16.0))
        self._content.set_margin_start(margin)
        self._content.set_margin_end(margin)
        self._buttons.set_spacing(scale.px(16.0))
        # A measured line length: full-width body text on a 4K panel is a
        # single 1800px line nobody can track back to the left margin. The
        # character cap in __init__ does the bounding; this only stops the
        # column collapsing narrower than it on a small viewport.
        self._body.set_size_request(scale.px(700.0), -1)

    def start(self) -> None:
        self._index = 0
        self.set_visible(True)
        self._refresh()

    def advance(self) -> None:
        if self._index + 1 >= len(PAGES):
            self.finish()
            return
        self._index += 1
        self._refresh()

    def retreat(self) -> None:
        # BACK on the first page finishes rather than trapping the user on a
        # screen with no way out.
        if self._index == 0:
            self.finish()
            return
        self._index -= 1
        self._refresh()

    def finish(self) -> None:
        self.set_visible(False)
        self._on_finished()

    def _refresh(self) -> None:
        page = PAGES[self._index]
        self._step.set_label(f"{self._index + 1} of {len(PAGES)}")
        self._title.set_label(page.title)
        self._body.set_label(page.body)
        self._hint.set_label(page.hint)
        last = self._index + 1 >= len(PAGES)
        self._next_button.set_label("Start" if last else "Continue")
        self._skip_button.set_visible(not last)

    def handle_action(self, action: Action) -> None:
        if action in (Action.OK, Action.RIGHT):
            self.advance()
        elif action in (Action.BACK, Action.LEFT):
            self.retreat()
