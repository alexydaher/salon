# SPDX-License-Identifier: GPL-3.0-or-later
"""Choice, range, and text-entry settings rows."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from salon.ui.settings.settings_row import SettingsRow


class ChoiceRow(SettingsRow):
    def __init__(
        self,
        label: str,
        options: Sequence[tuple[str, str]],
        get: Callable[[], str],
        set_: Callable[[str], None],
        *,
        detail: str = "",
        preview: bool = False,
    ) -> None:
        super().__init__(label, detail=detail, preview=preview)
        self._options = list(options)
        self._get = get
        self._set = set_
        self.refresh()

    def _index(self) -> int:
        current = self._get()
        for index, (value, _) in enumerate(self._options):
            if value == current:
                return index
        return 0

    @property
    def choices(self) -> list[tuple[str, str]]:
        return list(self._options)

    @property
    def current_choice(self) -> str:
        return self._get()

    def choose(self, key: str) -> None:
        self._set(key)
        self.refresh()

    @property
    def hint(self) -> str:
        return "A/OK opens the list"

    def refresh(self) -> None:
        if self._options:
            self.set_value(self._options[self._index()][1])

    def can_adjust(self, delta: int) -> bool:
        return bool(self._options) and 0 <= self._index() + delta < len(self._options)

    def adjust(self, delta: int) -> bool:
        if not self.can_adjust(delta):
            return False
        self._set(self._options[self._index() + delta][0])
        self.refresh()
        return True


class RangeRow(SettingsRow):
    def __init__(
        self,
        label: str,
        get: Callable[[], float],
        set_: Callable[[float], None],
        *,
        minimum: float,
        maximum: float,
        step: float,
        fmt: Callable[[float], str] = lambda v: f"{v:g}",
        detail: str = "",
        preview: bool = False,
    ) -> None:
        super().__init__(label, detail=detail, preview=preview)
        self._get = get
        self._set = set_
        self._minimum = minimum
        self._maximum = maximum
        self._step = step
        self._fmt = fmt
        self.refresh()

    @property
    def choices(self) -> list[tuple[str, str]]:
        """Every step from minimum to maximum, as a list.

        A range is a set of values like any other here — these are all
        coarse, deliberately chosen steps (5% of a scale, 50ms of a repeat
        delay), not continuous quantities, and the longest of them is a few
        dozen entries in a list that scrolls. Enumerating them means the
        user can jump to the end instead of pressing RIGHT forty times.

        Keyed by index rather than by the value: the labels go through
        `fmt` and two neighbouring steps can format identically ("Off" and
        "0 s"), so the key has to be the one thing that is unique.
        """
        return [(str(index), self._fmt(value)) for index, value in enumerate(self._steps())]

    def _steps(self) -> list[float]:
        values: list[float] = []
        value = self._minimum
        # Accumulated by addition rather than by index * step so the last
        # entry is exactly `maximum` when the span divides evenly, and the
        # epsilon keeps a float that lands a hair over the top from being
        # dropped.
        while value <= self._maximum + 1e-9:
            values.append(min(value, self._maximum))
            value += self._step
        return values

    @property
    def current_choice(self) -> str:
        current = self._get()
        steps = self._steps()
        if not steps:
            return ""
        nearest = min(range(len(steps)), key=lambda i: abs(steps[i] - current))
        return str(nearest)

    def choose(self, key: str) -> None:
        steps = self._steps()
        index = int(key)
        if 0 <= index < len(steps):
            self._set(steps[index])
            self.refresh()

    @property
    def hint(self) -> str:
        return "A/OK opens the list"

    def refresh(self) -> None:
        self.set_value(self._fmt(self._get()))

    def _target(self, delta: int) -> float:
        return min(self._maximum, max(self._minimum, self._get() + delta * self._step))

    def can_adjust(self, delta: int) -> bool:
        return abs(self._target(delta) - self._get()) >= 1e-9

    def adjust(self, delta: int) -> bool:
        if not self.can_adjust(delta):
            return False
        self._set(self._target(delta))
        self.refresh()
        return True


class TextRow(SettingsRow):
    """Opens the on-screen keyboard; the value arrives back through the
    callback the caller wires to `ui/textentry.py`."""

    def __init__(
        self,
        label: str,
        get: Callable[[], str],
        on_edit: Callable[[], None],
        *,
        placeholder: str = "Not set",
        detail: str = "",
    ) -> None:
        super().__init__(label, detail=detail)
        self._get = get
        self._on_edit = on_edit
        self._placeholder = placeholder
        self.refresh()

    @property
    def enterable(self) -> bool:
        return True

    @property
    def hint(self) -> str:
        return "A/OK or RIGHT edits it"

    def refresh(self) -> None:
        self.set_value(self._get() or self._placeholder)

    def activate_row(self) -> None:
        self._on_edit()
