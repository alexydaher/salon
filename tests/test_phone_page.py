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

import json
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


def test_phone_navigation_stays_small_and_typing_is_contextual() -> None:
    """Typing belongs to Pointer rather than permanently taxing navigation."""
    page = PAGE.read_text()
    assert re.findall(r'data-tab="([a-z]+)"', page) == ["apps", "remote", "pad"]
    assert 'id="pane-type"' not in page
    assert 'id="type-drawer"' in page
    session = (UI / "session.js").read_text()
    assert 'stored === "type" ? "pad"' in session


def test_pairing_and_player_have_complete_visual_states() -> None:
    page = PAGE.read_text()
    assert page.count("<span></span>") == 4
    assert 'id="connect-go" class="primary" disabled' in page
    assert 'id="np-fallback"' in page


def test_installed_remote_uses_the_whole_phone_screen() -> None:
    """The remote is the appliance's control surface, not a browser window.

    ``standalone`` keeps system window chrome around an installed web app,
    while a portrait lock also defeats the landscape layout maintained by the
    stylesheets.  Ask for the physical screen and let the phone rotate.
    """
    manifest = json.loads((REMOTE / "manifest.webmanifest").read_text())
    assert manifest["display"] == "fullscreen"
    assert manifest["orientation"] == "any"


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


def test_no_card_grid_track_can_be_widened_by_its_contents() -> None:
    """A bare `1fr` is `minmax(auto, 1fr)`, whose floor is the item's
    min-content width — and a card's subtitle is `white-space: nowrap`. An
    installed application's subtitle is its `Comment=` line, so the A-Z list
    drew one 312px card, one 89px card and one of exactly zero width across
    a 390px phone. Every track here has to have a floor of zero.
    """
    catalog = (UI / "catalog.css").read_text()
    templates = re.findall(
        r"\.row-tiles\.[a-z]+\s*\{[^}]*grid-template-columns:([^;]+);", catalog
    )
    assert len(templates) >= 3, "the card grid stopped declaring its own columns"
    for template in templates:
        assert "minmax(0" in template, (
            f"{template.strip()} lets a card widen the column it is in"
        )


def test_the_browse_surfaces_clear_the_sticky_search_row() -> None:
    """Both the A-Z rail and the mirrored cursor scroll things into view in
    a scrollport whose first 60px are covered by the search field. Without a
    scroll margin, jumping to M hid the M heading and the whole first row of
    it behind that field."""
    catalog = (UI / "catalog.css").read_text()
    allapps = (UI / "allapps.css").read_text()
    assert "--search-h" in (UI / "dom.js").read_text(), "nothing measures the search row"
    for name, rule in (("catalog.css", catalog), ("allapps.css", allapps)):
        assert "scroll-margin-top" in rule, f"{name} has no scroll margin"
    # And the offset the headings stick at is the measured one, not a guess.
    assert "top: var(--search-h" in catalog


def test_the_header_can_give_the_player_a_line_of_its_own() -> None:
    """An application in front and something playing put four controls in a
    390px row — the identity, "Close Netflix", the track and the volume —
    and every one of them came out as two clipped characters. The player
    takes the second line instead, which needs three things: a header that
    wraps at all, a rule that sends the player down, and `order` on the keys
    that must stay up, because a full-width flex item takes everything after
    it down with it."""
    header = (UI / "base.css").read_text()
    player = (UI / "strips.css").read_text()
    assert "flex-wrap: wrap" in header, "the header cannot wrap any more"
    assert "flex: 1 0 100%" in player, "nothing gives the player its own line"
    assert "#hdr-volume, body.in-app.playing #hdr-menu { order: 0" in player, (
        "the volume key can be carried down with the player"
    )
    # And the state the rule keys on is actually published.
    assert 'classList.toggle("playing"' in (UI / "render.js").read_text()


def test_the_volume_popover_hangs_off_a_measured_header() -> None:
    """It is `position: fixed`, so it is placed against the viewport rather
    than against the header it belongs to. The header is no longer one fixed
    row — the player takes a second one — so the 3.5rem it used to assume put
    the popover straight over the track title."""
    assert "--header-h" in (UI / "dom.js").read_text(), "nothing measures the header"
    assert "measureHeader" in (UI / "render.js").read_text(), "it is measured but never"
    assert "top: calc(var(--header-h" in (UI / "overlays.css").read_text()
