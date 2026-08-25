#!/usr/bin/env python3
"""Write the public installer files for Salon's signed Flatpak repository."""

from __future__ import annotations

import argparse
import base64
import html
from pathlib import Path

APP_ID = "io.github.alexydaher.Salon"
DEFAULT_REPOSITORY_URL = "https://alexydaher.github.io/salon/repo/"
HOMEPAGE = "https://github.com/alexydaher/salon"
RUNTIME_REPOSITORY = "https://dl.flathub.org/repo/flathub.flatpakrepo"


def public_key_text(path: Path) -> str:
    key = path.read_bytes()
    if not key:
        raise ValueError(f"public key is empty: {path}")
    return base64.b64encode(key).decode("ascii")


def write_installers(output: Path, repository_url: str, key: str) -> None:
    if not repository_url.startswith("https://") or not repository_url.endswith("/"):
        raise ValueError("repository URL must be an HTTPS URL ending in a slash")

    output.mkdir(parents=True, exist_ok=True)
    (output / "salon.flatpakrepo").write_text(
        "\n".join(
            (
                "[Flatpak Repo]",
                "Title=Salon",
                f"Url={repository_url}",
                f"Homepage={HOMEPAGE}",
                "Comment=Official Salon releases",
                "Description=Signed Flatpak releases of the Salon living-room launcher",
                f"GPGKey={key}",
                # Existing standalone bundles use Flatpak's historical default
                # branch. Keep it so adding this remote upgrades those installs
                # instead of installing a second branch beside them.
                "DefaultBranch=master",
                "",
            )
        )
    )
    (output / f"{APP_ID}.flatpakref").write_text(
        "\n".join(
            (
                "[Flatpak Ref]",
                f"Name={APP_ID}",
                "Branch=master",
                "Title=Salon",
                f"Url={repository_url}",
                f"Homepage={HOMEPAGE}",
                f"RuntimeRepo={RUNTIME_REPOSITORY}",
                "IsRuntime=false",
                f"GPGKey={key}",
                "SuggestRemoteName=salon",
                "",
            )
        )
    )

    ref_name = f"{APP_ID}.flatpakref"
    escaped_ref = html.escape(ref_name, quote=True)
    (output / "index.html").write_text(
        "<!doctype html>\n"
        '<html lang="en"><meta charset="utf-8">\n'
        "<title>Install Salon</title>\n"
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<h1>Salon</h1>\n"
        "<p>A fullscreen living-room launcher for GNOME.</p>\n"
        f'<p><a href="{escaped_ref}">Install Salon with Flatpak</a></p>\n'
        f'<p><a href="{HOMEPAGE}">Source code and other downloads</a></p>\n'
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-key", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--repository-url", default=DEFAULT_REPOSITORY_URL)
    args = parser.parse_args()

    try:
        write_installers(
            args.output_dir,
            args.repository_url,
            public_key_text(args.public_key),
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
