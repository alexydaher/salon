# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _minimum_versions() -> dict[str, str]:
    # ConfigParser needs a section; the key-value file intentionally stays
    # directly consumable by Meson's keyval module.
    text = "[minimum]\n" + (ROOT / "build-aux" / "minimum-versions.ini").read_text()
    parser = ConfigParser()
    parser.read_string(text)
    return dict(parser["minimum"])


def test_readme_and_meson_share_the_authoritative_minimums() -> None:
    versions = _minimum_versions()
    readme = (ROOT / "README.md").read_text()
    meson = (ROOT / "meson.build").read_text()
    assert "minimum-versions.ini" in readme
    assert "minimum-versions.ini" in meson
    for version in versions.values():
        assert version in readme


def test_ci_installs_every_native_dependency_family() -> None:
    workflow = (ROOT / ".github" / "workflows" / "checks.yml").read_text()
    for package in (
        "gtk4-devel",
        "libadwaita-devel",
        "glib2-devel",
        "gdk-pixbuf2-devel",
        "libsoup3-devel",
        "libmanette-devel",
        "python3-gobject",
    ):
        assert package in workflow
