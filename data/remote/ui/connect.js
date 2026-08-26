// SPDX-License-Identifier: GPL-3.0-or-later
//
// Getting in, and being thrown out. Two credentials: the four-digit code is
// a bootstrap accepted at /connect and nowhere else, and what comes back is
// the session token every later request carries.

import { $ } from "./dom.js";
import { rememberKey, session } from "./session.js";
import { setLive } from "./transport.js";
import { startFeed, stopFeed } from "./feed.js";
import { keepAwake } from "./awake.js";
import { showTab } from "./tabs.js";
import { closeSheet } from "./sheet.js";
import { clearSearch } from "./search.js";
import { closeBrowsing, forgetAllApps } from "./allapps.js";
import { closeNowPlaying } from "./nowplaying.js";

function showRemote(visible) {
  $("connect").style.display = visible ? "none" : "";
  $("chrome").hidden = !visible;
  $("body").hidden = !visible;
  $("tabs").hidden = !visible;
}

export async function connect(credential) {
  const body = /^[0-9]{4}$/.test(credential) ? { code: credential } : { key: credential };
  let response;
  try {
    response = await fetch("/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    $("connect-status").textContent = "Could not reach Salon. Same Wi-Fi?";
    return false;
  }
  if (!response.ok) {
    $("connect-status").textContent = await response.text();
    return false;
  }
  const data = await response.json();
  rememberKey(data.key);
  showRemote(true);
  $("connect-status").textContent = "";
  showTab(session.tab);
  setLive(true);
  startFeed();
  keepAwake();
  return true;
}

// The session is gone rather than unreachable: a new code has been minted
// on the television, or this one was burned by wrong guesses.
export function dropSession(message) {
  rememberKey("");
  stopFeed();
  showRemote(false);
  closeSheet();
  clearSearch();
  closeBrowsing();
  forgetAllApps();
  closeNowPlaying();
  $("playing").classList.remove("on");
  $("volume").classList.remove("on");
  document.body.classList.remove("in-app");
  $("connect-status").textContent = message || "";
  $("code").value = "";
}

export function bindConnect() {
  $("connect-go").addEventListener("click", () => {
    const code = $("code").value.trim();
    if (!/^[0-9]{4}$/.test(code)) {
      $("connect-status").textContent = "Four digits, as shown on the television.";
      return;
    }
    connect(code);
  });
  // Four digits is the whole form; making someone reach for a button after
  // the last one is a step that exists for no reason.
  $("code").addEventListener("input", () => {
    if (/^[0-9]{4}$/.test($("code").value.trim())) $("connect-go").click();
  });
  $("code").addEventListener("keydown", (event) => {
    if (event.key === "Enter") $("connect-go").click();
  });
}
