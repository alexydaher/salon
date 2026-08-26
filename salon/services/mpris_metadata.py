# SPDX-License-Identifier: GPL-3.0-or-later
"""Translate MPRIS property dictionaries into Salon player records."""

from __future__ import annotations

import time
from collections.abc import Mapping

from gi.repository import GLib

from salon.core.nowplaying import Player

_PREFIX = "org.mpris.MediaPlayer2."


def _artist(metadata: Mapping[str, object]) -> str:
    value = metadata.get("xesam:artist")
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value if item)
    return ""


def _art_url(metadata: Mapping[str, object]) -> str:
    """`mpris:artUrl`, kept as the URI the player published.

    Deciding what to do with it belongs further up: an `https://` cover goes
    to the phone as it stands and the phone fetches it, and a `file://` one
    becomes a path Salon serves. Turning it into either here would mean this
    pure translation layer knowing about the remote.
    """
    value = metadata.get("mpris:artUrl")
    return value if isinstance(value, str) else ""


def _fallback_identity(bus_name: str) -> str:
    tail = bus_name.removeprefix(_PREFIX).split(".")[0]
    return tail.replace("_", " ").title() if tail else "Media"


def player_from_properties(
    bus_name: str,
    properties: Mapping[str, object],
    previous: Player | None,
) -> Player:
    raw_metadata = properties.get("Metadata") or {}
    metadata = raw_metadata if isinstance(raw_metadata, (dict, GLib.VariantDict)) else {}
    status = str(properties.get("PlaybackStatus", ""))
    title = str(metadata.get("xesam:title", "") or "")
    unchanged = previous is not None and previous.status == status and previous.title == title
    return Player(
        bus_name=bus_name,
        identity=previous.identity if previous else _fallback_identity(bus_name),
        status=status,
        title=title,
        artist=_artist(metadata),
        changed_at=previous.changed_at if unchanged and previous else time.monotonic(),
        can_go_next=bool(properties.get("CanGoNext", False)),
        can_go_previous=bool(properties.get("CanGoPrevious", False)),
        art_url=_art_url(metadata),
    )
