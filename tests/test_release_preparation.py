from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "prepare-flatpak-release.py"


def run_script(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_versions_are_consistent() -> None:
    result = run_script()
    assert result.returncode == 0, result.stderr
    assert "Salon 0.2.3" in result.stdout


def test_debian_changelog_matches_project_version() -> None:
    changelog = (ROOT / "debian" / "changelog").read_text()
    assert changelog.startswith("salon (0.2.3-1) ")


def test_release_tag_must_match_project_version() -> None:
    result = run_script("--tag", "v9.9.9")
    assert result.returncode == 1
    assert "expected 'v0.2.3'" in result.stderr


def test_prepared_manifest_pins_the_release_commit(tmp_path: Path) -> None:
    output = tmp_path / "manifest.yaml"
    commit = "0123456789abcdef0123456789abcdef01234567"
    result = run_script(
        "--tag", "v0.2.3", "--commit", commit, "--output", str(output)
    )
    assert result.returncode == 0, result.stderr

    manifest = output.read_text()
    source = "url: https://github.com/alexydaher/salon.git"
    salon_source = manifest[manifest.index(source) :]
    assert f"tag: v0.2.3\n        commit: {commit}\n" in salon_source
