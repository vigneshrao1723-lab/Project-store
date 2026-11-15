/* The contact block's map. Until the visitor presses "Load map" nothing is requested from Google: the box shows a
   poster with the city and an "Open in Google Maps" link (which works without this script). Pressing the button
   creates the iframe (hybrid view, city level, no API key) and moves focus to it. The Content-Security-Policy allows
   frames from maps.google.com and www.google.com only. */
(() => {
  "use strict";
  document.querySelectorAll("[data-map]").forEach((box) => {
    const btn = box.querySelector("[data-map-load]");
    const src = box.dataset.src || "";
    if (!btn || src.indexOf("https://maps.google.com/") !== 0) return;
    btn.hidden = false;
    btn.addEventListener("click", () => {
      const frame = document.createElement("iframe");
      frame.className = "map-frame";
      frame.title = box.dataset.title || "Map (Google Maps)";
      frame.loading = "lazy";
      frame.referrerPolicy = "strict-origin-when-cross-origin";
      frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups");
      frame.setAttribute("tabindex", "0");
      frame.src = src;
      box.appendChild(frame);
      box.classList.add("is-loaded");
      frame.focus();
    }, { once: true });
  });
})();
