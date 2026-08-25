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
) -> None:
    """Fetch a successful response without ever retaining more than *limit*."""
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
        if not 200 <= status < 300 or declared > limit:
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
                finish(body if declared < 0 or len(body) == declared else None, source)
                return
            total += len(data)
            if total > limit:
                finish(None, source)
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
