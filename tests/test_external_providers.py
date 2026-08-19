# SPDX-License-Identifier: GPL-3.0-or-later
"""Loading third-party providers from a folder (§6.10).

Import is outside `collect()`'s protection — it happens before the provider
exists — so it needs its own guard, and these tests are mostly about the
ways a stranger's file can be wrong.
"""

from __future__ import annotations

from pathlib import Path

from salon.core.provider import Provider
from salon.providers.external import load_all

GOOD = '''
from salon.core.model import Row
from salon.core.provider import Provider


class Mine(Provider):
    id = "mine"
    title = "Mine"
    priority = 42

    def rows(self, context):
        return [Row(id="mine", title="Mine", tiles=[], provider_id="mine")]


def provider():
    return Mine()
'''

RAISES_ON_IMPORT = "raise RuntimeError('boom at import time')\n"

NO_FACTORY = "x = 1\n"

WRONG_TYPE = "def provider():\n    return 'not a provider'\n"


def write(directory: Path, name: str, body: str) -> None:
    (directory / name).write_text(body)


def test_loads_a_well_formed_provider(tmp_path: Path) -> None:
    write(tmp_path, "mine.py", GOOD)
    providers, errors = load_all(tmp_path)
    assert errors == []
    assert len(providers) == 1
    assert isinstance(providers[0], Provider)
    assert providers[0].priority == 42


def test_a_missing_directory_is_not_an_error(tmp_path: Path) -> None:
    providers, errors = load_all(tmp_path / "nope")
    assert providers == []
    assert errors == []


def test_a_module_that_raises_on_import_is_reported_not_raised(tmp_path: Path) -> None:
    write(tmp_path, "bad.py", RAISES_ON_IMPORT)
    write(tmp_path, "mine.py", GOOD)
    providers, errors = load_all(tmp_path)
    assert [p.id for p in providers] == ["mine"]
    assert [e.provider_id for e in errors] == ["bad"]
    assert "boom at import time" in errors[0].reason


def test_a_module_without_a_factory_is_reported(tmp_path: Path) -> None:
    write(tmp_path, "empty.py", NO_FACTORY)
    providers, errors = load_all(tmp_path)
    assert providers == []
    assert "no provider() function" in errors[0].reason


def test_a_factory_returning_the_wrong_type_is_reported(tmp_path: Path) -> None:
    write(tmp_path, "wrong.py", WRONG_TYPE)
    providers, errors = load_all(tmp_path)
    assert providers == []
    assert "expected a salon.core.provider.Provider" in errors[0].reason


def test_a_failed_import_does_not_linger_in_sys_modules(tmp_path: Path) -> None:
    import sys

    write(tmp_path, "bad.py", RAISES_ON_IMPORT)
    load_all(tmp_path)
    assert not [name for name in sys.modules if name.endswith("_provider_bad")]


def test_dunder_init_is_skipped(tmp_path: Path) -> None:
    write(tmp_path, "__init__.py", RAISES_ON_IMPORT)
    write(tmp_path, "mine.py", GOOD)
    providers, errors = load_all(tmp_path)
    assert [p.id for p in providers] == ["mine"]
    assert errors == []
