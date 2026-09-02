"""Every relative link in the README must point at a file that is published.

`docs/sessions.md` and `docs/development.md` existed on the maintainer's
machine for months while `docs/` was gitignored, so four README links —
including step one of the Kiosk instructions — were 404 for everyone reading
it on GitHub, and nothing anywhere said so.

"Published" is asked two ways, because neither works everywhere. Given a git
checkout, it means tracked: on the machine where the mistake is made, the
file is sitting right there on disk and only git knows it is not in the
repository. CI's gates run in a container with no git, so actions/checkout
downloads a tarball through the REST API — and a tarball contains nothing but
tracked files, which makes plain existence the same question. Neither mode is
a skip; the check is real in both places.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# [text](target) and [label]: target, minus anything absolute or an anchor.
INLINE = re.compile(r"\[[^\]]*\]\((?!https?://|#)([^)#\s]+)")
REFERENCE = re.compile(r"^\[[^\]]+\]:\s+(?!https?://|#)(\S+)", re.MULTILINE)


def tracked_files() -> set[str] | None:
    """Tracked paths, or None where that cannot be asked."""

    if not (ROOT / ".git").exists():
        return None
    try:
        listing = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
        )
    except (FileNotFoundError, OSError):
        return None
    return set(listing.stdout.split()) if listing.returncode == 0 else None


def unpublished(targets: set[str], tracked: set[str] | None) -> list[str]:
    if tracked is None:
        return sorted(target for target in targets if not (ROOT / target).exists())
    return sorted(target for target in targets if target not in tracked)


def readme_targets() -> set[str]:
    readme = (ROOT / "README.md").read_text()
    return set(INLINE.findall(readme)) | set(REFERENCE.findall(readme))


def test_every_relative_readme_link_is_published() -> None:
    targets = readme_targets()
    assert targets, "the README has no relative links; this test has stopped working"

    missing = unpublished(targets, tracked_files())
    assert not missing, (
        "README links to files that are not in the repository, so they are "
        f"404 for anyone reading it on GitHub: {missing}"
    )


def test_both_modes_reject_a_file_that_is_only_on_this_machine() -> None:
    # LICENSE is tracked; .gitignore's own target docs/ is not published, and
    # docs/publishing.md is on this machine — which is the case that has to
    # fail in the git mode and cannot even arise in the tarball one.
    assert unpublished({"LICENSE"}, {"LICENSE"}) == []
    assert unpublished({"docs/publishing.md"}, {"LICENSE"}) == ["docs/publishing.md"]
    assert unpublished({"no/such/file.md"}, None) == ["no/such/file.md"]
    assert unpublished({"LICENSE"}, None) == []
