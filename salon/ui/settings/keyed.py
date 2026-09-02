# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings rows bound to a GSettings key, and what that buys.

Every row used to spell out its own plumbing:

    RangeRow("Tile size",
             lambda: settings.get_double("tile-scale"),
             lambda v: settings.set_double("tile-scale", v), ...)

Four mentions of one key, a getter and a setter that must agree about the
type, and no way for the row to know what Salon shipped as the default —
so no "you have changed this", no "put it back", and a panel that wanted
either had to keep a second table of keys and defaults beside the rows.

`Keyed` takes the key and reads the rest off the schema. The type comes
from the stored variant, the default from `get_default_value`, and both are
things the schema already asserts, so there is one place that can be wrong
instead of three. The rows come back knowing whether they hold what was
shipped, which is `modified` (a dot in the margin) and `reset_to_default`
(the OPTIONS menu, and "Restore this section's defaults").
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon.ui.settings.action_rows import ActionRow, ToggleRow  # noqa: E402
from salon.ui.settings.settings_row import SettingsRow  # noqa: E402
from salon.ui.settings.value_rows import ChoiceRow, RangeRow, TextRow  # noqa: E402


class Keyed:
    """A row factory over one `Gio.Settings`, remembering what it built.

    Kept per panel and constructed *outside* `build()`, so `keys` is the
    set of settings that panel owns however many times it rebuilds — which
    is what "Restore this section's defaults" acts on.
    """

    def __init__(self, settings: Gio.Settings) -> None:
        self._settings = settings
        self.keys: set[str] = set()

    # --- reading the schema ----------------------------------------------

    def default(self, key: str) -> object:
        variant = self._settings.get_default_value(key)
        return None if variant is None else variant.unpack()

    def _type(self, key: str) -> str:
        return str(self._settings.get_value(key).get_type_string())

    def get(self, key: str) -> object:
        return self._settings.get_value(key).unpack()

    def set(self, key: str, value: object) -> None:
        self._settings.set_value(key, GLib.Variant(self._type(key), value))

    def reset(self, key: str) -> None:
        self._settings.reset(key)

    def is_modified(self, key: str) -> bool:
        return self.get(key) != self.default(key)

    @property
    def modified_keys(self) -> list[str]:
        return sorted(key for key in self.keys if self.is_modified(key))

    def reset_all(self) -> int:
        """Put every key this panel owns back. Returns how many moved, so
        the caller can say "nothing to restore" rather than claiming to
        have done something."""
        changed = self.modified_keys
        for key in changed:
            self.reset(key)
        return len(changed)

    # --- rows -------------------------------------------------------------

    def toggle(self, key: str, label: str, *, detail: str = "", preview: bool = False) -> ToggleRow:
        self.keys.add(key)
        return ToggleRow(
            label,
            lambda: self._settings.get_boolean(key),
            lambda value: self._settings.set_boolean(key, value),
            detail=detail,
            preview=preview,
            default=bool(self.default(key)),
        )

    def choice(
        self,
        key: str,
        label: str,
        options: Sequence[tuple[str, str]],
        *,
        detail: str = "",
        preview: bool = False,
    ) -> ChoiceRow:
        self.keys.add(key)
        return ChoiceRow(
            label,
            options,
            lambda: self._settings.get_string(key),
            lambda value: self._settings.set_string(key, value),
            detail=detail,
            preview=preview,
            default=str(self.default(key)),
        )

    def ranged(
        self,
        key: str,
        label: str,
        *,
        minimum: float,
        maximum: float,
        step: float,
        fmt: Callable[[float], str],
        detail: str = "",
        preview: bool = False,
        off_at: float | None = None,
    ) -> RangeRow:
        """A numeric key, whether the schema calls it `i` or `d`.

        The integer case is the one that used to be spelled by hand at
        every call site (`lambda: float(settings.get_int(...))` paired with
        `int(value)`), and getting one half of that pair wrong is a
        `GLib.Variant` type error at runtime rather than a type error here.
        """
        self.keys.add(key)
        integer = self._type(key) == "i"

        def get() -> float:
            return float(self._settings.get_int(key) if integer else self._settings.get_double(key))

        def set_(value: float) -> None:
            if integer:
                self._settings.set_int(key, int(round(value)))
            else:
                self._settings.set_double(key, value)

        return RangeRow(
            label,
            get,
            set_,
            minimum=minimum,
            maximum=maximum,
            step=step,
            fmt=fmt,
            detail=detail,
            preview=preview,
            off_at=off_at,
            default=float(self.default(key)),  # type: ignore[arg-type]
        )

    def text(
        self,
        key: str,
        label: str,
        on_edit: Callable[[], None],
        *,
        placeholder: str = "Not set",
        detail: str = "",
    ) -> TextRow:
        self.keys.add(key)
        return TextRow(
            label,
            lambda: self._settings.get_string(key),
            on_edit,
            placeholder=placeholder,
            detail=detail,
            default=str(self.default(key)),
        )


def restore_defaults_row(
    keyed: Keyed, toast: Callable[[str], None], rebuild: Callable[[], None]
) -> SettingsRow:
    """"Restore defaults", knowing whether there is anything to restore.

    It reports the count rather than confirming first: unlike deleting a
    row this is entirely undoable by hand, the values are all visible on
    the screen it returns to, and a confirmation panel for something with
    no consequence is a press that teaches people to press through them.
    """
    count = len(keyed.modified_keys)

    def restore() -> None:
        moved = keyed.reset_all()
        toast(
            f"{moved} setting{'s' if moved != 1 else ''} restored."
            if moved
            else "Everything here is already at its default."
        )
        rebuild()

    row = ActionRow(
        "Restore defaults",
        restore,
        value=f"{count} changed" if count else "",
    )
    if not count:
        row.set_value("Nothing changed", muted=True)
    return row
