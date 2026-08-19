# SPDX-License-Identifier: GPL-3.0-or-later
"""The static provider: the user's own catalogue, from `tiles.json`.

Trusted and synchronous — it hands back rows the caller already parsed —
but it goes through the same `Provider` contract as everything else so
there is exactly one path into the catalogue. A user's hand-written row and
a third-party provider's row are assembled, ordered and failure-isolated by
the same code.
"""

from __future__ import annotations

from salon.core.model import Row
from salon.core.provider import Provider, ProviderContext

PROVIDER_ID = "static"


class StaticProvider(Provider):
    id = PROVIDER_ID
    title = "My tiles"
    # After recents, before anything discovered automatically: the rows the
    # user built by hand are the ones they came to the screen for.
    priority = 20

    def rows(self, context: ProviderContext) -> list[Row]:
        return list(context.config.rows)
