# SPDX-License-Identifier: GPL-3.0-or-later
"""MPRIS snapshots used by Salon's locally advancing progress bars."""

from salon.services.mpris_metadata import player_from_properties


def test_position_and_track_length_are_read_as_microseconds() -> None:
    player = player_from_properties(
        "org.mpris.MediaPlayer2.spotify",
        {
            "PlaybackStatus": "Playing",
            "Position": 107_000_000,
            "Metadata": {
                "xesam:title": "Nightcall",
                "mpris:length": 258_000_000,
            },
        },
        None,
    )

    assert player.position_us == 107_000_000
    assert player.length_us == 258_000_000
    assert player.position_at > 0


def test_missing_timing_data_keeps_the_progress_bar_hidden() -> None:
    player = player_from_properties(
        "org.mpris.MediaPlayer2.firefox",
        {"PlaybackStatus": "Paused", "Metadata": {}},
        None,
    )

    assert player.position_us == -1
    assert player.length_us == 0
