# SPDX-License-Identifier: GPL-3.0-or-later
"""A-Z grouping, rail rendering, and letter jumps for All Apps."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.core.model import Tile  # noqa: E402

_BUMP_DISTANCE_DU = 26.0


class AppsGridAlphabet:
    @staticmethod
    def _initial(tile: Tile) -> str:
        first = (tile.title or "?").strip()[:1].upper()
        return first if "A" <= first <= "Z" else "#"

    def _letters(self) -> list[tuple[str, int]]:
        found: list[tuple[str, int]] = []
        seen: set[str] = set()
        for index, tile in enumerate(self._tiles):
            letter = self._initial(tile)
            if letter not in seen:
                seen.add(letter)
                found.append((letter, index))
        return found

    def _rebuild_rail(self) -> None:
        child = self._rail.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self._rail.remove(child)
            child = following
        self._rail_labels = {}
        present = dict(self._letters())
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            label = Gtk.Label(label=letter)
            label.add_css_class("salon-letter")
            label.set_halign(Gtk.Align.CENTER)
            label.set_vexpand(True)
            label.set_valign(Gtk.Align.CENTER)
            if letter in present:
                click = Gtk.GestureClick()
                click.connect("released", lambda *_, i=present[letter]: self._jump_to_index(i))
                label.add_controller(click)
            else:
                label.add_css_class("unavailable")
            self._rail.append(label)
            self._rail_labels[letter] = label

    def _update_rail(self) -> None:
        tile = self.focused_tile
        current = self._initial(tile) if tile is not None else ""
        for letter, label in self._rail_labels.items():
            if letter == current:
                label.add_css_class("current")
            else:
                label.remove_css_class("current")

    def _jump_letter(self, delta: int) -> None:
        letters = self._letters()
        if not letters:
            return
        index = self._focused_index()
        position = 0
        for i, (_letter, start) in enumerate(letters):
            if start <= index:
                position = i
            else:
                break
        target = position if delta < 0 and letters[position][1] != index else position + delta
        if not 0 <= target < len(letters):
            distance = self._scale.du(_BUMP_DISTANCE_DU)
            self._scroll.bump(distance if delta < 0 else -distance)
            return
        self._jump_to_index(letters[target][1])
