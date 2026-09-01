// SPDX-License-Identifier: GPL-3.0-or-later
import { $, buzz, el, icon, measureHeader, toast } from "./dom.js";
import { pollSoon } from "./feed.js";
import { session } from "./session.js";
import { post } from "./transport.js";
const OPTIMISTIC_MS = 1600;
let renderedHeaderArt = null;
let current = null;
let restoreFocus = null;
let timelineTimer = null;
let renderedApplications = "";
let renderedSources = "";
function sourceCover(source) {
  if (source.artUrl) return source.artUrl;
  if (!source.art) return "";
  const key = encodeURIComponent(session.key);
  const id = encodeURIComponent(source.id || "");
  return `/np-art?k=${key}&source=${id}&v=${session.version}`;
}
function applyHeaderCover(url) {
  if (url === renderedHeaderArt) return;
  renderedHeaderArt = url;
  const cover = $("np-header-cover");
  const fallback = $("np-header-glyph");
  cover.hidden = !url;
  fallback.hidden = Boolean(url);
  if (url) cover.src = url;
  else cover.removeAttribute("src");
  cover.onerror = () => {
    cover.hidden = true;
    fallback.hidden = false;
  };
}
function setGlyph(button, playing) {
  button.querySelector("use").setAttribute("href", playing ? "#i-pause" : "#i-play");
}
function drawHeader(playing) {
  $("hdr-playing").hidden = !playing;
  if (!playing) {
    closeNowPlaying();
    applyHeaderCover("");
    return;
  }
  $("np-header-title").textContent = playing.title;
  $("np-header-detail").textContent = playing.detail;
  const said = playing.detail ? `${playing.title}, ${playing.detail}` : playing.title;
  $("np-open").setAttribute("aria-label", `Media controls: ${said}`);
  $("np-pill-play").setAttribute("aria-label", `${playing.playing ? "Pause" : "Play"} ${playing.identity || playing.title}`);
  setGlyph($("np-pill-play"), Boolean(playing.playing));
  applyHeaderCover(sourceCover(playing));
}
function hueFor(value) {
  let hash = 0;
  for (const char of value || "Media") hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0;
  return Math.abs(hash) % 360;
}
function identityBadge(name, className = "") {
  const badge = el("span", `source-badge ${className}`.trim());
  badge.style.setProperty("--source-hue", hueFor(name));
  badge.textContent = (name || "Media").trim().charAt(0).toUpperCase();
  badge.setAttribute("aria-hidden", "true");
  return badge;
}
function formatTime(milliseconds) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const tail = String(seconds % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${tail}` : `${minutes}:${tail}`;
}
function timeline(source) {
  if (!Number.isFinite(source.positionMs) || !Number.isFinite(source.durationMs)
      || source.positionMs < 0 || source.durationMs <= 0) return null;
  const block = el("div", "source-timeline");
  const progress = el("div", "source-progress");
  progress.setAttribute("role", "progressbar");
  progress.setAttribute("aria-label", `Progress in ${source.title}`);
  progress.setAttribute("aria-valuemin", "0");
  progress.setAttribute("aria-valuemax", String(Math.round(source.durationMs / 1000)));
  progress.dataset.position = source.positionMs;
  progress.dataset.duration = source.durationMs;
  progress.dataset.started = performance.now();
  progress.dataset.playing = source.playing ? "1" : "0";
  progress.append(el("i"));
  const times = el("div", "source-times");
  times.append(el("span", "source-elapsed"), el("span", "", formatTime(source.durationMs)));
  block.append(progress, times);
  return block;
}
function updateTimelines() {
  const now = performance.now();
  for (const node of document.querySelectorAll(".source-progress")) {
    const base = Number(node.dataset.position);
    const duration = Number(node.dataset.duration);
    const elapsed = node.dataset.playing === "1" ? now - Number(node.dataset.started) : 0;
    const position = Math.min(duration, base + elapsed);
    node.firstElementChild.style.width = `${duration ? position / duration * 100 : 0}%`;
    node.setAttribute("aria-valuenow", String(Math.round(position / 1000)));
    node.nextElementSibling.querySelector(".source-elapsed").textContent = formatTime(position);
  }
}
function keepTimelinesRunning(wanted) {
  if (wanted && timelineTimer === null) timelineTimer = setInterval(updateTimelines, 500);
  if (!wanted && timelineTimer !== null) {
    clearInterval(timelineTimer);
    timelineTimer = null;
  }
  updateTimelines();
}
function mediaCard(source) {
  const card = el("article", `media-source${source.playKey ? " primary" : ""}`);
  const head = el("div", "media-source-head");
  const coverUrl = sourceCover(source);
  if (coverUrl) {
    const cover = document.createElement("img");
    cover.className = "media-source-cover";
    cover.alt = "";
    cover.src = coverUrl;
    cover.onerror = () => cover.replaceWith(identityBadge(source.identity));
    head.append(cover);
  } else {
    head.append(identityBadge(source.identity));
  }
  const copy = el("div", "media-source-copy");
  const identity = el("div", "media-source-identity");
  const status = el("span", `source-status ${source.playing ? "playing" : "paused"}`);
  status.append(el("i"), document.createTextNode(source.playing ? "Playing" : "Paused"));
  identity.append(el("b", "", source.identity || "Media"), status);
  copy.append(identity, el("strong", "media-source-title", source.title));
  const appSuffix = source.identity ? ` · ${source.identity}` : "";
  const detail = source.detail === source.identity ? "" : (appSuffix && source.detail.endsWith(appSuffix) ? source.detail.slice(0, -appSuffix.length) : source.detail);
  if (detail) copy.append(el("small", "media-source-detail", detail));
  head.append(copy);
  card.append(head);
  const progress = timeline(source);
  if (progress) card.append(progress);
  const controls = el("div", "media-source-controls");
  const makeTransport = (what, label, glyph, disabled = false) => {
    const button = el("button", `np-key${what === "play_pause" ? " big" : ""}`);
    button.setAttribute("aria-label", `${label} ${source.identity || source.title}`);
    button.disabled = disabled;
    button.append(icon(glyph));
    button.addEventListener("click", () => {
      buzz(8);
      if (what === "play_pause") {
        const truth = source.playing;
        const optimistic = !truth;
        setGlyph(button, optimistic);
        status.className = `source-status ${optimistic ? "playing" : "paused"}`;
        status.lastChild.textContent = optimistic ? "Playing" : "Paused";
        button.setAttribute("aria-label", `${optimistic ? "Pause" : "Play"} ${source.identity || source.title}`);
        const meter = card.querySelector(".source-progress");
        if (meter) {
          meter.dataset.playing = optimistic ? "1" : "0";
          meter.dataset.started = performance.now();
        }
        setTimeout(() => {
          if (!button.isConnected) return;
          setGlyph(button, truth);
          status.className = `source-status ${truth ? "playing" : "paused"}`;
          status.lastChild.textContent = truth ? "Playing" : "Paused";
          button.setAttribute("aria-label", `${truth ? "Pause" : "Play"} ${source.identity || source.title}`);
          if (meter) {
            meter.dataset.playing = truth ? "1" : "0";
            meter.dataset.started = performance.now();
          }
        }, OPTIMISTIC_MS);
      }
      post("/transport", { what, source: source.id });
      pollSoon();
    });
    return button;
  };
  controls.append(
    makeTransport("previous", "Previous in", "i-prev", !source.previous),
    makeTransport("play_pause", source.playing ? "Pause" : "Play", source.playing ? "i-pause" : "i-play"),
    makeTransport("next", "Next in", "i-next", !source.next),
  );
  card.append(controls);
  return card;
}
function appArtwork(app) {
  const wrap = el("span", "running-art");
  wrap.append(identityBadge(app.title, "app-fallback"));
  if (!app.id) return wrap;
  const image = document.createElement("img");
  image.alt = "";
  image.src = `/art/${encodeURIComponent(app.id)}?k=${encodeURIComponent(session.key)}`;
  image.onerror = () => image.remove();
  wrap.prepend(image);
  return wrap;
}
function closeAppButton(app) {
  const button = el("button", "running-close");
  button.setAttribute("aria-label", `Close ${app.title}`);
  button.append(icon("i-close"), document.createTextNode("Close"));
  button.addEventListener("click", async () => {
    buzz(14);
    button.disabled = true;
    const result = await post("/running", { what: "close", id: app.id || "" });
    if (result) toast(`Closing ${app.title}…`);
    else button.disabled = false;
    pollSoon();
  });
  return button;
}
function appRow(app, front = false) {
  const row = el("article", `running-app${front ? " front" : ""}`);
  row.append(appArtwork(app));
  const copy = el("div", "running-copy");
  copy.append(el("b", "", app.title));
  if (!front) copy.append(el("small", "", "Running in the background"));
  row.append(copy);
  if (app.closeable) row.append(closeAppButton(app));
  return row;
}
function drawApplications(runningApps, appName, appId) {
  const signature = JSON.stringify([runningApps, appName, appId]);
  if (signature === renderedApplications) return;
  renderedApplications = signature;
  const front = runningApps.find((app) => app.front);
  const television = $("television-current");
  if (front || appName) {
    television.replaceChildren(appRow(front || {
      id: appId || "", title: appName, front: true, closeable: false,
    }, true));
  } else {
    const salon = el("article", "running-app front salon-current");
    const badge = el("span", "source-badge salon-badge");
    badge.append(icon("i-apps"));
    const copy = el("div", "running-copy");
    copy.append(el("b", "", "Salon"), el("small", "", "Home"));
    salon.append(badge, copy);
    television.replaceChildren(salon);
  }
  const background = runningApps.filter((app) => !app.front);
  $("running-section").hidden = background.length === 0;
  $("running-apps").replaceChildren(...background.map((app) => appRow(app)));
}
function drawSources(sources) {
  const signature = JSON.stringify(sources);
  if (signature === renderedSources) return;
  renderedSources = signature;
  $("media-sources").replaceChildren(...sources.map(mediaCard));
  $("np-full").classList.toggle("single-source", sources.length === 1);
  $("media-count").textContent = sources.length > 1 ? `${sources.length} sources` : "";
  $("np-fallback").hidden = sources.length > 0;
  keepTimelinesRunning(sources.some((source) => source.positionMs >= 0));
}
export function renderPlaying(playing, media = [], runningApps = [], app = "", appId = "") {
  current = playing;
  drawHeader(playing);
  drawApplications(runningApps, app, appId);
  drawSources(media.length ? media : (playing ? [playing] : []));
}
function setOpen(open) {
  const surface = $("np-full");
  if (open === !surface.hidden) return;
  if (open) restoreFocus = document.activeElement;
  surface.hidden = !open;
  surface.classList.toggle("on", open);
  $("np-open").setAttribute("aria-expanded", open ? "true" : "false");
  document.body.classList.toggle("np-open", open);
  for (const pane of document.querySelectorAll(".pane.on")) {
    pane.inert = open;
    pane.setAttribute("aria-hidden", open ? "true" : "false");
  }
  if (open) requestAnimationFrame(() => surface.focus({ preventScroll: true }));
  else if (surface.contains(document.activeElement) && restoreFocus?.isConnected) restoreFocus.focus();
  measureHeader();
}
export function closeNowPlaying() {
  setOpen(false);
}
export function openNowPlaying() {
  if (current) setOpen(true);
}
export function bindNowPlaying(onOpen = () => {}) {
  $("np-open").addEventListener("click", () => {
    const opening = $("np-full").hidden;
    closeNowPlaying();
    if (!opening) return;
    onOpen();
    setOpen(true);
  });
  $("np-close").addEventListener("click", closeNowPlaying);
  $("np-pill-play").addEventListener("click", () => {
    if (!current) return;
    const snapshot = current;
    const truth = current.playing;
    setGlyph($("np-pill-play"), !truth);
    setTimeout(() => {
      if (current !== snapshot) return;
      setGlyph($("np-pill-play"), truth);
    }, OPTIMISTIC_MS);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("np-full").hidden) closeNowPlaying();
  });
}
