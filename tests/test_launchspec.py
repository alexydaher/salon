# SPDX-License-Identifier: GPL-3.0-or-later
"""LaunchSpec -> argv resolution (§6.3).

M1's acceptance criterion is that every LaunchKind resolves to correct argv,
including the full Chrome flag set and the *conditional* ozone flag. The
conditional part is the one that matters most: §0 lists hardcoding
--ozone-platform=wayland as a mistake that has burned a real project,
because it leaves the browser unable to start at all on an X11 session.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from salon.core import launchspec
from salon.core.errors import LaunchResolutionError
from salon.core.model import LaunchKind, LaunchSpec

BROWSER = ("/usr/bin/google-chrome-stable",)


def url_spec(**kwargs: object) -> LaunchSpec:
    defaults: dict[str, object] = {
        "kind": LaunchKind.URL,
        "target": "https://www.netflix.com",
        "browser_profile": "netflix",
    }
    defaults.update(kwargs)
    return LaunchSpec(**defaults)  # type: ignore[arg-type]


def test_builtin_spawns_nothing() -> None:
    spec = LaunchSpec(kind=LaunchKind.BUILTIN, target="settings")
    assert launchspec.resolve(spec) is None


def test_command_is_verbatim_and_never_shelled() -> None:
    spec = LaunchSpec(kind=LaunchKind.COMMAND, target="/usr/bin/mpv", args=("--fs", "a b.mkv"))
    assert launchspec.resolve(spec) == ["/usr/bin/mpv", "--fs", "a b.mkv"]


def test_flatpak() -> None:
    spec = LaunchSpec(kind=LaunchKind.FLATPAK, target="com.nvidia.geforcenow", args=("--x",))
    assert launchspec.resolve(spec) == ["flatpak", "run", "com.nvidia.geforcenow", "--x"]


def test_url_carries_the_full_flag_set() -> None:
    argv = launchspec.resolve(url_spec(), browser_command=BROWSER, scale_factor=1.5)
    assert argv is not None
    assert argv[0] == BROWSER[0]
    assert "--app=https://www.netflix.com" in argv
    assert "--start-fullscreen" in argv
    assert "--enable-spatial-navigation" in argv
    assert "--force-device-scale-factor=1.5" in argv
    # One profile per service: separate cookie jars keep one service's login
    # state from disturbing another's.
    assert any(a.startswith("--user-data-dir=") and a.endswith("/netflix") for a in argv)
    # --app=, never --kiosk: kiosk mode makes OAuth logins almost impossible
    # to complete with a remote.
    assert not any(a.startswith("--kiosk") for a in argv)


def test_ozone_flag_is_added_only_on_wayland() -> None:
    wayland = launchspec.resolve(url_spec(), browser_command=BROWSER, session_type="wayland")
    assert wayland is not None
    assert "--ozone-platform=wayland" in wayland


@pytest.mark.parametrize("session_type", ["x11", "tty", ""])
def test_ozone_flag_is_absent_off_wayland(session_type: str) -> None:
    argv = launchspec.resolve(url_spec(), browser_command=BROWSER, session_type=session_type)
    assert argv is not None
    assert "--ozone-platform=wayland" not in argv


def test_url_per_tile_toggles() -> None:
    argv = launchspec.resolve(
        url_spec(spatial_nav=False, fullscreen=False, user_agent="SmartTV/1.0"),
        browser_command=BROWSER,
    )
    assert argv is not None
    assert "--enable-spatial-navigation" not in argv
    assert "--start-fullscreen" not in argv
    assert "--user-agent=SmartTV/1.0" in argv


def test_url_without_a_browser_is_an_actionable_error() -> None:
    with pytest.raises(LaunchResolutionError):
        launchspec.resolve(url_spec(), browser_command=())


def test_desktop_reads_exec_and_strips_field_codes(tmp_path: Path) -> None:
    (tmp_path / "org.gnome.Console.desktop").write_text(
        "[Desktop Entry]\nName=Console\nExec=kgx --window %U\n", encoding="utf-8"
    )
    spec = LaunchSpec(kind=LaunchKind.DESKTOP, target="org.gnome.Console")
    argv = launchspec.resolve(spec, desktop_search_dirs=(tmp_path,))
    assert argv == ["kgx", "--window"]


def test_desktop_missing_entry_is_an_error(tmp_path: Path) -> None:
    spec = LaunchSpec(kind=LaunchKind.DESKTOP, target="does.not.Exist")
    with pytest.raises(LaunchResolutionError):
        launchspec.resolve(spec, desktop_search_dirs=(tmp_path,))
