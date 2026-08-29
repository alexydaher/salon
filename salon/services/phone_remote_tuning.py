# SPDX-License-Identifier: GPL-3.0-or-later
"""`GET /tune` and `POST /tune`: the phone as a control surface.

The television is the display; the phone is the thing in your hand. That is
already the arrangement live preview reaches for on the Appearance strip,
where Settings collapses to a bar so the home screen can answer for itself
— and here it comes for free, because the phone is not covering anything.

What may be changed is `core/remote_settings.FIELDS` and nothing else: an
allow-list of the settings whose effect is visible on the home screen. The
handler never names a GSettings key of its own, so the endpoint cannot be
talked into writing one nobody meant to expose, and every value goes
through `coerce` before it reaches the main loop.

Writes are delivered on an idle like every other phone-originated change,
because they end in a GSettings write and a re-render, and the reply is
written before that runs — the page flips its own control immediately and
the next snapshot is what confirms it, exactly as the play/pause key does.
"""

from __future__ import annotations

import json
from typing import Any

from salon.core import remote_settings
from salon.services.component import ServiceComponent
from salon.services.phone_remote_shared import GLib, Soup


class PhoneRemoteTuning(ServiceComponent):
    def _handle_tune(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        if message.get_method() == "GET":
            self._read(message, query)
            return
        self._write(message)

    def _read(self, message: Soup.ServerMessage, query: dict[str, str] | None) -> None:
        if not self._owner._authorize_get(message, query):
            return
        reader = self._owner._tune_read
        if reader is None:
            self._owner._refuse(
                message, Soup.Status.NOT_IMPLEMENTED, "Picture settings aren't available."
            )
            return
        payload = remote_settings.describe(reader())
        self._owner._json(message, json.dumps(payload).encode())

    def _write(self, message: Soup.ServerMessage) -> None:
        fields = self._owner._authorize(message)
        if fields is None:
            return
        writer = self._owner._tune_write
        if writer is None:
            self._owner._refuse(
                message, Soup.Status.NOT_IMPLEMENTED, "Picture settings aren't available."
            )
            return
        # `name`, not `key`: every POST body already carries the session
        # token as `key`, and a setting called `key` would be indexing into
        # the credential.
        coerced = remote_settings.coerce(fields.get("name"), fields.get("value"))
        if coerced is None:
            # Deliberately not specific. A refusal that distinguished "no
            # such key" from "value out of range" would enumerate the
            # allow-list for anything asking.
            self._owner._refuse(message, Soup.Status.BAD_REQUEST, "That can't be set from here.")
            return
        setting, value = coerced
        GLib.idle_add(lambda: _apply(writer, setting.key, value))
        self._owner._ok(message)


def _apply(writer: Any, key: str, value: object) -> bool:
    writer(key, value)
    return GLib.SOURCE_REMOVE
