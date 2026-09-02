#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cut a Salon release.

Two subcommands, in the order they are used:

    scripts/cut-release.py prepare 0.4.3
    scripts/cut-release.py publish

`prepare` takes the release notes the human wrote in CHANGELOG.md and
writes every other version location from them: meson.build, pyproject.toml,
the Flatpak manifest's tag, the AppStream screenshot tags and release entry,
and a debian/changelog stanza. Those notes used to be typed three times in
three formats, and nothing checked that the three agreed — the version
*numbers* are cross-checked by prepare-flatpak-release.py, the prose was
checked by nobody.

`publish` runs the gates, pushes main, waits for that push to go green, and
only then applies and pushes the tag. That order is the whole point: the tag
is immutable and the run it starts publishes to people's machines, so it may
only ever land on a commit CI has already passed. Remembering to do it in
that order has failed twice — v0.3.0 was moved off a red commit, and nothing
tested main between 0.3.2 and 0.4.0.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import subprocess
import sys
import textwrap
import time
from datetime import UTC, datetime
from pathlib import Path

APP_ID = "io.github.alexydaher.Salon"
DEFAULT_BRANCH = "main"
VERSION_RE = re.compile(r"\A\d+\.\d+\.\d+\Z")
# The heading the notes live under, with the date this release is dated by.
# One date, read from here, so the AppStream entry and the Debian stanza
# cannot drift from the changelog or from each other.
HEADING_RE_TEMPLATE = r"^## {version}\s+[—-]\s+(\d{{4}}-\d{{2}}-\d{{2}})\s*$"


class ReleaseError(Exception):
    """Anything that should stop the release with a sentence, not a traceback."""


def load_checker(root: Path):
    """Import prepare-flatpak-release.py, whose filename is not importable."""

    path = root / "scripts" / "prepare-flatpak-release.py"
    spec = importlib.util.spec_from_file_location("prepare_flatpak_release", path)
    if spec is None or spec.loader is None:  # pragma: no cover - unreachable
        raise ReleaseError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- reading the notes -----------------------------------------------------


def parse_changelog(text: str, version: str) -> tuple[str, list[tuple[str, list[str]]]]:
    """Return the release date and the (group, bullets) pairs for `version`."""

    heading = re.compile(HEADING_RE_TEMPLATE.format(version=re.escape(version)), re.M)
    found = heading.search(text)
    if found is None:
        raise ReleaseError(
            f"CHANGELOG.md has no section for {version}. Write the notes first, "
            f"under a heading like:\n\n    ## {version} — YYYY-MM-DD\n"
        )
    date = found.group(1)
    rest = text[found.end() :]
    end = re.search(r"^## ", rest, re.M)
    body = rest[: end.start()] if end else rest

    groups: list[tuple[str, list[str]]] = []
    bullets: list[str] = []
    for line in body.splitlines():
        if line.startswith("### "):
            groups.append((line[4:].strip(), bullets := []))
        elif line.startswith("- "):
            if not groups:
                groups.append(("", bullets := []))
            bullets.append(line[2:].strip())
        elif line.strip() and bullets and line.startswith((" ", "\t")):
            # A wrapped bullet. Joined back into one sentence, because both
            # output formats do their own wrapping at their own width.
            bullets[-1] += " " + line.strip()
        elif line.strip() and not line.startswith("#"):
            # Deliberately strict: the notes are the source every other format
            # is generated from, so a stray paragraph would be silently lost
            # from the AppStream entry and the Debian stanza rather than
            # rendered somewhere sensible.
            raise ReleaseError(
                f"the {version} notes take '### Group' headings and '- ' bullets "
                f"only; found: {line.strip()!r}"
            )

    groups = [(name, items) for name, items in groups if items]
    if not groups:
        raise ReleaseError(f"the {version} section of CHANGELOG.md has no bullets")
    return date, groups


# --- writing the other formats ---------------------------------------------


def appstream_release(version: str, date: str, groups: list[tuple[str, list[str]]]) -> str:
    """Render one <release> entry. Each list is introduced by its group name,
    so that a software centre shows the same distinction the changelog makes."""

    lines = [f'    <release version="{version}" date="{date}">', "      <description>"]
    for name, items in groups:
        if name:
            lines.append(f"        <p>{html.escape(name)}</p>")
        lines.append("        <ul>")
        for item in items:
            wrapped = textwrap.wrap(
                html.escape(item), width=76, initial_indent="", subsequent_indent=""
            )
            body = "\n            ".join(wrapped)
            lines.append(f"          <li>{body}</li>")
        lines.append("        </ul>")
    lines += ["      </description>", "    </release>"]
    return "\n".join(lines) + "\n"


def debian_stanza(
    version: str, groups: list[tuple[str, list[str]]], maintainer: str, stamp: str
) -> str:
    lines = [f"salon ({version}-1) unstable; urgency=medium", ""]
    for _name, items in groups:
        for item in items:
            lines += textwrap.wrap(
                item, width=76, initial_indent="  * ", subsequent_indent="    "
            )
    lines += ["", f" -- {maintainer}  {stamp}", ""]
    return "\n".join(lines) + "\n"


def release_timestamp(date: str, now: datetime) -> str:
    """RFC 2822 for the Debian trailer: the real clock on the day the notes
    are dated, noon otherwise, always with this machine's offset."""

    local = now.astimezone()
    if local.strftime("%Y-%m-%d") != date:
        local = datetime.fromisoformat(f"{date}T12:00:00").astimezone()
    return local.strftime("%a, %d %b %Y %H:%M:%S %z")


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, flags=re.M)
    if count != 1:
        raise ReleaseError(f"expected one {label} to update, found {count}")
    return updated


def bump_metainfo(text: str, version: str, previous: str, entry: str) -> str:
    old, new = f"/salon/v{previous}/", f"/salon/v{version}/"
    if old not in text:
        raise ReleaseError(f"no screenshot URLs pinned to v{previous}")
    text = text.replace(old, new)
    if f'<release version="{version}"' in text:
        raise ReleaseError(f"the AppStream metadata already has a {version} release")
    # Inserted above the newest existing entry rather than substituted, because
    # every release in the file matches the same pattern and the list is
    # ordered newest first.
    newest = re.search(r"^    <release version=", text, re.M)
    if newest is None:
        raise ReleaseError("the AppStream metadata has no releases to insert above")
    return text[: newest.start()] + entry + text[newest.start() :]


def maintainer_of(changelog: str) -> str:
    found = re.search(r"^ -- (.+?)  ", changelog, re.M)
    if found is None:
        raise ReleaseError("debian/changelog has no maintainer trailer to copy")
    return found.group(1)


# --- the two commands ------------------------------------------------------


def run(command: list[str], root: Path, capture: bool = False) -> str:
    result = subprocess.run(
        command, cwd=root, text=True, check=False,
        stdout=subprocess.PIPE if capture else None,
    )
    if result.returncode != 0:
        raise ReleaseError(f"{' '.join(command)} failed with {result.returncode}")
    return (result.stdout or "").strip()


def project_version(root: Path) -> str:
    meson = (root / "meson.build").read_text()
    found = re.search(r"^\s*version: '([^']+)'", meson, re.M)
    if found is None:
        raise ReleaseError("meson.build has no version")
    return found.group(1)


def prepare(root: Path, version: str, commit: bool) -> None:
    if not VERSION_RE.match(version):
        raise ReleaseError(f"{version!r} is not a three-part version")
    previous = project_version(root)
    if previous == version:
        raise ReleaseError(f"the project is already on {version}")

    changelog = (root / "CHANGELOG.md").read_text()
    date, groups = parse_changelog(changelog, version)
    debian_path = root / "debian" / "changelog"
    debian = debian_path.read_text()
    metainfo_path = root / "data" / f"{APP_ID}.metainfo.xml.in"

    edits: dict[Path, str] = {
        root / "meson.build": replace_once(
            (root / "meson.build").read_text(),
            rf"^(\s*version: ')({re.escape(previous)})(',)",
            rf"\g<1>{version}\g<3>",
            "Meson version",
        ),
        root / "pyproject.toml": replace_once(
            (root / "pyproject.toml").read_text(),
            rf'^version = "{re.escape(previous)}"',
            f'version = "{version}"',
            "pyproject version",
        ),
        metainfo_path: bump_metainfo(
            metainfo_path.read_text(), version, previous,
            appstream_release(version, date, groups),
        ),
        debian_path: debian_stanza(
            version, groups, maintainer_of(debian),
            release_timestamp(date, datetime.now()),
        ) + debian,
    }

    # The Salon source's tag, found the way the checker finds it, so the two
    # cannot disagree about which of the manifest's tags is Salon's.
    checker = load_checker(root)
    manifest_path = root / f"{APP_ID}.yaml"
    lines, _url, tag_index = checker.salon_source_lines(manifest_path.read_text())
    indent = lines[tag_index][: len(lines[tag_index]) - len(lines[tag_index].lstrip())]
    lines[tag_index] = f"{indent}tag: v{version}\n"
    edits[manifest_path] = "".join(lines)

    for path, text in edits.items():
        path.write_text(text)

    run([sys.executable, "scripts/prepare-flatpak-release.py", "--require-changelog"], root)
    print(f"Prepared Salon {version}, dated {date}:")
    for path in edits:
        print(f"  {path.relative_to(root)}")

    if commit:
        body = "\n".join(f"* {item}" for _name, items in groups for item in items)
        run(["git", "add", *[str(p.relative_to(root)) for p in edits]], root)
        run(["git", "commit", "-m", f"Release {version}", "-m", body], root)
        print("\nCommitted. Review it, then: scripts/cut-release.py publish")


def wait_for_run(root: Path, sha: str, ref: str, since: datetime, timeout: int = 180) -> str:
    """The run id GitHub started for this push, once it exists.

    Matched on the ref as well as the commit, and on having been created
    after the push: the branch push and the tag push carry the *same* commit,
    so a run identified by SHA alone would find the already-finished branch
    run when asked for the tag's — and `gh run watch --exit-status` on a run
    that has already succeeded returns 0 at once, silently skipping the wait
    that is the entire point. For a tag push, headBranch is the tag name.
    """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        listed = run(
            ["gh", "run", "list", "--limit", "20", "--json",
             "databaseId,headSha,headBranch,event,createdAt"],
            root, capture=True,
        )
        for entry in json.loads(listed):
            created = datetime.fromisoformat(entry["createdAt"].replace("Z", "+00:00"))
            if (
                entry["headSha"] == sha
                and entry["headBranch"] == ref
                and entry["event"] == "push"
                and created >= since
            ):
                return str(entry["databaseId"])
        time.sleep(5)
    raise ReleaseError(f"no workflow run appeared for {ref} at {sha[:7]} within {timeout}s")


def publish(root: Path, branch: str, skip_checks: bool) -> None:
    if run(["git", "status", "--porcelain"], root, capture=True):
        raise ReleaseError("the working tree has uncommitted changes")
    current = run(["git", "branch", "--show-current"], root, capture=True)
    if current != branch:
        raise ReleaseError(f"on branch {current!r}, expected {branch!r}")

    version = project_version(root)
    tag = f"v{version}"
    run([sys.executable, "scripts/prepare-flatpak-release.py", "--tag", tag,
         "--require-changelog"], root)
    if run(["git", "tag", "--list", tag], root, capture=True):
        raise ReleaseError(f"{tag} already exists locally")
    if run(["git", "ls-remote", "--tags", "origin", tag], root, capture=True):
        raise ReleaseError(f"{tag} already exists on origin; release tags cannot move")

    if not skip_checks:
        run(["scripts/check.sh"], root)

    pushed_at = datetime.now(UTC)
    run(["git", "push", "origin", branch], root)
    sha = run(["git", "rev-parse", "HEAD"], root, capture=True)
    print(f"Pushed {branch} at {sha[:7]}; waiting for the gates.")
    run(["gh", "run", "watch", wait_for_run(root, sha, branch, pushed_at),
         "--exit-status", "--interval", "20"], root)

    # Only now. Everything above this line can be repeated; nothing below it
    # can be taken back.
    tagged_at = datetime.now(UTC)
    run(["git", "tag", "-a", tag, "-m", f"Salon {version}"], root)
    run(["git", "push", "origin", tag], root)
    print(f"\nTagged {tag} at {sha[:7]}. Watching the release run.")
    run(["gh", "run", "watch", wait_for_run(root, sha, tag, tagged_at),
         "--exit-status", "--interval", "30"], root)
    print(f"\nSalon {version} is published.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    sub = parser.add_subparsers(dest="command", required=True)

    prepared = sub.add_parser("prepare", help="bump every version location")
    prepared.add_argument("version")
    prepared.add_argument("--no-commit", action="store_true")

    published = sub.add_parser("publish", help="gate, push, wait, tag")
    published.add_argument("--branch", default=DEFAULT_BRANCH)
    published.add_argument("--skip-checks", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.root, args.version, commit=not args.no_commit)
        else:
            publish(args.root, args.branch, args.skip_checks)
    except (ReleaseError, OSError, json.JSONDecodeError) as error:
        print(f"release failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
