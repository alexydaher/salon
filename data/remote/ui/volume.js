// SPDX-License-Identifier: GPL-3.0-or-later
//
// The header keeps volume one tap away without charging every pane the
// height of a slider. The popover closes on an outside tap or Escape, like
// the native compact controls phones already use.

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
  const known = typeof data.volume === "number" && data.volume >= 0;
  $("hdr-volume").hidden = !known;
  if (!known) {
    closeVolume();
    return;
  }
  // Not while a thumb is on it: writing the television's value back into
  // the slider mid-drag is what makes a remote slider fight the finger
  // holding it.
  if (!dragging) $("vol").value = Math.round(data.volume * 100);
  const muted = Boolean(data.muted);
  for (const id of ["mute", "hdr-volume"]) {
    $(id).classList.toggle("muted", muted);
    $(id).querySelector("use").setAttribute("href", muted ? "#i-mute" : "#i-volume");
  }
  $("mute").setAttribute("aria-label", muted ? "Unmute" : "Mute");
  $("hdr-volume").setAttribute("aria-label", muted ? "Volume, muted" : "Volume");
  $("volume").classList.toggle("off", muted);
}

export function closeVolume() {
  $("volume").classList.remove("on");
  $("hdr-volume").classList.remove("open");
  $("hdr-volume").setAttribute("aria-expanded", "false");
}

export function bindVolume(onOpen = () => {}) {
  $("hdr-volume").addEventListener("click", () => {
    const opening = !$("volume").classList.contains("on");
    closeVolume();
    if (!opening) return;
    onOpen();
    $("volume").classList.add("on");
    $("hdr-volume").classList.add("open");
    $("hdr-volume").setAttribute("aria-expanded", "true");
  });
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
  document.addEventListener("pointerdown", (event) => {
    if (!$("volume").contains(event.target) && !$("hdr-volume").contains(event.target)) {
      closeVolume();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeVolume();
  });
}
