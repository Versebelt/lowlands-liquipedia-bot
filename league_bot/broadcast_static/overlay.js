/*
 * Shared runtime for the GeoNederland broadcast overlays.
 *
 * Query parameters (all optional):
 *   api=https://host        Render service when the HTML runs from a local file (CasparCG templates folder)
 *   tournament=ID           Tournament instead of the active one
 *   match=ID                Match instead of the featured one
 *   poll=5                  Seconds between refreshes (minimum 2)
 *   autoplay=0              Wait for CasparCG play() instead of animating in on load
 *   preview=1               Checkerboard background for checking the layout in a normal browser
 *   accent=f47806           Accent colour (hex without #)
 *
 * CasparCG calls play(), stop(), next() and update(data) on templates; they are
 * implemented here so every overlay works as a CasparCG HTML template.
 */
(function () {
  "use strict";
  const params = new URLSearchParams(window.location.search);
  const scriptSrc = (document.currentScript && document.currentScript.src) || window.location.href;
  // Overlays are served from /broadcast/overlay/<name>, the script from /broadcast/assets/overlay.js.
  const base = params.get("api")
    ? params.get("api").replace(/\/+$/, "").replace(/\/broadcast$/, "") + "/broadcast/"
    : new URL("../", scriptSrc).href;
  const pollSeconds = Math.max(2, Number(params.get("poll") || 5));
  const handlers = { play: [], stop: [], next: [], update: [] };

  const accent = (params.get("accent") || "").replace(/[^0-9a-f]/gi, "");
  if (accent.length === 6 || accent.length === 3) document.documentElement.style.setProperty("--accent", "#" + accent);
  if (params.get("preview") === "1") document.body.classList.add("preview");

  function feedUrl(name, extra) {
    const url = new URL("feed/" + name + ".json", base);
    ["tournament", "match", "limit"].forEach((key) => { if (params.get(key)) url.searchParams.set(key, params.get(key)); });
    Object.entries(extra || {}).forEach(([key, value]) => url.searchParams.set(key, value));
    return url.href;
  }

  /* Poll a feed; on errors the last good data stays on screen. */
  function poll(name, callback, extra, seconds) {
    let last = "";
    async function tick() {
      try {
        const response = await fetch(feedUrl(name, extra), { cache: "no-store" });
        if (!response.ok) throw new Error("HTTP " + response.status);
        document.body.classList.toggle("stale", response.headers.get("X-Broadcast-Stale") === "1");
        const body = await response.text();
        if (body !== last) {
          last = body;
          callback(JSON.parse(body));
        }
      } catch (error) {
        document.body.classList.add("stale");
      } finally {
        window.setTimeout(tick, (seconds || pollSeconds) * 1000);
      }
    }
    tick();
  }

  function setText(element, value, flashOnChange) {
    if (!element) return;
    const next = value == null ? "" : String(value);
    if (element.textContent === next) return;
    const changed = element.textContent !== "";
    element.textContent = next;
    if (flashOnChange && changed) {
      element.classList.remove("flash");
      void element.offsetWidth;
      element.classList.add("flash");
    }
  }

  function setImage(element, url) {
    if (!element) return;
    const safe = /^https:\/\//i.test(url || "") ? url : "";
    if (element.getAttribute("src") === safe) return;
    // Never show a broken-image icon on air: hide images that fail to load.
    element.onerror = () => { element.classList.add("hidden"); element.dispatchEvent(new CustomEvent("gn-image", { detail: false })); };
    element.onload = () => { element.classList.remove("hidden"); element.dispatchEvent(new CustomEvent("gn-image", { detail: true })); };
    element.classList.toggle("hidden", !safe);
    element.setAttribute("src", safe);
    if (!safe) element.dispatchEvent(new CustomEvent("gn-image", { detail: false }));
  }

  /* Fill every [data-field] inside root from a row object. */
  function bind(root, row) {
    root.querySelectorAll("[data-field]").forEach((element) => setText(element, row[element.dataset.field], element.hasAttribute("data-flash")));
    root.querySelectorAll("[data-src]").forEach((element) => setImage(element, row[element.dataset.src]));
    root.querySelectorAll("[data-flag]").forEach((element) => element.classList.toggle("on", Boolean(row[element.dataset.flag])));
  }

  function el(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content != null) node.textContent = content;
    return node;
  }

  function play() { document.body.classList.remove("out"); document.body.classList.add("in"); handlers.play.forEach((fn) => fn()); }
  function stop() { document.body.classList.remove("in"); document.body.classList.add("out"); handlers.stop.forEach((fn) => fn()); }
  function next() { handlers.next.forEach((fn) => fn()); }
  function update(raw) {
    let data = raw;
    try { data = typeof raw === "string" ? JSON.parse(raw) : raw; } catch (error) { data = {}; }
    handlers.update.forEach((fn) => fn(data || {}));
  }

  window.play = play;
  window.stop = stop;
  window.next = next;
  window.update = update;

  window.GN = {
    base, params, poll, setText, setImage, bind, el, feedUrl,
    on(event, fn) { handlers[event].push(fn); },
    ready(fn) {
      const start = () => {
        fn();
        if (params.get("autoplay") !== "0") window.setTimeout(play, 150);
      };
      if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
      else start();
    },
  };
})();
