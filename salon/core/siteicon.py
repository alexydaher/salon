# SPDX-License-Identifier: GPL-3.0-or-later
"""Working out which image on a website is its icon. Pure — no gi, no I/O.

A URL tile that names nothing but its address used to render with the
*browser's* icon, because that is the only icon name such a tile has. On a
home screen whose whole point is streaming services, that meant Netflix and
Prime Video drew as the same white compass glyph on slightly different
gradients — the worst-looking thing on the flagship screen.

The fix is to ask the site itself. This module holds the pure half: given a
page's HTML, produce the candidate icon URLs in the order worth trying.
`services/artwork.py` does the fetching.

The order matters and is not "biggest first":

* `apple-touch-icon` wins outright when present. It is specified as a
  square, opaque, 180px-ish app icon — exactly the shape a tile wants —
  whereas `rel=icon` is a favicon and is frequently a 16px monochrome mark
  that looks like dirt at tile size.
* Among the rest, the largest declared `sizes` wins, and an undeclared size
  sorts last rather than first: a site that bothers to say `512x512` is
  more likely to mean it than one that says nothing.
* `.svg` sorts above equal-sized raster, being resolution-independent.

Deliberately narrow: this reads the page the tile already points at, and
nothing else. There is no TMDB, no fanart.tv, no icon CDN and no search —
§7.4 rules those out, and asking the same origin the tile is about to open
anyway is a different thing from scraping a third-party database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

# Deliberately a regex and not an HTML parser: this runs against the first
# few KiB of arbitrary, frequently malformed markup, and the only thing it
# needs is <link> elements in <head>. html.parser would be stricter about
# things that do not matter here and no more correct about the ones that do.
_LINK_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(
    r"""(?P<name>[a-zA-Z-]+)\s*=\s*(?P<quote>["']?)(?P<value>[^"'>\s]*)(?P=quote)"""
)
_SIZE_RE = re.compile(r"(?P<width>\d+)\s*[xX]\s*(?P<height>\d+)")

# rel values that mean "this is the site's icon", lowercased. `mask-icon` is
# excluded on purpose: Safari's pinned-tab icon is a monochrome silhouette
# and renders as a black square on a dark tile.
_ICON_RELS = frozenset(
    {"icon", "shortcut icon", "apple-touch-icon", "apple-touch-icon-precomposed"}
)
_APPLE_RELS = frozenset({"apple-touch-icon", "apple-touch-icon-precomposed"})

# Below this there is nothing to draw: a 16x16 mark upscaled to the tile's
# icon box is mush. 32 survives it, because a site icon is composited at
# icon size on a gradient rather than stretched to fill the card — see
# Artwork.icon_texture in services/artwork.py.
MIN_USEFUL_SIZE = 32


@dataclass(frozen=True, slots=True)
class IconCandidate:
    url: str
    size: int
    """Longest declared edge in pixels, or 0 when the page didn't say."""
    apple: bool
    svg: bool

    @property
    def sort_key(self) -> tuple[int, int, int]:
        # Negated because callers sort ascending and want the best first.
        return (0 if self.apple else 1, 0 if self.svg else 1, -self.size)


def origin(url: str) -> str | None:
    """The scheme://host[:port] a URL belongs to, or None if it isn't http."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def default_favicon(url: str) -> str | None:
    """The last-resort guess every site is supposed to answer."""
    root = origin(url)
    return f"{root}/favicon.ico" if root else None


def _attributes(tag: str) -> dict[str, str]:
    return {m.group("name").lower(): m.group("value") for m in _ATTR_RE.finditer(tag)}


def _declared_size(value: str) -> int:
    """The longest edge among a `sizes` attribute's entries. `any` (which is
    what SVGs declare) reports as 0 and is ranked by the svg flag instead."""
    best = 0
    for match in _SIZE_RE.finditer(value):
        best = max(best, int(match.group("width")), int(match.group("height")))
    return best


def icon_candidates(html: str, page_url: str) -> list[IconCandidate]:
    """Every declared icon in `html`, best first, resolved against page_url."""
    found: list[IconCandidate] = []
    seen: set[str] = set()
    for tag in _LINK_RE.finditer(html):
        attrs = _attributes(tag.group(0))
        rel = " ".join(attrs.get("rel", "").lower().split())
        href = attrs.get("href", "").strip()
        if not href or rel not in _ICON_RELS:
            continue
        resolved = urljoin(page_url, href)
        if resolved in seen or origin(resolved) is None:
            continue
        seen.add(resolved)
        found.append(
            IconCandidate(
                url=resolved,
                size=_declared_size(attrs.get("sizes", "")),
                apple=rel in _APPLE_RELS,
                svg=resolved.lower().split("?")[0].endswith(".svg"),
            )
        )
    found.sort(key=lambda candidate: candidate.sort_key)
    return found
