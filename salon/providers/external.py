# SPDX-License-Identifier: GPL-3.0-or-later
"""Loading third-party providers from `$XDG_DATA_HOME/salon/providers/*.py`.

The contract is one function: a module in that directory exposes
`provider()` returning a `salon.core.provider.Provider`. No entry points, no
manifest, no packaging step — dropping a `.py` file in a folder is the whole
install, which is the right weight for "add a row that lists my NAS".

Import is where most third-party code fails, and it fails *before* the
provider ever runs, so it is outside `collect()`'s protection and has to be
guarded separately here. A module that raises on import, has no `provider()`,
or returns something that isn't a `Provider` is reported as a failed
provider rather than being allowed to take the launcher down.

Loading executes arbitrary Python as the user, which is worth being plain
about: this is the same trust level as a file in `~/.local/bin`, not a
sandboxed plugin system. It is a directory the user has to put a file into
deliberately.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from salon.core.provider import Provider

_MODULE_PREFIX = "salon_external_provider_"


def provider_dir() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "salon" / "providers"


@dataclass(frozen=True, slots=True)
class LoadError:
    path: Path
    reason: str

    @property
    def provider_id(self) -> str:
        return self.path.stem


def load_all(directory: Path | None = None) -> tuple[list[Provider], list[LoadError]]:
    """Import every `*.py` in the provider directory. Never raises."""
    target = directory if directory is not None else provider_dir()
    providers: list[Provider] = []
    errors: list[LoadError] = []
    try:
        paths = sorted(p for p in target.glob("*.py") if p.name != "__init__.py")
    except OSError:
        # A missing directory is the normal case, not a problem worth
        # telling the user about.
        return providers, errors

    for path in paths:
        try:
            providers.append(_load_one(path))
        except Exception as exc:  # noqa: BLE001 — a stranger's import must not be fatal
            errors.append(LoadError(path, f"{type(exc).__name__}: {exc}"))
    return providers, errors


def _load_one(path: Path) -> Provider:
    module_name = f"{_MODULE_PREFIX}{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"{path.name} is not importable")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so a module that imports itself, or uses
    # dataclasses/pickle (both of which look the module up by name), works
    # the same as one installed normally.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    factory = getattr(module, "provider", None)
    if not callable(factory):
        raise AttributeError(f"{path.name} has no provider() function")
    instance = factory()
    if not isinstance(instance, Provider):
        raise TypeError(
            f"{path.name}'s provider() returned {type(instance).__name__}, "
            "expected a salon.core.provider.Provider"
        )
    return instance
