"""Resolve a LaunchSpec to argv. Pure — no subprocess execution, no gi.

Actually spawning processes belongs to salon.services.launcher, which may
prefer richer gi APIs (e.g. Gio.DesktopAppInfo.launch_uris_as_manager for a
PID callback) over exec'ing the argv this module returns. This module only
answers "what would run" so it can be unit-tested headlessly.
"""

from __future__ import annotations

import configparser
import os
import shlex
from pathlib import Path

from salon.core.errors import LaunchResolutionError
from salon.core.model import LaunchKind, LaunchSpec

# Desktop entry field codes (XDG Desktop Entry spec) — stripped, not expanded,
# since Salon never passes file/URI arguments through a .desktop Exec= line.
_FIELD_CODES = ("%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N", "%i", "%c", "%k", "%v", "%m")


def resolve(
    spec: LaunchSpec,
    *,
    browser_command: tuple[str, ...] = (),
    scale_factor: float = 1.0,
    desktop_search_dirs: tuple[Path, ...] | None = None,
) -> list[str] | None:
    """Resolve a LaunchSpec to argv, or None for BUILTIN (no process spawned)."""
    if spec.kind is LaunchKind.BUILTIN:
        return None
    if spec.kind is LaunchKind.COMMAND:
        return [spec.target, *spec.args]
    if spec.kind is LaunchKind.FLATPAK:
        return ["flatpak", "run", spec.target, *spec.args]
    if spec.kind is LaunchKind.URL:
        return _resolve_url(spec, browser_command=browser_command, scale_factor=scale_factor)
    if spec.kind is LaunchKind.DESKTOP:
        return _resolve_desktop(spec, search_dirs=desktop_search_dirs)
    raise LaunchResolutionError(f"Unknown launch kind: {spec.kind!r}")  # pragma: no cover


def _resolve_url(
    spec: LaunchSpec, *, browser_command: tuple[str, ...], scale_factor: float
) -> list[str]:
    if not browser_command:
        raise LaunchResolutionError("No browser command configured for URL launch.")
    profile = spec.browser_profile or _slugify(spec.target)
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    user_data_dir = data_home / "salon" / "browser" / profile

    argv = [
        *browser_command,
        f"--user-data-dir={user_data_dir}",
        f"--app={spec.target}",
        "--ozone-platform=wayland",
        f"--force-device-scale-factor={scale_factor}",
    ]
    if spec.fullscreen:
        argv.append("--start-fullscreen")
    if spec.spatial_nav:
        argv.append("--enable-spatial-navigation")
    if spec.user_agent:
        argv.append(f"--user-agent={spec.user_agent}")
    return argv


def _slugify(text: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in text).strip("-").lower()
    return slug or "default"


def _resolve_desktop(spec: LaunchSpec, *, search_dirs: tuple[Path, ...] | None) -> list[str]:
    path = _find_desktop_file(spec.target, search_dirs)
    if path is None:
        raise LaunchResolutionError(f"No .desktop file found for {spec.target!r}")

    parser = configparser.RawConfigParser(interpolation=None, strict=False)
    parser.read(path, encoding="utf-8")
    section = "Desktop Entry"
    if not parser.has_section(section) or not parser.has_option(section, "Exec"):
        raise LaunchResolutionError(f"{path} has no Exec= entry")

    exec_line = parser.get(section, "Exec")
    for code in _FIELD_CODES:
        exec_line = exec_line.replace(code, "")
    argv = shlex.split(exec_line)
    if not argv:
        raise LaunchResolutionError(f"{path} has an empty Exec= entry")
    return [*argv, *spec.args]


def _find_desktop_file(app_id: str, search_dirs: tuple[Path, ...] | None) -> Path | None:
    name = app_id if app_id.endswith(".desktop") else f"{app_id}.desktop"
    for directory in search_dirs if search_dirs is not None else default_desktop_search_dirs():
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def default_desktop_search_dirs() -> tuple[Path, ...]:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    dirs = [data_home / "applications"]
    data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    dirs.extend(Path(d) / "applications" for d in data_dirs.split(":") if d)
    return tuple(dirs)
