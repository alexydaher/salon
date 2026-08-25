# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused phone-remote server component."""

from __future__ import annotations

from salon.services.phone_remote_shared import *


class PhoneRemoteResources(PhoneRemoteComponent):
    def _serve_resource(self, message: Soup.ServerMessage, name: str, content_type: str) -> None:
        """The page and its two attachments.

        Not behind the credential, and deliberately so: the phone has to be
        able to load the page *before* it can authenticate, and a browser
        fetches a manifest and an icon on its own without passing anything
        the script holds. Nothing served here contains a secret — the token
        arrives in the fragment, which never reaches this process.
        """
        if message.get_method() != "GET":
            message.set_status(Soup.Status.METHOD_NOT_ALLOWED, None)
            return
        if not self._from_local_network(message):
            self._refuse(message, Soup.Status.FORBIDDEN, "Not on this network.")
            return
        data = _resource_bytes(name)
        if data is None:
            self._refuse(
                message,
                Soup.Status.INTERNAL_SERVER_ERROR,
                "Salon could not find the remote's page. This copy may be installed wrong.",
            )
            return
        message.set_status(Soup.Status.OK, None)
        message.set_response(content_type, Soup.MemoryUse.COPY, data)

    def _handle_page(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        self._serve_resource(message, "index.html", "text/html; charset=utf-8")

    def _handle_manifest(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        self._serve_resource(message, "manifest.webmanifest", "application/manifest+json")

    def _handle_icon(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        self._serve_resource(message, "icon.svg", "image/svg+xml")

    def _handle_awake(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """The clip that keeps the phone's screen on.

        `navigator.wakeLock` is gated on a secure context, and the remote is
        plain HTTP on a LAN address — so on a phone the API is not refused,
        it is *absent*, and the `"wakeLock" in navigator` guard around it
        made the whole feature dead code. Playing a muted video is the
        fallback every phone honours, and it needs something to play.
        """
        name, content_type = _AWAKE_CLIPS.get(path, ("", ""))
        if not name:
            message.set_status(Soup.Status.NOT_FOUND, None)
            return
        self._serve_resource(message, name, content_type)
