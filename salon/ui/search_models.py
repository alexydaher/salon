# SPDX-License-Identifier: GPL-3.0-or-later
"""Presentation state shared by search UI components."""

from enum import Enum, auto


class Pane(Enum):
    KEYBOARD = auto()
    RESULTS = auto()
