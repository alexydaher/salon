# SPDX-License-Identifier: GPL-3.0-or-later
"""Error types raised by salon.core. No gi here, ever — see the AST test."""

from __future__ import annotations


class SalonError(Exception):
    """Base class for errors raised by salon.core."""


class ConfigError(SalonError):
    """Raised when the tile config file is invalid, corrupt, or from an
    unsupported future schema version."""


class CatalogError(SalonError):
    """Raised for invalid catalog mutations: duplicate or missing ids."""


class LaunchResolutionError(SalonError):
    """Raised when a LaunchSpec cannot be resolved to argv."""
