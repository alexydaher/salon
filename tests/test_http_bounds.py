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


def fetch(
    body: bytes, *, limit: int, status: int = 200, declared: int = -1, prefix: bool = False
) -> bytes | None:
    stream = Stream(body)
    result: list[bytes | None] = []
    fetch_bytes(
        Session(stream),  # type: ignore[arg-type]
        Message(status, declared),  # type: ignore[arg-type]
        limit,
        result.append,
        prefix=prefix,
    )
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


# --- prefix mode -------------------------------------------------------
#
# The site-icon path reads `<link rel=icon>` out of `<head>`, which is in
# the first few KiB. Rejecting on size meant netflix.com (3.2 MB),
# disneyplus.com (1.6 MB), youtube.com (917 KB) and primevideo.com (529 KB)
# all resolved no icon against a 512 KiB cap — and those four *are* the
# shipped catalogue's flagship row. See DECISIONS 2026-09-04.


def test_prefix_keeps_the_front_of_an_oversized_body() -> None:
    assert fetch(b"123456789", limit=8, prefix=True) == b"12345678"


def test_prefix_keeps_the_whole_body_when_it_fits() -> None:
    assert fetch(b"12345", limit=8, prefix=True) == b"12345"


def test_prefix_reads_despite_a_declared_size_over_the_limit() -> None:
    """The refusal happened before a byte was read, so a big page never
    even got as far as being truncated."""
    assert fetch(b"123456789", limit=8, declared=9, prefix=True) == b"12345678"


def test_prefix_accepts_a_body_shorter_than_its_declared_length() -> None:
    """The front of the document is what was asked for, and it arrived."""
    assert fetch(b"short", limit=8, declared=8, prefix=True) == b"short"


def test_prefix_still_refuses_a_failed_request() -> None:
    """Truncation is about size, not about status: a 302 body is not a page."""
    assert fetch(b"redirect", limit=16, status=302, prefix=True) is None


def test_the_default_is_still_all_or_nothing() -> None:
    """An image has to arrive whole — half a PNG is not an icon."""
    assert fetch(b"123456789", limit=8) is None
    assert fetch(b"unused", limit=8, declared=9) is None
