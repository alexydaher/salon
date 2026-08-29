// SPDX-License-Identifier: GPL-3.0-or-later

import { $, buzz, store } from "./dom.js";
import { rememberTab, session, TABS } from "./session.js";

let onShow = () => {};
const POINTER_HELP_STORE = "salon.pointer-help";
let helpTimer = null;

export function showTab(name) {
  if (!TABS.includes(name)) return;
  rememberTab(name);
  for (const button of document.querySelectorAll("[data-tab]")) {
    button.classList.toggle("on", button.dataset.tab === name);
  }
  for (const pane of document.querySelectorAll(".pane")) {
    pane.classList.toggle("on", pane.id === `pane-${name}`);
  }
  // Which pane is showing, for the things drawn *outside* `main` and so out
  // of reach of a sibling selector. The A-Z rail is one: it is fixed to the
  // viewport, and browsing the list and then tapping Remote left an index
  // for an invisible list floating over the D-pad.
  document.body.dataset.tab = name;
  if (name === "pad" && !store.get(POINTER_HELP_STORE)) {
    $("gesture-help").open = true;
    store.set(POINTER_HELP_STORE, "seen");
    helpTimer = setTimeout(() => { $("gesture-help").open = false; }, 4500);
  } else if (name !== "pad") {
    clearTimeout(helpTimer);
    $("gesture-help").open = false;
  }
  onShow(name);
}

export function currentTab() {
  return session.tab;
}

export function bindTabs(handler) {
  onShow = handler;
  $("gesture-help").querySelector("summary").addEventListener("click", () => {
    clearTimeout(helpTimer);
  });
  for (const button of document.querySelectorAll("[data-tab]")) {
    button.addEventListener("click", () => {
      buzz(6);
      showTab(button.dataset.tab);
    });
  }
}
