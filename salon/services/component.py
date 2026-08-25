# SPDX-License-Identifier: GPL-3.0-or-later
"""Small composition primitive for stateful service facades."""
from __future__ import annotations

from typing import Any


class ServiceComponent:
    """Delegate component state to one canonical owning service."""

    def __init__(self, owner: object) -> None:
        object.__setattr__(self, "_owner", owner)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._owner, name)

    def __setattr__(self, name: str, value: object) -> None:
        setattr(self._owner, name, value)


def component_attribute(components: tuple[object, ...], name: str) -> Any:
    """Return a method or property exposed by a focused component."""
    for component in components:
        descriptor = vars(type(component)).get(name)
        if descriptor is not None:
            return descriptor.__get__(component, type(component))
    raise AttributeError(name)
