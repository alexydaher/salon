// SPDX-License-Identifier: GPL-3.0-or-later
//
// The card in the header, its play/pause key, and the full player behind
// them. Artwork comes either as a URL the phone loads itself (a streaming
// player publishes an https one) or from /np-art, for a player whose art is
// a file on the television.

import { $, measureHeader } from "./dom.js";
import { session } from "./session.js";

// Null rather than "": the first render of a player with no cover has to
// actually hide the two <img> elements, and "" as the starting value made
// that the one case the early return swallowed.
let renderedArt = null;

// What the television last said is playing, what the two keys are currently
// drawing, and how long a guess is allowed to stand. `/transport` is
// delivered on an idle and answered 200 before the command runs, so the page
// is never told whether it worked: a key flips its own glyph at once,
// because a remote that waits a round trip feels broken, and puts the truth
// back if no new state has arrived by then.
const OPTIMISTIC_MS = 1500;
let truth = false;
let drawn = null;
let restore = null;

function drawPlaying(value) {
  if (value === drawn) return;
  drawn = value;
  const glyph = value ? "#i-pause" : "#i-play";
  for (const id of ["np-pill-play", "np-big-play"]) {
    $(id).querySelector("use").setAttribute("href", glyph);
  }
}

function coverUrl(playing) {
  if (playing.artUrl) return playing.artUrl;
  if (!playing.art) return "";
  // Keyed on the version so a new track's cover is fetched rather than
  // read out of the cache under the previous one's URL.
  return `/np-art?k=${encodeURIComponent(session.key)}&v=${session.version}`;
}

function applyCover(url) {
  if (url === renderedArt) return;
  renderedArt = url;
  const header = $("np-header-cover");
  const fallback = $("np-header-glyph");
  header.hidden = !url;
  fallback.hidden = Boolean(url);
  if (url) header.src = url;
  else header.removeAttribute("src");
  const big = $("np-big");
  big.hidden = !url;
  $("np-fallback").hidden = Boolean(url);
  if (url) big.src = url;
  else big.removeAttribute("src");
  // A cover that 404s or is a format the phone will not decode falls back
  // to no cover at all, rather than to the browser's broken-image glyph.
  header.onerror = () => {
    header.hidden = true;
    fallback.hidden = false;
  };
  $("np-big").onerror = () => {
    $("np-big").hidden = true;
    $("np-fallback").hidden = false;
    $("np-big").removeAttribute("src");
  };
}

export function renderPlaying(playing) {
  $("hdr-playing").hidden = !playing;
  if (!playing) {
    closeNowPlaying();
    applyCover("");
    return;
  }
  $("np-big-title").textContent = playing.title;
  $("np-big-detail").textContent = playing.detail;
  $("np-header-title").textContent = playing.title;
  // The same second line as the full player: the artist, and the
  // application after it. Empty collapses the line rather than drawing a
  // blank one — `:empty` in strips.css is what does that.
  $("np-header-detail").textContent = playing.detail;
  const said = playing.detail ? `${playing.title}, ${playing.detail}` : playing.title;
  $("np-open").setAttribute("aria-label", `Now playing: ${said}`);
  truth = Boolean(playing.playing);
  clearTimeout(restore);
  drawPlaying(truth);
  $("np-big-prev").disabled = !playing.previous;
  $("np-big-next").disabled = !playing.next;
  applyCover(coverUrl(playing));
}

// The one place the screen is opened or closed. While it is up, the header
// card is a second, smaller copy of everything on it — the same cover, the
// same title, the same play key, a few centimetres above their larger
// selves — so `body.np-open` takes it out of the header (strips.css). The
// header loses a row when it goes, so `--header-h` is re-measured here:
// nothing else would, because the television has not said anything and a
// render is what usually triggers a measurement.
function setOpen(open) {
  $("np-full").classList.toggle("on", open);
  $("np-open").setAttribute("aria-expanded", open ? "true" : "false");
  document.body.classList.toggle("np-open", open);
  measureHeader();
}

export function closeNowPlaying() {
  setOpen(false);
}

export function bindNowPlaying(onOpen = () => {}) {
  $("np-open").addEventListener("click", () => {
    const opening = !$("np-full").classList.contains("on");
    closeNowPlaying();
    if (!opening) return;
    onOpen();
    setOpen(true);
  });
  $("np-close").addEventListener("click", closeNowPlaying);
  // The press itself is sent by keys.js, which binds every [data-transport].
  // This is the drawing half of the same tap.
  for (const id of ["np-pill-play", "np-big-play"]) {
    $(id).addEventListener("click", () => {
      drawPlaying(!drawn);
      clearTimeout(restore);
      restore = setTimeout(() => drawPlaying(truth), OPTIMISTIC_MS);
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeNowPlaying();
  });
}
