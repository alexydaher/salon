# SPDX-License-Identifier: GPL-3.0-or-later
"""A minimal QR encoder. Pure — no gi, no dependencies.

Salon shows a QR code so a phone can reach the pairing page (§6.12) by
pointing a camera at the TV instead of reading an IP address off it and
typing it in. That is the whole requirement, and it's narrow enough that
adding a third-party encoder to a launcher's dependency set — and to the
Flatpak manifest, and to every distro package — is a worse trade than the
few hundred lines below.

**Scope, deliberately limited:** byte mode, error-correction level M,
versions 1 to 6 (up to 108 bytes). A LAN URL is about 25 bytes, so version
2 usually suffices. Versions 7 and up need an extra version-information
block that nothing here would ever exercise, so they're rejected rather
than half-implemented.

Level M (~15% recovery) rather than L: the code is being read off a
television across a room, at an angle, possibly with the panel's own glare
across it, and the extra redundancy costs one version step.

Implements ISO/IEC 18004. The encoder is verified end to end against
libzbar in tests/test_qr.py — a real decoder reading the real output,
because "it looks like a QR code" is not evidence that a phone can read it.
"""

from __future__ import annotations

# Total data codewords, EC codewords per block, and block count for each
# version at error-correction level M. Every version here has uniform
# blocks, which is why the interleaving below needs no second group.
_VERSIONS: dict[int, tuple[int, int, int]] = {
    # version: (data codewords, EC codewords per block, blocks)
    1: (16, 10, 1),
    2: (28, 16, 1),
    3: (44, 26, 1),
    4: (64, 18, 2),
    5: (86, 24, 2),
    6: (108, 16, 4),
}

# Alignment-pattern centre coordinates per version (the row/column values
# are combined pairwise; combinations that collide with a finder pattern
# are skipped when the matrix is drawn).
_ALIGNMENT: dict[int, list[int]] = {
    1: [],
    2: [6, 18],
    3: [6, 22],
    4: [6, 26],
    5: [6, 30],
    6: [6, 34],
}

_MODE_BYTE = 0b0100
_EC_LEVEL_M = 0b00

# BCH(15,5) generator for format information, and the mask the standard
# applies afterwards so an all-zero format still has a non-trivial pattern.
_FORMAT_GENERATOR = 0b10100110111
_FORMAT_MASK = 0b101010000010010

_PAD_BYTES = (0xEC, 0x11)

Matrix = list[list[bool]]


# --- GF(256) arithmetic --------------------------------------------------

_EXP: list[int] = [0] * 512
_LOG: list[int] = [0] * 256


def _build_tables() -> None:
    value = 1
    for i in range(255):
        _EXP[i] = value
        _LOG[value] = i
        value <<= 1
        if value & 0x100:  # primitive polynomial x^8 + x^4 + x^3 + x^2 + 1
            value ^= 0x11D
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_build_tables()


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _generator_polynomial(degree: int) -> list[int]:
    poly = [1]
    for i in range(degree):
        # Multiply by (x - alpha^i); in GF(256) subtraction is XOR.
        next_poly = [0] * (len(poly) + 1)
        for index, coefficient in enumerate(poly):
            next_poly[index] ^= coefficient
            next_poly[index + 1] ^= _gf_mul(coefficient, _EXP[i])
        poly = next_poly
    return poly


def _ec_codewords(data: list[int], count: int) -> list[int]:
    generator = _generator_polynomial(count)
    remainder = list(data) + [0] * count
    for i in range(len(data)):
        factor = remainder[i]
        if factor == 0:
            continue
        for j, coefficient in enumerate(generator):
            remainder[i + j] ^= _gf_mul(coefficient, factor)
    return remainder[len(data) :]


# --- encoding ------------------------------------------------------------


class QREncodeError(ValueError):
    """The payload doesn't fit in the versions this encoder supports."""


def _choose_version(length: int) -> int:
    for version, (data_codewords, _, _) in sorted(_VERSIONS.items()):
        # 4 bits of mode + 8 bits of length = 1.5 codewords of overhead.
        if length + 2 <= data_codewords:
            return version
    raise QREncodeError(
        f"{length} bytes is too long for this encoder (max "
        f"{_VERSIONS[max(_VERSIONS)][0] - 2} bytes)."
    )


def _bitstream(payload: bytes, version: int) -> list[int]:
    capacity_bits = _VERSIONS[version][0] * 8
    bits: list[int] = []

    def push(value: int, width: int) -> None:
        for shift in range(width - 1, -1, -1):
            bits.append((value >> shift) & 1)

    push(_MODE_BYTE, 4)
    push(len(payload), 8)  # versions 1-9 use an 8-bit byte-mode count
    for byte in payload:
        push(byte, 8)

    # Terminator, then pad to a byte boundary, then alternate pad bytes.
    push(0, min(4, capacity_bits - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    index = 0
    while len(bits) < capacity_bits:
        push(_PAD_BYTES[index % 2], 8)
        index += 1
    return bits


def _codewords(payload: bytes, version: int) -> list[int]:
    bits = _bitstream(payload, version)
    data = [int("".join(str(b) for b in bits[i : i + 8]), 2) for i in range(0, len(bits), 8)]

    _, ec_per_block, block_count = _VERSIONS[version]
    per_block = len(data) // block_count
    blocks = [data[i * per_block : (i + 1) * per_block] for i in range(block_count)]
    ec_blocks = [_ec_codewords(block, ec_per_block) for block in blocks]

    # Interleave: one codeword from each block in turn, data first then EC.
    result: list[int] = []
    for i in range(per_block):
        result.extend(block[i] for block in blocks)
    for i in range(ec_per_block):
        result.extend(block[i] for block in ec_blocks)
    return result


# --- matrix --------------------------------------------------------------


def _size(version: int) -> int:
    return version * 4 + 17


def _new_matrix(size: int) -> tuple[Matrix, list[list[bool]]]:
    """The module grid plus a parallel grid marking reserved function
    patterns, which data placement and masking must both skip."""
    return (
        [[False] * size for _ in range(size)],
        [[False] * size for _ in range(size)],
    )


def _place_finder(matrix: Matrix, reserved: list[list[bool]], top: int, left: int) -> None:
    for row in range(-1, 8):
        for col in range(-1, 8):
            r, c = top + row, left + col
            if not (0 <= r < len(matrix) and 0 <= c < len(matrix)):
                continue
            in_ring = 0 <= row <= 6 and col in (0, 6) or 0 <= col <= 6 and row in (0, 6)
            in_core = 2 <= row <= 4 and 2 <= col <= 4
            matrix[r][c] = in_ring or in_core
            reserved[r][c] = True


def _place_alignment(matrix: Matrix, reserved: list[list[bool]], version: int) -> None:
    centres = _ALIGNMENT[version]
    size = len(matrix)
    for row in centres:
        for col in centres:
            # Skip the three positions that would sit on a finder pattern.
            if (row, col) in ((6, 6), (6, size - 7), (size - 7, 6)):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    matrix[row + dr][col + dc] = max(abs(dr), abs(dc)) != 1
                    reserved[row + dr][col + dc] = True


def _place_timing(matrix: Matrix, reserved: list[list[bool]]) -> None:
    size = len(matrix)
    for i in range(8, size - 8):
        value = i % 2 == 0
        matrix[6][i] = value
        matrix[i][6] = value
        reserved[6][i] = True
        reserved[i][6] = True


def _reserve_format(matrix: Matrix, reserved: list[list[bool]]) -> None:
    size = len(matrix)
    for i in range(9):
        if i != 6:
            reserved[8][i] = True
            reserved[i][8] = True
    for i in range(8):
        reserved[8][size - 1 - i] = True
        reserved[size - 1 - i][8] = True
    # The dark module, always set, always reserved.
    matrix[size - 8][8] = True
    reserved[size - 8][8] = True


def _place_data(matrix: Matrix, reserved: list[list[bool]], codewords: list[int]) -> None:
    size = len(matrix)
    bits = [(word >> shift) & 1 for word in codewords for shift in range(7, -1, -1)]
    index = 0
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1  # the vertical timing pattern is not a data column
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for offset in (0, 1):
                c = col - offset
                if reserved[row][c]:
                    continue
                if index < len(bits):
                    matrix[row][c] = bool(bits[index])
                    index += 1
        upward = not upward
        col -= 2


def _mask_condition(mask: int, row: int, col: int) -> bool:
    if mask == 0:
        return (row + col) % 2 == 0
    if mask == 1:
        return row % 2 == 0
    if mask == 2:
        return col % 3 == 0
    if mask == 3:
        return (row + col) % 3 == 0
    if mask == 4:
        return (row // 2 + col // 3) % 2 == 0
    if mask == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if mask == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    return ((row + col) % 2 + (row * col) % 3) % 2 == 0


def _apply_mask(matrix: Matrix, reserved: list[list[bool]], mask: int) -> Matrix:
    return [
        [
            module != _mask_condition(mask, row, col) if not reserved[row][col] else module
            for col, module in enumerate(line)
        ]
        for row, line in enumerate(matrix)
    ]


def _format_bits(mask: int) -> list[int]:
    """The 15-bit format string: 5 data bits, 10 BCH parity bits, masked.

    Returned most-significant bit first, which is the order the placement
    positions below run in — verified against libqrencode's output rather
    than inferred, because getting this backwards produces a symbol that
    looks entirely correct and decodes on nothing.
    """
    value = (_EC_LEVEL_M << 3) | mask
    remainder = value << 10
    while remainder.bit_length() >= 11:
        remainder ^= _FORMAT_GENERATOR << (remainder.bit_length() - 11)
    combined = ((value << 10) | remainder) ^ _FORMAT_MASK
    return [(combined >> shift) & 1 for shift in range(14, -1, -1)]


def _place_format(matrix: Matrix, mask: int) -> None:
    bits = _format_bits(mask)
    size = len(matrix)
    # Copy one, around the top-left finder.
    positions_a = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8)]
    positions_a += [(7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    # Copy two, split between the other two finders.
    positions_b = [(size - 1 - i, 8) for i in range(7)]
    positions_b += [(8, size - 8 + i) for i in range(8)]
    for bit, (row, col) in zip(bits, positions_a, strict=True):
        matrix[row][col] = bool(bit)
    for bit, (row, col) in zip(bits, positions_b, strict=True):
        matrix[row][col] = bool(bit)


# --- mask penalty scoring ------------------------------------------------


def _penalty(matrix: Matrix) -> int:
    size = len(matrix)
    score = 0
    lines: list[list[bool]] = [list(row) for row in matrix]
    lines += [list(column) for column in zip(*matrix, strict=True)]

    # Rule 1: runs of five or more same-coloured modules in a line.
    for line in lines:
        run_value = line[0]
        run_length = 1
        for module in line[1:]:
            if module == run_value:
                run_length += 1
            else:
                if run_length >= 5:
                    score += 3 + (run_length - 5)
                run_value = module
                run_length = 1
        if run_length >= 5:
            score += 3 + (run_length - 5)

    # Rule 2: 2x2 blocks of one colour.
    for row in range(size - 1):
        for col in range(size - 1):
            block = (
                matrix[row][col],
                matrix[row][col + 1],
                matrix[row + 1][col],
                matrix[row + 1][col + 1],
            )
            if all(block) or not any(block):
                score += 3

    # Rule 3: the finder-like 1:1:3:1:1 pattern with four light modules
    # beside it, which a decoder can mistake for a real finder.
    pattern_a = [True, False, True, True, True, False, True, False, False, False, False]
    pattern_b = list(reversed(pattern_a))
    for line in lines:
        for i in range(size - 10):
            window = line[i : i + 11]
            if window == pattern_a or window == pattern_b:
                score += 40

    # Rule 4: deviation from an even balance of dark and light.
    dark = sum(1 for line in matrix for module in line if module)
    percent = dark * 100 // (size * size)
    lower = (percent // 5) * 5
    upper = lower + 5
    score += 10 * min(abs(lower - 50) // 5, abs(upper - 50) // 5)
    return score


# --- public API ----------------------------------------------------------


def encode(text: str) -> Matrix:
    """Encode `text` as a QR matrix — True is a dark module.

    Raises QREncodeError if the payload is longer than version 6 at error
    level M can carry (106 bytes).
    """
    payload = text.encode("utf-8")
    version = _choose_version(len(payload))
    codewords = _codewords(payload, version)

    size = _size(version)
    matrix, reserved = _new_matrix(size)
    _place_finder(matrix, reserved, 0, 0)
    _place_finder(matrix, reserved, 0, size - 7)
    _place_finder(matrix, reserved, size - 7, 0)
    _place_alignment(matrix, reserved, version)
    _place_timing(matrix, reserved)
    _reserve_format(matrix, reserved)
    _place_data(matrix, reserved, codewords)

    best: Matrix | None = None
    best_score = 0
    for mask in range(8):
        candidate = _apply_mask(matrix, reserved, mask)
        _place_format(candidate, mask)
        score = _penalty(candidate)
        if best is None or score < best_score:
            best, best_score = candidate, score
    assert best is not None
    return best
