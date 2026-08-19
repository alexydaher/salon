# SPDX-License-Identifier: GPL-3.0-or-later
"""The provider contract and the runner that isolates providers from each
other (§6.10). Pure — no gi, so the whole thing is testable headlessly.

A provider answers one question: "what rows do you contribute?". Everything
else here exists because a provider may be third-party code dropped into
`$XDG_DATA_HOME/salon/providers/`, and a launcher that a stranger's Python
file can hang or crash is not a launcher.

So `collect()` gives every provider its own thread and one shared deadline,
and treats a raise, a timeout and a malformed return the same way: that
provider contributes nothing, a `ProviderFailure` is recorded against its
name, and the rest of the catalogue is built as if it had never been there.
The failures are returned rather than logged and dropped, because the user
needs somewhere to see *why* their row vanished — Settings shows them.

A thread that never finishes cannot be killed in Python. Provider threads
are daemons and their late results are discarded, so a hung provider costs
one leaked thread until exit rather than a launcher that won't start or
won't quit.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from salon.core.config import Config
from salon.core.model import Row

# §6.10: a provider gets three seconds to answer. Long enough for a network
# round trip that's actually working, short enough that a dead one doesn't
# hold the home screen hostage.
DEFAULT_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class ProviderContext:
    """Everything a provider is given. Deliberately small.

    Providers read the user's catalogue rather than each other's output:
    the recents row resolves tile ids against `config`, not against rows the
    static provider happened to emit. That keeps them genuinely independent,
    which is the only reason running them in parallel is sound.
    """

    config: Config


class Provider(ABC):
    """One source of rows.

    `priority` orders the finished catalogue, lowest first; ties keep
    registration order. It is not an execution order — providers run
    concurrently and must not depend on one another.
    """

    id: str = "provider"
    title: str = "Provider"
    priority: int = 100

    @abstractmethod
    def rows(self, context: ProviderContext) -> list[Row]:
        """Return this provider's rows. May raise; may block up to the
        collection timeout. Called off the main thread."""


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    provider_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    """What one provider actually did, for Settings to display."""

    provider_id: str
    title: str
    row_count: int
    failure: str | None = None
    # A provider the user switched off is *not* a failure. It still needs an
    # outcome so Settings can account for it, but reporting it as one means
    # the user gets told about their own decision every time the catalogue
    # rebuilds.
    disabled: bool = False

    @property
    def ok(self) -> bool:
        return self.failure is None or self.disabled


@dataclass(frozen=True, slots=True)
class CatalogBuild:
    rows: list[Row] = field(default_factory=list)
    outcomes: tuple[ProviderOutcome, ...] = ()

    @property
    def failures(self) -> tuple[ProviderFailure, ...]:
        return tuple(
            ProviderFailure(o.provider_id, o.failure)
            for o in self.outcomes
            if o.failure is not None and not o.disabled
        )


def _validate(rows: object) -> list[Row]:
    """A third-party provider can return anything at all, including None or
    a list with a string in it. Reject the whole return rather than letting
    it reach the widget layer, where the failure would surface as a
    traceback in a snapshot callback with no hint of which provider caused
    it."""
    if not isinstance(rows, list):
        raise TypeError(f"rows() returned {type(rows).__name__}, expected list[Row]")
    for row in rows:
        if not isinstance(row, Row):
            raise TypeError(f"rows() returned a list containing {type(row).__name__}")
    return rows


def collect(
    providers: Sequence[Provider],
    context: ProviderContext,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> CatalogBuild:
    """Run every provider concurrently under one shared deadline.

    One deadline for all of them, not one each: three providers with a 3s
    timeout apiece would be a 9s worst case, and the user is looking at an
    empty screen for every one of those seconds.
    """
    results: dict[str, list[Row]] = {}
    errors: dict[str, str] = {}
    lock = threading.Lock()

    def run(provider: Provider) -> None:
        try:
            rows = _validate(provider.rows(context))
        except Exception as exc:  # noqa: BLE001 — isolation is the whole point
            with lock:
                errors[provider.id] = f"{type(exc).__name__}: {exc}"
            return
        with lock:
            results[provider.id] = rows

    threads = [
        (
            provider,
            threading.Thread(
                target=run,
                args=(provider,),
                name=f"salon-provider-{provider.id}",
                daemon=True,
            ),
        )
        for provider in providers
    ]
    for _, thread in threads:
        thread.start()

    deadline = clock() + timeout_seconds
    for _, thread in threads:
        thread.join(max(0.0, deadline - clock()))

    ordered = sorted(enumerate(providers), key=lambda pair: (pair[1].priority, pair[0]))
    rows: list[Row] = []
    outcomes: list[ProviderOutcome] = []
    seen_row_ids: set[str] = set()
    for _, provider in ordered:
        with lock:
            produced = results.get(provider.id)
            error = errors.get(provider.id)
        if error is not None:
            outcomes.append(ProviderOutcome(provider.id, provider.title, 0, error))
            continue
        if produced is None:
            outcomes.append(
                ProviderOutcome(
                    provider.id,
                    provider.title,
                    0,
                    f"Took longer than {timeout_seconds:g}s and was skipped",
                )
            )
            continue
        # Row ids are catalogue-wide unique (Catalog enforces it). A clash
        # is the later provider's problem, not a reason to fail the build:
        # dropping the row and saying so beats a blank home screen.
        kept = []
        clashes = []
        for row in produced:
            if row.id in seen_row_ids:
                clashes.append(row.id)
                continue
            seen_row_ids.add(row.id)
            kept.append(row)
        rows.extend(kept)
        failure = None
        if clashes:
            joined = ", ".join(sorted(set(clashes)))
            failure = f"Row id already used by another provider: {joined}"
        outcomes.append(ProviderOutcome(provider.id, provider.title, len(kept), failure))

    return CatalogBuild(rows=rows, outcomes=tuple(outcomes))
