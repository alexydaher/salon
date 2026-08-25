# SPDX-License-Identifier: GPL-3.0-or-later
"""Presentation-neutral network status returned by NetworkManager adapters."""

from __future__ import annotations

from dataclasses import dataclass

from salon.core import status as status_tokens


@dataclass(frozen=True, slots=True)
class NetworkStatus:
    name: str
    kind: str
    connectivity: str
    available: bool = True
    state: int = status_tokens.CONNECTIVITY_UNKNOWN
    strength: int = -1

    @property
    def summary(self) -> str:
        if not self.available:
            return "NetworkManager isn't running"
        if not self.name:
            return "Not connected"
        return f"{self.name} ({self.kind})" if self.kind else self.name

    @property
    def icon_name(self) -> str:
        return status_tokens.network_glyph(
            self.kind,
            self.strength,
            self.state,
            available=self.available,
        )

    @property
    def phrase(self) -> str:
        return status_tokens.network_phrase(
            self.name,
            self.kind,
            self.state,
            available=self.available,
        )
