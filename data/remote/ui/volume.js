// SPDX-License-Identifier: GPL-3.0-or-later
//
// Above the tabs and on every pane, because volume is the one control that
// is guaranteed to work whatever is on the television — it acts on the
// system's audio, not on a window. It is also the control a touchscreen is
// unambiguously better at than a physical remote, which is why this is a
// slider and not two more repeat-buttons.

import { $, buzz } from "./dom.js";
import { post } from "./transport.js";
import { pollSoon } from "./feed.js";

// One request per 60ms while the thumb is down. A range input fires on
// every pixel, and a slider dragged across the screen would otherwise be
// two hundred requests, each of which spawns a `wpctl` on the television.
const THROTTLE_MS = 60;

let dragging = false;
let timer = null;

function sendLevel() {
  clearTimeout(timer);
  timer = setTimeout(() => {
    post("/volume", { level: Number($("vol").value) / 100 });
  }, THROTTLE_MS);
}

export function renderVolume(data) {
  const strip = $("volume");
  const known = typeof data.volume === "number" && data.volume >= 0;
  strip.classList.toggle("on", known);
  if (!known) return;
  // Not while a thumb is on it: writing the television's value back into
  // the slider mid-drag is what makes a remote slider fight the finger
  // holding it.
  if (!dragging) $("vol").value = Math.round(data.volume * 100);
  const muted = Boolean(data.muted);
  $("mute").classList.toggle("muted", muted);
  $("mute").querySelector("use").setAttribute("href", muted ? "#i-mute" : "#i-volume");
  strip.classList.toggle("off", muted);
}

export function bindVolume() {
  $("vol").addEventListener("input", () => {
    dragging = true;
    sendLevel();
  });
  for (const name of ["change", "pointerup", "pointercancel"]) {
    $("vol").addEventListener(name, () => {
      dragging = false;
      sendLevel();
    });
  }
  $("mute").addEventListener("click", () => {
    buzz(8);
    post("/volume", { mute: true });
    pollSoon();
  });
}
