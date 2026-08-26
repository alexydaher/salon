// SPDX-License-Identifier: GPL-3.0-or-later
//
// The handful of things every other module needs: element lookup, storage
// that survives private browsing, the toast, haptics, and the accent.

export const $ = (id) => document.getElementById(id);

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// localStorage throws outright in private mode on some browsers rather
// than merely failing to persist, so every access is guarded. Losing the
// remembered tab is not worth losing the page over.
export const store = {
  get(key) {
    try { return localStorage.getItem(key) || ""; } catch (error) { return ""; }
  },
  set(key, value) {
    try {
      if (value) localStorage.setItem(key, value);
      else localStorage.removeItem(key);
    } catch (error) { /* private mode; it just will not survive a reload */ }
  },
};

export function buzz(ms) {
  // Absent on iOS Safari, which has no vibration API at all — so the
  // haptics on this page are an Android enhancement, not a signal anyone
  // is allowed to depend on.
  if (navigator.vibrate) navigator.vibrate(ms);
}

let toastTimer = null;

export function toast(message) {
  if (!message) return;
  const node = $("toast");
  node.textContent = message;
  node.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("on"), 2600);
}

// What is readable *on* the accent. The page used to hardcode near-black
// ink on every accented surface — the primary button, a pressed key, the
// selected tab, the close-app button — which is fine for the default amber
// and unreadable the moment somebody picks a deep blue in Settings →
// Appearance. WCAG relative luminance, and a threshold rather than a
// contrast ratio because there are only two inks to choose between.
export function inkOn(colour) {
  const match = /^#?([0-9a-f]{6})$/i.exec((colour || "").trim());
  if (!match) return "#12151A";
  const value = parseInt(match[1], 16);
  const channels = [(value >> 16) & 255, (value >> 8) & 255, value & 255];
  const linear = channels.map((byte) => {
    const part = byte / 255;
    return part <= 0.04045 ? part / 12.92 : ((part + 0.055) / 1.055) ** 2.4;
  });
  const luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
  return luminance > 0.32 ? "#12151A" : "#F7F3EC";
}

let appliedAccent = "";

export function applyAccent(colour) {
  const accent = colour || "#E8A33D";
  if (accent === appliedAccent) return;
  appliedAccent = accent;
  const root = document.documentElement.style;
  root.setProperty("--accent", accent);
  root.setProperty("--on-accent", inkOn(accent));
}

let measuredStrips = "";

// How much room the fixed strips below `main` are taking, published as a
// variable. The toast used to sit at a hardcoded 5.5rem — the tab strip's
// height — and landed squarely on the volume slider whenever the
// now-playing card was up as well.
export function measureStrips() {
  const signature = ["playing", "volume", "tabs"]
    .map((id) => ($(id).offsetParent === null ? 0 : $(id).offsetHeight))
    .join(":");
  if (signature === measuredStrips) return;
  measuredStrips = signature;
  const total = signature.split(":").reduce((sum, part) => sum + Number(part), 0);
  document.documentElement.style.setProperty("--strips", `${total}px`);
}
