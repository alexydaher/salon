# SPDX-License-Identifier: GPL-3.0-or-later
"""Typed results shared by the wpctl backend and Settings UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Sink:
    """A transient WirePlumber node; persist its description, not its id."""

    id: int
    description: str
    is_default: bool


class AudioAvailability(StrEnum):
    AVAILABLE = "available"
    NOT_INSTALLED = "not-installed"
    HOST_EXECUTION_FAILED = "host-execution-failed"
    NO_OUTPUTS = "no-outputs"
    PROCESS_FAILED = "process-failed"
    MALFORMED_OUTPUT = "malformed-output"


@dataclass(frozen=True, slots=True)
class AudioResult:
    availability: AudioAvailability
    output: str = ""
    error: str = ""
