// SPDX-License-Identifier: GPL-3.0-or-later

import { $, buzz } from "./dom.js";
import { rememberTab, session, TABS } from "./session.js";

let onShow = () => {};

export function showTab(name) {
  if (!TABS.includes(name)) return;
  rememberTab(name);
  for (const button of document.querySelectorAll("[data-tab]")) {
    button.classList.toggle("on", button.dataset.tab === name);
  }
  for (const pane of document.querySelectorAll(".pane")) {
    pane.classList.toggle("on", pane.id === `pane-${name}`);
  }
  onShow(name);
}

export function currentTab() {
  return session.tab;
}

export function bindTabs(handler) {
  onShow = handler;
  for (const button of document.querySelectorAll("[data-tab]")) {
    button.addEventListener("click", () => {
      buzz(6);
      showTab(button.dataset.tab);
    });
  }
}
