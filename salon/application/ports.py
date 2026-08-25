# SPDX-License-Identifier: GPL-3.0-or-later
"""Narrow interfaces used by application coordinators."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from salon.core.actions import Action
from salon.core.config import Config
from salon.core.model import Tile
from salon.core.remote import RemoteState


class CatalogStorage(Protocol):
    """Persistent storage for the editable tile configuration."""

    def load(self) -> Config: ...

    def save(self, config: Config) -> None: ...


class ActionTarget(Protocol):
    """A destination for normalized user actions."""

    def dispatch(self, action: Action) -> bool: ...


class TileLauncher(Protocol):
    """Launches an existing tile and reports failure asynchronously."""

    def launch(self, tile: Tile, on_error: Callable[[str], None]) -> None: ...


class RemoteStatePublisher(Protocol):
    """Publishes the currently offered remote-control state."""

    def publish(self, state: RemoteState) -> bool: ...


class SearchIndex(Protocol):
    """Supplies the tiles currently searchable by application workflows."""

    def tiles(self) -> Sequence[Tile]: ...
