#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

salon_runtime_dir="$(mktemp -d)"
chmod 700 "$salon_runtime_dir"
salon_weston_pid=""
cleanup() {
  if [ -n "$salon_weston_pid" ]; then
    kill "$salon_weston_pid" 2>/dev/null || true
    wait "$salon_weston_pid" 2>/dev/null || true
  fi
  find "$salon_runtime_dir" -mindepth 1 -delete
  rmdir "$salon_runtime_dir"
}
trap cleanup EXIT

XDG_RUNTIME_DIR="$salon_runtime_dir" \
  weston --backend=headless-backend.so --socket=salon-wayland --idle-time=0 >"$salon_runtime_dir/weston.log" 2>&1 &
salon_weston_pid=$!

for _attempt in $(seq 1 50); do
  [ -S "$salon_runtime_dir/salon-wayland" ] && break
  sleep 0.1
done
test -S "$salon_runtime_dir/salon-wayland"

XDG_RUNTIME_DIR="$salon_runtime_dir" \
WAYLAND_DISPLAY=salon-wayland \
GDK_BACKEND=wayland \
GSETTINGS_SCHEMA_DIR="$PWD/build/data" \
SALON_GRESOURCE_PATH="$PWD/build/data/salon.gresource" \
PYTHONPATH="$PWD/build" \
dbus-run-session -- python3 tests/wayland_smoke.py
