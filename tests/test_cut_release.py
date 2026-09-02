"""The release notes are written once, so everything derived from them is
generated. These tests cover the derivation, and then run the whole `prepare`
step against a copy of the real files — which is the only way to know the
generated AppStream entry and Debian stanza land where the checker expects.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "cut-release.py"
APP_ID = "io.github.alexydaher.Salon"
NOTES = """\
## 9.9.9 — 2026-12-24

### Added

- A first thing that is long enough to need wrapping when it is rendered into
  a Debian changelog stanza, which wraps at seventy-six columns.
- A second thing.

### Fixed

- A third thing with <angle brackets> & an ampersand.
"""


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("cut_release", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_notes_are_read_as_groups_with_wrapped_bullets_joined() -> None:
    cut = load()
    date, groups = cut.parse_changelog(NOTES, "9.9.9")
    assert date == "2026-12-24"
    assert [name for name, _ in groups] == ["Added", "Fixed"]
    assert groups[0][1][0].endswith("wraps at seventy-six columns.")
    assert "\n" not in groups[0][1][0]
    assert len(groups[0][1]) == 2


def test_a_missing_section_says_what_to_write() -> None:
    cut = load()
    try:
        cut.parse_changelog(NOTES, "1.2.3")
    except cut.ReleaseError as error:
        assert "## 1.2.3 — YYYY-MM-DD" in str(error)
    else:  # pragma: no cover - the call above must raise
        raise AssertionError("a missing section must be an error")


def test_appstream_entry_escapes_and_keeps_the_group_names() -> None:
    cut = load()
    date, groups = cut.parse_changelog(NOTES, "9.9.9")
    entry = cut.appstream_release("9.9.9", date, groups)
    assert entry.startswith('    <release version="9.9.9" date="2026-12-24">')
    assert "<p>Added</p>" in entry and "<p>Fixed</p>" in entry
    assert "&lt;angle brackets&gt; &amp; an ampersand" in entry
    assert entry.rstrip().endswith("</release>")


def test_debian_stanza_wraps_and_carries_the_trailer() -> None:
    cut = load()
    _date, groups = cut.parse_changelog(NOTES, "9.9.9")
    stanza = cut.debian_stanza(
        "9.9.9", groups, "A Maintainer <a@example.invalid>",
        "Thu, 24 Dec 2026 12:00:00 +0100",
    )
    lines = stanza.rstrip("\n").splitlines()
    assert lines[0] == "salon (9.9.9-1) unstable; urgency=medium"
    assert all(len(line) <= 79 for line in lines)
    assert sum(line.startswith("  * ") for line in lines) == 3
    assert lines[-1] == (
        " -- A Maintainer <a@example.invalid>  Thu, 24 Dec 2026 12:00:00 +0100"
    )


def test_the_trailer_date_follows_the_notes_not_the_clock() -> None:
    cut = load()
    stamp = cut.release_timestamp("2026-12-24", datetime(2027, 1, 1, 9, 0))
    assert stamp.startswith("Thu, 24 Dec 2026 12:00:00")


def test_prepare_rewrites_every_version_location(tmp_path: Path) -> None:
    for name in ("meson.build", "pyproject.toml", f"{APP_ID}.yaml", "CHANGELOG.md"):
        shutil.copy(ROOT / name, tmp_path / name)
    for name, target in (
        (Path("data") / f"{APP_ID}.metainfo.xml.in", "data"),
        (Path("debian") / "changelog", "debian"),
        (Path("scripts") / "prepare-flatpak-release.py", "scripts"),
    ):
        (tmp_path / target).mkdir(exist_ok=True)
        shutil.copy(ROOT / name, tmp_path / name)

    previous = (tmp_path / "meson.build").read_text()
    version = "9.9.9"
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        changelog.read_text().replace("## 0.4.2", NOTES + "\n## 0.4.2", 1)
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path),
         "prepare", version, "--no-commit"],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    assert f"version: '{version}'" in (tmp_path / "meson.build").read_text()
    assert previous != (tmp_path / "meson.build").read_text()
    assert f'version = "{version}"' in (tmp_path / "pyproject.toml").read_text()
    manifest = (tmp_path / f"{APP_ID}.yaml").read_text()
    assert f"tag: v{version}" in manifest
    # The libmanette source has a tag too, and it must be left alone.
    assert "tag: '0.2.9'" in manifest
    metainfo = (tmp_path / "data" / f"{APP_ID}.metainfo.xml.in").read_text()
    assert f'<release version="{version}" date="2026-12-24">' in metainfo
    assert f"/salon/v{version}/docs/screenshots/" in metainfo
    assert "/salon/v0.4.2/" not in metainfo
    assert (tmp_path / "debian" / "changelog").read_text().startswith(
        f"salon ({version}-1) unstable; urgency=medium"
    )
    # prepare-flatpak-release.py runs at the end of prepare, over the tree it
    # just rewrote; its own line in stdout is the proof that it agreed.
    assert f"Release metadata agrees on Salon {version}" in result.stdout
    assert f"Prepared Salon {version}, dated 2026-12-24" in result.stdout


def test_prepare_refuses_a_version_the_notes_do_not_cover(tmp_path: Path) -> None:
    for name in ("meson.build", "CHANGELOG.md"):
        shutil.copy(ROOT / name, tmp_path / name)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path),
         "prepare", "9.9.9", "--no-commit"],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "CHANGELOG.md has no section for 9.9.9" in result.stderr
