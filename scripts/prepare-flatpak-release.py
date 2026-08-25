#!/usr/bin/env python3
"""Check release versions and optionally write a commit-pinned manifest."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

APP_ID = "io.github.alexydaher.Salon"
SOURCE_URL = "https://github.com/alexydaher/salon.git"
COMMIT_RE = re.compile(r"[0-9a-f]{40}")


def fail(message: str) -> None:
    raise ValueError(message)


def match_one(pattern: str, text: str, label: str) -> str:
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if len(matches) != 1:
        fail(f"expected one {label}, found {len(matches)}")
    return matches[0]


def salon_source_lines(manifest: str) -> tuple[list[str], int, int]:
    lines = manifest.splitlines(keepends=True)
    url_indexes = [index for index, line in enumerate(lines) if SOURCE_URL in line]
    if len(url_indexes) != 1:
        fail(f"expected one Salon git source, found {len(url_indexes)}")

    url_index = url_indexes[0]
    tag_index = next(
        (index for index in range(url_index + 1, min(url_index + 8, len(lines)))
         if re.match(r"\s+tag:\s*", lines[index])),
        -1,
    )
    if tag_index < 0:
        fail("Salon git source has no tag")
    return lines, url_index, tag_index


def checked_version(root: Path, requested_tag: str | None) -> tuple[str, str]:
    meson = (root / "meson.build").read_text()
    pyproject = tomllib.loads((root / "pyproject.toml").read_text())
    metainfo_path = root / "data" / f"{APP_ID}.metainfo.xml.in"
    metainfo_text = metainfo_path.read_text()
    manifest = (root / f"{APP_ID}.yaml").read_text()
    changelog = (root / "CHANGELOG.md").read_text()
    debian_changelog = (root / "debian" / "changelog").read_text()

    meson_version = match_one(r"^\s*version:\s*'([^']+)'", meson, "Meson version")
    python_version = str(pyproject["project"]["version"])
    releases = ET.fromstring(metainfo_text).find("releases")
    if releases is None or len(releases) == 0:
        fail("AppStream metadata has no releases")
    appstream_version = releases[0].attrib.get("version", "")

    lines, _url_index, tag_index = salon_source_lines(manifest)
    manifest_tag = lines[tag_index].split(":", 1)[1].strip().strip("'\"")
    version = meson_version
    expected_tag = f"v{version}"
    values = {
        "pyproject.toml": python_version,
        "latest AppStream release": appstream_version,
        "Debian package": match_one(
            r"\Asalon \(([^)-]+)(?:-[^)]+)?\)",
            debian_changelog,
            "Debian package version",
        ),
    }
    for label, value in values.items():
        if value != version:
            fail(f"{label} is {value!r}; expected {version!r}")
    if manifest_tag != expected_tag:
        fail(f"manifest tag is {manifest_tag!r}; expected {expected_tag!r}")
    if requested_tag is not None and requested_tag != expected_tag:
        fail(f"pushed tag is {requested_tag!r}; expected {expected_tag!r}")
    if not re.search(rf"^## {re.escape(version)}(?:\s|$)", changelog, re.MULTILINE):
        fail(f"CHANGELOG.md has no {version} release heading")

    screenshot_pattern = r"raw\.githubusercontent\.com/alexydaher/salon/(v[^/]+)/"
    screenshot_tags = set(re.findall(screenshot_pattern, metainfo_text))
    if screenshot_tags != {expected_tag}:
        fail(
            f"AppStream screenshot tags are {sorted(screenshot_tags)!r}; "
            f"expected [{expected_tag!r}]"
        )
    return version, manifest


def write_pinned_manifest(root: Path, manifest: str, commit: str, output: Path) -> None:
    if not COMMIT_RE.fullmatch(commit):
        fail("--commit must be a lowercase 40-character Git commit hash")
    source = (root / f"{APP_ID}.yaml").resolve()
    destination = output.resolve()
    if destination == source:
        fail("refusing to overwrite the source manifest")

    lines, _url_index, tag_index = salon_source_lines(manifest)
    indent = lines[tag_index][: len(lines[tag_index]) - len(lines[tag_index].lstrip())]
    commit_line = f"{indent}commit: {commit}\n"
    following = tag_index + 1
    if following < len(lines) and re.match(r"\s+commit:\s*", lines[following]):
        lines[following] = commit_line
    else:
        lines.insert(following, commit_line)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="release tag received from GitHub")
    parser.add_argument("--commit", help="commit to pin in the prepared Flathub manifest")
    parser.add_argument("--output", type=Path, help="path for the prepared manifest")
    args = parser.parse_args()

    if (args.commit is None) != (args.output is None):
        parser.error("--commit and --output must be used together")

    root = Path(__file__).resolve().parent.parent
    try:
        version, manifest = checked_version(root, args.tag)
        if args.commit is not None and args.output is not None:
            write_pinned_manifest(root, manifest, args.commit, args.output)
            print(f"Prepared {args.output} for Salon {version} at {args.commit}")
        else:
            print(f"Release metadata agrees on Salon {version}")
    except (KeyError, OSError, ET.ParseError, ValueError) as error:
        print(f"release preparation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
