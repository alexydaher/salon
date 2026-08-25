#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Runs every quality gate from the implementation plan (§10). Must exit 0
# before any milestone is considered done — see CLAUDE.md ground rules.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "== ruff =="
ruff check salon tests scripts

echo "== mypy --strict (salon.core, salon.input) =="
mypy --strict salon/core salon/input

echo "== pytest (includes the no-gi-under-core AST check) =="
python3 -m pytest -q

echo "== meson build =="
if [ ! -d build ]; then
  meson setup build
fi
meson compile -C build

echo "== meson dependency rejection tests =="
python3 scripts/meson-negative-dependencies.py

echo "== real Wayland smoke test =="
scripts/wayland-smoke.sh

# The AppStream metainfo and the desktop entry are validated here rather
# than at submission time, which is the worst moment to learn a tag is
# wrong. Skipped automatically when appstreamcli/desktop-file-validate
# aren't installed — see data/meson.build.
echo "== meson test (metadata validation) =="
meson test -C build --print-errorlogs

echo "All gates passed."
