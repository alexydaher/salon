# SPDX-License-Identifier: GPL-3.0-or-later
"""Nothing outside the application may write the user's GSettings.

The harnesses — the screenshot capture, the UX audit, the Wayland smoke
test — all run the *real* `SalonApplication` against the *real* schema, and
they all set a few keys first to get a predictable screen. Each of them
redirects `XDG_CONFIG_HOME` into a temporary tree and each of them was wrong
to think that isolated anything: a dconf write is a D-Bus call to the writer
daemon, which resolves the user database from its own environment, so the
value lands in the live session while the read comes back out of the empty
temporary copy. Nothing fails, nothing is logged, and the keys stay changed
after the run.

It cost a real feature. `remote-hint=false` was left behind by a screenshot
run, which is the setting the corner pairing card is gated on — so the one
thing Salon shows when there is no controller and no phone silently stopped
appearing on the machine it was developed on, and `animation-scale=0.0`,
`fetch-site-icons=false` and `onboarding-complete=true` were sitting in the
same database as evidence.

The rule is therefore mechanical: a file that builds a `Gio.Settings` and is
not part of the application pins the memory backend, before `gi.repository`
is imported, which is when the backend is chosen.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN = 'os.environ["GSETTINGS_BACKEND"] = "memory"'


def _harness_sources() -> list[Path]:
    """Every Python file we ship that is a harness rather than the app."""
    return sorted(
        path
        for directory in ("scripts", "tests")
        for path in (ROOT / directory).glob("*.py")
        if path.name != Path(__file__).name
    )


def test_harnesses_that_write_settings_pin_the_memory_backend() -> None:
    for path in _harness_sources():
        source = path.read_text(encoding="utf-8")
        if "Gio.Settings.new" not in source:
            continue
        assert PIN in source, (
            f"{path.relative_to(ROOT)} builds a Gio.Settings without pinning the memory "
            "backend, so its writes land in the user's own dconf"
        )
        lines = source.splitlines()
        pinned_at = next(index for index, line in enumerate(lines) if PIN in line)
        imported_at = next(
            (index for index, line in enumerate(lines) if "from gi.repository import" in line),
            len(lines),
        )
        assert pinned_at < imported_at, (
            f"{path.relative_to(ROOT)} pins the memory backend after importing gi.repository; "
            "the backend is chosen at import time, so the pin arrives too late"
        )


def test_setdefault_is_not_enough() -> None:
    """`setdefault` honours an inherited GSETTINGS_BACKEND, which is exactly
    the value a developer's shell or a CI image is entitled to set — and
    honouring it here means putting dconf back underneath the harness."""
    for path in _harness_sources():
        source = path.read_text(encoding="utf-8")
        assert 'setdefault("GSETTINGS_BACKEND"' not in source, (
            f"{path.relative_to(ROOT)} sets the backend with setdefault; assign it instead"
        )
