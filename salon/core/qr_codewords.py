# SPDX-License-Identifier: GPL-3.0-or-later
"""QR byte-mode encoding and Reed-Solomon error-correction codewords."""

from __future__ import annotations

VERSIONS: dict[int, tuple[int, int, int]] = {
    1: (16, 10, 1),
    2: (28, 16, 1),
    3: (44, 26, 1),
    4: (64, 18, 2),
    5: (86, 24, 2),
    6: (108, 16, 4),
}
_MODE_BYTE = 0b0100
_PAD_BYTES = (0xEC, 0x11)
_EXP: list[int] = [0] * 512
_LOG: list[int] = [0] * 256


class QREncodeError(ValueError):
    """The payload does not fit in the supported QR versions."""


def _build_tables() -> None:
    value = 1
    for index in range(255):
        _EXP[index] = value
        _LOG[value] = index
        value <<= 1
        if value & 0x100:
            value ^= 0x11D
    for index in range(255, 512):
        _EXP[index] = _EXP[index - 255]


_build_tables()


def _gf_multiply(left: int, right: int) -> int:
    if left == 0 or right == 0:
        return 0
    return _EXP[_LOG[left] + _LOG[right]]


def _generator_polynomial(degree: int) -> list[int]:
    polynomial = [1]
    for exponent in range(degree):
        expanded = [0] * (len(polynomial) + 1)
        for index, coefficient in enumerate(polynomial):
            expanded[index] ^= coefficient
            expanded[index + 1] ^= _gf_multiply(coefficient, _EXP[exponent])
        polynomial = expanded
    return polynomial


def _error_correction_codewords(data: list[int], count: int) -> list[int]:
    generator = _generator_polynomial(count)
    remainder = list(data) + [0] * count
    for index in range(len(data)):
        factor = remainder[index]
        if factor == 0:
            continue
        for offset, coefficient in enumerate(generator):
            remainder[index + offset] ^= _gf_multiply(coefficient, factor)
    return remainder[len(data) :]


def _choose_version(length: int) -> int:
    for version, (data_codewords, _, _) in sorted(VERSIONS.items()):
        if length + 2 <= data_codewords:
            return version
    maximum = VERSIONS[max(VERSIONS)][0] - 2
    raise QREncodeError(f"{length} bytes is too long for this encoder (max {maximum} bytes).")


def _bitstream(payload: bytes, version: int) -> list[int]:
    capacity_bits = VERSIONS[version][0] * 8
    bits: list[int] = []

    def push(value: int, width: int) -> None:
        bits.extend((value >> shift) & 1 for shift in range(width - 1, -1, -1))

    push(_MODE_BYTE, 4)
    push(len(payload), 8)
    for byte in payload:
        push(byte, 8)
    push(0, min(4, capacity_bits - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    padding_index = 0
    while len(bits) < capacity_bits:
        push(_PAD_BYTES[padding_index % 2], 8)
        padding_index += 1
    return bits


def encode_codewords(payload: bytes) -> tuple[int, list[int]]:
    """Return the selected version and interleaved data/error codewords."""
    version = _choose_version(len(payload))
    bits = _bitstream(payload, version)
    data = [
        int("".join(str(bit) for bit in bits[index : index + 8]), 2)
        for index in range(0, len(bits), 8)
    ]
    _, error_count, block_count = VERSIONS[version]
    block_size = len(data) // block_count
    blocks = [
        data[index * block_size : (index + 1) * block_size]
        for index in range(block_count)
    ]
    error_blocks = [
        _error_correction_codewords(block, error_count) for block in blocks
    ]
    result: list[int] = []
    for index in range(block_size):
        result.extend(block[index] for block in blocks)
    for index in range(error_count):
        result.extend(block[index] for block in error_blocks)
    return version, result
