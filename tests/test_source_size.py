# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep production modules small enough to retain one clear responsibility."""
from pathlib import Path

SALON_DIR = Path(__file__).resolve().parent.parent / "salon"
MAXIMUM_LINES = 250


def test_production_python_files_do_not_exceed_line_limit() -> None:
    violations = []
    for path in sorted(SALON_DIR.rglob("*.py")):
        line_count = len(path.read_bytes().splitlines())
        if line_count > MAXIMUM_LINES:
            violations.append(f"{path.relative_to(SALON_DIR)}: {line_count} lines")

    assert not violations, "production source line limit exceeded:\n" + "\n".join(violations)
