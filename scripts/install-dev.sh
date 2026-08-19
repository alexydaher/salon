#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Point GNOME's Show Applications at the *working tree* instead of a
# snapshot.
#
# `meson install` copies the whole source tree into $prefix, so the Salon
# icon in the shell keeps launching whatever the last install captured —
# every edit needs a re-install before the desktop entry catches up, and
# forgetting is silent (you just test the old build). This writes a desktop
# entry whose Exec is the uninstalled dev launcher, `bin/salon`, which
# rebuilds and then runs ./build. After running this once, the shell's Salon
# icon is always the current source.
#
#   ./scripts/install-dev.sh          # link the shell entry to this checkout
#   ./scripts/install-dev.sh --undo   # remove it again
#
# The real `meson install` path is untouched and still the right thing for
# an actual deployment; the two entries have the same desktop file id, so
# whichever was written last wins. Re-run this after a `meson install` if
# you want the development one back.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID="rocks.salon.Salon"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
ENTRY="$APPS_DIR/$APP_ID.desktop"

if [ "${1:-}" = "--undo" ]; then
  rm -f "$ENTRY"
  update-desktop-database "$APPS_DIR" 2>/dev/null || true
  echo "Removed $ENTRY."
  exit 0
fi

if [ ! -d "$ROOT/build" ]; then
  echo "No build directory. Run: meson setup build" >&2
  exit 1
fi

mkdir -p "$APPS_DIR"
mkdir -p "$ICONS_DIR/scalable/apps" "$ICONS_DIR/symbolic/apps"

# Icons are static; a symlink keeps them current for free.
ln -sf "$ROOT/data/icons/hicolor/scalable/apps/$APP_ID.svg" \
  "$ICONS_DIR/scalable/apps/$APP_ID.svg"
ln -sf "$ROOT/data/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg" \
  "$ICONS_DIR/symbolic/apps/$APP_ID-symbolic.svg"

# Same template the installed entry is built from, with Exec repointed at
# the dev launcher. Keeping the template as the source means the two entries
# can't drift in the fields that matter (StartupWMClass, SingleMainWindow).
sed -e "s|@APP_ID@|$APP_ID|g" \
    -e "s|^Exec=salon$|Exec=$ROOT/bin/salon|" \
    -e "s|^Name=Salon$|Name=Salon (development)|" \
    "$ROOT/data/$APP_ID.desktop.in" > "$ENTRY"

update-desktop-database "$APPS_DIR" 2>/dev/null || true
gtk4-update-icon-cache -q -t -f "$ICONS_DIR" 2>/dev/null || true

echo "Show Applications now launches $ROOT/bin/salon."
echo "It rebuilds ./build on every start, so it is never stale."
