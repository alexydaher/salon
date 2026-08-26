// SPDX-License-Identifier: GPL-3.0-or-later
//
// The transport card, and the screen behind it.
//
// The card is a summary: two lines and three circles, on every pane. The
// screen is the thing itself — artwork at full width, which is what makes
// this a second screen rather than a listing. Artwork comes either as a URL
// the phone loads itself (a streaming player publishes an https one) or
// from /np-art, for a player whose art is a file on the television.

import { $ } from "./dom.js";
import { session } from "./session.js";

// Null rather than "": the first render of a player with no cover has to
// actually hide the two <img> elements, and "" as the starting value made
// that the one case the early return swallowed.
let renderedArt = null;

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
  for (const id of ["np-cover", "np-big"]) {
    const node = $(id);
    node.hidden = !url;
    if (url) node.src = url;
    else node.removeAttribute("src");
  }
  // A cover that 404s or is a format the phone will not decode falls back
  // to no cover at all, rather than to the browser's broken-image glyph.
  $("np-cover").onerror = () => { $("np-cover").hidden = true; };
  $("np-big").onerror = () => { $("np-big").removeAttribute("src"); };
}

export function renderPlaying(playing) {
  $("playing").classList.toggle("on", Boolean(playing));
  if (!playing) {
    closeNowPlaying();
    applyCover("");
    return;
  }
  for (const id of ["np-title", "np-big-title"]) $(id).textContent = playing.title;
  for (const id of ["np-detail", "np-big-detail"]) $(id).textContent = playing.detail;
  const glyph = playing.playing ? "#i-pause" : "#i-play";
  for (const id of ["np-play", "np-big-play"]) {
    $(id).querySelector("use").setAttribute("href", glyph);
  }
  for (const id of ["np-prev", "np-big-prev"]) $(id).disabled = !playing.previous;
  for (const id of ["np-next", "np-big-next"]) $(id).disabled = !playing.next;
  applyCover(coverUrl(playing));
}

export function closeNowPlaying() {
  $("np-full").classList.remove("on");
}

export function bindNowPlaying() {
  $("np-open").addEventListener("click", () => {
    $("np-full").classList.add("on");
  });
  $("np-close").addEventListener("click", closeNowPlaying);
}
