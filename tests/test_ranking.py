# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from salon.core.ranking import rank, score


def test_exact_match_scores_highest() -> None:
    assert score("netflix", "Netflix") > score("net", "Netflix")


def test_prefix_match() -> None:
    assert score("net", "Netflix") > 0.0


def test_initialism_match() -> None:
    assert score("gfn", "GeForce NOW") > 0.0


def test_initialism_requires_matching_word_starts() -> None:
    assert score("xyz", "GeForce NOW") == 0.0


def test_substring_match_not_at_start() -> None:
    assert score("flix", "Netflix") > 0.0


def test_no_match_scores_zero() -> None:
    assert score("zzz", "Netflix") == 0.0


def test_empty_query_scores_zero() -> None:
    assert score("", "Netflix") == 0.0


def test_rank_orders_best_matches_first() -> None:
    items = [
        ("prime", "Prime Video"),
        ("netflix", "Netflix"),
        ("geforce", "GeForce NOW"),
    ]
    assert rank("net", items) == ["netflix"]
    result = rank("e", items)
    assert set(result) == {"prime", "netflix", "geforce"}


def test_rank_drops_non_matches() -> None:
    items = [("a", "Netflix"), ("b", "Calculator")]
    assert rank("netflix", items) == ["a"]


def test_rank_is_case_insensitive() -> None:
    assert rank("NETFLIX", [("a", "netflix")]) == ["a"]


def test_rank_preserves_input_order_for_ties() -> None:
    items = [("a", "Apple"), ("b", "Apricot")]
    assert rank("ap", items) == ["a", "b"]
