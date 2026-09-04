# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure presentation rules for the console's small system-status card."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tone = Literal["normal", "warning", "danger"]


@dataclass(frozen=True, slots=True)
class StatusItem:
    key: str
    icon_name: str
    name: str
    value: str
    phrase: str
    priority: int
    tone: Tone = "normal"


def choose(items: tuple[StatusItem, ...], limit: int = 4) -> tuple[StatusItem, ...]:
    """Keep the most useful facts, then draw them in their stable source order.

    Choosing and ordering are deliberately separate. A warning can displace a
    quiet row without making every surviving row jump to a new position.
    """
    if limit <= 0:
        return ()
    ranked = sorted(enumerate(items), key=lambda pair: (-pair[1].priority, pair[0]))
    kept = {index for index, _item in ranked[:limit]}
    return tuple(item for index, item in enumerate(items) if index in kept)


def network_value(strength: int, connectivity: int) -> tuple[str, int, Tone]:
    """Compact wording wins over signal bars when the internet is unusable."""
    if connectivity == 1:
        return ("Offline", 96, "danger")
    if connectivity == 2:
        return ("Sign in", 90, "warning")
    if connectivity == 3:
        return ("No internet", 90, "warning")
    if strength >= 75:
        return ("Strong", 60, "normal")
    if strength >= 40:
        return ("Good", 60, "normal")
    if strength >= 0:
        return ("Weak", 72, "warning")
    return ("Connected", 60, "normal")


def battery_priority(percent: float, *, charging: bool) -> tuple[int, Tone]:
    if charging:
        return (46, "normal")
    if percent <= 10:
        return (94, "danger")
    if percent <= 20:
        return (88, "danger")
    if percent <= 40:
        return (76, "warning")
    return (52, "normal")
