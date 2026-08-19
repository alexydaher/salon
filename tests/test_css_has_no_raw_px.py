# SPDX-License-Identifier: GPL-3.0-or-later
"""§10's stylesheet gate: salon.css never contains a raw px value.

Every size in Salon is a design unit resolved against the monitor's height
at runtime by ui/scale.py (§7.2). A literal px in the stylesheet is a size
that silently stays the same on a 4K TV as on a 1080p one, which is exactly
the failure the du pipeline exists to prevent — and it's invisible until
someone runs the launcher on the other screen.
"""

from __future__ import annotations

import re
from pathlib import Path

STYLESHEET = Path(__file__).resolve().parent.parent / "data" / "style" / "salon.css"

_COMMENTS = re.compile(r"/\*.*?\*/", re.DOTALL)
_RAW_PX = re.compile(r"(?<![\w-])\d+(?:\.\d+)?px")


def test_salon_css_uses_no_raw_px() -> None:
    source = _COMMENTS.sub("", STYLESHEET.read_text(encoding="utf-8"))
    offenders = sorted(set(_RAW_PX.findall(source)))
    assert not offenders, (
        f"salon.css must size everything through var(--…) from ui/scale.py; "
        f"found raw px values: {offenders}"
    )


def test_salon_css_actually_uses_the_custom_properties() -> None:
    """Guards against the gate above being satisfied by removing sizes
    altogether rather than by routing them through the scale pipeline."""
    source = STYLESHEET.read_text(encoding="utf-8")
    assert "var(--font-row-heading)" in source
    assert "var(--radius)" in source
