// SPDX-License-Identifier: GPL-3.0-or-later
//
// The D-pad plate is one gesture surface as well as four buttons.
//
// Four arrow keys is how you drive a launcher while looking at your hand.
// Swiping is how you drive one while looking at the television, which is
// the whole point of a remote — so the buttons stay (they are labelled,
// reachable by a screen reader, and they answer on the way down like a
// physical key), and dragging anywhere across the plate emits a step per
// cell crossed on top of them.
//
// The middle key is the reason `data-on-release` exists: a swipe usually
// starts in the centre, and a centre key that fired on the way down would
// select something every time somebody tried to move.

import { $, buzz } from "./dom.js";
import { sendAction } from "./keys.js";

// How far a finger travels per step. A plate is about 300px across, so a
// full swipe is six or seven moves — roughly what a thumb-flick on a phone
// list scrolls, and slow enough that a two-cell correction is possible.
const STEP_PX = 38;

export function bindDpad() {
  const plate = $("dpad");
  let anchor = null;
  let moved = false;

  const release = () => {
    anchor = null;
    moved = false;
    plate.classList.remove("swiping");
  };

  plate.addEventListener("pointerdown", (event) => {
    anchor = { x: event.clientX, y: event.clientY };
    moved = false;
  });

  plate.addEventListener("pointermove", (event) => {
    if (anchor === null) return;
    // Salon goes quiet behind a launched application, so the directions
    // genuinely do nothing there — and a gesture that silently does nothing
    // is worse than a greyed button, which at least says so.
    if (document.body.classList.contains("in-app")) return;
    const dx = event.clientX - anchor.x;
    const dy = event.clientY - anchor.y;
    const horizontal = Math.abs(dx) > Math.abs(dy);
    const travelled = horizontal ? Math.abs(dx) : Math.abs(dy);
    if (travelled < STEP_PX) return;
    // The anchor moves with each step rather than staying at the origin, so
    // one long drag is a run of presses instead of a single one.
    anchor = { x: event.clientX, y: event.clientY };
    if (!moved) {
      moved = true;
      plate.classList.add("swiping");
    }
    buzz(6);
    sendAction(
      horizontal ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up")
    );
  });

  for (const name of ["pointerup", "pointercancel", "pointerleave"]) {
    plate.addEventListener(name, release);
  }
  window.addEventListener("blur", release);
}
