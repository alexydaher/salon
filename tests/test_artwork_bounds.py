# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from gi.repository import GLib

from salon.services import artwork_io, artwork_network, artwork_paths


class SizeProbeLoader:
    dimensions = (1, 1)

    def __init__(self) -> None:
        self.on_size = None
        self.scaled_to: tuple[int, int] | None = None

    def connect(self, _signal: str, callback) -> None:
        self.on_size = callback

    def write(self, _data: bytes) -> None:
        assert self.on_size is not None
        self.on_size(self, *self.dimensions)

    def set_size(self, width: int, height: int) -> None:
        self.scaled_to = (width, height)

    def close(self) -> None:
        pass

    def get_pixbuf(self):
        return self


def test_cache_pruning_bounds_entries_and_bytes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(artwork_paths, "artwork_cache_dir", lambda: tmp_path)
    for index in range(6):
        path = tmp_path / f"{index}.png"
        path.write_bytes(bytes([index]) * 10)
        path.touch()
    artwork_paths.prune_artwork_cache(max_bytes=25, max_entries=3)
    remaining = list(tmp_path.iterdir())
    assert len(remaining) <= 3
    assert sum(path.stat().st_size for path in remaining) <= 25


def test_cache_pruning_counts_zero_byte_miss_markers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(artwork_paths, "artwork_cache_dir", lambda: tmp_path)
    for index in range(5):
        (tmp_path / f"{index}.miss").touch()
    artwork_paths.prune_artwork_cache(max_entries=2)
    assert len(list(tmp_path.iterdir())) == 2


def test_cache_pruning_never_touches_user_artwork(tmp_path: Path, monkeypatch) -> None:
    cache = tmp_path / "cache"
    drop = tmp_path / "artwork"
    cache.mkdir()
    drop.mkdir()
    user_file = drop / "mine.png"
    user_file.write_bytes(b"user")
    (cache / "old.png").write_bytes(b"cache")
    monkeypatch.setattr(artwork_paths, "artwork_cache_dir", lambda: cache)
    artwork_paths.prune_artwork_cache(max_bytes=0, max_entries=0)
    assert user_file.read_bytes() == b"user"


def test_decode_scales_before_allocating_an_oversized_edge(monkeypatch) -> None:
    SizeProbeLoader.dimensions = (20_000, 1_000)
    monkeypatch.setattr(artwork_io.GdkPixbuf, "PixbufLoader", SizeProbeLoader)
    loader = artwork_io.decode_image(b"encoded image")
    assert loader is not None
    assert loader.scaled_to == (4096, 204)


def test_decode_scales_to_at_most_sixteen_megapixels(monkeypatch) -> None:
    SizeProbeLoader.dimensions = (4_001, 4_001)
    monkeypatch.setattr(artwork_io.GdkPixbuf, "PixbufLoader", SizeProbeLoader)
    loader = artwork_io.decode_image(b"encoded image")
    assert loader is not None and loader.scaled_to is not None
    assert loader.scaled_to[0] * loader.scaled_to[1] <= 16_000_000


def test_decode_contains_decompression_failure(monkeypatch) -> None:
    class BombLoader(SizeProbeLoader):
        def write(self, _data: bytes) -> None:
            raise GLib.Error("decompression bomb")

    monkeypatch.setattr(artwork_io.GdkPixbuf, "PixbufLoader", BombLoader)
    assert artwork_io.decode_image(b"bomb") is None


def test_player_remote_art_uses_the_bounded_artwork_fetch(tmp_path: Path, monkeypatch) -> None:
    requested: list[tuple[object, int]] = []
    session = object()
    loader = artwork_network.ArtworkNetworkLoader(
        settings=object(),  # type: ignore[arg-type]
        session_for=lambda: session,  # type: ignore[arg-type,return-value]
        in_flight=set(),
        on_fetched=None,
    )
    monkeypatch.setattr(artwork_network, "cached_remote_path", lambda _url: tmp_path / "art.png")
    monkeypatch.setattr(
        artwork_network,
        "fetch_bytes",
        lambda owner, _message, limit, _callback: requested.append((owner, limit)),
    )

    loader.maybe_fetch_url("https://example.invalid/cover.jpg")

    assert requested == [(session, artwork_network._IMAGE_DOWNLOAD_BYTES)]  # noqa: SLF001
