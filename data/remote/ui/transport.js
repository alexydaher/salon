// SPDX-License-Identifier: GPL-3.0-or-later
//
// Every request the page makes, and the one piece of state that says
// whether the television is answering at all.

import { $, toast } from "./dom.js";
import { emit } from "./bus.js";
import { session } from "./session.js";

// How long to wait before the next poll while the television is not
// answering. Backs off so a phone left on the remote with Salon shut down
// is not making a request a second all night, and resets the moment it
// answers again.
const BACKOFF_MS = [1000, 2000, 4000, 8000, 15000, 30000];
let misses = 0;

export function setLive(value) {
  if (value) misses = 0;
  if (session.live === value) return;
  session.live = value;
  $("dot").classList.toggle("stale", !value);
  $("offline").classList.toggle("on", !value);
  if (!value) {
    $("offline-text").textContent =
      "Salon isn't answering. Still on the same Wi-Fi? Still switched on?";
  }
}

export function backoff() {
  misses = Math.min(misses + 1, BACKOFF_MS.length - 1);
  return BACKOFF_MS[misses];
}

export function resetBackoff() {
  misses = 0;
}

export async function post(path, extra) {
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ key: session.key }, extra)),
    });
    if (response.ok) {
      setLive(true);
      return await response.json().catch(() => ({}));
    }
    const text = await response.text();
    if (isGone(response.status)) {
      // The session is gone rather than unreachable: a new code has been
      // minted on the television, or this one was burned.
      emit("session-lost", text);
    } else {
      toast(text);
    }
    setLive(true);
    return null;
  } catch (error) {
    setLive(false);
    return null;
  }
}

export function isGone(status) {
  return status === 401 || status === 403 || status === 429;
}

// Two callers want the raw response rather than a parsed body: the state
// poll, which treats 204 as "nothing changed", and /connect, which is the
// one request made without a session.
export async function get(path) {
  return fetch(path);
}
