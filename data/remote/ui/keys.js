// SPDX-License-Identifier: GPL-3.0-or-later
//
// Everything that posts an `Action` or a transport command: the D-pad's
// four keys, OK, the bars either side of it, and the two controls in the
// header whose meaning never changes.

import { $, buzz } from "./dom.js";
import { session } from "./session.js";
import { post } from "./transport.js";
import { pollSoon } from "./feed.js";

// How far a finger may drift and still count as a press rather than the
// beginning of a swipe across the pad.
const SLOP_PX = 12;
const FALLBACK_TIMING = { delay: 400, interval: 120 };

function timing() {
  return (session.state && session.state.repeat) || FALLBACK_TIMING;
}

export function sendAction(name) {
  post("/action", { action: name });
  pollSoon();
}

// Press-and-hold, at the cadence the user chose in Settings → Input, so a
// held direction on the phone accelerates exactly like a held direction on
// a controller. §6.2: six repeats at the chosen interval, then half it.
function bindRepeat(button) {
  const action = button.dataset.action;
  const repeats = "repeat" in button.dataset;
  // OK is the one key that fires on the way *up*. Everything else answers
  // on the way down, which is what a remote button has to do — but the
  // middle of the pad is also where a swipe starts, and a centre-origin
  // swipe that selected something first would make the gesture unusable.
  const onRelease = "onRelease" in button.dataset;
  let delayTimer = null;
  let tickTimer = null;
  let fired = 0;
  let armed = false;
  let origin = null;

  const stop = () => {
    clearTimeout(delayTimer);
    clearTimeout(tickTimer);
    delayTimer = tickTimer = null;
    fired = 0;
    armed = false;
    button.classList.remove("pressed");
  };

  const tick = () => {
    sendAction(action);
    fired += 1;
    const chosen = timing();
    tickTimer = setTimeout(tick, fired >= 6 ? chosen.interval / 2 : chosen.interval);
  };

  button.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    if (button.disabled) return;
    armed = true;
    origin = { x: event.clientX, y: event.clientY };
    button.classList.add("pressed");
    buzz(8);
    if (onRelease) return;
    sendAction(action);
    if (repeats) delayTimer = setTimeout(tick, timing().delay);
  });

  button.addEventListener("pointermove", (event) => {
    if (!armed || origin === null) return;
    const travelled =
      Math.abs(event.clientX - origin.x) + Math.abs(event.clientY - origin.y);
    if (travelled > SLOP_PX) stop();
  });

  button.addEventListener("pointerup", () => {
    if (armed && onRelease) sendAction(action);
    stop();
  });
  for (const name of ["pointercancel", "pointerleave"]) {
    button.addEventListener(name, stop);
  }
  // A press that survives the page losing focus would repeat forever.
  window.addEventListener("blur", stop);
}

export function bindKeys(onCloseApp) {
  for (const button of document.querySelectorAll("[data-action]")) bindRepeat(button);

  for (const button of document.querySelectorAll("[data-transport]")) {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      buzz(8);
      post("/transport", { what: button.dataset.transport });
      pollSoon();
    });
  }

  // The same MENU a controller's START sends, which the television turns
  // into "close the child and come back". Not a new verb: the press arrives
  // over HTTP into Salon's own process, so unlike a keyboard it does not
  // need the compositor's focus to be heard.
  $("close-app").addEventListener("click", () => {
    buzz(14);
    const node = $("close-app");
    node.classList.add("pressed");
    setTimeout(() => node.classList.remove("pressed"), 180);
    sendAction("menu");
    onCloseApp();
  });
}
