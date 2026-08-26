// SPDX-License-Identifier: GPL-3.0-or-later
//
// One snapshot in, the whole page updated. Everything with real drawing in
// it lives in its own module; what is left here is the header, the two
// one-shot transitions, and the order the rest happen in.

import { $, applyAccent, measureStrips } from "./dom.js";
import { session } from "./session.js";
import { renderCatalog, renderFocus, renderMirror } from "./catalog.js";
import { renderVolume } from "./volume.js";
import { renderPlaying } from "./nowplaying.js";
import { focusTypeField, renderTyping } from "./typing.js";
import { showTab } from "./tabs.js";

const SCREEN_NAMES = {
  home: "Home",
  search: "Search",
  apps: "All apps",
  settings: "Settings",
  menu: "Menu",
  keyboard: "Text entry",
};

let wasInApp = false;
let wantedText = false;

// Everything that changes when an application is covering the television.
// Salon deliberately goes quiet while one is in front — a native app reads
// the same gamepad device directly, so fighting it for button presses is
// not a thing Salon can win — which means the D-pad, OK, Back, Search and
// Options genuinely do nothing. This is the page saying so instead of
// offering nine buttons of which two work.
function renderHeader(data) {
  const app = data.app || "";
  const inApp = Boolean(app);
  document.body.classList.toggle("in-app", inApp);
  $("screen").textContent = inApp
    ? app
    : SCREEN_NAMES[data.screen] || data.screen;
  $("close-app").hidden = !inApp;
  // MENU *is* "close the app" while one is in front, so two buttons doing
  // the same thing would be two things to work out. The named one wins.
  $("hdr-menu").hidden = inApp;
  $("close-app").querySelector(".app-name").textContent = `Close ${app}`;
  for (const node of document.querySelectorAll("[data-tv-only]")) node.disabled = inApp;

  // Move to the pointer *once*, on the transition, and only from a pane
  // that has just gone useless. Doing it on every render would fight anyone
  // who deliberately went to Apps to launch something else; not doing it at
  // all leaves a thumb resting on a dead D-pad.
  if (inApp && !wasInApp && (session.tab === "remote" || session.tab === "apps")) {
    showTab("pad");
  }
  wasInApp = inApp;
}

function renderPad(data) {
  $("pad").textContent = data.remoteInput
    ? "Drag to move the pointer · tap to click"
    : "Salon isn't allowed to move the pointer. Settings → Input → "
      + "Gamepad cursor.";
  for (const node of document.querySelectorAll("#click-left, #click-right")) {
    node.disabled = !data.remoteInput;
  }
}

// The television putting a text field on screen is the page's cue to open
// its keyboard. `wants_text` has been in the state payload since the phone
// stopped being only a keyboard, and until now nothing acted on it beyond
// recolouring a hint — so the one moment the phone is unambiguously the
// right tool was the one moment it waited to be asked.
function followTextField(data) {
  const wants = Boolean(data.wantsText);
  if (wants && !wantedText) {
    showTab("type");
    focusTypeField(data);
  }
  wantedText = wants;
}

export function render(data) {
  applyAccent(data.accent);
  renderHeader(data);
  renderVolume(data);
  renderCatalog(data.rows);
  renderFocus(data);
  renderMirror(data);
  renderPlaying(data.playing);
  renderTyping(data);
  renderPad(data);
  followTextField(data);
  measureStrips();
}
