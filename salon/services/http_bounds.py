# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded asynchronous libsoup response reads."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Soup", "3.0")
from gi.repository import Gio, GLib, Soup  # noqa: E402

_CHUNK_BYTES = 64 * 1024


def fetch_bytes(
    session: Soup.Session,
    message: Soup.Message,
    limit: int,
    callback: Callable[[bytes | None], None],
    *,
    prefix: bool = False,
) -> None:
    """Fetch a successful response without ever retaining more than *limit*.

    By default the limit is a *rejection*: a body that does not fit is
    thrown away, which is what an image wants — half a PNG is not an icon.

    `prefix=True` makes it a *truncation* instead, for callers that only
    ever read the front of the response. Site-icon resolution is the one
    that matters: it reads `<link rel=icon>` out of `<head>`, which is in
    the first few KiB, and rejecting on size meant the four largest
    streaming homepages — netflix.com at 3.2 MB, disneyplus.com at 1.6 MB,
    youtube.com at 917 KB, primevideo.com at 529 KB, against a 512 KiB cap
    — resolved no icon at all, while the one small page in the shipped
    catalogue did. Those four *are* the shipped catalogue's flagship row,
    so the whole feature looked implemented and was dead on the screen it
    was written for. In prefix mode a declared length over the limit is
    also not grounds for refusing, and a body shorter than a declared
    Content-Length is returned rather than discarded: the front of the
    document is what was asked for and the front of it arrived.
    """
    completed = False

    def finish(value: bytes | None, stream: Gio.InputStream | None = None) -> None:
        nonlocal completed
        if completed:
            return
        completed = True
        if stream is not None:
            try:
                stream.close(None)
            except GLib.Error:
                pass
        callback(value)

    def sent(owner: Soup.Session, result: Gio.AsyncResult) -> None:
        try:
            stream = owner.send_finish(result)
        except GLib.Error:
            finish(None)
            return
        status = int(message.get_status())
        declared = message.get_response_headers().get_content_length()
        if not 200 <= status < 300 or (declared > limit and not prefix):
            finish(None, stream)
            return
        chunks: list[bytes] = []
        total = 0

        def read_done(source: Gio.InputStream, read_result: Gio.AsyncResult) -> None:
            nonlocal total
            try:
                block = source.read_bytes_finish(read_result)
            except GLib.Error:
                finish(None, source)
                return
            data = bytes(block.get_data() or b"")
            if not data:
                body = b"".join(chunks)
                if prefix or declared < 0 or len(body) == declared:
                    finish(body, source)
                else:
                    finish(None, source)
                return
            total += len(data)
            if total > limit:
                # Stop reading either way; keep what fits only in prefix
                # mode, where the front of the document is the answer. The
                # chunk that crossed the line is included before trimming —
                # it holds the bytes up to the limit.
                kept = (b"".join(chunks) + data)[:limit] if prefix else None
                finish(kept, source)
                return
            chunks.append(data)
            source.read_bytes_async(
                min(_CHUNK_BYTES, limit - total + 1),
                GLib.PRIORITY_LOW,
                None,
                read_done,
            )

        stream.read_bytes_async(min(_CHUNK_BYTES, limit + 1), GLib.PRIORITY_LOW, None, read_done)

    try:
        session.send_async(message, GLib.PRIORITY_LOW, None, sent)
    except (GLib.Error, TypeError, ValueError):
        finish(None)
