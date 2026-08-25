# SPDX-License-Identifier: GPL-3.0-or-later
"""Small composition primitive for stateful service facades."""

from __future__ import annotations


class ServiceComponent:
    """Hold an explicit owner for a focused service responsibility."""

    def __init__(self, owner: object) -> None:
        self._owner = owner
