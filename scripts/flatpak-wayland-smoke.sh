#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

if [[ $# != 1 ]]; then
  echo "usage: $0 SALON.flatpak" >&2
  exit 2
fi

bundle=$(realpath "$1")
runtime_dir=$(mktemp -d)
weston_pid=""
cleanup() {
  flatpak uninstall --user --noninteractive io.github.alexydaher.Salon >/dev/null 2>&1 || true
  if [[ -n $weston_pid ]]; then
    kill "$weston_pid" 2>/dev/null || true
    wait "$weston_pid" 2>/dev/null || true
  fi
  find "$runtime_dir" -mindepth 1 -delete
  rmdir "$runtime_dir"
}
trap cleanup EXIT
chmod 700 "$runtime_dir"

flatpak install --user --noninteractive "$bundle"
XDG_RUNTIME_DIR="$runtime_dir" \
  weston --backend=headless-backend.so --socket=salon-flatpak-wayland --idle-time=0 \
  >"$runtime_dir/weston.log" 2>&1 &
weston_pid=$!
for _attempt in {1..50}; do
  [[ -S $runtime_dir/salon-flatpak-wayland ]] && break
  sleep 0.1
done
[[ -S $runtime_dir/salon-flatpak-wayland ]]

# Exercise the installed bundle, not the source tree. The assertions run
# inside the sandbox and cover the host-prefixed capabilities that cannot be
# truthfully inferred from a host-side unit test.
#
# Until 2026-08-29 every assertion below was the opposite: this script
# asserted the sandbox withheld power, Wi-Fi, Bluetooth, CEC and GNOME
# Settings, and it kept asserting it after the manifest gave them back,
# which is what failed the first v0.3.0 release run. Two things stay
# withheld and they are the whole list — `mutter_injection` and
# `autostart` — so those are what this checks for, in both directions.
XDG_RUNTIME_DIR="$runtime_dir" WAYLAND_DISPLAY=salon-flatpak-wayland \
  flatpak run --env=PYTHONPATH=/app/share/salon --env=GSETTINGS_BACKEND=memory --command=python3 \
  io.github.alexydaher.Salon -c '
from salon.core import sandbox
from salon.services.audio import wpctl_argv
from salon.services.launcher_shared import detect_browser
from gi.repository import Gio, Gtk
from salon import config
from salon.ui.settings.advanced_input_panel import advanced_input_panel
from salon.ui.settings.network_panel import network_panel
from salon.ui.settings.system_panel import system_panel
caps = sandbox.capabilities()
assert caps.sandboxed and caps.host_spawn
assert caps.control_center and caps.network_configuration
assert caps.bluetooth_pairing and caps.cec and caps.host_power
assert caps.shell_keyboard
assert not caps.autostart and not caps.mutter_injection
assert wpctl_argv("status")[:2] == ["flatpak-spawn", "--host"]
assert detect_browser() == ("flatpak", "run", "com.google.Chrome")
Gtk.init()
class Context:
    def phone_remote_running(self): return False
    def phone_remote_hint(self): return ""
    def pointer_backend(self): return ""
    def set_phone_remote(self, _enabled): return False
    def push(self, _panel): pass
    def open_control_center(self, _panel): pass
    def rebuild(self): pass
    def toast(self, _message): pass
    def quit_app(self): pass
context = Context()
settings = Gio.Settings.new(config.APP_ID)
network_rows = network_panel(context, settings).build()
assert next(row for row in network_rows if row.label_text == "Choose a network").selectable
advanced_input_rows = advanced_input_panel(context, settings).build()
assert next(
    row for row in advanced_input_rows if row.label_text == "HDMI-CEC input"
).selectable
# Still portal-only: mutter injection is one of the two things withheld,
# so the compositor choice must not appear inside the sandbox.
injection = next(row for row in advanced_input_rows if row.label_text == "Input injection")
assert injection.choices == [("portal", "Ask the desktop")]
system_rows = system_panel(context, settings).build()
assert next(row for row in system_rows if row.label_text == "Display and resolution").selectable
# The other withheld one: the host desktop owns the autostart entry.
assert not next(row for row in system_rows if row.label_text == "Start Salon at login").selectable
'

XDG_RUNTIME_DIR="$runtime_dir" WAYLAND_DISPLAY=salon-flatpak-wayland GDK_BACKEND=wayland \
  GSETTINGS_BACKEND=memory \
  timeout 8s flatpak run io.github.alexydaher.Salon >"$runtime_dir/salon.log" 2>&1 &
app_pid=$!
sleep 4
kill -0 "$app_pid"
kill "$app_pid"
wait "$app_pid" || true
! grep -Eiq "traceback|segmentation fault" "$runtime_dir/salon.log"
