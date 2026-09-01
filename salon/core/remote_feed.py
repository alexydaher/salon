# SPDX-License-Identifier: GPL-3.0-or-later
"""Versioned publication and authorization state for the phone remote."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field

from salon.core.remote import RemoteState


@dataclass(slots=True)
class StateFeed:
    state: RemoteState = field(default_factory=RemoteState)
    version: int = 1
    _payload: bytes | None = field(default=None, repr=False)

    def publish(self, state: RemoteState) -> bool:
        if state == self.state:
            return False
        self.state = state
        self.version += 1
        self._payload = None
        return True

    def payload(self) -> bytes:
        if self._payload is None:
            body = self.state.to_dict()
            body["v"] = self.version
            self._payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        return self._payload

    def is_current(self, version: str | int | None) -> bool:
        try:
            return int(version) == self.version  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False

    def tile_ids(self) -> frozenset[str]:
        visible = {tile.id for row in self.state.rows for tile in row.tiles}
        # Running apps are visible on the media surface too. Authorizing
        # their ids here lets /art draw the same application image there
        # without widening the endpoint beyond things the phone was shown.
        visible.update(app.id for app in self.state.running_apps)
        return frozenset(visible)


@dataclass(slots=True)
class OfferedIds:
    """A bounded insertion-ordered set of tile IDs the phone has been shown.

    Two sources feed it: search results, and the A-Z list of every installed
    application. The ceiling has to clear both at once — a phone that
    browsed the whole app list and then searched once would otherwise have
    the earliest applications evicted out from under the artwork it is still
    displaying, and their cards would fall back to a coloured letter.
    """

    limit: int = 800
    _ids: dict[str, None] = field(default_factory=dict, repr=False)

    def offer(self, ids: Iterable[str]) -> None:
        for item_id in ids:
            self._ids.pop(item_id, None)
            self._ids[item_id] = None
        while len(self._ids) > self.limit:
            self._ids.pop(next(iter(self._ids)))

    def __contains__(self, item_id: object) -> bool:
        return item_id in self._ids

    def clear(self) -> None:
        self._ids.clear()
