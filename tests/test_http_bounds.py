# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from gi.repository import GLib

from salon.services.http_bounds import fetch_bytes


class Headers:
    def __init__(self, length: int) -> None:
        self.length = length

    def get_content_length(self) -> int:
        return self.length


class Message:
    def __init__(self, status: int, declared: int) -> None:
        self.status = status
        self.headers = Headers(declared)

    def get_status(self) -> int:
        return self.status

    def get_response_headers(self) -> Headers:
        return self.headers


class Stream:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.requested = 0
        self.closed = False

    def read_bytes_async(self, size: int, *_args: object) -> None:
        self.requested = size
        callback = _args[-1]
        callback(self, object())

    def read_bytes_finish(self, _result: object) -> GLib.Bytes:
        chunk, self.body = self.body[: self.requested], self.body[self.requested :]
        return GLib.Bytes.new(chunk)

    def close(self, _cancellable: object) -> None:
        self.closed = True


class Session:
    def __init__(self, stream: Stream) -> None:
        self.stream = stream

    def send_async(self, *_args: object) -> None:
        callback = _args[-1]
        callback(self, object())

    def send_finish(self, _result: object) -> Stream:
        return self.stream


def fetch(body: bytes, *, limit: int, status: int = 200, declared: int = -1) -> bytes | None:
    stream = Stream(body)
    result: list[bytes | None] = []
    fetch_bytes(Session(stream), Message(status, declared), limit, result.append)  # type: ignore[arg-type]
    assert stream.closed
    return result[0]


def test_exact_limit_is_accepted() -> None:
    assert fetch(b"12345678", limit=8) == b"12345678"


def test_streamed_byte_over_limit_is_rejected() -> None:
    assert fetch(b"123456789", limit=8) is None


def test_declared_size_over_limit_is_rejected_before_reading() -> None:
    assert fetch(b"unused", limit=8, declared=9) is None


def test_truncated_declared_body_is_rejected() -> None:
    assert fetch(b"short", limit=8, declared=8) is None


def test_non_success_status_is_rejected() -> None:
    assert fetch(b"redirect", limit=16, status=302) is None
