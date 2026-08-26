# SPDX-License-Identifier: GPL-3.0-or-later
"""Every fixed number and table the remote's HTTP surface is bounded by.

Split out of `phone_remote_shared` so that module can be what its docstring
says it is — the argument for how the phone remote works — rather than that
argument followed by two hundred lines of ceilings. Nothing here has any
behaviour; `phone_remote_shared` re-exports the lot, so every component
still imports from one place.
"""

from __future__ import annotations

import re

# The most results a search will return. A phone screen shows about six at a
# time and nobody scrolls a remote control; past this the ranking is doing
# no work that anyone reads.
MAX_SEARCH_RESULTS = 40

# The most applications /apps will list. Unlike a result list this is meant
# to be scrolled, so the ceiling is about the cost of serialising it on the
# thread that draws the television rather than about how much anyone reads.
MAX_BROWSE_RESULTS = 300

DEFAULT_PORT = 8437
SESSION_TIMEOUT_SECONDS = 300

# How often the idle deadline is checked. A repeating timer that compares a
# monotonic stamp, rather than a timeout rescheduled per request: the phone
# polls once a second, and tearing down and rebuilding a GLib source at that
# rate to express "still here" is work for nothing.
_IDLE_CHECK_SECONDS = 15

# How long after the last authenticated request a phone still counts as
# connected. A little over the page's one-second poll, so a phone sitting on
# the remote reads as present without flickering between polls.
_CONNECTED_SECONDS = 4.0

# Wrong codes allowed before the session is burned. Low enough that a brute
# force gets nowhere, high enough to survive a person mistyping four digits
# on a phone keyboard a few times.
MAX_ATTEMPTS = 5

# 128 bits. `token_urlsafe(16)` is 22 characters, which keeps the pairing
# URL inside QR version 4 at error-correction level M — comfortably within
# what core/qr.py encodes and what a camera reads off a television.
_TOKEN_BYTES = 16

# Soup.Status has no TOO_MANY_REQUESTS member in libsoup 3.
_STATUS_TOO_MANY_REQUESTS = 429
_STATUS_CONTENT_TOO_LARGE = 413
_MAX_REQUEST_BODY_BYTES = 64 * 1024

# Artwork is read off disk on the main loop, so a pathological file must not
# become a stall. Nothing legitimate here is close to this: the largest
# thing served is a cached poster.
_MAX_ART_BYTES = 8 * 1024 * 1024

_ART_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}

# What /ui/<name> will serve. A name has to match this exactly — no dots
# beyond the one before the suffix, no slashes — so the resource path built
# from it cannot leave `remote/ui/` however the request is spelled. The set
# of files is the bundle's, not a list kept by hand here: a module added to
# salon.gresource.xml is served, and one that is not in the bundle is a 404
# rather than a read off the disk.
_UI_ASSET_NAME = re.compile(r"^[a-z0-9_-]+\.(css|js)$")

_UI_TYPES = {
    "css": "text/css; charset=utf-8",
    # The exact spelling matters: a browser refuses a module script served
    # as anything but a JavaScript MIME type, and refuses it silently
    # enough that the page simply does nothing.
    "js": "text/javascript; charset=utf-8",
}

# The blank loop the page plays to hold a phone's screen on, in the two
# containers between them cover every phone: Safari wants H.264, and VP8 has
# been on Android for longer than anything else. See the `#awake` element.
_AWAKE_CLIPS = {
    "/awake.webm": ("awake.webm", "video/webm"),
    "/awake.mp4": ("awake.mp4", "video/mp4"),
}
