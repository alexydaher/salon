# SPDX-License-Identifier: GPL-3.0-or-later
"""Turning a PipeWire sink description into something readable. Pure.

§8 calls the wrong HDMI output a top-three real-world failure on a machine
under a television, and Settings → Audio exists to fix it — but what it was
listing is what WirePlumber says, verbatim:

    Tiger Lake-LP Smart Sound Technology Audio Controller HDMI / DisplayPort 3 Output
    Tiger Lake-LP Smart Sound Technology Audio Controller HDMI / DisplayPort 2 Output
    Tiger Lake-LP Smart Sound Technology Audio Controller HDMI / DisplayPort 1 Output
    Tiger Lake-LP Smart Sound Technology Audio Controller Speaker

Four rows of fifty-five characters, three of them differing only in one
digit, on a screen read from three metres. The distinguishing part is at
the end, which is also the part an ellipsis eats first.

So: name the *port*, keep the controller as the detail line. The full
string is never thrown away — a machine with two sound cards needs it, and
that is exactly what the second line is for.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# The port half of a description, matched at the end because that is where
# ALSA puts it. Ordered: the first pattern that matches wins, so the
# HDMI/DisplayPort form is tried before the bare "Digital Output".
_PORTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bHDMI\s*/\s*DisplayPort\s*(\d+)\b", re.I), "HDMI {0}"),
    (re.compile(r"\bDisplayPort\s*(\d+)\b", re.I), "DisplayPort {0}"),
    (re.compile(r"\bHDMI\s*(\d+)\b", re.I), "HDMI {0}"),
    (re.compile(r"\bHDMI\b", re.I), "HDMI"),
    (re.compile(r"\bHeadphones?\b", re.I), "Headphones"),
    (re.compile(r"\bHeadset\b", re.I), "Headset"),
    (re.compile(r"\bSpeakers?\b", re.I), "Speakers"),
    (re.compile(r"\bLine\s*Out\b", re.I), "Line out"),
    (re.compile(r"\bS/?PDIF\b", re.I), "S/PDIF"),
    (re.compile(r"\bDigital\s*(?:Stereo\s*)?Output\b", re.I), "Digital output"),
    (re.compile(r"\bAnalog(?:ue)?\s*(?:Stereo\s*)?Output\b", re.I), "Analogue output"),
    (re.compile(r"\bBluetooth\b", re.I), "Bluetooth"),
)

# Marketing that carries no information at this distance. Removed only from
# the *detail* line, never from the short name, which is built from the
# port instead.
_NOISE = re.compile(
    r"\b(?:Smart\s+Sound\s+Technology|Audio\s+Controller|Controller|Device|Output|Sink|"
    r"Built-?in|Internal|PCH|Family|Corporation|Corp\.?|Inc\.?)\b",
    re.I,
)
_SPACES = re.compile(r"\s{2,}")
_TRAILING = re.compile(r"^[\s\-–—,/]+|[\s\-–—,/]+$")


def short_name(description: str) -> str:
    """The name to put on the row: the port, if this description names one.

    Falls back to the description itself so an unrecognised card is still
    listed by whatever it calls itself — a sink that does not appear is a
    worse bug than a sink with a long name.
    """
    text = description.strip()
    if not text:
        return "Unknown output"
    for pattern, template in _PORTS:
        match = pattern.search(text)
        if match is not None:
            return template.format(*match.groups())
    return text


def device_names(descriptions: Sequence[str]) -> list[str]:
    """The detail lines for a whole list of outputs, at once.

    `device_name` can only judge one description, and "does the card add
    anything?" is a question about the list: a machine with one sound card
    gave four rows reading `HDMI 3 / Tiger Lake-LP`, `HDMI 2 / Tiger
    Lake-LP`, `HDMI 1 / Tiger Lake-LP`, `Speakers / Tiger Lake-LP`. The
    card is what tells two outputs apart when there are two cards, and
    noise when there is one — so it is printed only when it differs
    somewhere in the list.
    """
    names = [device_name(description) for description in descriptions]
    return names if len(set(names)) > 1 else [""] * len(names)


def device_name(description: str) -> str:
    """The card, for the detail line under the port. "" when it adds nothing.

    Empty is a real answer: when the short name already *is* the whole
    description there is no second half worth printing, and a detail line
    repeating the label above it is how a list stops being scannable.
    """
    text = description.strip()
    short = short_name(text)
    if short == text:
        return ""
    for pattern, _template in _PORTS:
        text = pattern.sub(" ", text)
    text = _NOISE.sub(" ", text)
    text = _TRAILING.sub("", _SPACES.sub(" ", text))
    return text
