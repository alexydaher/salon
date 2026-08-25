#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

unit=io.github.alexydaher.Salon.service

if [[ ${SALON_DISPOSABLE_SESSION_TEST:-} != 1 ]]; then
  echo "Refusing to crash Salon outside a declared disposable session." >&2
  echo "Run with SALON_DISPOSABLE_SESSION_TEST=1 from a Salon login session." >&2
  exit 77
fi

if [[ ${XDG_CURRENT_DESKTOP:-} != *Salon* ]]; then
  echo "This test must run in a disposable native Salon session." >&2
  exit 77
fi

lock_before=$(gsettings get org.gnome.desktop.screensaver lock-enabled)
catalog=${XDG_CONFIG_HOME:-"$HOME/.config"}/salon/tiles.json
python3 -c 'from pathlib import Path; from salon.core.config import load; load(Path(__import__("sys").argv[1]))' "$catalog"

main_pid() {
  systemctl --user show --property=MainPID --value "$unit"
}

wait_for_new_pid() {
  local old_pid=$1
  local attempt new_pid
  for attempt in {1..50}; do
    new_pid=$(main_pid)
    if [[ $new_pid =~ ^[1-9][0-9]*$ && $new_pid != "$old_pid" ]]; then
      printf '%s\n' "$new_pid"
      return 0
    fi
    sleep 0.1
  done
  echo "Salon did not restart within five seconds" >&2
  return 1
}

systemctl --user reset-failed "$unit"
old_pid=$(main_pid)
kill -SEGV "$old_pid"
new_pid=$(wait_for_new_pid "$old_pid")
python3 -c 'from pathlib import Path; from salon.core.config import load; load(Path(__import__("sys").argv[1]))' "$catalog"
[[ $(gsettings get org.gnome.desktop.screensaver lock-enabled) == "$lock_before" ]]

# The recovered start above is start one inside the limit window. Four more
# crashes reach five starts; the fifth rapid crash then requests the refused
# sixth start.
for crash_number in {1..5}; do
  old_pid=$new_pid
  kill -SEGV "$old_pid"
  if [[ $crash_number == 5 ]]; then
    break
  fi
  new_pid=$(wait_for_new_pid "$old_pid")
done

for _ in {1..50}; do
  [[ $(systemctl --user is-failed "$unit" 2>/dev/null || true) == failed ]] && break
  sleep 0.1
done
[[ $(systemctl --user is-failed "$unit") == failed ]]
[[ $(gsettings get org.gnome.desktop.screensaver lock-enabled) == "$lock_before" ]]

echo "Crash recovery, catalogue reload, lock preservation, and crash-loop limiting passed."
