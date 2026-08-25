# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused phone-remote server component."""

from __future__ import annotations

from salon.services.phone_remote_shared import (
    _MAX_REQUEST_BODY_BYTES,
    _STATUS_CONTENT_TOO_LARGE,
    _STATUS_TOO_MANY_REQUESTS,
    Gio,
    PhoneRemoteComponent,
    Soup,
    is_local_address,
    json,
    secrets,
)


class PhoneRemoteAuthorization(PhoneRemoteComponent):
    def _from_local_network(self, message: Soup.ServerMessage) -> bool:
        """Refuse anything that did not come from our own network.

        A source we can't identify is refused too: the alternative is
        deciding that an unreadable address is trustworthy.
        """
        address = message.get_remote_address()
        if isinstance(address, Gio.InetSocketAddress):
            inet = address.get_address()
            return inet is not None and is_local_address(inet.to_string())
        return False

    @staticmethod
    def _refuse(message: Soup.ServerMessage, status: int, text: str) -> None:
        message.set_status(status, None)
        message.set_response("text/plain; charset=utf-8", Soup.MemoryUse.COPY, text.encode())

    def _fields(self, message: Soup.ServerMessage) -> dict[str, object] | None:
        """The JSON body of a POST, or None having written the refusal."""
        if message.get_method() != "POST":
            message.set_status(Soup.Status.METHOD_NOT_ALLOWED, None)
            return None
        body = message.get_request_body()
        if body.length > _MAX_REQUEST_BODY_BYTES:
            self._refuse(
                message,
                _STATUS_CONTENT_TOO_LARGE,
                "Request body is too large.",
            )
            return None
        payload = bytes(body.flatten().get_data() or b"")
        if len(payload) > _MAX_REQUEST_BODY_BYTES:
            self._refuse(message, _STATUS_CONTENT_TOO_LARGE, "Request body is too large.")
            return None
        try:
            fields = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            fields = None
        if not isinstance(fields, dict):
            self._refuse(message, Soup.Status.BAD_REQUEST, "Malformed request.")
            return None
        return fields

    def _has_token(self, candidate: object) -> bool:
        # compare_digest even here, where the secret is long enough that a
        # timing oracle is not a practical route in: it costs nothing, and
        # the alternative is a reader having to work out why this one
        # comparison is different from the other.
        return bool(self._owner._token) and secrets.compare_digest(
            str(candidate or ""), self._owner._token
        )

    def _authorize(self, message: Soup.ServerMessage) -> dict[str, object] | None:
        """The gate every POST but `/connect` goes through. Returns the
        request's fields, or None having already written the refusal.

        One function rather than eight, because the D-pad, the trackpad, the
        catalogue and the launch endpoint must all be exactly as hard to
        reach as the keyboard was — an endpoint that skipped the credential
        would make the credential pointless.
        """
        if not self._from_local_network(message):
            self._refuse(message, Soup.Status.FORBIDDEN, "Not on this network.")
            return None
        fields = self._fields(message)
        if fields is None:
            return None
        if self._owner._locked:
            self._refuse(
                message,
                _STATUS_TOO_MANY_REQUESTS,
                "Too many wrong codes. Turn the phone remote off and on again on the TV.",
            )
            return None
        if not self._has_token(fields.get("key")):
            # 401, not 403: this is "your session is over", and the page
            # turns it into the code screen rather than an error.
            self._refuse(message, Soup.Status.UNAUTHORIZED, "Not connected any more.")
            return None
        self._owner._touch()
        return fields

    def _authorize_get(self, message: Soup.ServerMessage, query: dict[str, str] | None) -> bool:
        """The same gate for the two things a browser fetches by URL rather
        than by script: the state poll and a tile's artwork. An `<img>` tag
        cannot send a POST body, so the token travels in the query string —
        which is exactly why the token is what is in the QR and the code is
        not: a guessable secret in a URL is a guessable secret in a log.
        """
        if message.get_method() != "GET":
            message.set_status(Soup.Status.METHOD_NOT_ALLOWED, None)
            return False
        if not self._from_local_network(message):
            self._refuse(message, Soup.Status.FORBIDDEN, "Not on this network.")
            return False
        if self._owner._locked:
            self._refuse(message, _STATUS_TOO_MANY_REQUESTS, "Locked.")
            return False
        if not self._has_token((query or {}).get("k")):
            self._refuse(message, Soup.Status.UNAUTHORIZED, "Not connected any more.")
            return False
        self._owner._touch()
        return True

    @staticmethod
    def _ok(message: Soup.ServerMessage) -> None:
        message.set_status(Soup.Status.OK, None)
        message.set_response("application/json", Soup.MemoryUse.COPY, b"{}")

    @staticmethod
    def _json(message: Soup.ServerMessage, payload: bytes) -> None:
        message.set_status(Soup.Status.OK, None)
        message.set_response("application/json; charset=utf-8", Soup.MemoryUse.COPY, payload)
