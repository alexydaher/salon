# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused phone-remote server component."""

from __future__ import annotations

from salon.services.phone_remote_shared import (
    _AWAKE_CLIPS,
    _UI_ASSET_NAME,
    _UI_TYPES,
    PhoneRemoteComponent,
    Soup,
    _resource_bytes,
)


class PhoneRemoteResources(PhoneRemoteComponent):
    def _serve_resource(
        self,
        message: Soup.ServerMessage,
        name: str,
        content_type: str,
        *,
        missing_is_broken: bool = True,
    ) -> None:
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
        if not self._owner._from_local_network(message):
            self._owner._refuse(message, Soup.Status.FORBIDDEN, "Not on this network.")
            return
        data = _resource_bytes(name)
        if data is None:
            # A missing page really is a broken install and says so. A
            # missing `/ui/<name>` is more often a URL somebody made up,
            # and the whole set is checked against the bundle by
            # tests/test_phone_page.py rather than at request time.
            if not missing_is_broken:
                message.set_status(Soup.Status.NOT_FOUND, None)
                return
            self._owner._refuse(
                message,
                Soup.Status.INTERNAL_SERVER_ERROR,
                "Salon could not find the remote's page. This copy may be installed wrong.",
            )
            return
        # These URLs stay the same across Salon upgrades. Reusing an older
        # page, stylesheet or module on the first QR navigation makes fixes
        # appear only after a manual refresh, so the phone shell must never
        # be satisfied from a previous installed version.
        if name == "index.html" or name.startswith("ui/"):
            message.get_response_headers().append("Cache-Control", "no-store")
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

    def _handle_asset(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """One of the page's stylesheets or ES modules.

        The page is markup only; its four stylesheets and its twenty modules
        live under `remote/ui/` in the same bundle and are asked for by
        name. The name is matched against a pattern with no dot-dot and no
        slash in it before it is joined to anything, so there is no
        traversal to get wrong — and a name that is not in the bundle is a
        404 rather than a read off the disk beside the module.
        """
        name = path.removeprefix("/ui/") if path.startswith("/ui/") else ""
        if not _UI_ASSET_NAME.fullmatch(name):
            message.set_status(Soup.Status.NOT_FOUND, None)
            return
        self._serve_resource(
            message,
            f"ui/{name}",
            _UI_TYPES[name.rsplit(".", 1)[1]],
            missing_is_broken=False,
        )

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
