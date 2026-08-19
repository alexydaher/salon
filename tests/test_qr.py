# SPDX-License-Identifier: GPL-3.0-or-later
"""The QR encoder (§6.12's pairing hand-off).

The important test here decodes the generated matrix with libzbar — a real,
independent decoder — because a QR encoder that produces something
*shaped* like a QR code but subtly wrong (a bad mask, a mis-ordered format
string, wrong Reed-Solomon) still looks perfectly correct in a screenshot
and simply fails on every phone.

libzbar is loaded through ctypes and only for tests; Salon itself has no
such dependency. The decoding tests skip when the library isn't installed,
so a CI container without it still runs the structural checks.
"""

from __future__ import annotations

import ctypes
import ctypes.util

import pytest

from salon.core import qr

_ZBAR_CFG_ENABLE = 0
_ZBAR_NONE = 0


def _load_zbar() -> ctypes.CDLL | None:
    name = ctypes.util.find_library("zbar")
    if name is None:
        return None
    try:
        return ctypes.CDLL(name)
    except OSError:
        return None


_ZBAR = _load_zbar()
needs_zbar = pytest.mark.skipif(_ZBAR is None, reason="libzbar not installed")


def _decode(matrix: qr.Matrix, module_px: int = 8, quiet: int = 4) -> list[str]:
    """Render the matrix to an 8-bit greyscale buffer and decode it."""
    assert _ZBAR is not None
    size = len(matrix)
    width = (size + 2 * quiet) * module_px
    buffer = bytearray(b"\xff" * (width * width))
    for row in range(size):
        for col in range(size):
            if not matrix[row][col]:
                continue
            for y in range(module_px):
                start = ((row + quiet) * module_px + y) * width + (col + quiet) * module_px
                buffer[start : start + module_px] = b"\x00" * module_px

    zbar = _ZBAR
    zbar.zbar_image_scanner_create.restype = ctypes.c_void_p
    zbar.zbar_image_create.restype = ctypes.c_void_p
    zbar.zbar_image_first_symbol.restype = ctypes.c_void_p
    zbar.zbar_symbol_get_data.restype = ctypes.c_char_p
    zbar.zbar_symbol_next.restype = ctypes.c_void_p

    scanner = zbar.zbar_image_scanner_create()
    zbar.zbar_image_scanner_set_config(
        ctypes.c_void_p(scanner), 0, _ZBAR_CFG_ENABLE, 1
    )
    image = zbar.zbar_image_create()
    fourcc = int.from_bytes(b"Y800", "little")
    zbar.zbar_image_set_format(ctypes.c_void_p(image), fourcc)
    zbar.zbar_image_set_size(ctypes.c_void_p(image), width, width)
    data = (ctypes.c_char * len(buffer)).from_buffer(buffer)
    zbar.zbar_image_set_data(
        ctypes.c_void_p(image), data, len(buffer), ctypes.c_void_p(_ZBAR_NONE)
    )

    found = zbar.zbar_scan_image(ctypes.c_void_p(scanner), ctypes.c_void_p(image))
    results: list[str] = []
    if found > 0:
        symbol = zbar.zbar_image_first_symbol(ctypes.c_void_p(image))
        while symbol:
            payload = zbar.zbar_symbol_get_data(ctypes.c_void_p(symbol))
            results.append(payload.decode("utf-8"))
            symbol = zbar.zbar_symbol_next(ctypes.c_void_p(symbol))
    zbar.zbar_image_destroy(ctypes.c_void_p(image))
    zbar.zbar_image_scanner_destroy(ctypes.c_void_p(scanner))
    return results


@needs_zbar
@pytest.mark.parametrize(
    "text",
    [
        "http://192.168.1.151:8437",
        "http://10.0.0.2:8437",
        "A",
        "http://192.168.100.200:65535/pair?code=0000",
        "salon" * 12,  # 60 bytes, forces a larger version
    ],
)
def test_a_real_decoder_reads_what_we_encode(text: str) -> None:
    assert _decode(qr.encode(text)) == [text]


@needs_zbar
def test_every_supported_length_round_trips() -> None:
    """Walks the version boundaries, where off-by-one capacity errors and
    block-interleaving mistakes actually live."""
    for length in (1, 14, 15, 26, 42, 62, 84, 106):
        text = "x" * length
        assert _decode(qr.encode(text)) == [text], length


def test_matrix_is_square_and_correctly_sized() -> None:
    matrix = qr.encode("http://192.168.1.151:8437")
    assert len(matrix) == 25  # version 2
    assert all(len(row) == 25 for row in matrix)


def test_finder_patterns_are_in_all_three_corners() -> None:
    matrix = qr.encode("hello")
    size = len(matrix)
    for top, left in ((0, 0), (0, size - 7), (size - 7, 0)):
        assert matrix[top][left] is True
        assert matrix[top + 1][left + 1] is False
        assert matrix[top + 3][left + 3] is True


def test_timing_patterns_alternate() -> None:
    matrix = qr.encode("hello")
    size = len(matrix)
    for i in range(8, size - 8):
        assert matrix[6][i] is (i % 2 == 0)
        assert matrix[i][6] is (i % 2 == 0)


def test_payload_too_long_is_rejected_clearly() -> None:
    with pytest.raises(qr.QREncodeError):
        qr.encode("x" * 200)
