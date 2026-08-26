// SPDX-License-Identifier: GPL-3.0-or-later
//
// The trackpad. The gesture vocabulary, and why each one is here:
//
//   one finger, drag        move the pointer
//   one finger, tap         left click
//   two fingers, drag       scroll  — the gesture everyone tries first
//   two fingers, tap        right click
//   three fingers, tap      middle click (paste on X11, close a browser tab)
//   long press, then drag   hold the left button down and move: this is
//                           what selects text and drags a window, and a tap
//                           that releases itself 50ms later never could
//   double-tap, then drag   the same, for the hand that learned it on a
//                           laptop
//
// All of it goes through the same RemoteDesktop grant the right stick uses,
// so a phone is a mouse over a browser tile that was never built for a
// remote — which is the whole reason the trackpad exists.

import { buzz } from "./dom.js";
import { post } from "./transport.js";

const TAP_SLOP_PX = 12;        // a finger on glass always moves a little
const TAP_MS = 350;            // longer than this and it was not a tap
const HOLD_MS = 500;           // press-and-hold before a drag begins
const DOUBLE_TAP_MS = 300;
// A finger travels far more pixels than a wheel does clicks. This turns
// the drag into scroll units the compositor recognises without a flick
// throwing the page to the bottom.
const SCROLL_DIVISOR = 2.2;

// Pointer acceleration. Motion used to go through at 1:1, which means a
// 350px pad driving a 3840px television needs eleven full swipes to cross
// it — the surface worked perfectly and was unusable. A speed-dependent
// gain is the same curve every laptop trackpad applies: slow movement
// stays exactly 1:1 so a button is still aimable, and a flick multiplies.
const ACCEL_PER_PX_MS = 1.9;
const MAX_GAIN = 4.5;

function gainFor(distance, elapsed) {
  if (elapsed <= 0) return 1;
  const speed = distance / elapsed;  // pixels per millisecond
  return Math.min(MAX_GAIN, 1 + ACCEL_PER_PX_MS * speed);
}

export function bindPad(surface) {
  let touches = 0;        // the most fingers seen during this gesture
  let last = null;
  let lastAt = 0;
  let startedAt = 0;
  let travelled = 0;
  let dx = 0;
  let dy = 0;
  let sx = 0;
  let sy = 0;
  let queued = false;
  let holding = false;    // the left button is down and we are dragging
  let holdTimer = null;
  let lastTapAt = 0;
  let scrolled = false;

  // One post per animation frame. A touchmove stream is far faster than
  // the network, and posting every event turns a flick into a queue of
  // requests that arrive after the finger has stopped.
  const flush = () => {
    queued = false;
    const body = {};
    if (dx || dy) { body.dx = dx; body.dy = dy; dx = dy = 0; }
    if (sx || sy) { body.sx = sx; body.sy = sy; sx = sy = 0; }
    if (body.dx || body.dy || body.sx || body.sy) post("/pointer", body);
  };

  const queue = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(flush);
  };

  const releaseHold = () => {
    clearTimeout(holdTimer);
    holdTimer = null;
    if (!holding) return;
    holding = false;
    post("/pointer", { hold: "up", button: "left" });
  };

  const centre = (event) => {
    // The midpoint of however many fingers are down, so a two-finger drag
    // does not lurch when one of them lands a frame after the other.
    let x = 0;
    let y = 0;
    for (const touch of event.touches) { x += touch.clientX; y += touch.clientY; }
    const count = event.touches.length || 1;
    return { clientX: x / count, clientY: y / count };
  };

  surface.addEventListener("touchstart", (event) => {
    event.preventDefault();
    touches = Math.max(touches, event.touches.length);
    last = centre(event);
    lastAt = event.timeStamp;
    if (event.touches.length === 1) {
      startedAt = Date.now();
      travelled = 0;
      scrolled = false;
      surface.classList.add("live");
      // A second tap in quick succession, held: drag. The browser will not
      // tell us this happened, so the first tap's timestamp is kept.
      if (Date.now() - lastTapAt < DOUBLE_TAP_MS) {
        holding = true;
        buzz(12);
        post("/pointer", { hold: "down", button: "left" });
      } else {
        holdTimer = setTimeout(() => {
          holdTimer = null;
          if (travelled >= TAP_SLOP_PX || touches > 1) return;
          holding = true;
          buzz(18);
          post("/pointer", { hold: "down", button: "left" });
        }, HOLD_MS);
      }
    }
    if (event.touches.length > 1) {
      // Two fingers means scroll, not drag — including if a hold had
      // already started, because that was a misread of the first finger.
      clearTimeout(holdTimer);
      holdTimer = null;
      releaseHold();
      surface.classList.add("scrolling");
    }
  }, { passive: false });

  surface.addEventListener("touchmove", (event) => {
    event.preventDefault();
    const point = centre(event);
    if (last) {
      const mx = point.clientX - last.clientX;
      const my = point.clientY - last.clientY;
      const step = Math.hypot(mx, my);
      travelled += Math.abs(mx) + Math.abs(my);
      if (event.touches.length >= 2) {
        // Inverted, and on purpose: dragging two fingers *up* pushes the
        // content up, which is what the same gesture does on every laptop
        // trackpad and on the phone's own screen. Deliberately not
        // accelerated — a scroll is a distance, not a nudge at a target.
        sx -= mx / SCROLL_DIVISOR;
        sy -= my / SCROLL_DIVISOR;
        scrolled = true;
      } else {
        const gain = gainFor(step, event.timeStamp - lastAt);
        dx += mx * gain;
        dy += my * gain;
      }
      queue();
    }
    last = point;
    lastAt = event.timeStamp;
  }, { passive: false });

  const end = (event) => {
    event.preventDefault();
    last = event.touches.length ? centre(event) : null;
    if (event.touches.length) return;  // some fingers are still down

    surface.classList.remove("live", "scrolling");
    clearTimeout(holdTimer);
    holdTimer = null;
    const quick = Date.now() - startedAt < TAP_MS;
    const still = travelled < TAP_SLOP_PX;
    const wasHolding = holding;
    releaseHold();

    if (!wasHolding && quick && still && !scrolled) {
      // Which button depends on how many fingers took part, which is why
      // `touches` is the high-water mark rather than the current count:
      // by the time the last finger lifts, the others are already gone.
      const button = touches >= 3 ? "middle" : touches === 2 ? "right" : "left";
      buzz(button === "left" ? 8 : 14);
      post("/pointer", { click: true, button: button });
      if (button === "left") lastTapAt = Date.now();
    }
    if (scrolled) post("/pointer", { scrollEnd: true });
    touches = 0;
  };

  surface.addEventListener("touchend", end, { passive: false });
  surface.addEventListener("touchcancel", end, { passive: false });
}
