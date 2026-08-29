// SPDX-License-Identifier: GPL-3.0-or-later
//
// What this phone is, as far as the television is concerned: the session
// credential, the last snapshot, and the tab the thumb was last on.

import { store } from "./dom.js";

// Where the credential lives between page loads. It has to survive one:
// Android discards backgrounded tabs, "Add to Home Screen" relaunches from
// scratch, and pull-to-refresh is one thumb away — and the token is
// stripped from the address bar below, so without this every one of those
// dropped you back to the code screen. Storing it is not a weakening: it
// is the phone's own remote, and anyone who can read this phone's storage
// can already read the screen it is displayed on.
const KEY_STORE = "salon.key";
const TAB_STORE = "salon.tab";

export const TABS = ["apps", "remote", "pad"];

export const session = {
  key: "",
  tab: "apps",
  version: 0,
  // The last snapshot the television sent, or null before the first one.
  state: null,
  live: false,
};

export function rememberKey(value) {
  session.key = value;
  store.set(KEY_STORE, value);
}

export function rememberTab(name) {
  session.tab = name;
  store.set(TAB_STORE, name);
}

// The fragment wins over the remembered token: scanning a fresh QR is how
// you replace a stale one. A fragment is never sent to a server, which is
// the whole reason the television puts the credential there.
export function readLaunchOptions() {
  const params = new URLSearchParams(location.hash.slice(1));
  session.key = params.get("k") || store.get(KEY_STORE);
  // The remembered tab, because whoever uses this as a trackpad uses it as
  // a trackpad every time and should not have to say so again; overridable
  // from the fragment so a home-screen shortcut can point straight at one.
  const stored = params.get("tab") || store.get(TAB_STORE) || "apps";
  // Old home-screen shortcuts used `type`; typing now opens inside Pointer.
  const wanted = stored === "type" ? "pad" : stored;
  session.tab = TABS.includes(wanted) ? wanted : "apps";
  // Off the address bar immediately: the credential should not survive in
  // history, in a screenshot of the phone, or in whatever the browser
  // syncs between devices.
  if (location.hash) history.replaceState(null, "", location.pathname);
}
