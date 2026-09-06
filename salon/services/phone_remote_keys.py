# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""`POST /key`: the keys that are a name rather than a character.

Escape, Tab and the four arrows, injected into whatever the compositor has
focused. They exist for the one state the rest of the remote is switched
off in. With an application covering the television Salon stops routing its
own Actions — a native app reads the same devices directly and fighting it
for presses is not a fight Salon can win — so the page greys the D-pad, OK,
Back, Search and Options and says why. That is honest about Salon, and it
leaves a video player's own menu with nothing at all to walk it.

These take the trackpad's route instead: the same RemoteDesktop grant, the
same refusal when there is no grant to use. Small enough to live in
`phone_remote_input` and kept out of it anyway, because that file was at
the 250-line cap and a component per concern is what the rest of this
package does.
"""

from __future__ import annotations

from salon.services.phone_remote_shared import (
    KEY_NAMES,
    PhoneRemoteComponent,
    Soup,
)


class PhoneRemoteKeys(PhoneRemoteComponent):
    def _handle_key(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """One named key — Escape, Tab, an arrow — into whatever is focused.

        Not `/action`: those are Salon's own vocabulary and Salon stops
        routing them while an application is in front, which is the one
        state this is for. Not `/type` either — `keysym_for` refuses control
        characters, so there is no string that means Escape.

        Note this does *not* prefer Salon's text sink the way `/type` does.
        A field Salon draws is walked with the D-pad, which is live on that
        screen and is the better instrument; these keys exist for the far
        side of the grant, and sending them both ways would make one button
        mean two things.

        The key travels as `name`, not as `key`: `key` is the session token
        in every request body on this server, and `/tune` had to make the
        same substitution for the same reason.
        """
        fields = self._owner._authorize(message)
        if fields is None:
            return
        name = str(fields.get("name", ""))
        if name not in KEY_NAMES:
            self._owner._refuse(message, Soup.Status.BAD_REQUEST, "Unknown key.")
            return
        if self._owner._on_key is None or not self._owner._on_key(name):
            self._owner._refuse(
                message,
                Soup.Status.CONFLICT,
                "Salon isn't allowed to press keys in other apps. Turn on "
                "Settings \u2192 Input \u2192 Gamepad cursor.",
            )
            return
        self._owner._ok(message)
