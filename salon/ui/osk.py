# SPDX-License-Identifier: GPL-3.0-or-later
"""The D-pad on-screen keyboard (§6.6).

GNOME's built-in OSK is touch-oriented and can't be driven with a D-pad, so
this is a custom one. Layout and cursor movement live in `core/osk.py`
(pure, tested); this renders that model and nothing more.

Every key is a real `Gtk.Button`, so a mouse or a phone trackpad can click
one directly with no extra wiring — the same reason `ui/overlays.py`'s
system menu is built from buttons. Selection follows the pointer, but only
when the pointer has actually moved, because GTK delivers motion events
whenever a widget maps under a stationary cursor.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from salon.core.osk import LAYOUT, Key, KeyboardModel  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


class OnScreenKeyboard(Gtk.Grid):
    def __init__(
        self,
        model: KeyboardModel,
        scale: Scale,
        *,
        on_key_pressed: Callable[[], None],
        cell_du: float = 76.0,
    ) -> None:
        super().__init__()
        self._model = model
        self._on_key_pressed = on_key_pressed
        self._cell_du = cell_du
        self._hover_enabled = False
        self._buttons: dict[tuple[int, int], Gtk.Button] = {}
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.START)

        column = 0
        for row_index, row in enumerate(LAYOUT):
            column = 0
            for key_index, key in enumerate(row):
                button = Gtk.Button(label=key.display_label(shift=model.shift))
                button.add_css_class("salon-osk-key")
                if key.width > 1:
                    button.add_css_class("wide")
                button.connect("clicked", lambda _b, r=row_index, c=key_index: self._activate(r, c))
                motion = Gtk.EventControllerMotion()
                motion.connect("motion", lambda *_, r=row_index, c=key_index: self._hover(r, c))
                button.add_controller(motion)
                self.attach(button, column, row_index, key.width, 1)
                self._buttons[(row_index, key_index)] = button
                column += key.width

        self.set_scale(scale)
        self.refresh()

    def set_scale(self, scale: Scale) -> None:
        spacing = scale.px(8.0)
        self.set_row_spacing(spacing)
        self.set_column_spacing(spacing)
        cell = scale.px(self._cell_du)
        for (row_index, key_index), button in self._buttons.items():
            key: Key = LAYOUT[row_index][key_index]
            button.set_size_request(cell * key.width + spacing * (key.width - 1), cell)

    def set_hover_enabled(self, enabled: bool) -> None:
        self._hover_enabled = enabled

    def set_model(self, model: KeyboardModel) -> None:
        """Point at a fresh model — how a caller clears the field between
        uses without rebuilding thirty buttons."""
        self._model = model
        self.refresh()

    def refresh(self) -> None:
        """Repaint labels (shift changes them all) and the selection."""
        position = self._model.position
        for (row_index, key_index), button in self._buttons.items():
            key = LAYOUT[row_index][key_index]
            button.set_label(key.display_label(shift=self._model.shift))
            if (row_index, key_index) == position:
                button.add_css_class("selected")
            else:
                button.remove_css_class("selected")
            if key.kind.value == "shift" and self._model.shift:
                button.add_css_class("latched")
            else:
                button.remove_css_class("latched")

    def _hover(self, row: int, key_index: int) -> None:
        if not self._hover_enabled or self._model.position == (row, key_index):
            return
        self._model.jump_to(row, key_index)
        self.refresh()

    def _activate(self, row: int, key_index: int) -> None:
        self._model.jump_to(row, key_index)
        self._on_key_pressed()
