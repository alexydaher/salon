# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

pytest.importorskip("gi")

from salon.services import audio  # noqa: E402

WPCTL_STATUS = """
Audio
 ├─ Sinks:
 │  *   59. HDMI / DisplayPort 3 Output [vol: 0.42]
 │      72. Built-in Audio Analog Stereo [vol: 0.30]
 ├─ Sources:
"""


def test_wpctl_sink_parser_finds_default_and_descriptions() -> None:
    assert audio.parse_sinks(WPCTL_STATUS) == [
        audio.Sink(59, "HDMI / DisplayPort 3 Output", True),
        audio.Sink(72, "Built-in Audio Analog Stereo", False),
    ]


def test_native_wpctl_argv_is_direct() -> None:
    assert audio.wpctl_argv("status", sandboxed=False) == ["wpctl", "status"]


def test_flatpak_wpctl_argv_always_executes_on_host() -> None:
    assert audio.wpctl_argv("set-mute", "@DEFAULT_AUDIO_SINK@", "toggle", sandboxed=True) == [
        "flatpak-spawn",
        "--host",
        "wpctl",
        "set-mute",
        "@DEFAULT_AUDIO_SINK@",
        "toggle",
    ]


def test_no_pactl_fallback_survives() -> None:
    assert "pactl" not in open(audio.__file__, encoding="utf-8").read()


def test_missing_wpctl_has_structured_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audio, "_have_wpctl", lambda: False)
    results: list[audio.AudioResult] = []
    audio.run_wpctl(("status",), results.append)
    assert results == [
        audio.AudioResult(audio.AudioAvailability.NOT_INSTALLED, error="wpctl is not installed")
    ]


def test_empty_status_distinguishes_no_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(_args: tuple[str, ...], callback) -> None:
        callback(audio.AudioResult(audio.AudioAvailability.AVAILABLE, output="Audio\n Sinks:\n"))

    monkeypatch.setattr(audio, "run_wpctl", fake_run)
    results: list[tuple[audio.AudioResult, list[audio.Sink]]] = []
    audio.list_sinks_result(lambda status, sinks: results.append((status, sinks)))
    assert results[0][0].availability is audio.AudioAvailability.NO_OUTPUTS
    assert results[0][1] == []


def test_malformed_status_is_not_reported_as_no_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        audio,
        "run_wpctl",
        lambda _args, callback: callback(
            audio.AudioResult(audio.AudioAvailability.AVAILABLE, output="not wpctl output")
        ),
    )
    results: list[tuple[audio.AudioResult, list[audio.Sink]]] = []
    audio.list_sinks_result(lambda status, sinks: results.append((status, sinks)))
    assert results[0][0].availability is audio.AudioAvailability.MALFORMED_OUTPUT
