# SPDX-License-Identifier: GPL-3.0-or-later
"""Thresholds and human wording for the two alert-only health readings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["normal", "warning", "critical"]
GIB = 1024**3


@dataclass(frozen=True, slots=True)
class StorageReading:
    total_bytes: int
    free_bytes: int

    @property
    def severity(self) -> Severity:
        if self.total_bytes <= 0 or self.free_bytes < 0:
            return "normal"
        ratio = self.free_bytes / self.total_bytes
        # Both gates avoid nagging a large drive merely for crossing 10%, or
        # a tiny appliance drive merely for having fewer than 10 GiB.
        if self.free_bytes <= 2 * GIB:
            return "critical"
        if self.free_bytes <= 10 * GIB and ratio <= 0.10:
            return "warning"
        return "normal"

    @property
    def value(self) -> str:
        gib = self.free_bytes / GIB
        return f"{gib:.1f} GB free" if gib < 10 else f"{gib:.0f} GB free"


@dataclass(frozen=True, slots=True)
class TemperatureReading:
    celsius: float
    warning_c: float = 85.0
    critical_c: float = 95.0
    source: str = "System"

    @property
    def severity(self) -> Severity:
        if self.celsius >= self.critical_c:
            return "critical"
        if self.celsius >= self.warning_c:
            return "warning"
        return "normal"

    @property
    def value(self) -> str:
        return f"{self.celsius:.0f}°C"
