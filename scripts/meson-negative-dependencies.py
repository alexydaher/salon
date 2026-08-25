#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prove Meson rejects missing and too-old native dependencies."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPENDENCIES = {
    "gtk4": "4.16.0",
    "libadwaita-1": "1.5.0",
    "gio-2.0": "2.80.0",
    "gdk-pixbuf-2.0": "2.42.0",
    "libsoup-3.0": "3.0.0",
    "manette-0.2": "0.2.0",
}


def _pc(name: str, version: str) -> str:
    return f"""prefix=/nonexistent
libdir=${{prefix}}/lib
includedir=${{prefix}}/include
Name: {name}
Description: setup-only fixture for Salon
Version: {version}
Libs:
Cflags:
"""


def _expect_failure(target: str, *, missing: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="salon-meson-negative-") as temporary:
        root = Path(temporary)
        pc_dir = root / "pkgconfig"
        pc_dir.mkdir()
        for name, minimum in DEPENDENCIES.items():
            if missing and name == target:
                continue
            version = "0.0.1" if name == target else minimum
            (pc_dir / f"{name}.pc").write_text(_pc(name, version))
        env = os.environ.copy()
        env["PKG_CONFIG_LIBDIR"] = str(pc_dir)
        result = subprocess.run(
            ["meson", "setup", str(root / "build"), str(ROOT)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr
        if result.returncode == 0 or target not in output:
            kind = "missing" if missing else "too-old"
            raise RuntimeError(f"Meson did not reject {kind} {target}:\n{output}")


def main() -> int:
    for dependency in DEPENDENCIES:
        _expect_failure(dependency, missing=True)
        _expect_failure(dependency, missing=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
