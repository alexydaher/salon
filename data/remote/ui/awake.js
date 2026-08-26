// SPDX-License-Identifier: GPL-3.0-or-later
//
// A remote whose screen sleeps between the pause button and the play button
// is a remote you unlock twice per film.

import { $ } from "./dom.js";

let lock = null;

export async function keepAwake() {
  if (document.hidden) return;
  // The real API first. It is present on localhost and would be present if
  // this were ever served over HTTPS, and it is the only one of the two
  // that the operating system actually knows about.
  if ("wakeLock" in navigator) {
    try {
      lock = await navigator.wakeLock.request("screen");
      return;
    } catch (error) {
      lock = null;
    }
  }
  playAwake();
}

// Autoplay of a muted video is normally allowed, but "normally" is doing
// work there: a page opened from a scanned QR has had no gesture at all,
// and some browsers still refuse. The next tap tries again, and on a remote
// control there is always a next tap.
function playAwake() {
  const video = $("awake");
  if (!video) return;
  const attempt = video.play();
  if (attempt) {
    attempt.catch(() => {
      document.addEventListener("pointerdown", playAwake, { once: true });
    });
  }
}

export function releaseAwake() {
  if (lock) {
    lock.release().catch(() => {});
    lock = null;
  }
  const video = $("awake");
  if (video) video.pause();
}
