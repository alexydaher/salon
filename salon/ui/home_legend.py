# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow: what the button legend currently says."""

from salon.services.component import ServiceComponent
from salon.ui.home_legend_policy import HOME_ACTION_MEANINGS
from salon.ui.home_shared import (
    CEC,
    GAMEPAD,
    Action,
    buttons,
)
from salon.ui.legend import ControllerGlyph, Hint


class HomeLegendController(ServiceComponent):
    def _note_input_source(self, source: str) -> None:
        """Remember which kind of device sent the last press.

        Every source calls this on its way in, because the legend's whole
        point is naming the button in the hand that is holding it — and a
        living room routinely has two of them. Only a *change* costs
        anything; the common case is the same source pressing again.
        """
        if source == self._owner._input_source:
            return
        self._owner._input_source = source
        family = buttons.GENERIC
        if source == GAMEPAD:
            family = buttons.gamepad_family(self._owner._gamepad.device_name)
        self._owner._apps_grid.set_input_device(source, family)
        self._owner._settings_screen.set_input_device(source, family)
        self._update_legend()

    def _legend_caption(self, action: Action) -> str | ControllerGlyph:
        source = self._owner._input_source
        family = buttons.GENERIC
        if source == GAMEPAD:
            family = buttons.gamepad_family(self._owner._gamepad.device_name)
        label = buttons.label(action, source, family=family)
        glyph = buttons.glyph(action, source, family=family)
        if glyph:
            return ControllerGlyph(glyph, label)
        return label.upper() if source == CEC else label

    def _legend_hints(self) -> tuple[Hint, ...]:
        """What can be pressed *here*, most-used first.

        Keyed on the mode and nothing else. It used to be the third line of
        the detail strip, which meant it was a fact about the selected tile
        — so it was rebuilt on every cursor move and it could never say
        anything about a menu, the top bar or a launched app.
        """
        cap = self._legend_caption
        for menu in (self._owner._system_menu, self._owner._tile_menu):
            if not menu.get_visible():
                continue
            # "Close" is a lie on a second level, and the power list is one.
            leaving = "Back a step" if menu.has_back else "Close"
            return ((cap(Action.OK), "Choose"), (cap(Action.BACK), leaving))
        if self._owner._child_active or self._owner._pointer_mode:
            # The one thing that still works from behind another
            # application, and the one nobody can guess.
            return ((cap(Action.MENU), "Back to Salon"),)
        if self._owner._nav_focused:
            return ((cap(Action.OK), "Choose"), (cap(Action.DOWN), "Back to tiles"))
        # Home's available actions do not change with time. Keeping the
        # complete mapping here also means that covering Home with Settings
        # and returning cannot reveal a shorter legend than the one that was
        # visible before the round trip.
        return tuple((cap(action), meaning) for action, meaning in HOME_ACTION_MEANINGS)

    def _update_legend(self) -> None:
        hints = self._legend_hints()
        visible_menu = None
        for menu in (self._owner._system_menu, self._owner._tile_menu):
            if menu.get_visible():
                visible_menu = menu
            menu.set_hints(hints if menu.get_visible() else ())
        # A menu carries its own copy above the scrim; the standing Home
        # legend is deliberately underneath it with the rest of Home.
        self._owner._legend.set_hints(() if visible_menu is not None else hints)
