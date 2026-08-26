// SPDX-License-Identifier: GPL-3.0-or-later
//
// How the phone finds out what the television is doing. Two paths, both
// reading the same feed on the server so they cannot disagree:
//
// `GET /events` is server-sent events — told rather than asking, which is
// what keeps the mirrored cursor up with the thumb. `GET /state` is a one
// second poll answering 204 when nothing changed, and it is the fallback,
// because a held connection is exactly the thing a phone breaks: a screen
// lock, a Wi-Fi roam, a tab eviction and a captive portal all end one, some
// of them silently.

import { emit } from "./bus.js";
import { session } from "./session.js";
import { backoff, isGone, setLive } from "./transport.js";

// The things that change — the cursor, what is playing, which screen is in
// front — are all things a person glances at, not things they track frame
// by frame, and an unchanged poll costs a 204 with no body.
const POLL_MS = 1000;

let pollTimer = null;
let stream = null;
let streamOk = false;

function accept(data) {
  session.version = data.v;
  session.state = data;
  emit("state", data);
  setLive(true);
}

export async function poll() {
  try {
    const url = `/state?k=${encodeURIComponent(session.key)}&v=${session.version}`;
    const response = await fetch(url);
    if (response.status === 204) {
      setLive(true);
      return;
    }
    if (isGone(response.status)) {
      emit("session-lost", await response.text());
      return;
    }
    if (!response.ok) return;
    accept(await response.json());
  } catch (error) {
    setLive(false);
  }
}

// A self-scheduling loop rather than setInterval: the gap has to change
// when the television stops answering, and an interval cannot do that
// without being torn down and rebuilt anyway.
export function startPolling() {
  stopPolling();
  const tick = async () => {
    await poll();
    if (!session.key) return;
    pollTimer = setTimeout(tick, session.live ? POLL_MS : backoff());
  };
  tick();
}

export function stopPolling() {
  if (pollTimer !== null) clearTimeout(pollTimer);
  pollTimer = null;
}

export function startStream() {
  if (!session.key || !window.EventSource) return;
  stopStream();
  try {
    stream = new EventSource(`/events?k=${encodeURIComponent(session.key)}`);
  } catch (error) {
    stream = null;
    return;
  }
  stream.addEventListener("open", () => {
    streamOk = true;
    setLive(true);
    // Only now is the poll redundant. Stopping it before the stream is
    // actually open would leave a phone with neither if /events is refused.
    stopPolling();
  });
  stream.addEventListener("message", (event) => {
    let data = null;
    try { data = JSON.parse(event.data); } catch (error) { return; }
    accept(data);
  });
  stream.addEventListener("error", () => {
    // EventSource retries by itself, and would go on doing so forever
    // against a television that has been switched off. One failure is
    // enough to go back to the poll, which knows how to back off and how
    // to say "Salon isn't answering".
    stopStream();
    if (session.key) startPolling();
  });
}

export function stopStream() {
  if (stream) stream.close();
  stream = null;
  streamOk = false;
}

// A press changes what is on the television; waiting up to a second to
// find out makes the cursor mirror feel broken even though it is correct.
export function pollSoon() {
  // The stream will say so by itself, and sooner.
  if (streamOk) return;
  setTimeout(poll, 90);
}

export function startFeed() {
  // The poll first, always: it is what proves the television is there. The
  // stream takes over from it once it is actually open.
  startPolling();
  startStream();
}

export function stopFeed() {
  stopPolling();
  stopStream();
}
