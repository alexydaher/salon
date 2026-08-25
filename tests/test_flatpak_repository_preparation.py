from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "prepare-flatpak-repository.py"
APP_ID = "io.github.alexydaher.Salon"


def test_writes_keyed_repository_and_application_references(tmp_path: Path) -> None:
    key = b"not a real OpenPGP key\x00\xff"
    key_path = tmp_path / "salon.gpg"
    output = tmp_path / "site"
    key_path.write_bytes(key)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--public-key",
            str(key_path),
            "--output-dir",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    encoded_key = base64.b64encode(key).decode("ascii")
    repository = (output / "salon.flatpakrepo").read_text()
    reference = (output / f"{APP_ID}.flatpakref").read_text()
    assert "Url=https://alexydaher.github.io/salon/repo/" in repository
    assert f"GPGKey={encoded_key}" in repository
    assert f"Name={APP_ID}" in reference
    assert "Branch=master" in reference
    assert "RuntimeRepo=https://dl.flathub.org/repo/flathub.flatpakrepo" in reference
    assert f'href="{APP_ID}.flatpakref"' in (output / "index.html").read_text()


def test_rejects_an_empty_public_key(tmp_path: Path) -> None:
    key_path = tmp_path / "empty.gpg"
    key_path.write_bytes(b"")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--public-key",
            str(key_path),
            "--output-dir",
            str(tmp_path / "site"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "public key is empty" in result.stderr
