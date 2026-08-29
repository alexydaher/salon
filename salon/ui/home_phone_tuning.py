# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading and writing the settings the phone is allowed to touch.

The allow-list is `core/remote_settings.FIELDS` and this is the only place
that turns one of its keys into a GSettings call. The type comes off the
stored variant rather than from a table here, for the same reason
`ui/settings/keyed.py` reads it there: the schema already asserts it, and a
second copy is a second thing that can be wrong.

Nothing is special-cased for the phone. These are the same keys the
Appearance panel writes, so a change made on a phone and a change made with
a remote arrive at the home screen by exactly the same route — the
`changed::` handlers that were already there.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402

from salon.core import remote_settings  # noqa: E402
from salon.services.component import ServiceComponent  # noqa: E402


class HomePhoneTuning(ServiceComponent):
    def _tune_read_for_phone(self) -> dict[str, object]:
        """Every allowed key's current value, for `GET /tune`.

        A key that cannot be read is left out rather than sent as a guess:
        `remote_settings.describe` sends values only for what it was given,
        and the page draws a field with no value as untouched.
        """
        values: dict[str, object] = {}
        for setting in remote_settings.FIELDS:
            try:
                values[setting.key] = self._owner._settings.get_value(setting.key).unpack()
            except (GLib.Error, TypeError, ValueError):
                continue
        return values

    def _tune_write_for_phone(self, key: str, value: object) -> None:
        """One validated write, on the main loop.

        `key` has already been checked against the allow-list and `value`
        clamped to the field's own range by `core/remote_settings.coerce`,
        so the only thing left that can go wrong here is the variant type —
        which is read off the stored value rather than assumed.
        """
        settings = self._owner._settings
        try:
            type_string = settings.get_value(key).get_type_string()
            settings.set_value(key, GLib.Variant(type_string, value))
        except (GLib.Error, TypeError, ValueError):
            return
        self._owner.wake()
        self._owner._publish_remote_state()
