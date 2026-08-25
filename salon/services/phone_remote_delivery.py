# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Validation and main-loop delivery helpers for remote commands."""

from salon.services.phone_remote_shared import Callable, GLib


def _finite(value: object) -> float:
    """A number from an untrusted JSON body, or zero.

    JSON permits NaN and Infinity in practice, and either of those reaching
    a pointer-motion accumulator moves the cursor somewhere it can never
    come back from.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return 0.0
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    # A phone screen is not a thousand pixels wide; anything larger is
    # either a bug or someone probing.
    return max(-2000.0, min(2000.0, number))


def _sse_frame(payload: bytes) -> bytes:
    """One server-sent event carrying the state JSON.

    The payload is JSON with no newlines in it (`json.dumps` with the
    separators `StateFeed` uses emits none, and a newline inside a `data:`
    line would split one event into two half-parsed ones), so this is a
    prefix and two line feeds rather than a line-by-line encoder.
    """
    return b"data: " + payload + b"\n\n"


def _deliver_button(callback: Callable[[str, str], None], button: str, what: str) -> bool:
    callback(button, what)
    return GLib.SOURCE_REMOVE


def _deliver_level(callback: Callable[[float], None], level: float) -> bool:
    callback(level)
    return GLib.SOURCE_REMOVE


def _deliver(callback: Callable[[str], None], text: str) -> bool:
    callback(text)
    return GLib.SOURCE_REMOVE


def _deliver_motion(callback: Callable[[float, float], None], dx: float, dy: float) -> bool:
    callback(dx, dy)
    return GLib.SOURCE_REMOVE


def _deliver_transport(callback: Callable[[str], bool], what: str) -> bool:
    callback(what)
    return GLib.SOURCE_REMOVE


def _notify(callback: Callable[[], None]) -> bool:
    callback()
    return GLib.SOURCE_REMOVE
