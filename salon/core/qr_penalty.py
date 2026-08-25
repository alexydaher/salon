# SPDX-License-Identifier: GPL-3.0-or-later
"""ISO/IEC 18004 mask penalty scoring."""

from __future__ import annotations

Matrix = list[list[bool]]


def penalty_score(matrix: Matrix) -> int:
    size = len(matrix)
    score = 0
    lines = [list(row) for row in matrix]
    lines += [list(column) for column in zip(*matrix, strict=True)]
    for line in lines:
        run_value = line[0]
        run_length = 1
        for module in line[1:]:
            if module == run_value:
                run_length += 1
            else:
                if run_length >= 5:
                    score += 3 + run_length - 5
                run_value = module
                run_length = 1
        if run_length >= 5:
            score += 3 + run_length - 5
    for row in range(size - 1):
        for column in range(size - 1):
            block = (
                matrix[row][column],
                matrix[row][column + 1],
                matrix[row + 1][column],
                matrix[row + 1][column + 1],
            )
            if all(block) or not any(block):
                score += 3
    finder_pattern = [
        True,
        False,
        True,
        True,
        True,
        False,
        True,
        False,
        False,
        False,
        False,
    ]
    reverse_pattern = list(reversed(finder_pattern))
    for line in lines:
        for index in range(size - 10):
            window = line[index : index + 11]
            if window == finder_pattern or window == reverse_pattern:
                score += 40
    dark = sum(1 for line in matrix for module in line if module)
    percent = dark * 100 // (size * size)
    lower = percent // 5 * 5
    score += 10 * min(abs(lower - 50) // 5, abs(lower + 5 - 50) // 5)
    return score
