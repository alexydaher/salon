# SPDX-License-Identifier: GPL-3.0-or-later
"""No rule in salon.css is shadowed by a later restatement of a sibling state.

CSS resolves ties in source order, so a selector restated later in the file
wins against everything of equal specificity declared before it — including
rules that describe a *different state* of the same element. Nothing about
that reads as an override: the losing rule is still there, still commented,
and still looks like it applies.

It cost two states at once, both found on 2026-09-06 by capturing the screen
rather than by reading. The Aurora Console section restated
`.salon-settings-row.selected`, which sits at exactly the specificity of
`.salon-settings-row.adjusting` (the row whose value list is open) and of the
inactive pane's `:not(.active)` hairline. Both silently lost their
background-color to it, so a row with a popup behind it drew *pixel*-
identically to any other selected row — 6px ring, fill luminance 67 against
68 — and the pane that does not hold the cursor went back to drawing the
filled block the comment above it says it stopped drawing.

The gate is deliberately narrower than "no selector twice". A dozen selectors
in this stylesheet are restated by the Aurora section and merely override
themselves; those are dead rules under live comments, worth tidying, but they
draw the right pixels. What can never be right is a restatement that reaches
past its own selector into a neighbouring state, because the two rules are not
in an override relationship at all — they describe different things. A theme
variation belongs behind a scoping class, where specificity says so.
"""

from __future__ import annotations

import re
from pathlib import Path

STYLESHEET = Path(__file__).resolve().parent.parent / "data" / "style" / "salon.css"

_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
# A class, a pseudo-class (:hover, :not(...)) or an attribute test. Each is
# worth one specificity point, which is the whole reason `.a:hover` survives a
# later bare `.a` while `.a.b` does not survive a later `.a.c`.
_POINT = re.compile(r"\.[\w-]+|:[\w-]+|\[[^\]]*\]")


class Rule:
    def __init__(self, selector: str, line: int, body: str) -> None:
        self.selector = selector
        self.line = line
        self.properties = {
            part.split(":", 1)[0].strip() for part in body.split(";") if ":" in part
        }
        # `:not(.active)` contributes its own argument's point, not two.
        self.weight = len(_POINT.findall(re.sub(r":not\(([^)]*)\)", r"\1", selector)))

    def __repr__(self) -> str:
        return f"{self.selector} (line {self.line})"


def _rules() -> list[Rule]:
    # Blank the comments without moving any line, so reported lines are real.
    source = _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), STYLESHEET.read_text("utf-8"))
    rules = []
    for match in _RULE.finditer(source):
        prelude = match.group(1).strip()
        # At-rules are declarations or containers, not element rules.
        if not prelude or prelude.startswith("@"):
            continue
        line = source[: match.start()].count("\n") + 1
        for selector in prelude.split(","):
            normalised = " ".join(selector.split())
            if normalised:
                rules.append(Rule(normalised, line, match.group(2)))
    return rules


def _shadowed() -> list[tuple[Rule, Rule]]:
    """Every (victim, winner) pair where a later restatement of some *other*
    selector takes a property the victim declares."""
    rules = _rules()
    first_seen: dict[str, int] = {}
    for rule in rules:
        first_seen.setdefault(rule.selector, rule.line)

    losses = []
    for winner in rules:
        opened = first_seen[winner.selector]
        if opened >= winner.line:
            continue  # not a restatement
        for victim in rules:
            if not opened < victim.line < winner.line:
                continue
            if victim.selector == winner.selector:
                continue  # self-overrides are the other gate's business
            if victim.weight != winner.weight:
                # Unequal specificity is decided before source order is even
                # consulted, so the restatement changes nothing. A lower-
                # weight victim losing to a higher-weight winner is just a
                # base rule and its modifier.
                continue
            if not victim.properties & winner.properties:
                continue
            # Only rules that can match the same element are at risk. Two
            # unrelated selectors sharing `color` are not in conflict.
            if not _may_share_an_element(victim.selector, winner.selector):
                continue
            losses.append((victim, winner))
    return losses


def _may_share_an_element(a: str, b: str) -> bool:
    """True when one selector's points are a subset of the other's, which is
    the shape that matters here: `.row.selected` restated later swallows
    `.row.adjusting`, because a row carries both classes at once."""
    if _elements(a) != _elements(b):
        # `.salon-media-progress trough` and `.salon-media-progress progress`
        # are two nodes inside one widget, never the same element.
        return False
    a_points, b_points = set(_POINT.findall(a)), set(_POINT.findall(b))
    return bool(a_points & b_points) and (a_points <= b_points or b_points <= a_points)


def _elements(selector: str) -> list[str]:
    """The bare element names in a selector, in order — `trough`, `progress`,
    `contents`. Two selectors naming different ones cannot collide."""
    return [
        name
        for name in _POINT.sub(" ", selector).replace(">", " ").split()
        if name and name != "*"
    ]


def test_no_rule_is_shadowed_by_a_later_sibling_state() -> None:
    losses = _shadowed()
    report = "\n".join(
        f"  {victim} loses {sorted(victim.properties & winner.properties)} to {winner}"
        for victim, winner in losses
    )
    assert not losses, (
        "salon.css restates a selector after a sibling state of the same "
        "element, so the later rule wins on source order and the earlier "
        "state stops drawing what its declaration says:\n" + report
    )


def test_the_gate_can_see_the_bug_it_was_written_for() -> None:
    """The parser is a regex over a real stylesheet, so check it against the
    three rules whose collision this test exists to prevent."""
    weights = {rule.selector: rule.weight for rule in _rules()}
    assert weights[".salon-settings-row.selected"] == 2
    assert weights[".salon-settings-row.adjusting"] == 2
    assert weights[".salon-settings-list:not(.active) .salon-settings-row.selected"] == 4
    # A pseudo-class outranks the bare selector, which is why the dozen
    # remaining self-overrides in this file are not reported.
    assert weights[".salon-status-button:hover"] > weights[".salon-status-button"]


# Every selector salon.css already declared twice when this gate was written.
# All twelve are self-overrides from the Aurora Console redesign restating a
# rule rather than scoping a variant of it: the later block wins, the earlier
# one is dead, and the comment above the earlier one still describes the
# screen. They draw correct pixels today only because nothing of equal
# specificity happens to sit between each pair — which is luck, not design.
# The settings rows were the pair where that luck ran out.
#
# Frozen rather than fixed: consolidating them is mechanical (hoist the later
# value into the earlier rule, delete the later block) but it touches five
# surfaces that would each need re-capturing, and that is a separate job from
# the one this file was added for. New entries are not accepted.
KNOWN_DUPLICATES = frozenset(
    {
        ".salon-detail-title",
        ".salon-media-progress progress",
        ".salon-media-progress trough",
        ".salon-remote-hint",
        ".salon-remote-hint-detail",
        ".salon-remote-hint-title",
        ".salon-row-heading",
        ".salon-row-heading.row-focused",
        ".salon-settings-preview-bar",
        ".salon-status-button",
        ".salon-value-option.selected",
        ".salon-value-popup > contents",
    }
)


def _repeated() -> set[str]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for rule in _rules():
        if rule.selector in seen:
            repeated.add(rule.selector)
        seen.add(rule.selector)
    return repeated


def test_no_new_selector_is_declared_twice() -> None:
    """The debt above is frozen, so the next restatement fails here instead of
    in a screenshot six weeks later."""
    assert not _repeated() - KNOWN_DUPLICATES, (
        "salon.css declares these selectors more than once: "
        f"{sorted(_repeated() - KNOWN_DUPLICATES)}. The later one wins on source "
        "order and every rule of equal specificity between them loses with it. "
        "State the rule once, or scope the variant behind a class."
    )


def test_the_frozen_list_has_not_gone_stale() -> None:
    """A fixed duplicate should leave the list, or it stops meaning anything."""
    assert not KNOWN_DUPLICATES - _repeated(), (
        "these selectors are no longer duplicated and should come off the "
        f"frozen list: {sorted(KNOWN_DUPLICATES - _repeated())}"
    )
