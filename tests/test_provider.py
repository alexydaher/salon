# SPDX-License-Identifier: GPL-3.0-or-later
"""The provider contract and its failure isolation (§6.10).

The whole point of this layer is that a stranger's Python file can't take
the launcher down, so most of these tests are about misbehaviour: raising,
hanging, and returning nonsense.
"""

from __future__ import annotations

import threading
import time

from salon.core.config import Config
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile
from salon.core.provider import (
    Provider,
    ProviderContext,
    collect,
)


def tile(tile_id: str) -> Tile:
    return Tile(
        id=tile_id,
        title=tile_id,
        subtitle=None,
        launch=LaunchSpec(kind=LaunchKind.BUILTIN, target="noop"),
        artwork=None,
        icon_name=None,
        accent=None,
    )


def row(row_id: str, *tile_ids: str) -> Row:
    return Row(id=row_id, title=row_id, tiles=[tile(t) for t in tile_ids], provider_id="test")


class Fixed(Provider):
    def __init__(self, provider_id: str, rows_: list[Row], priority: int = 100) -> None:
        self.id = provider_id
        self.title = provider_id
        self.priority = priority
        self._rows = rows_

    def rows(self, context: ProviderContext) -> list[Row]:
        return self._rows


class Exploding(Provider):
    id = "boom"
    title = "boom"

    def rows(self, context: ProviderContext) -> list[Row]:
        raise RuntimeError("no")


class Hanging(Provider):
    id = "hang"
    title = "hang"

    def __init__(self) -> None:
        self.released = threading.Event()

    def rows(self, context: ProviderContext) -> list[Row]:
        self.released.wait(30)
        return []


class Nonsense(Provider):
    id = "nonsense"
    title = "nonsense"

    def rows(self, context: ProviderContext) -> list[Row]:
        return "not a list"  # type: ignore[return-value]


CONTEXT = ProviderContext(config=Config())


def test_rows_are_ordered_by_priority_not_registration() -> None:
    build = collect(
        [Fixed("late", [row("c")], priority=90), Fixed("early", [row("a")], priority=10)],
        CONTEXT,
    )
    assert [r.id for r in build.rows] == ["a", "c"]


def test_equal_priority_keeps_registration_order() -> None:
    build = collect(
        [Fixed("first", [row("a")], priority=50), Fixed("second", [row("b")], priority=50)],
        CONTEXT,
    )
    assert [r.id for r in build.rows] == ["a", "b"]


def test_a_raising_provider_does_not_stop_the_others() -> None:
    build = collect([Exploding(), Fixed("good", [row("a")])], CONTEXT)
    assert [r.id for r in build.rows] == ["a"]
    failures = {f.provider_id: f.reason for f in build.failures}
    assert "RuntimeError: no" in failures["boom"]


def test_a_provider_returning_a_non_list_is_a_failure_not_a_crash() -> None:
    build = collect([Nonsense(), Fixed("good", [row("a")])], CONTEXT)
    assert [r.id for r in build.rows] == ["a"]
    assert "expected list[Row]" in build.failures[0].reason


def test_a_hanging_provider_is_skipped_and_the_rest_still_build() -> None:
    hanging = Hanging()
    started = time.monotonic()
    build = collect([hanging, Fixed("good", [row("a")])], CONTEXT, timeout_seconds=0.2)
    elapsed = time.monotonic() - started
    hanging.released.set()

    assert [r.id for r in build.rows] == ["a"]
    assert "longer than" in build.failures[0].reason
    # One shared deadline, not one per provider.
    assert elapsed < 2.0


def test_providers_share_one_deadline() -> None:
    slow = [Hanging() for _ in range(3)]
    for index, provider in enumerate(slow):
        provider.id = f"hang{index}"
        provider.title = provider.id
    started = time.monotonic()
    collect(list(slow), CONTEXT, timeout_seconds=0.3)
    elapsed = time.monotonic() - started
    for provider in slow:
        provider.released.set()
    assert elapsed < 0.9  # not 3 x 0.3 serialised


def test_a_second_provider_cannot_steal_a_row_id() -> None:
    build = collect(
        [Fixed("a", [row("shared")], priority=10), Fixed("b", [row("shared")], priority=20)],
        CONTEXT,
    )
    assert len(build.rows) == 1
    assert build.rows[0].provider_id == "test"
    failures = {f.provider_id: f.reason for f in build.failures}
    assert "shared" in failures["b"]
    assert "a" not in failures


def test_outcomes_account_for_every_provider() -> None:
    build = collect([Fixed("a", [row("x")]), Exploding()], CONTEXT)
    assert {o.provider_id for o in build.outcomes} == {"a", "boom"}
    by_id = {o.provider_id: o for o in build.outcomes}
    assert by_id["a"].ok is True
    assert by_id["a"].row_count == 1
    assert by_id["boom"].ok is False


def test_providers_see_the_config_not_each_others_output() -> None:
    seen: list[int] = []

    class Peeker(Provider):
        id = "peek"
        title = "peek"

        def rows(self, context: ProviderContext) -> list[Row]:
            seen.append(len(context.config.rows))
            return []

    config = Config(rows=[row("from-config")])
    collect([Peeker(), Fixed("other", [row("other")])], ProviderContext(config=config))
    assert seen == [1]


def test_a_disabled_provider_is_not_reported_as_a_failure() -> None:
    """Turning a provider off is the user's decision, not a fault. Reporting
    it as one means being told about your own choice on every rebuild."""
    from salon.core.provider import CatalogBuild, ProviderOutcome

    build = CatalogBuild(
        rows=[],
        outcomes=(
            ProviderOutcome("off", "Off", 0, "Turned off", disabled=True),
            ProviderOutcome("bad", "Bad", 0, "RuntimeError: no"),
        ),
    )
    assert [f.provider_id for f in build.failures] == ["bad"]
    by_id = {o.provider_id: o for o in build.outcomes}
    assert by_id["off"].ok is True
    assert by_id["bad"].ok is False
