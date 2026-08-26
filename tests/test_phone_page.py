# SPDX-License-Identifier: GPL-3.0-or-later
"""The remote's page is many files now, and nothing else notices if one goes.

Splitting a 1900-line document into a shell, four stylesheets and twenty ES
modules bought editability at the cost of a new failure mode: a file that
exists on disk, is imported by another module, and is not in the GResource
bundle. An installed Salon then serves a 404 for it and the page dies with
a blank screen and a console message nobody on a phone can read.

These are pure text assertions on the source tree — no browser, no server —
because that is exactly the class of mistake they have to catch.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
REMOTE = ROOT / "data" / "remote"
PAGE = REMOTE / "index.html"
UI = REMOTE / "ui"

# The same ceiling the Python is held to, for the same reason. The page was
# one file until it was too big to edit; the modules replacing it do not get
# to grow back into that.
MAXIMUM_LINES = 300


def _bundled() -> set[str]:
    """Every path listed in the GResource manifest."""
    tree = ElementTree.parse(ROOT / "data" / "salon.gresource.xml")
    return {(node.text or "").strip() for node in tree.iter("file")}


def test_every_asset_the_page_asks_for_is_in_the_bundle() -> None:
    page = PAGE.read_text()
    referenced = set(re.findall(r'(?:href|src)="/ui/([a-z0-9_.-]+)"', page))
    assert referenced, "the page stopped referencing its own stylesheets"
    bundled = _bundled()
    for name in sorted(referenced):
        assert (UI / name).is_file(), f"{name} is referenced by the page and does not exist"
        assert f"remote/ui/{name}" in bundled, f"{name} is not in salon.gresource.xml"


def test_every_module_import_resolves_and_is_bundled() -> None:
    """A module imported by another module is fetched by the browser, so it
    is exactly as load-bearing as one the page names itself."""
    bundled = _bundled()
    for module in sorted(UI.glob("*.js")):
        for target in re.findall(r'from "\./([a-z0-9_.-]+)"', module.read_text()):
            assert (UI / target).is_file(), f"{module.name} imports missing {target}"
            assert f"remote/ui/{target}" in bundled, f"{target} is not in salon.gresource.xml"


def test_nothing_in_the_bundle_is_an_orphan() -> None:
    """The other direction: a module nobody imports is dead weight being
    compressed into every install."""
    page = PAGE.read_text()
    reached = set(re.findall(r'(?:href|src)="/ui/([a-z0-9_.-]+)"', page))
    frontier = list(reached)
    while frontier:
        current = frontier.pop()
        if not current.endswith(".js"):
            continue
        for target in re.findall(r'from "\./([a-z0-9_.-]+)"', (UI / current).read_text()):
            if target not in reached:
                reached.add(target)
                frontier.append(target)
    on_disk = {path.name for path in UI.iterdir()}
    assert on_disk == reached, f"unreachable: {sorted(on_disk - reached)}"


def test_the_page_and_its_assets_stay_small() -> None:
    oversized = [
        f"{path.relative_to(REMOTE)}: {len(path.read_bytes().splitlines())} lines"
        for path in sorted([PAGE, *UI.iterdir()])
        if len(path.read_bytes().splitlines()) > MAXIMUM_LINES
    ]
    assert not oversized, "remote page source limit exceeded:\n" + "\n".join(oversized)


def test_the_asset_name_pattern_refuses_anything_but_a_bare_filename() -> None:
    """The one guard between `/ui/<name>` and the resource path built from
    it. A name with a slash or a dot-dot in it never reaches the join."""
    from salon.services.phone_remote_limits import _UI_ASSET_NAME

    for name in ("dom.js", "base.css", "all-apps.js", "now_playing.js"):
        assert _UI_ASSET_NAME.fullmatch(name), name
    for name in (
        "../index.html",
        "..%2findex.html",
        "sub/dom.js",
        "dom.js/../../secret",
        "dom.txt",
        "DOM.js",
        "",
        ".js",
    ):
        assert not _UI_ASSET_NAME.fullmatch(name), name
