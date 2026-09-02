"""Every relative link in the README must point at a file that is *tracked*.

Checking that the target exists on disk is the check that fails to catch
this: `docs/sessions.md` and `docs/development.md` existed on the maintainer's
machine for months while `docs/` was gitignored, so four README links —
including step one of the Kiosk instructions — were 404 for everyone reading
it on GitHub, and nothing anywhere said so.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# [text](target) and [label]: target, minus anything absolute or an anchor.
INLINE = re.compile(r"\[[^\]]*\]\((?!https?://|#)([^)#\s]+)")
REFERENCE = re.compile(r"^\[[^\]]+\]:\s+(?!https?://|#)(\S+)", re.MULTILINE)


def tracked_files() -> set[str]:
    listing = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if listing.returncode != 0:
        pytest.skip("not a git checkout, so 'tracked' has no meaning here")
    return set(listing.stdout.split())


def test_every_relative_readme_link_is_a_tracked_file() -> None:
    readme = (ROOT / "README.md").read_text()
    targets = set(INLINE.findall(readme)) | set(REFERENCE.findall(readme))
    assert targets, "the README has no relative links; this test has stopped working"

    tracked = tracked_files()
    missing = sorted(target for target in targets if target not in tracked)
    assert not missing, (
        "README links to files that are not in the repository, so they are "
        f"404 for anyone reading it on GitHub: {missing}"
    )
