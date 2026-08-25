# SPDX-License-Identifier: GPL-3.0-or-later
"""The on-screen keyboard's layout and navigation. Pure — no gi.

GNOME's built-in OSK is touch-oriented and can't be driven with a D-pad, so
§6.6 calls for a custom one. The layout and the cursor live here rather than
in the widget for the same reason `core/focus.py` does: keyboard navigation
that skips a key, or refuses to leave a row, is the kind of bug a user hits
in the first ten seconds and a test catches in a millisecond.

**Deviation from §6.6, recorded deliberately.** The brief asks for "a 6x5
grid: QWERTY layout". Those two requirements contradict each other — QWERTY
rows are ten, nine and seven keys wide, and wrapping the alphabet at six
columns produces a grid nobody can read as a keyboard. The stated intent is
a recognisable QWERTY that arrow keys can cross, so this is a ten-column
layout with ragged rows, which is what every TV keyboard worth copying
does. See DECISIONS.md.

Vertical movement is spatial, not by index: each key occupies a span of
grid cells, and moving up or down lands on whichever key in the target row
contains the current key's centre. Moving by index instead would send you
from the "m" key to "Done" simply because both are seventh in their row.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from salon.core.actions import Action

GRID_COLUMNS = 10


class KeyKind(StrEnum):
    CHAR = "char"
    SPACE = "space"
    BACKSPACE = "backspace"
    SHIFT = "shift"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class Key:
    kind: KeyKind
    value: str = ""
    label: str = ""
    width: int = 1

    def display_label(self, *, shift: bool) -> str:
        if self.kind is KeyKind.CHAR:
            return self.value.upper() if shift else self.value
        return self.label


def _chars(text: str) -> tuple[Key, ...]:
    return tuple(Key(kind=KeyKind.CHAR, value=c) for c in text)


# Symbols are placed where they help most: "@" and "." and "/" and "-" are
# what a URL or an account name needs, and this keyboard exists largely to
# type those into bookmark and sign-in fields.
LAYOUT: tuple[tuple[Key, ...], ...] = (
    _chars("1234567890"),
    _chars("qwertyuiop"),
    _chars("asdfghjkl") + (Key(kind=KeyKind.CHAR, value="@"),),
    _chars("zxcvbnm") + _chars(".-/"),
    (
        Key(kind=KeyKind.SHIFT, label="Shift", width=2),
        Key(kind=KeyKind.SPACE, label="Space", width=4),
        Key(kind=KeyKind.BACKSPACE, label="⌫", width=2),
        Key(kind=KeyKind.DONE, label="Done", width=2),
    ),
)


@dataclass(frozen=True, slots=True)
class KeyPress:
    """What a press did. `text` is always the full resulting text, so the
    caller never has to reimplement the edit itself."""

    text: str
    done: bool = False
    changed: bool = False


def _spans(row: tuple[Key, ...]) -> list[tuple[int, int]]:
    """(start, end) grid-cell span of each key in a row, end exclusive."""
    spans: list[tuple[int, int]] = []
    cell = 0
    for key in row:
        spans.append((cell, cell + key.width))
        cell += key.width
    return spans


def _key_at_cell(row: tuple[Key, ...], cell: int) -> int:
    for index, (start, end) in enumerate(_spans(row)):
        if start <= cell < end:
            return index
    return len(row) - 1


class KeyboardModel:
    """Cursor, shift state and the text being edited.

    Holding the text here rather than in the entry widget means every edit
    — including the ones the phone-pairing server pushes in — goes through
    one code path that tests can drive.
    """

    def __init__(self, text: str = "") -> None:
        self._text = text
        self._row = 1  # the "q" row: where the eye and the hand both start
        self._col = 0
        self._shift = False

    @property
    def text(self) -> str:
        return self._text

    @property
    def shift(self) -> bool:
        return self._shift

    @property
    def position(self) -> tuple[int, int]:
        return (self._row, self._col)

    @property
    def key(self) -> Key:
        return LAYOUT[self._row][self._col]

    def set_text(self, text: str) -> None:
        """Used by the phone-pairing path, which inserts text the keyboard
        cursor knows nothing about."""
        self._text = text

    def insert_text(self, text: str) -> bool:
        """Insert text supplied by a hardware keyboard, paste, or phone."""
        if not text:
            return False
        self._text += text
        return True

    def backspace(self) -> bool:
        if not self._text:
            return False
        self._text = self._text[:-1]
        return True

    def jump_to(self, row: int, col: int) -> None:
        """Point the cursor straight at a key — how a mouse click or a
        pointer hover moves it, since neither arrives as a direction."""
        if not (0 <= row < len(LAYOUT)):
            return
        self._row = row
        self._col = max(0, min(col, len(LAYOUT[row]) - 1))

    def move(self, action: Action) -> bool:
        """Move the cursor. Returns False at an edge so the caller can
        render a rubber-band, or hand the move to whatever is beside the
        keyboard (the results grid)."""
        if action is Action.LEFT:
            if self._col == 0:
                return False
            self._col -= 1
            return True
        if action is Action.RIGHT:
            if self._col >= len(LAYOUT[self._row]) - 1:
                return False
            self._col += 1
            return True
        if action in (Action.UP, Action.DOWN):
            delta = -1 if action is Action.UP else 1
            new_row = self._row + delta
            if not (0 <= new_row < len(LAYOUT)):
                return False
            start, end = _spans(LAYOUT[self._row])[self._col]
            centre = (start + end - 1) // 2
            self._row = new_row
            self._col = _key_at_cell(LAYOUT[new_row], centre)
            return True
        return False

    def press(self) -> KeyPress:
        key = self.key
        if key.kind is KeyKind.CHAR:
            char = key.value.upper() if self._shift else key.value
            self._text += char
            # Shift is one-shot, like a phone keyboard: holding it on after
            # a letter is almost never what someone typing a name wants.
            self._shift = False
            return KeyPress(self._text, changed=True)
        if key.kind is KeyKind.SPACE:
            self._text += " "
            return KeyPress(self._text, changed=True)
        if key.kind is KeyKind.BACKSPACE:
            if not self._text:
                return KeyPress(self._text)
            self._text = self._text[:-1]
            return KeyPress(self._text, changed=True)
        if key.kind is KeyKind.SHIFT:
            self._shift = not self._shift
            return KeyPress(self._text)
        return KeyPress(self._text, done=True)
