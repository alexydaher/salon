# SPDX-License-Identifier: GPL-3.0-or-later
"""Smart starter selection and its no-overwrite migration guard."""

from __future__ import annotations

from salon.core import editing, starter
from salon.core.config import Config, load, save
from salon.core.model import LaunchKind, LaunchSpec, Tile


def app(target: str, title: str, icon: str | None = None) -> Tile:
    return Tile(
        id=f"app:{target}",
        title=title,
        subtitle=f"{title} description",
        launch=LaunchSpec(LaunchKind.DESKTOP, target),
        artwork=None,
        icon_name=icon,
        accent=None,
        tags=("installed",),
    )


def discovery(*apps: Tile) -> starter.StarterDiscovery:
    return starter.StarterDiscovery(
        installed=apps,
        browser_id="org.chromium.Chromium.desktop",
        file_manager_id="org.gnome.Nautilus.desktop",
    )


def test_balanced_selection_uses_real_apps_and_stops_at_six() -> None:
    found = discovery(
        app("org.chromium.Chromium.desktop", "Chromium", "chromium"),
        app("com.valvesoftware.Steam.desktop", "Steam", "steam"),
        app("tv.kodi.Kodi.desktop", "Kodi", "kodi"),
        app("org.gnome.Nautilus.desktop", "Files", "files"),
        app("com.heroicgameslauncher.hgl.desktop", "Heroic"),
        app("net.lutris.Lutris.desktop", "Lutris"),
        app("org.videolan.VLC.desktop", "VLC"),
        app("org.example.Unrelated.desktop", "Calculator"),
    )

    row = starter.build_starter_config(found).rows[0]

    assert [tile.title for tile in row.tiles] == [
        "Chromium",
        "Steam",
        "Kodi",
        "Files",
        "Heroic",
        "Lutris",
    ]
    assert len(row.tiles) == starter.MAX_STARTER_APPS
    assert row.tiles[0].launch.target == "org.chromium.Chromium.desktop"
    assert row.tiles[0].icon_name == "chromium"
    assert all(tile.launch.kind is LaunchKind.DESKTOP for tile in row.tiles)


def test_sparse_selection_never_adds_unrelated_or_uninstalled_apps() -> None:
    config = starter.build_starter_config(
        discovery(
            app("org.chromium.Chromium.desktop", "Chromium"),
            app("org.gnome.Nautilus.desktop", "Files"),
            app("org.gnome.Calculator.desktop", "Calculator"),
        )
    )
    assert [tile.title for tile in config.rows[0].tiles] == ["Chromium", "Files"]


def test_selection_deduplicates_targets_and_tile_ids() -> None:
    config = starter.build_starter_config(
        starter.StarterDiscovery(
            installed=(
                app("steam.desktop", "Living Room"),
                app("tv.kodi.Kodi.desktop", "Living Room"),
            ),
            browser_id="steam.desktop",
            file_manager_id="tv.kodi.Kodi.desktop",
        )
    )
    row = config.rows[0]
    assert [tile.launch.target for tile in row.tiles] == ["steam.desktop", "tv.kodi.Kodi.desktop"]
    assert [tile.id for tile in row.tiles] == ["living-room", "living-room-2"]


def test_streaming_defaults_use_web_fallbacks() -> None:
    streaming = starter.build_starter_config(discovery()).rows[1]
    assert [tile.title for tile in streaming.tiles] == [
        "Netflix",
        "Prime Video",
        "Disney+",
        "YouTube",
        "GeForce NOW",
    ]
    assert all(tile.launch.kind is LaunchKind.URL for tile in streaming.tiles)
    assert all(tile.launch.target.startswith("https://") for tile in streaming.tiles)
    assert all(tile.launch.browser_profile for tile in streaming.tiles)


def test_installed_geforce_now_replaces_only_its_web_fallback() -> None:
    detected = app("com.nvidia.geforcenow.desktop", "GeForce NOW", "geforce")
    streaming = starter.build_starter_config(discovery(detected)).rows[1]
    geforce = streaming.tiles[-1]
    assert geforce.launch.kind is LaunchKind.DESKTOP
    assert geforce.launch.target == "com.nvidia.geforcenow.desktop"
    assert geforce.icon_name == "geforce"


def test_only_the_exact_historical_seed_matches_for_migration(tmp_path) -> None:
    legacy = Config(rows=starter._legacy_seed_rows())
    assert starter.is_legacy_seed(legacy)
    path = tmp_path / "legacy.json"
    save(legacy, path)
    assert starter.is_legacy_seed(load(path))

    legacy.rows[0].tiles.pop()
    assert not starter.is_legacy_seed(legacy)
    assert not starter.is_legacy_seed(starter.pending_starter_config())


def test_async_guard_rejects_memory_or_disk_edits() -> None:
    current = starter.pending_starter_config()
    expected = starter.fingerprint(current)
    disk = starter.pending_starter_config()
    assert starter.can_finalize(current, None, expected)
    assert starter.can_finalize(current, disk, expected)

    current.rows[0].title = "My apps"
    assert not starter.can_finalize(current, disk, expected)
    current = starter.pending_starter_config()
    disk.rows[1].tiles.pop()
    assert not starter.can_finalize(current, disk, expected)


def test_starter_is_persisted_and_remains_editable(tmp_path) -> None:
    config = starter.build_starter_config(
        discovery(app("org.chromium.Chromium.desktop", "Chromium"))
    )
    assert editing.remove_tile(config, "streaming", "netflix")
    created = editing.new_tile(
        config,
        "apps",
        title="My player",
        kind=LaunchKind.COMMAND,
        target="my-player",
    )
    assert editing.add_tile(config, "apps", created) is created

    path = tmp_path / "tiles.json"
    save(config, path)
    loaded = load(path)
    assert [tile.title for tile in loaded.rows[0].tiles] == ["Chromium", "My player"]
    assert "Netflix" not in [tile.title for tile in loaded.rows[1].tiles]
