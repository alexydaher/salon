# SPDX-License-Identifier: GPL-3.0-or-later
"""Keeping the television out of a password prompt it cannot answer.

GNOME's defaults blank the screen after five minutes and lock it when it
blanks. On a desk that is correct. In a living room it is a dead end: the
screen comes back showing a password field, and the only input devices in
the room are a gamepad and a TV remote, neither of which can type one. The
set becomes a brick until someone fetches a keyboard.

So when Salon is the session — and *only* then, see `core.session` — the
lock is turned off for as long as Salon is running, and restored on the way
out. Blanking is deliberately left alone: the screen still goes dark on
idle, which is what saves the panel and the power. It just comes back.

Two things this does not do. It doesn't touch anything when Salon is a guest
in someone's ordinary desktop session, because changing a global preference
on behalf of a window the user opened from Show Applications would be
indefensible. And it doesn't try hard to restore after a crash: the value it
leaves behind is the unlocked one, which is the safe direction to fail for
an appliance, and the next clean exit puts it back.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio  # noqa: E402

from salon.core import sandbox, session  # noqa: E402
from salon.logs import logger  # noqa: E402

_SCHEMA = "org.gnome.desktop.screensaver"
_KEY = "lock-enabled"


def _schema_exists(schema: str) -> bool:
    source = Gio.SettingsSchemaSource.get_default()
    return source is not None and source.lookup(schema, True) is not None


class ScreenLockPolicy:
    """Suppresses the idle screen lock while Salon owns the session."""

    def __init__(
        self,
        settings: Gio.Settings | None = None,
        *,
        active: bool | None = None,
        sandboxed: bool | None = None,
    ) -> None:
        session_active = session.is_session() if active is None else active
        self._active = session_active and sandbox.host_settings_available(sandboxed)
        self._settings = settings
        self._previous: bool | None = None

    def _resolve(self) -> Gio.Settings | None:
        if self._settings is not None:
            return self._settings
        if not _schema_exists(_SCHEMA):
            # Not GNOME, or a stripped-down install. Nothing to switch off.
            logger().info("No %s schema; leaving the screen lock alone.", _SCHEMA)
            return None
        self._settings = Gio.Settings.new(_SCHEMA)
        return self._settings

    def apply(self) -> None:
        """Turn the lock off, remembering what it was."""
        if not self._active:
            return
        settings = self._resolve()
        if settings is None:
            return
        previous = settings.get_boolean(_KEY)
        if not previous:
            return  # already off; nothing to restore later either
        self._previous = previous
        settings.set_boolean(_KEY, False)
        logger().info(
            "Salon is the session: idle screen lock suppressed "
            "(the screen still blanks, it just doesn't ask for a password)."
        )

    def restore(self) -> None:
        """Put it back, if we were the ones who changed it."""
        if self._previous is None:
            return
        settings = self._resolve()
        if settings is not None:
            settings.set_boolean(_KEY, self._previous)
            logger().info("Idle screen lock restored to %s.", self._previous)
        self._previous = None
