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

// One glyph out of the page's sprite. `createElementNS`, not `innerHTML`:
// an <svg> built with the HTML parser lands in the wrong namespace and
// renders as nothing at all.
export function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "i");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#${name}`);
  svg.append(use);
  return svg;
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

let measuredSearch = 0;

// How tall the sticky search row actually is. Every row heading sticks
// under it and every `scrollIntoView` on the Browse pane has to clear it,
// and the 3.2rem those two used to assume was short by about half a rem —
// which is why jumping to a letter hid that letter and the row below it.
export function measureSearchRow() {
  const height = $("search-row").offsetHeight;
  if (!height || height === measuredSearch) return;
  measuredSearch = height;
  document.documentElement.style.setProperty("--search-h", `${height}px`);
}

let measuredHeader = 0;

// How tall the header actually is. The volume popover hangs off the bottom
// of it, and the header is no longer one fixed row: the now-playing pill
// takes a second line on a narrow screen, and the 3.5rem the popover used
// to assume put it over the track title it had just pushed down there.
export function measureHeader() {
  const height = $("chrome").offsetHeight;
  if (!height || height === measuredHeader) return;
  measuredHeader = height;
  document.documentElement.style.setProperty("--header-h", `${height}px`);
}

let measuredStrips = "";

// How much room the tab strip below `main` is taking, published as a
// variable so the toast stays immediately above it in either orientation.
export function measureStrips() {
  const signature = ["tabs"]
    .map((id) => ($(id).offsetParent === null ? 0 : $(id).offsetHeight))
    .join(":");
  if (signature === measuredStrips) return;
  measuredStrips = signature;
  const total = signature.split(":").reduce((sum, part) => sum + Number(part), 0);
  document.documentElement.style.setProperty("--strips", `${total}px`);
}

let measuredViewport = 0;
let viewportSettleFrame = 0;
let viewportSettleUntil = 0;

// iOS browsers can lay 100dvh out against a viewport origin left behind by
// their collapsing toolbars. The result is symmetrical: the top of the app
// is unreachable and the same amount of empty document shows at the bottom.
// VisualViewport is the browser's actual unobscured rectangle. Do not follow
// it while pinch-zoomed, since that would counteract an accessibility zoom.
export function measureViewport() {
  const viewport = window.visualViewport;
  if (viewport && Math.abs(viewport.scale - 1) > 0.01) return;
  const height = Math.round(viewport ? viewport.height : window.innerHeight);
  if (height && height !== measuredViewport) {
    measuredViewport = height;
    document.documentElement.style.setProperty("--viewport-h", `${height}px`);
  }
  // This shell has its own scrollports. A restored document scroll only
  // moves the whole remote under the browser chrome and exposes its root.
  if (window.scrollX || window.scrollY) window.scrollTo(0, 0);
}

// A first navigation is not one layout event on mobile. The address bar,
// manifest mode and safe-area geometry can settle after `pageshow`, and some
// browsers do not emit another VisualViewport resize for the final value.
// Sample only through that short startup window; the normal event listeners
// take over afterwards, so an idle remote does not keep drawing frames.
export function settleViewport() {
  viewportSettleUntil = performance.now() + 1500;
  if (viewportSettleFrame) return;

  const tick = () => {
    measureViewport();
    if (performance.now() < viewportSettleUntil) {
      viewportSettleFrame = requestAnimationFrame(tick);
    } else {
      viewportSettleFrame = 0;
    }
  };
  tick();
}
