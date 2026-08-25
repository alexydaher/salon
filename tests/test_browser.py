# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import subprocess

import pytest

pytest.importorskip("gi")

from salon.services import launcher_shared as browser  # noqa: E402
from salon.ui.settings import browser_panel  # noqa: E402


class Settings:
    def __init__(self) -> None:
        self.command = "chromium --old"
        self.flags = ["--old-flag"]

    def get_string(self, _key: str) -> str:
        return self.command

    def set_string(self, _key: str, value: str) -> None:
        self.command = value

    def get_strv(self, _key: str) -> list[str]:
        return self.flags

    def set_strv(self, _key: str, value: list[str]) -> None:
        self.flags = value


class Context:
    def __init__(self, edit: str) -> None:
        self.edit = edit
        self.toasts: list[str] = []
        self.rebuilds = 0

    def edit_text(self, _title: str, _initial: str, done) -> None:
        done(self.edit)

    def toast(self, message: str) -> None:
        self.toasts.append(message)

    def rebuild(self) -> None:
        self.rebuilds += 1


def test_browser_command_uses_shell_quoting_without_a_shell() -> None:
    assert browser.parse_browser_command('chromium --profile-directory="Living Room"') == (
        "chromium",
        "--profile-directory=Living Room",
    )


def test_malformed_browser_command_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid browser command"):
        browser.parse_browser_command("chromium 'unterminated")


def test_invalid_browser_edit_retains_previous_setting() -> None:
    settings = Settings()
    context = Context("chromium 'unterminated")
    browser_panel._edit_browser(context, settings)  # type: ignore[arg-type]
    assert settings.command == "chromium --old"
    assert context.toasts and context.rebuilds == 0


def test_extra_flags_are_parsed_and_saved_in_order() -> None:
    settings = Settings()
    context = Context('--first "two words" --last')
    browser_panel._edit_flags(context, settings)  # type: ignore[arg-type]
    assert settings.flags == ["--first", "two words", "--last"]
    assert context.rebuilds == 1


def test_native_resolution_reports_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(browser.shutil, "which", lambda _name: None)
    result = browser.resolve_browser(sandboxed=False)
    assert result.availability is browser.BrowserAvailability.NOT_INSTALLED
    assert result.argv == ()


def test_flatpak_resolution_probes_the_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        browser.shutil,
        "which",
        lambda name: "/usr/bin/flatpak-spawn" if name == "flatpak-spawn" else None,
    )
    calls: list[list[str]] = []

    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv[-1] == "chromium":
            return subprocess.CompletedProcess(argv, 0, "/usr/bin/chromium\n", "")
        return subprocess.CompletedProcess(argv, 1, "", "not found")

    monkeypatch.setattr(browser.subprocess, "run", run)
    result = browser.resolve_browser(sandboxed=True)
    assert result.argv == ("/usr/bin/chromium",)
    assert calls[0][:2] == ["flatpak-spawn", "--host"]


def test_flatpak_resolution_distinguishes_host_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(browser.shutil, "which", lambda _name: "/usr/bin/flatpak-spawn")
    monkeypatch.setattr(
        browser.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("host spawn failed")),
    )
    result = browser.resolve_browser(sandboxed=True)
    assert result.availability is browser.BrowserAvailability.HOST_EXECUTION_FAILED
