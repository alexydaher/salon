// SPDX-License-Identifier: GPL-3.0-or-later
//
// Wiring. Nothing below this file imports anything above it, and the two
// directions that would otherwise be a cycle — the feed handing a snapshot
// to the renderer, and the renderer asking the feed to poll again — meet
// here through `bus.js`.

import {
  $, buzz, measureHeader, measureSearchRow, measureStrips, measureViewport,
  settleViewport, toast,
} from "./dom.js";
import { on } from "./bus.js";
import { readLaunchOptions, session } from "./session.js";
import { post, resetBackoff } from "./transport.js";
import { pollSoon, startFeed, stopFeed } from "./feed.js";
import { render } from "./render.js";
import { bindCatalog } from "./catalog.js";
import { bindSearch, clearSearch } from "./search.js";
import { bindAllApps } from "./allapps.js";
import { bindSheet, openSheet } from "./sheet.js";
import { bindKeys } from "./keys.js";
import { bindDpad } from "./dpad.js";
import { bindPad } from "./pad.js";
import { bindTyping, closeTypeDrawer, focusTypeField } from "./typing.js";
import { bindVolume, closeVolume } from "./volume.js";
import { bindNowPlaying, closeNowPlaying } from "./nowplaying.js";
import { bindTune } from "./tune.js";
import { bindTabs, showTab } from "./tabs.js";
import { keepAwake, releaseAwake } from "./awake.js";
import { bindConnect, connect, dropSession } from "./connect.js";

on("state", render);
on("session-lost", dropSession);

bindConnect();
bindTabs((name) => {
  if (name === "type") focusTypeField(session.state);
  if (name !== "remote") closeNowPlaying();
  // The keyboard drawer belongs to Pointer; leaving that pane closes it
  // rather than leaving it to reappear the next time Pointer is opened.
  if (name !== "pad") closeTypeDrawer();
});
bindCatalog(openSheet);
bindSearch(openSheet);
bindAllApps(openSheet, clearSearch);
bindSheet((tile) => {
  buzz(12);
  post("/launch", { id: tile.id }).then((result) => {
    if (result) toast(`Opening ${tile.title}`);
    pollSoon();
  });
});
bindKeys(pollSoon);
bindDpad();
bindPad($("pad"));
bindTyping();
bindVolume(closeNowPlaying);
bindNowPlaying(() => {
  closeVolume();
  closeTypeDrawer();
});
bindTune();

$("retry").addEventListener("click", () => {
  resetBackoff();
  $("offline-text").textContent = "Trying…";
  startFeed();
});

// The content measurements are taken during a render, and a render only
// happens when the television says something changed — so turning the phone
// on its side re-laid the page out and left every one of them describing the
// orientation before it.
window.addEventListener("resize", () => {
  measureViewport();
  measureStrips();
  measureSearchRow();
  measureHeader();
});
window.visualViewport?.addEventListener("resize", measureViewport);
window.visualViewport?.addEventListener("scroll", measureViewport);
window.visualViewport?.addEventListener("scrollend", measureViewport);
window.addEventListener("scroll", measureViewport, { passive: true });
window.addEventListener("pageshow", settleViewport);

// Polling while the phone is in a pocket is a request a second for nothing.
document.addEventListener("visibilitychange", () => {
  if (!session.key) return;
  if (document.hidden) {
    stopFeed();
    releaseAwake();
  } else {
    startFeed();
    keepAwake();
  }
});

settleViewport();
readLaunchOptions();
showTab(session.tab);

if (session.key) {
  // Scanned or remembered, not typed. Validate before showing the remote,
  // so a stale token from a previous session lands on the code screen
  // rather than on a page whose every button fails.
  $("connect").style.display = "none";
  connect(session.key).then((ok) => {
    if (!ok) $("connect").style.display = "";
  });
}
